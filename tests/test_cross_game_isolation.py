"""Verify manifest-derived cross-game, Core, Python import, and storage-key isolation."""

from __future__ import annotations

import ast
import io
import json
import re
import subprocess
import sys
import tempfile
import tokenize
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Tools'))
from generate_game_binding import generate_module_sources  # noqa: E402,I001
from product_support import load_selection, swift_module_sources  # noqa: E402
from swift_module_layout import SWIFT_APP_MODULE, SWIFT_CORE_MODULE  # noqa: E402


# Existing unprefixed Hades II UserDefaults keys retained until #771 WP4.1
# migrates `shortcut.*` to `hades2.shortcut.*` (v6 -> v7 migration).
WP4_1_UNPREFIXED_USERDEFAULTS_ALLOWLIST: dict[str, frozenset[str]] = {
    'hades2': frozenset(
        {
            'shortcut.layoutVersion',
            'shortcut.action.godMode',
            'shortcut.action.gardenQoL',
            'shortcut.action.damageEnabled',
            'shortcut.action.',
        }
    ),
}

# Pre-WP4.2 Hades II root data directory accesses retained until #771 WP4.2
# moves desired-state.json / profiles / backups / diagnostics under data_dir.
WP4_2_ROOT_DATA_DIR_ALLOWLIST: dict[str, frozenset[str]] = {
    'hades2': frozenset(
        {
            'Backend/games/hades2/adapter.py',
            'Backend/games/hades2/command_contract.py',
            'Backend/games/hades2/diagnostics.py',
            'Backend/games/hades2/preparation.py',
        }
    ),
}

_FINDER_DUPLICATE_RE = re.compile(r'^(.+) [2-9]\d*$')


@dataclass(frozen=True)
class ModuleSpec:
    id: str
    display_name: str
    frontend_dir: Path
    frontend_name: str
    module_type: str
    backend_dir: Path
    adapter_module: str
    adapter_type: str
    is_fixture: bool = False


def _git_tracked_paths(root: Path) -> Optional[frozenset[str]]:
    if not (root / '.git').exists():
        return None
    result = subprocess.run(
        ['git', '-C', str(root), 'ls-files', '-z'],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return frozenset(item.decode('utf-8', errors='replace') for item in result.stdout.split(b'\x00') if item)


def _ignore_local_finder_duplicate(path: Path, root: Path, tracked: Optional[frozenset[str]]) -> bool:
    """Ignore untracked Finder/iCloud `name 2.ext` copies whose base file exists alongside them."""
    if tracked is not None and path.relative_to(root).as_posix() in tracked:
        return False
    match = _FINDER_DUPLICATE_RE.fullmatch(path.stem)
    if not match:
        return False
    base = path.with_name(f'{match.group(1)}{path.suffix}')
    return base.is_file()


def _discover_manifests(root: Path) -> list[ModuleSpec]:
    app_data = json.loads((root / 'app.json').read_text(encoding='utf-8'))
    declared_ids = list(app_data.get('modules', ()))
    seen_ids: set[str] = set()
    manifest_paths: list[tuple[Path, Path, bool]] = []

    for game_id in declared_ids:
        mpath = root / 'Backend' / 'games' / game_id / 'module.json'
        manifest_paths.append((mpath, mpath.parent, False))
        seen_ids.add(game_id)

    games_root = root / 'Backend' / 'games'
    if games_root.is_dir():
        for mpath in sorted(games_root.glob('*/module.json')):
            if mpath.parent.name not in seen_ids:
                manifest_paths.append((mpath, mpath.parent, False))
                seen_ids.add(mpath.parent.name)

    fixture_manifest = root / 'ContractFixtures' / 'reference_module' / 'backend' / 'module.json'
    if fixture_manifest.is_file():
        raw_fixture = json.loads(fixture_manifest.read_text(encoding='utf-8'))
        if raw_fixture.get('id') not in seen_ids:
            manifest_paths.append((fixture_manifest, fixture_manifest.parent, True))

    specs: list[ModuleSpec] = []
    for mpath, backend_dir, is_fixture in manifest_paths:
        raw = json.loads(mpath.read_text(encoding='utf-8'))
        adapter_mod, _, adapter_cls = raw.get('backend', {}).get('adapter', '').partition(':')
        frontend = raw.get('frontend', {})
        frontend_rel = frontend.get('sourceDirectory', '')
        if is_fixture:
            fixture_frontend = root / 'ContractFixtures' / 'reference_module' / 'frontend'
            frontend_dir = fixture_frontend if fixture_frontend.is_dir() else (root / frontend_rel)
        else:
            frontend_dir = root / frontend_rel
        specs.append(
            ModuleSpec(
                id=raw['id'],
                display_name=raw.get('displayName', ''),
                frontend_dir=frontend_dir,
                frontend_name=Path(frontend_rel).name if frontend_rel else frontend_dir.name,
                module_type=frontend.get('moduleType', ''),
                backend_dir=backend_dir,
                adapter_module=adapter_mod,
                adapter_type=adapter_cls,
                is_fixture=is_fixture,
            )
        )
    return specs


def _iter_python_files(directory: Path, root: Path, tracked: Optional[frozenset[str]]) -> list[Path]:
    if not directory.is_dir():
        return []
    return [p for p in sorted(directory.rglob('*.py')) if not _ignore_local_finder_duplicate(p, root, tracked)]


def _iter_swift_files(directory: Path, root: Path, tracked: Optional[frozenset[str]]) -> list[Path]:
    if not directory.is_dir():
        return []
    return [p for p in sorted(directory.rglob('*.swift')) if not _ignore_local_finder_duplicate(p, root, tracked)]


def _is_game_owned_tool(path: Path, game_ids: Iterable[str], root: Path) -> bool:
    return any(path.is_relative_to(root / 'Tools' / 'games' / gid) for gid in game_ids)


def _resolved_python_imports(py_path: Path, package_root: Optional[Path]) -> set[str]:
    """Return dotted module names imported by `py_path`, including dynamic constant imports."""
    tree = ast.parse(py_path.read_text(encoding='utf-8'), filename=str(py_path))
    if package_root is not None and py_path.is_relative_to(package_root):
        pkg_parts = list(py_path.relative_to(package_root).parts[:-1])
    else:
        pkg_parts = []

    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                targets.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    targets.add(node.module)
                    for alias in node.names:
                        if alias.name != '*':
                            targets.add(f'{node.module}.{alias.name}')
            else:
                up = node.level - 1
                if up <= len(pkg_parts):
                    base = pkg_parts[: len(pkg_parts) - up]
                    mod_parts = node.module.split('.') if node.module else []
                    prefix = '.'.join(base + mod_parts)
                    if prefix:
                        targets.add(prefix)
                    for alias in node.names:
                        if alias.name != '*':
                            full = '.'.join(base + mod_parts + [alias.name])
                            if full:
                                targets.add(full)
        elif isinstance(node, ast.Call):
            fn = node.func
            fn_name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else None)
            if fn_name in ('import_module', '__import__'):
                mod_arg = node.args[0] if node.args else None
                pkg_kw = next((kw.value for kw in node.keywords if kw.arg == 'package'), None)
                fromlist_kw = next((kw.value for kw in node.keywords if kw.arg == 'fromlist'), None)
                if isinstance(mod_arg, ast.Constant) and isinstance(mod_arg.value, str):
                    mod_name = mod_arg.value
                    if mod_name.startswith('.') and isinstance(pkg_kw, ast.Constant) and isinstance(pkg_kw.value, str):
                        dots = len(mod_name) - len(mod_name.lstrip('.'))
                        base_parts = pkg_kw.value.split('.')
                        up = dots - 1
                        if up <= len(base_parts):
                            suffix = mod_name.lstrip('.')
                            resolved = '.'.join(base_parts[: len(base_parts) - up] + ([suffix] if suffix else []))
                            targets.add(resolved)
                    else:
                        targets.add(mod_name)
                        if isinstance(fromlist_kw, (ast.List, ast.Tuple)):
                            for elt in fromlist_kw.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    targets.add(f'{mod_name}.{elt.value}')
    return targets


def _non_constant_dynamic_imports(py_path: Path) -> list[str]:
    tree = ast.parse(py_path.read_text(encoding='utf-8'), filename=str(py_path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            fn_name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else None)
            if fn_name in ('import_module', '__import__'):
                mod_arg = node.args[0] if node.args else None
                if not (isinstance(mod_arg, ast.Constant) and isinstance(mod_arg.value, str)):
                    found.append(ast.unparse(node) if hasattr(ast, 'unparse') else fn_name)
    return found


def _non_docstring_string_literals(py_path: Path) -> list[str]:
    tree = ast.parse(py_path.read_text(encoding='utf-8'), filename=str(py_path))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                docstrings.add(id(first.value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings
    ]


def _normalized_backend_target(target: str) -> str:
    return target[len('Backend.') :] if target.startswith('Backend.') else target


def _target_matches_game(target: str, game_id: str) -> bool:
    norm = _normalized_backend_target(target)
    return (
        norm == f'games.{game_id}'
        or norm.startswith(f'games.{game_id}.')
        or target == game_id
        or target.startswith(f'{game_id}.')
    )


def _target_matches_any_games_pkg(target: str) -> Optional[str]:
    norm = _normalized_backend_target(target)
    if norm == 'games':
        return 'games'
    if norm.startswith('games.'):
        return norm.split('.', 2)[1]
    return None


def _literal_game_target(literal: str) -> Optional[str]:
    norm = _normalized_backend_target(literal)
    if norm.startswith('games.'):
        parts = norm.split('.')
        if len(parts) >= 2 and parts[1]:
            return parts[1]
    return None


def check_python_import_boundaries(root: Path) -> list[str]:
    """Verify Core imports no `games.*` and each game imports no other game (derived from manifests)."""
    tracked = _git_tracked_paths(root)
    specs = _discover_manifests(root)
    all_ids = {spec.id for spec in specs}
    backend_root = root / 'Backend'
    errors: list[str] = []

    shared_py = (
        _iter_python_files(backend_root / 'core', root, tracked)
        + _iter_python_files(backend_root / 'debugger', root, tracked)
        + [path for path in _iter_python_files(root / 'Tools', root, tracked) if not _is_game_owned_tool(path, all_ids, root)]
    )

    for path in shared_py:
        rel = path.relative_to(root).as_posix()
        imports = _resolved_python_imports(path, backend_root)
        for target in sorted(imports):
            pkg = _target_matches_any_games_pkg(target)
            if pkg is not None or any(_target_matches_game(target, gid) for gid in all_ids):
                errors.append(f'{rel}: shared Python must not import game module ({target})')
        for literal in _non_docstring_string_literals(path):
            lit_gid = _literal_game_target(literal)
            if lit_gid in all_ids:
                errors.append(f'{rel}: shared Python references game module string {literal!r}')

    for spec in specs:
        other_ids = all_ids - {spec.id}
        game_tool_dir = root / 'Tools' / 'games' / spec.id
        owned_files = [
            (spec.backend_dir, backend_root if spec.backend_dir.is_relative_to(backend_root) else spec.backend_dir.parent),
            (game_tool_dir, root / 'Tools'),
        ]
        for directory, pkg_root in owned_files:
            for path in _iter_python_files(directory, root, tracked):
                rel = path.relative_to(root).as_posix()
                for target in sorted(_resolved_python_imports(path, pkg_root)):
                    imported_game = _target_matches_any_games_pkg(target)
                    if imported_game is not None and imported_game not in ('games', spec.id):
                        errors.append(f'{rel}: module {spec.id!r} imports foreign game package {target!r}')
                        continue
                    for other in sorted(other_ids):
                        if _target_matches_game(target, other):
                            errors.append(f'{rel}: module {spec.id!r} imports foreign game {other!r} ({target})')
                for call_text in _non_constant_dynamic_imports(path):
                    errors.append(f'{rel}: module {spec.id!r} uses non-constant dynamic import {call_text!r}')
                for literal in _non_docstring_string_literals(path):
                    lit_gid = _literal_game_target(literal)
                    if lit_gid is not None and lit_gid != spec.id:
                        errors.append(f'{rel}: module {spec.id!r} references foreign game string {literal!r}')
    return errors


def _non_comment_python_text(path: Path) -> str:
    src = path.read_text(encoding='utf-8')
    parts: list[str] = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type != tokenize.COMMENT:
            parts.append(tok.string)
    return ' '.join(parts)


def _boundary_pattern(tokens: Iterable[str]) -> Optional[re.Pattern[str]]:
    unique = sorted({t for t in tokens if t}, key=len, reverse=True)
    if not unique:
        return None
    return re.compile('|'.join(f'(?<![A-Za-z0-9_]){re.escape(t)}(?![A-Za-z0-9_])' for t in unique))


def check_manifest_derived_identities(root: Path) -> list[str]:
    """Replace hand-maintained vocabulary lists with tokens derived from all manifests."""
    tracked = _git_tracked_paths(root)
    specs = _discover_manifests(root)
    real_specs = [s for s in specs if not s.is_fixture]
    fixture_specs = [s for s in specs if s.is_fixture]
    errors: list[str] = []

    def shared_tokens_for(spec: ModuleSpec) -> set[str]:
        tokens = {
            spec.id,
            f'games.{spec.id}',
            spec.display_name,
            spec.frontend_name,
            spec.module_type,
            spec.adapter_module,
            spec.adapter_type,
        }
        return {t for t in tokens if t}

    def cross_game_tokens_for(spec: ModuleSpec) -> set[str]:
        tokens = {
            f'games.{spec.id}',
            spec.module_type,
            spec.adapter_module,
            spec.adapter_type,
        }
        return {t for t in tokens if t}

    all_shared_tokens = {tok for spec in specs for tok in shared_tokens_for(spec)}
    shared_pattern = _boundary_pattern(all_shared_tokens)

    shared_tool_names = (
        'Tools/module_support.py',
        'Tools/product_support.py',
        'Tools/generate_game_binding.py',
        'Tools/validate_game_module.py',
        'Tools/supported_build.py',
        'Tools/verify_module_build.py',
    )
    shared_files = (
        _iter_python_files(root / 'Backend' / 'core', root, tracked)
        + _iter_python_files(root / 'Backend' / 'debugger', root, tracked)
        + [root / name for name in shared_tool_names if (root / name).is_file()]
    )
    if shared_pattern is not None:
        for path in shared_files:
            rel = path.relative_to(root).as_posix()
            hits = sorted(set(shared_pattern.findall(_non_comment_python_text(path))))
            if hits:
                errors.append(f'{rel}: shared code mentions module identity tokens {hits}')
        shared_swift = _iter_swift_files(root / 'Sources' / 'Core', root, tracked)
        app_swift = root / 'Sources' / 'App.swift'
        if app_swift.is_file():
            shared_swift.append(app_swift)
        for path in shared_swift:
            rel = path.relative_to(root).as_posix()
            hits = sorted(set(shared_pattern.findall(_strip_swift_comments(path.read_text(encoding='utf-8')))))
            if hits:
                errors.append(f'{rel}: shared Swift mentions module identity tokens {hits}')

    real_tokens = {tok for spec in real_specs for tok in shared_tokens_for(spec)}
    fixture_pat = _boundary_pattern(real_tokens)
    if fixture_pat is not None and fixture_specs:
        for fspec in fixture_specs:
            for directory in (fspec.backend_dir, fspec.frontend_dir):
                if not directory.is_dir():
                    continue
                for path in sorted(directory.rglob('*')):
                    if not path.is_file() or path.suffix not in ('.py', '.swift', '.json', '.lua'):
                        continue
                    if _ignore_local_finder_duplicate(path, root, tracked):
                        continue
                    rel = path.relative_to(root).as_posix()
                    text = path.read_text(encoding='utf-8', errors='ignore')
                    hits = sorted(set(fixture_pat.findall(text)))
                    if hits:
                        errors.append(f'{rel}: fixture mentions real module tokens {hits}')

    for spec in specs:
        other_tokens = {tok for other in specs if other.id != spec.id for tok in cross_game_tokens_for(other)}
        pat = _boundary_pattern(other_tokens)
        if pat is None:
            continue
        all_mod_files = (
            _iter_python_files(spec.backend_dir, root, tracked)
            + _iter_python_files(root / 'Tools' / 'games' / spec.id, root, tracked)
            + _iter_swift_files(spec.frontend_dir, root, tracked)
        )
        for path in all_mod_files:
            rel = path.relative_to(root).as_posix()
            if path.suffix == '.py':
                text = _non_comment_python_text(path)
            else:
                text = _strip_swift_comments(path.read_text(encoding='utf-8'))
            hits = sorted(set(pat.findall(text)))
            if hits:
                errors.append(f'{rel}: module {spec.id!r} mentions foreign module identifiers {hits}')
    return errors


def _swift_string_span(source: str, start: int) -> Optional[tuple[int, Optional[tuple[str, bool]]]]:
    """If `source[start]` opens a Swift string literal, return `(end_index, (prefix_or_value, is_template))`."""
    n = len(source)
    i = start
    hashes = 0
    while i < n and source[i] == '#':
        hashes += 1
        i += 1
    if i >= n or source[i] != '"':
        return None
    if source.startswith('"""', i):
        quote = '"""'
        i += 3
    else:
        quote = '"'
        i += 1
    closing = quote + ('#' * hashes)
    escape_prefix = '\\' + ('#' * hashes)
    buf: list[str] = []
    is_template = False

    while i < n:
        if source.startswith(closing, i):
            i += len(closing)
            return i, (''.join(buf), is_template)
        if source.startswith(escape_prefix, i):
            after = i + len(escape_prefix)
            if after < n and source[after] == '(':
                if not is_template:
                    is_template = True
                i = _skip_balanced_parens(source, after)
                continue
            if hashes == 0 and after < n:
                if not is_template:
                    buf.append(source[after])
                i = after + 1
                continue
        if not is_template:
            buf.append(source[i])
        i += 1
    return n, None


def _skip_balanced_parens(source: str, open_index: int) -> int:
    """Advance past balanced `(` ... `)` respecting nested comments and Swift string literals."""
    depth = 1
    i = open_index + 1
    n = len(source)
    block_depth = 0
    while i < n and depth > 0:
        if block_depth > 0:
            if source.startswith('/*', i):
                block_depth += 1
                i += 2
            elif source.startswith('*/', i):
                block_depth -= 1
                i += 2
            else:
                i += 1
            continue
        if source.startswith('//', i):
            nl = source.find('\n', i)
            i = n if nl < 0 else nl + 1
            continue
        if source.startswith('/*', i):
            block_depth = 1
            i += 2
            continue
        span = _swift_string_span(source, i)
        if span is not None:
            i = span[0]
            continue
        c = source[i]
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        i += 1
    return i


def _strip_swift_comments(source: str) -> str:
    """Strip Swift `//` and nested `/* */` comments while preserving all string literals."""
    out: list[str] = []
    i = 0
    n = len(source)
    block_depth = 0
    while i < n:
        if block_depth > 0:
            if source.startswith('/*', i):
                block_depth += 1
                i += 2
            elif source.startswith('*/', i):
                block_depth -= 1
                if block_depth == 0:
                    out.append(' ')
                i += 2
            else:
                if source[i] == '\n':
                    out.append('\n')
                i += 1
            continue
        if source.startswith('//', i):
            nl = source.find('\n', i)
            if nl < 0:
                break
            out.append('\n')
            i = nl + 1
            continue
        if source.startswith('/*', i):
            block_depth = 1
            i += 2
            continue
        span = _swift_string_span(source, i)
        if span is not None:
            end_idx, _ = span
            out.append(source[i:end_idx])
            i = end_idx
            continue
        out.append(source[i])
        i += 1
    return ''.join(out)


def _split_top_level(text: str, sep: str = ',') -> list[str]:
    """Split `text` at top-level `sep` outside parens, brackets, braces, and Swift strings."""
    parts: list[str] = []
    depth = 0
    cur_start = 0
    i = 0
    n = len(text)
    while i < n:
        span = _swift_string_span(text, i)
        if span is not None:
            i = span[0]
            continue
        c = text[i]
        if c in '([{':
            depth += 1
        elif c in ')]}' and depth > 0:
            depth -= 1
        elif c == sep and depth == 0:
            parts.append(text[cur_start:i])
            cur_start = i + 1
        i += 1
    parts.append(text[cur_start:])
    return parts


def _parse_single_string_literal(expr: str) -> Optional[tuple[str, bool]]:
    stripped = expr.strip()
    span = _swift_string_span(stripped, 0)
    if span is None:
        return None
    end_idx, parsed = span
    if end_idx != len(stripped):
        return None
    return parsed


def _split_top_level_ternary(expr: str) -> Optional[tuple[str, str]]:
    """If `expr` is `cond ? whenTrue : whenFalse` at top level, return `(whenTrue, whenFalse)`."""
    depth = 0
    i = 0
    n = len(expr)
    q_idx: Optional[int] = None
    ternary_depth = 0
    while i < n:
        span = _swift_string_span(expr, i)
        if span is not None:
            i = span[0]
            continue
        c = expr[i]
        if c in '([{':
            depth += 1
        elif c in ')]}' and depth > 0:
            depth -= 1
        elif depth == 0:
            if c == '?':
                if q_idx is None:
                    q_idx = i
                else:
                    ternary_depth += 1
            elif c == ':' and q_idx is not None:
                if ternary_depth == 0:
                    return expr[q_idx + 1 : i].strip(), expr[i + 1 :].strip()
                ternary_depth -= 1
        i += 1
    return None


def _extract_swift_brace_block(code: str, brace_index: int) -> str:
    depth = 0
    i = brace_index
    n = len(code)
    while i < n:
        span = _swift_string_span(code, i)
        if span is not None:
            i = span[0]
            continue
        c = code[i]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return code[brace_index : i + 1]
        i += 1
    return code[brace_index:]


def _parse_call_args(args_text: str) -> list[tuple[Optional[str], str]]:
    args: list[tuple[Optional[str], str]] = []
    for raw in _split_top_level(args_text, ','):
        part = raw.strip()
        if not part:
            continue
        colon_parts = _split_top_level(part, ':')
        if len(colon_parts) >= 2 and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', colon_parts[0].strip()):
            label = colon_parts[0].strip()
            value = ':'.join(colon_parts[1:]).strip()
            args.append((label, value))
        else:
            args.append((None, part))
    return args


def _type_block_for(code: str, type_name: str) -> Optional[str]:
    match = re.search(rf'\b(?:struct|class|enum|extension)\s+{re.escape(type_name)}\b[^{{]*\{{', code)
    if not match:
        return None
    return _extract_swift_brace_block(code, match.end() - 1)


def _body_return_expressions(body_inner: str) -> Optional[list[str]]:
    """Extract return expressions from a helper body; return `None` if control flow leaves unreturned paths."""
    stripped = body_inner.strip()
    if not stripped:
        return None
    explicit_returns = [
        match.group(1).strip() for match in re.finditer(r'(?:^|[;{}\n])\s*return\s+([^\n;]+)', stripped)
    ]
    if explicit_returns:
        # Reject bodies that mix `if/guard` early returns with a trailing non-`return` statement
        # or have control flow without explicit exhaustive returns.
        lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
        if not lines or not lines[-1].startswith('return '):
            return None
        return explicit_returns
    # Single-expression implicit return (no semicolons/multiple statements or `if`/`switch` blocks).
    if '\n' not in stripped and ';' not in stripped:
        return [stripped]
    return None


def _resolve_swift_key_expression(
    file_code: str,
    expr: str,
    *,
    module_code: str = '',
    seen: Optional[set[str]] = None,
) -> Optional[list[tuple[str, bool]]]:
    stripped = expr.strip()
    if not stripped:
        return None
    single = _parse_single_string_literal(stripped)
    if single is not None:
        return [single]

    ternary = _split_top_level_ternary(stripped)
    if ternary is not None:
        left_keys = _resolve_swift_key_expression(file_code, ternary[0], module_code=module_code, seen=seen)
        right_keys = _resolve_swift_key_expression(file_code, ternary[1], module_code=module_code, seen=seen)
        if left_keys is None or right_keys is None:
            return None
        return left_keys + right_keys

    seen = set() if seen is None else set(seen)
    call_match = re.fullmatch(
        r'(?:(Self|self|[A-Za-z_][A-Za-z0-9_]*)\.)?([A-Za-z_][A-Za-z0-9_]*)\((.*)\)',
        stripped,
        re.DOTALL,
    )
    if call_match:
        qualifier, fn_name, _ = call_match.group(1), call_match.group(2), call_match.group(3)
        visit_key = f'fn:{qualifier or ""}.{fn_name}'
        if visit_key in seen:
            return None
        seen.add(visit_key)
        search_scope = file_code
        if qualifier and qualifier not in ('Self', 'self') and module_code:
            scoped = _type_block_for(module_code, qualifier)
            if scoped is not None:
                search_scope = scoped
        results: list[tuple[str, bool]] = []
        fn_matches = list(
            re.finditer(rf'\bfunc\s+{re.escape(fn_name)}\s*\([^)]*\)\s*(?:->\s*[^{{]+)?\{{', search_scope)
        )
        if not fn_matches:
            return None
        for fn_match in fn_matches:
            block = _extract_swift_brace_block(search_scope, fn_match.end() - 1)
            ret_exprs = _body_return_expressions(block[1:-1])
            if not ret_exprs:
                return None
            for ret_expr in ret_exprs:
                sub = _resolve_swift_key_expression(search_scope, ret_expr, module_code=module_code, seen=seen)
                if sub is None:
                    return None
                results.extend(sub)
        return results or None

    prop_match = re.fullmatch(r'(?:(Self|self|[A-Za-z_][A-Za-z0-9_]*)\.)?([A-Za-z_][A-Za-z0-9_]*)', stripped)
    if prop_match:
        qualifier, prop_name = prop_match.group(1), prop_match.group(2)
        visit_key = f'prop:{qualifier or ""}.{prop_name}'
        if visit_key in seen:
            return None
        seen.add(visit_key)
        # Unqualified bare parameter names (`prop_name: Type`) are dynamic and must never match local constants.
        if not qualifier and re.search(rf'\b{re.escape(prop_name)}\s*:', file_code):
            return None
        search_scope = file_code
        if qualifier and qualifier not in ('Self', 'self') and module_code:
            scoped = _type_block_for(module_code, qualifier)
            if scoped is not None:
                search_scope = scoped
        prop_pattern = rf'\b(?:let|var)\s+{re.escape(prop_name)}(?:\s*:\s*String)?\s*=\s*([^\n;{{]+)'
        val_matches = list(re.finditer(prop_pattern, search_scope))
        if not val_matches:
            return None
        results = []
        for val_match in val_matches:
            rhs = val_match.group(1).strip()
            sub = _resolve_swift_key_expression(search_scope, rhs, module_code=module_code, seen=seen)
            if sub is None:
                return None
            results.extend(sub)
        return results or None

    return None


_USERDEFAULTS_KEYED_METHODS = frozenset(
    {
        'object',
        'string',
        'integer',
        'bool',
        'double',
        'float',
        'data',
        'array',
        'dictionary',
        'url',
        'stringArray',
        'removeObject',
        'set',
        'setValue',
        'value',
        'objectIsForced',
    }
)


def _collect_swift_user_defaults_receivers(module_code: str) -> set[str]:
    receivers = {'defaults'}
    for typed_match in re.finditer(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*:\s*UserDefaults\b', module_code):
        receivers.add(typed_match.group(1))
    for init_match in re.finditer(r'\b(?:let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*UserDefaults\b', module_code):
        receivers.add(init_match.group(1))
    return receivers


def _resolve_dict_literal_keys(
    dict_expr: str,
    file_code: str,
    *,
    module_code: str,
    context_label: str,
) -> tuple[list[tuple[str, bool]], list[str]]:
    stripped = dict_expr.strip()
    if not (stripped.startswith('[') and stripped.endswith(']')):
        return [], [f'{context_label}({stripped})']
    inner = stripped[1:-1].strip()
    if not inner or inner == ':':
        return [], []
    resolved: list[tuple[str, bool]] = []
    unresolved: list[str] = []
    for entry in _split_top_level(inner, ','):
        item = entry.strip()
        if not item:
            continue
        kv = _split_top_level(item, ':')
        if len(kv) < 2:
            unresolved.append(f'{context_label}({item})')
            continue
        keys = _resolve_swift_key_expression(file_code, kv[0].strip(), module_code=module_code)
        if keys is None:
            unresolved.append(kv[0].strip())
        else:
            resolved.extend(keys)
    return resolved, unresolved


def _scan_swift_user_defaults_keys(
    swift_path: Path,
    *,
    module_code: Optional[str] = None,
) -> tuple[list[tuple[str, bool]], list[str]]:
    """Return `(resolved_keys, unresolved_expressions)` for UserDefaults / AppStorage sites."""
    file_code = _strip_swift_comments(swift_path.read_text(encoding='utf-8'))
    mod_code = file_code if module_code is None else module_code
    resolved: list[tuple[str, bool]] = []
    unresolved: list[str] = []

    for match in re.finditer(r'@AppStorage\s*\(', file_code):
        open_idx = match.end() - 1
        end_idx = _skip_balanced_parens(file_code, open_idx)
        args = _parse_call_args(file_code[open_idx + 1 : end_idx - 1])
        positional = [val for label, val in args if label is None]
        if len(positional) != 1:
            unresolved.append(file_code[match.start() : end_idx].strip())
            continue
        keys = _resolve_swift_key_expression(file_code, positional[0], module_code=mod_code)
        if keys is None:
            unresolved.append(positional[0])
        else:
            resolved.extend(keys)

    receivers = _collect_swift_user_defaults_receivers(mod_code)
    receiver_group = '|'.join(sorted((re.escape(name) for name in receivers), key=len, reverse=True))
    receiver_pattern = (
        rf'(?:UserDefaults(?:\([^)]*\))?(?:\.(?:standard|globalDomain))?|(?:self\.)?(?:{receiver_group}))'
    )

    for match in re.finditer(rf'\b{receiver_pattern}(?:\?|!)?\.([A-Za-z_][A-Za-z0-9_]*)\s*\(', file_code):
        method = match.group(1)
        if method not in _USERDEFAULTS_KEYED_METHODS and method not in ('register', 'setValuesForKeys'):
            continue
        open_idx = match.end() - 1
        end_idx = _skip_balanced_parens(file_code, open_idx)
        call_args = _parse_call_args(file_code[open_idx + 1 : end_idx - 1])
        if method == 'register':
            defaults_args = [val for label, val in call_args if label == 'defaults']
            if not defaults_args:
                unresolved.append(file_code[match.start() : end_idx].strip())
                continue
            for arg_expr in defaults_args:
                r_keys, u_keys = _resolve_dict_literal_keys(
                    arg_expr, file_code, module_code=mod_code, context_label='register(defaults:)'
                )
                resolved.extend(r_keys)
                unresolved.extend(u_keys)
            continue
        if method == 'setValuesForKeys':
            if not call_args:
                unresolved.append('setValuesForKeys()')
            else:
                r_keys, u_keys = _resolve_dict_literal_keys(
                    call_args[0][1], file_code, module_code=mod_code, context_label='setValuesForKeys'
                )
                resolved.extend(r_keys)
                unresolved.extend(u_keys)
            continue
        for label, value in call_args:
            if label != 'forKey':
                continue
            keys = _resolve_swift_key_expression(file_code, value, module_code=mod_code)
            if keys is None:
                unresolved.append(value)
            else:
                resolved.extend(keys)

    return resolved, unresolved


def _is_key_allowed_for_module(key: str, is_template: bool, module_id: str) -> bool:
    if key.startswith(f'{module_id}.'):
        return True
    allowlist = WP4_1_UNPREFIXED_USERDEFAULTS_ALLOWLIST.get(module_id, frozenset())
    if is_template:
        return any(key.startswith(entry) for entry in allowlist if entry.endswith('.'))
    return key in allowlist


def check_module_storage_keys(root: Path) -> list[str]:
    """Enforce per-module UserDefaults/data-key prefixes with explicit #771 WP4.1 allowlist."""
    tracked = _git_tracked_paths(root)
    specs = _discover_manifests(root)
    all_ids = {spec.id for spec in specs}
    errors: list[str] = []

    for spec in specs:
        swift_files = _iter_swift_files(spec.frontend_dir, root, tracked)
        module_code = '\n'.join(_strip_swift_comments(p.read_text(encoding='utf-8')) for p in swift_files)
        for path in swift_files:
            rel = path.relative_to(root).as_posix()
            keys, unresolved = _scan_swift_user_defaults_keys(path, module_code=module_code)
            for expr in unresolved:
                errors.append(f'{rel}: unresolved UserDefaults key expression {expr!r} in module {spec.id!r}')
            for key, is_template in keys:
                if any(key.startswith(f'{other}.') for other in all_ids - {spec.id}):
                    errors.append(f'{rel}: module {spec.id!r} wrote foreign module key {key!r}')
                    continue
                if not _is_key_allowed_for_module(key, is_template, spec.id):
                    errors.append(
                        f'{rel}: UserDefaults/data key {key!r} in module {spec.id!r} must start with '
                        f'{spec.id + "."!r} (unprefixed Hades II keys are limited to the #771 WP4.1 allowlist)'
                    )

    core_files = _iter_swift_files(root / 'Sources' / 'Core', root, tracked)
    core_code = '\n'.join(_strip_swift_comments(p.read_text(encoding='utf-8')) for p in core_files)
    for path in core_files:
        rel = path.relative_to(root).as_posix()
        keys, unresolved = _scan_swift_user_defaults_keys(path, module_code=core_code)
        for expr in unresolved:
            errors.append(f'{rel}: unresolved Core UserDefaults key expression {expr!r}')
        for key, _is_template in keys:
            for gid in sorted(all_ids):
                if key.startswith(f'{gid}.'):
                    errors.append(f'{rel}: Core UserDefaults key {key!r} uses game module prefix {gid + "."!r}')

    # Python data-directory isolation: modules must use context.data_dir (MacGamingTrainer/<game_id>/),
    # never root trainer_data_root() / legacy_data_dir except pre-WP4.2 allowlisted files.
    for spec in specs:
        allowed_files = WP4_2_ROOT_DATA_DIR_ALLOWLIST.get(spec.id, frozenset())
        for path in _iter_python_files(spec.backend_dir, root, tracked):
            rel = path.relative_to(root).as_posix()
            src = _non_comment_python_text(path)
            if ('trainer_data_root' in src or 'legacy_data_dir' in src) and rel not in allowed_files:
                errors.append(f'{rel}: module {spec.id!r} uses root data dir outside context.data_dir')
            tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                fn_name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else None)
                if fn_name not in ('trainer_data_directory', 'trainer_log_directory'):
                    continue
                arg = (
                    node.args[0] if node.args else next((kw.value for kw in node.keywords if kw.arg == 'game_id'), None)
                )
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if arg.value != spec.id:
                        errors.append(f'{rel}: module {spec.id!r} accesses foreign data directory {arg.value!r}')
                else:
                    errors.append(f'{rel}: module {spec.id!r} uses dynamic {fn_name} argument')
    return errors


# 1. Swift isolation is the compiler's (`product_support.swift_layout` + `swift_module_sources`).
selection = load_selection('all')
normalized = selection.normalized()
layout = {module['name']: module for module in normalized['frontend']['swift']['modules']}
games = [module.frontend.swift_module for module in selection.modules]
assert list(layout) == [SWIFT_CORE_MODULE, *games, SWIFT_APP_MODULE], list(layout)
assert layout[SWIFT_CORE_MODULE]['dependencies'] == []
for game in games:
    assert layout[game]['dependencies'] == [SWIFT_CORE_MODULE], (game, layout[game])
assert layout[SWIFT_APP_MODULE]['dependencies'] == [SWIFT_CORE_MODULE, *games]
for module in selection.modules:
    isolated = load_selection(module.id).normalized()['frontend']['swift']['modules']
    assert [item['name'] for item in isolated] == [SWIFT_CORE_MODULE, module.frontend.swift_module, SWIFT_APP_MODULE]

with tempfile.TemporaryDirectory(prefix='mgt-swift-sources-') as tmp_gen:
    gen_dir = Path(tmp_gen)
    generate_module_sources(selection.modules, gen_dir)
    modules_payload = normalized['frontend']['swift']['modules']
    compiled = {m['name']: srcs for m, srcs in swift_module_sources(modules_payload, ROOT, gen_dir)}
    assert all(
        src.is_relative_to(ROOT / 'Sources' / 'Core') or src.is_relative_to(gen_dir / SWIFT_CORE_MODULE)
        for src in compiled[SWIFT_CORE_MODULE]
    )
    for module in selection.modules:
        mod_name = module.frontend.swift_module
        mod_dir = ROOT / module.frontend.source_directory
        assert all(
            src.is_relative_to(mod_dir) or src.is_relative_to(gen_dir / mod_name) for src in compiled[mod_name]
        ), f'{mod_name} compiled foreign sources: {compiled[mod_name]}'
    assert all(
        src == ROOT / 'Sources' / 'App.swift' or src.is_relative_to(gen_dir / SWIFT_APP_MODULE)
        for src in compiled[SWIFT_APP_MODULE]
    )

# 2. Enforce manifest-derived Python imports, identities, and storage-key prefixes on the repo.
assert not check_python_import_boundaries(ROOT), check_python_import_boundaries(ROOT)
assert not check_manifest_derived_identities(ROOT), check_manifest_derived_identities(ROOT)
assert not check_module_storage_keys(ROOT), check_module_storage_keys(ROOT)

assert not (ROOT / 'Backend/games/reference_fixture').exists()
assert not (ROOT / 'Sources/ReferenceFixture').exists()

fixture_ui_path = ROOT / 'ContractFixtures/reference_module/frontend/ReferenceFixtureModule.swift'
fixture_ui = fixture_ui_path.read_text(encoding='utf-8')
assert 'TrainerFeatureToggleRow(' in fixture_ui


# 3. Verify every check fails closed on synthetic N-module boundary & key mutations.
def _write_synthetic_repo(root: Path) -> None:
    (root / 'app.json').write_text(json.dumps({'schemaVersion': 1, 'modules': ['alpha', 'beta']}), encoding='utf-8')
    for gid, mtype, gdir, cls in (
        ('alpha', 'AlphaGameModule', 'Sources/Alpha', 'AlphaAdapter'),
        ('beta', 'BetaGameModule', 'Sources/Beta', 'BetaAdapter'),
    ):
        mdir = root / 'Backend' / 'games' / gid
        mdir.mkdir(parents=True)
        (mdir / 'module.json').write_text(
            json.dumps(
                {
                    'schemaVersion': 1,
                    'id': gid,
                    'displayName': gid.capitalize(),
                    'protocolVersion': 1,
                    'backend': {'adapter': f'games.{gid}.adapter:{cls}'},
                    'frontend': {'sourceDirectory': gdir, 'moduleType': mtype, 'minimumMacOS': '14.0'},
                }
            ),
            encoding='utf-8',
        )
        (mdir / 'adapter.py').write_text(
            f'from core.adapter import GameAdapter\nclass {cls}(GameAdapter): pass\n',
            encoding='utf-8',
        )
        sdir = root / gdir
        sdir.mkdir(parents=True)
        (sdir / f'{mtype}.swift').write_text(
            f'import Foundation\nfunc k() -> String {{ "{gid}.pref" }}\n'
            'func ok(d: UserDefaults) { d.set(1, forKey: k()) }\n',
            encoding='utf-8',
        )
    (root / 'Backend/core').mkdir(parents=True)
    (root / 'Backend/core/adapter.py').write_text('class GameAdapter: pass\n', encoding='utf-8')
    (root / 'Tools').mkdir(parents=True)
    (root / 'Tools/module_support.py').write_text('"""Generic helper"""\n', encoding='utf-8')
    (root / 'Sources/Core').mkdir(parents=True)
    (root / 'Sources/Core/HostPrefs.swift').write_text(
        'import Foundation\nfunc ok(d: UserDefaults) { d.set("en", forKey: "host.lang") }\n',
        encoding='utf-8',
    )


with tempfile.TemporaryDirectory(prefix='mgt-isolation-synth-') as tmp:
    synth = Path(tmp)
    _write_synthetic_repo(synth)
    assert check_python_import_boundaries(synth) == []
    assert check_manifest_derived_identities(synth) == []
    assert check_module_storage_keys(synth) == []

    # 3a. Core & shared Tools importing a declared game (absolute, relative, Backend.*, importlib) must fail.
    for target_file in (synth / 'Backend/core/leak.py', synth / 'Tools/shared_helper.py'):
        target_file.write_text('from games import beta\n', encoding='utf-8')
        assert any('shared Python must not import game module' in err for err in check_python_import_boundaries(synth))
        target_file.write_text('import Backend.games.alpha\n', encoding='utf-8')
        assert any('shared Python must not import game module' in err for err in check_python_import_boundaries(synth))
        target_file.unlink()
    (synth / 'Backend/core/leak.py').write_text('from ..games.alpha import adapter\n', encoding='utf-8')
    assert any('shared Python must not import game module' in err for err in check_python_import_boundaries(synth))
    (synth / 'Backend/core/leak.py').unlink()

    # 3b. Cross-game Python import (`alpha` importing `beta`, relative, Backend.*, importlib, string) must fail.
    cross_py = synth / 'Backend/games/alpha/cross.py'
    for body in (
        'from ..beta import adapter\n',
        'from Backend.games.beta import adapter\n',
        'import importlib\nmod = importlib.import_module(".beta", package="games")\n',
        'WORKER = "games.beta.worker"\n',
    ):
        cross_py.write_text(body, encoding='utf-8')
        errs = check_python_import_boundaries(synth)
        assert errs, f'expected Python boundary failure for {body!r}'
    cross_py.unlink()

    # 3c. Manifest-derived identity leakage in Core, Tools, ContractFixtures, and cross-game files must fail.
    (synth / 'Backend/core/ident.py').write_text('NAME = "AlphaGameModule"\n', encoding='utf-8')
    assert any('AlphaGameModule' in err for err in check_manifest_derived_identities(synth))
    (synth / 'Backend/core/ident.py').unlink()
    (synth / 'Backend/games/beta/cross_ident.py').write_text('OTHER = "AlphaAdapter"\n', encoding='utf-8')
    assert any('foreign module identifiers' in err for err in check_manifest_derived_identities(synth))
    (synth / 'Backend/games/beta/cross_ident.py').unlink()
    fx_dir = synth / 'ContractFixtures/reference_module'
    (fx_dir / 'backend').mkdir(parents=True)
    (fx_dir / 'frontend').mkdir(parents=True)
    (fx_dir / 'backend/module.json').write_text(
        json.dumps(
            {
                'schemaVersion': 1,
                'id': 'ref_fix',
                'displayName': 'Ref',
                'protocolVersion': 1,
                'backend': {'adapter': 'games.ref_fix.adapter:RefAdapter'},
                'frontend': {
                    'sourceDirectory': 'Sources/RefFix',
                    'moduleType': 'RefGameModule',
                    'minimumMacOS': '14.0',
                },
            }
        ),
        encoding='utf-8',
    )
    (fx_dir / 'frontend/Ref.swift').write_text('let leak = "AlphaGameModule"\n', encoding='utf-8')
    assert any('fixture mentions real module tokens' in err for err in check_manifest_derived_identities(synth))
    (fx_dir / 'frontend/Ref.swift').write_text(
        'import SwiftUI\n'
        'struct V { @AppStorage("ref_fix.ok", store: UserDefaults(suiteName: "com.example")) var x = true }\n',
        encoding='utf-8',
    )
    assert check_manifest_derived_identities(synth) == []
    assert check_module_storage_keys(synth) == []

    # 3d. Storage keys: helper fail-open paths, @AppStorage, register(defaults:),
    # raw strings, optional chaining, and cross-file receivers.
    bad_swift = synth / 'Sources/Alpha/BadStore.swift'
    failing_swift_snippets = [
        'import Foundation\nfunc f(d: UserDefaults) { d.set(true, forKey: "unprefixedKey") }\n',
        'import SwiftUI\nstruct V { @AppStorage("beta.stolen") var x = false }\n',
        (
            'import SwiftUI\n'
            'struct V { @AppStorage(dynKey, store: UserDefaults(suiteName: "alpha.suite")) var x = false }\n'
        ),
        'import Foundation\nfunc f(d: UserDefaults, k: String) { d.set(true, forKey: k) }\n',
        (
            'import Foundation\nfunc id(_ s: String) -> String { return s }\n'
            'func f(d: UserDefaults, s: String) { d.set(true, forKey: id(s)) }\n'
        ),
        (
            'import Foundation\n'
            'func partial(_ b: Bool, _ s: String) -> String { if b { return "alpha.ok" }\nreturn s }\n'
            'func f(d: UserDefaults, s: String) { d.set(true, forKey: partial(false, s)) }\n'
        ),
        'import Foundation\nfunc save(d: UserDefaults, k: String) { d.set(1, forKey: k) }\nlet k = "alpha.shadow"\n',
        'import Foundation\nfunc f(d: UserDefaults) { d.register(defaults: ["alpha.arr": [1, 2], "unprefixed": 3]) }\n',
        'import Foundation\nfunc f(d: UserDefaults, dk: String) { d.register(defaults: [dk: 1]) }\n',
        'import Foundation\nfunc f(ud: UserDefaults?) { ud?.set(true, forKey: "unprefixed") }\n',
        (
            'import Foundation\nlet x = #"quote " /* unclosed"#\n'
            'func f(d: UserDefaults) { d.set(true, forKey: "unprefixed") }\n'
        ),
        (
            'import Foundation\n'
            'func f(d: UserDefaults) { let y = "a \\(helper("//")) b"; d.set(true, forKey: "unprefixed") }\n'
        ),
    ]
    for snippet in failing_swift_snippets:
        bad_swift.write_text(snippet, encoding='utf-8')
        assert check_module_storage_keys(synth), f'expected storage key check failure for:\n{snippet}'

    # Valid tricky Swift patterns must NOT false-positive.
    valid_swift_snippets = [
        (
            'import Foundation\nfunc extract(forKey x: String) -> Int { 1 }\n'
            'func f(d: UserDefaults) { d.set(extract(forKey: "notUD"), forKey: "alpha.real") }\n'
        ),
        'import Foundation\nfunc f(d: UserDefaults) { d.set(true, forKey: """alpha.multi""") }\n',
        (
            'import SwiftUI\n'
            'struct V { @AppStorage(wrappedValue: "dark", "alpha.theme", '
            'store: UserDefaults(suiteName: "com.example.app")) var t: String = "dark" }\n'
        ),
    ]
    for snippet in valid_swift_snippets:
        bad_swift.write_text(snippet, encoding='utf-8')
        assert check_module_storage_keys(synth) == [], f'unexpected false positive on:\n{snippet}'
    bad_swift.unlink()

    # Cross-file receiver in another Swift file of the same module must still be checked.
    (synth / 'Sources/Alpha/Holder.swift').write_text(
        'import Foundation\nlet sharedUD = UserDefaults.standard\n', encoding='utf-8'
    )
    (synth / 'Sources/Alpha/Ext.swift').write_text(
        'func save() { sharedUD.set(true, forKey: "unprefixed") }\n', encoding='utf-8'
    )
    assert any('unprefixed' in err for err in check_module_storage_keys(synth))
    (synth / 'Sources/Alpha/Holder.swift').unlink()
    (synth / 'Sources/Alpha/Ext.swift').unlink()

    # Core must not write a module-prefixed UserDefaults key.
    (synth / 'Sources/Core/BadCore.swift').write_text(
        'import Foundation\nfunc c(d: UserDefaults) { d.set(1, forKey: "alpha.bad") }\n', encoding='utf-8'
    )
    assert any('game module prefix' in err for err in check_module_storage_keys(synth))
    (synth / 'Sources/Core/BadCore.swift').unlink()

    # 3e. Root / foreign data directory escapes must fail (`trainer_data_root`,
    # `trainer_data_directory`, `trainer_log_directory`).
    for bad_py in (
        'from core.log_paths import trainer_data_root\nROOT_DIR = trainer_data_root()\n',
        'from core.log_paths import trainer_data_directory\nDIR = trainer_data_directory(game_id="beta")\n',
        'from core.log_paths import trainer_log_directory\nLOGS = trainer_log_directory("beta")\n',
    ):
        (synth / 'Backend/games/alpha/store.py').write_text(bad_py, encoding='utf-8')
        assert check_module_storage_keys(synth), f'expected data-dir failure for {bad_py!r}'
    (synth / 'Backend/games/alpha/store.py').unlink()

    # 3f. WP4.1 allowlist allows existing `shortcut.*` keys in `hades2` only, rejecting unlisted ones.
    assert _is_key_allowed_for_module('shortcut.layoutVersion', False, 'hades2')
    assert not _is_key_allowed_for_module('shortcut.newUnlistedKey', False, 'hades2')
    assert not _is_key_allowed_for_module('shortcut.layoutVersion', False, 'alpha')

    # 3g. Tools/games/<id>/ isolation catches relative & absolute foreign imports,
    # token leaks, and unowned top-level Tools/ scripts referencing a game module.
    (synth / 'Tools/games/alpha').mkdir(parents=True)
    for filename, snippet in (
        ('bad_rel.py', 'from ..beta import adapter\n'),
        ('bad_abs.py', 'from games.beta import adapter\n'),
    ):
        bad_tool = synth / 'Tools/games/alpha' / filename
        bad_tool.write_text(snippet, encoding='utf-8')
        assert any('imports foreign game' in err for err in check_python_import_boundaries(synth)), filename
        bad_tool.unlink()

    leaky_top = synth / 'Tools/leaky_tool.py'
    leaky_top.write_text('import games.alpha\n', encoding='utf-8')
    assert any('shared Python must not import game module' in err for err in check_python_import_boundaries(synth))
    leaky_top.unlink()

    tok_tool = synth / 'Tools/games/alpha/leak_token.py'
    tok_tool.write_text('CLS = "BetaAdapter"\n', encoding='utf-8')
    assert any('foreign module identifiers' in err for err in check_manifest_derived_identities(synth))
    tok_tool.unlink()

print('cross_game_isolation_ok')
