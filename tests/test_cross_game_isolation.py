"""Verify manifest-derived cross-game, Core, Python import, and storage-key isolation."""
from __future__ import annotations

import ast
import io
import json
import re
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
    'hades2': frozenset({
        'shortcut.layoutVersion',
        'shortcut.action.godMode',
        'shortcut.action.gardenQoL',
        'shortcut.action.damageEnabled',
        'shortcut.action.',
    }),
}

# Pre-WP4.2 Hades II root data directory accesses retained until #771 WP4.2
# moves desired-state.json / profiles / backups / diagnostics under data_dir.
WP4_2_ROOT_DATA_DIR_ALLOWLIST: dict[str, frozenset[str]] = {
    'hades2': frozenset({
        'Backend/games/hades2/adapter.py',
        'Backend/games/hades2/command_contract.py',
        'Backend/games/hades2/diagnostics.py',
        'Backend/games/hades2/preparation.py',
    }),
}


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


def _ignore_local_finder_duplicate(path: Path) -> bool:
    """Ignore Finder/iCloud untracked `name 2.ext` copies when present locally."""
    return ' 2.' in path.name


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
        specs.append(ModuleSpec(
            id=raw['id'],
            display_name=raw.get('displayName', ''),
            frontend_dir=frontend_dir,
            frontend_name=Path(frontend_rel).name if frontend_rel else frontend_dir.name,
            module_type=frontend.get('moduleType', ''),
            backend_dir=backend_dir,
            adapter_module=adapter_mod,
            adapter_type=adapter_cls,
            is_fixture=is_fixture,
        ))
    return specs


def _iter_python_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return [p for p in sorted(directory.rglob('*.py')) if not _ignore_local_finder_duplicate(p)]


def _iter_swift_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return [p for p in sorted(directory.rglob('*.swift')) if not _ignore_local_finder_duplicate(p)]


def _is_game_owned_tool(path: Path, game_ids: Iterable[str]) -> bool:
    stem = path.stem
    for gid in game_ids:
        if (
            stem.startswith(f'{gid}_')
            or stem.startswith(f'generate_{gid}_')
            or stem.startswith(f'profile_{gid}_')
        ):
            return True
    return False


def _resolved_python_imports(py_path: Path, package_root: Optional[Path]) -> set[str]:
    """Return dotted module names imported by `py_path` (including relative & `from pkg import mod`)."""
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
                    base = pkg_parts[:len(pkg_parts) - up]
                    mod_parts = node.module.split('.') if node.module else []
                    prefix = '.'.join(base + mod_parts)
                    if prefix:
                        targets.add(prefix)
                    for alias in node.names:
                        if alias.name != '*':
                            full = '.'.join(base + mod_parts + [alias.name])
                            if full:
                                targets.add(full)
    return targets


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


def _target_matches_game(target: str, game_id: str) -> bool:
    return (
        target == f'games.{game_id}'
        or target.startswith(f'games.{game_id}.')
        or target == game_id
        or target.startswith(f'{game_id}.')
    )


def _target_matches_any_games_pkg(target: str) -> Optional[str]:
    if target == 'games':
        return 'games'
    if target.startswith('games.'):
        return target.split('.', 2)[1]
    return None


def check_python_import_boundaries(root: Path) -> list[str]:
    """Verify Core imports no `games.*` and each game imports no other game (derived from manifests)."""
    specs = _discover_manifests(root)
    all_ids = {spec.id for spec in specs}
    backend_root = root / 'Backend'
    errors: list[str] = []

    shared_py = (
        _iter_python_files(backend_root / 'core')
        + _iter_python_files(backend_root / 'debugger')
        + [
            path for path in _iter_python_files(root / 'Tools')
            if not _is_game_owned_tool(path, all_ids)
        ]
    )

    for path in shared_py:
        rel = path.relative_to(root).as_posix()
        imports = _resolved_python_imports(path, backend_root)
        for target in sorted(imports):
            pkg = _target_matches_any_games_pkg(target)
            if pkg is not None or any(_target_matches_game(target, gid) for gid in all_ids):
                errors.append(f'{rel}: shared Python must not import game module ({target})')
        for literal in _non_docstring_string_literals(path):
            for gid in sorted(all_ids):
                if literal == f'games.{gid}' or literal.startswith(f'games.{gid}.'):
                    errors.append(f'{rel}: shared Python references game module string {literal!r}')

    for spec in specs:
        other_ids = all_ids - {spec.id}
        pkg_root = backend_root if spec.backend_dir.is_relative_to(backend_root) else spec.backend_dir.parent
        for path in _iter_python_files(spec.backend_dir):
            rel = path.relative_to(root).as_posix()
            for target in sorted(_resolved_python_imports(path, pkg_root)):
                imported_game = _target_matches_any_games_pkg(target)
                if imported_game is not None and imported_game not in ('games', spec.id):
                    errors.append(f'{rel}: module {spec.id!r} imports foreign game package {target!r}')
                    continue
                for other in sorted(other_ids):
                    if _target_matches_game(target, other):
                        errors.append(f'{rel}: module {spec.id!r} imports foreign game {other!r} ({target})')
            for literal in _non_docstring_string_literals(path):
                for other in sorted(other_ids):
                    if literal == f'games.{other}' or literal.startswith(f'games.{other}.'):
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

    all_shared_tokens = {
        tok
        for spec in specs
        for tok in shared_tokens_for(spec)
    }
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
        _iter_python_files(root / 'Backend' / 'core')
        + _iter_python_files(root / 'Backend' / 'debugger')
        + [root / name for name in shared_tool_names if (root / name).is_file()]
    )
    if shared_pattern is not None:
        for path in shared_files:
            rel = path.relative_to(root).as_posix()
            hits = sorted(set(shared_pattern.findall(_non_comment_python_text(path))))
            if hits:
                errors.append(f'{rel}: shared code mentions module identity tokens {hits}')
        shared_swift = _iter_swift_files(root / 'Sources' / 'Core')
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
                    rel = path.relative_to(root).as_posix()
                    text = path.read_text(encoding='utf-8', errors='ignore')
                    hits = sorted(set(fixture_pat.findall(text)))
                    if hits:
                        errors.append(f'{rel}: fixture mentions real module tokens {hits}')

    for spec in specs:
        other_tokens = {
            tok
            for other in specs
            if other.id != spec.id
            for tok in cross_game_tokens_for(other)
        }
        pat = _boundary_pattern(other_tokens)
        if pat is None:
            continue
        for path in _iter_python_files(spec.backend_dir) + _iter_swift_files(spec.frontend_dir):
            rel = path.relative_to(root).as_posix()
            if path.suffix == '.py':
                text = _non_comment_python_text(path)
            else:
                text = _strip_swift_comments(path.read_text(encoding='utf-8'))
            hits = sorted(set(pat.findall(text)))
            if hits:
                errors.append(f'{rel}: module {spec.id!r} mentions foreign module identifiers {hits}')
    return errors


def _strip_swift_comments(source: str) -> str:
    """Strip Swift `//` and nested `/* */` comments while preserving string literals."""
    out: list[str] = []
    i = 0
    n = len(source)
    block_depth = 0
    while i < n:
        ch = source[i]
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
                if ch == '\n':
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
        if ch == '"':
            if source.startswith('"""', i):
                out.append('"""')
                i += 3
                while i < n and not source.startswith('"""', i):
                    if source[i] == '\\' and i + 1 < n:
                        out.append(source[i:i + 2])
                        i += 2
                    else:
                        out.append(source[i])
                        i += 1
                if source.startswith('"""', i):
                    out.append('"""')
                    i += 3
                continue
            out.append('"')
            i += 1
            while i < n:
                c = source[i]
                out.append(c)
                if c == '\\' and i + 1 < n:
                    out.append(source[i + 1])
                    i += 2
                    continue
                i += 1
                if c == '"':
                    break
            continue
        out.append(ch)
        i += 1
    return ''.join(out)


def _swift_string_patterns(text: str) -> list[tuple[str, bool]]:
    """Return `(literal_or_prefix, is_template_prefix)` for every Swift `"..."` literal in `text`."""
    patterns: list[tuple[str, bool]] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] != '"':
            i += 1
            continue
        i += 1
        buf: list[str] = []
        is_template = False
        while i < n:
            c = text[i]
            if c == '\\' and i + 1 < n:
                nxt = text[i + 1]
                if nxt == '(':
                    # Stop literal prefix at the first interpolation `\(`.
                    is_template = True
                    # Skip balanced parentheses of the interpolation before continuing.
                    i += 2
                    depth = 1
                    while i < n and depth > 0:
                        if text[i] == '(':
                            depth += 1
                        elif text[i] == ')':
                            depth -= 1
                        i += 1
                    break
                buf.append(nxt)
                i += 2
                continue
            i += 1
            if c == '"':
                break
            buf.append(c)
        if not is_template:
            patterns.append((''.join(buf), False))
        else:
            patterns.append((''.join(buf), True))
            # Consume remainder of interpolated string up to closing quote.
            while i < n and text[i] != '"':
                if text[i] == '\\' and i + 1 < n:
                    i += 2
                else:
                    i += 1
            if i < n and text[i] == '"':
                i += 1
    return patterns


def _extract_swift_brace_block(code: str, brace_index: int) -> str:
    depth = 0
    in_str = False
    i = brace_index
    n = len(code)
    while i < n:
        c = code[i]
        if in_str:
            if c == '\\' and i + 1 < n:
                i += 2
                continue
            if c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return code[brace_index:i + 1]
        i += 1
    return code[brace_index:]


_USERDEFAULTS_METHODS = frozenset({
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
})


def _resolve_swift_key_expression(
    code: str,
    expr: str,
    seen: Optional[set[str]] = None,
) -> Optional[list[tuple[str, bool]]]:
    stripped = expr.strip()
    if stripped.startswith('"'):
        pats = _swift_string_patterns(stripped)
        return pats or None

    seen = set() if seen is None else set(seen)
    call_match = re.fullmatch(
        r'(?:(?:Self|[A-Za-z_][A-Za-z0-9_]*)\.)?([A-Za-z_][A-Za-z0-9_]*)\(([^)]*)\)',
        stripped,
    )
    if call_match:
        fn_name = call_match.group(1)
        if fn_name in seen:
            return []
        seen.add(fn_name)
        results: list[tuple[str, bool]] = []
        found_def = False
        for fn_match in re.finditer(rf'\bfunc\s+{re.escape(fn_name)}\s*\([^)]*\)\s*(?:->\s*[^{{]+)?\{{', code):
            found_def = True
            body = _extract_swift_brace_block(code, fn_match.end() - 1)
            results.extend(_swift_string_patterns(body))
            for delegate in re.finditer(r'\b([A-Za-z_][A-Za-z0-9_]*)\([^)]*\)', body):
                dname = delegate.group(1)
                if dname not in seen and re.search(rf'\bfunc\s+{re.escape(dname)}\s*\(', code):
                    nested = _resolve_swift_key_expression(code, delegate.group(0), seen)
                    if nested:
                        results.extend(nested)
        return results if found_def else None

    prop_match = re.fullmatch(r'(?:(?:Self|[A-Za-z_][A-Za-z0-9_]*)\.)?([A-Za-z_][A-Za-z0-9_]*)', stripped)
    if prop_match:
        prop_name = prop_match.group(1)
        if prop_name in seen:
            return []
        seen.add(prop_name)
        results = []
        prop_pattern = rf'\b(?:let|var)\s+{re.escape(prop_name)}(?:\s*:\s*String)?\s*=\s*([^\n;{{]+)'
        for val_match in re.finditer(prop_pattern, code):
            rhs = val_match.group(1).strip()
            nested = _resolve_swift_key_expression(code, rhs, seen)
            if nested:
                results.extend(nested)
        return results or None

    return None


def _scan_swift_user_defaults_keys(
    swift_path: Path,
    *,
    module_code: Optional[str] = None,
) -> tuple[list[tuple[str, bool]], list[str]]:
    """Return `(resolved_keys, unresolved_expressions)` for UserDefaults / AppStorage sites."""
    code = _strip_swift_comments(swift_path.read_text(encoding='utf-8'))
    lookup_code = code if module_code is None else module_code
    resolved: list[tuple[str, bool]] = []
    unresolved: list[str] = []

    for match in re.finditer(r'@AppStorage\s*\(([^)]+)\)', code):
        args_text = match.group(1)
        pats = _swift_string_patterns(args_text)
        if pats:
            resolved.extend(pats)
        else:
            unresolved.append(f'@AppStorage({args_text.strip()})')

    has_user_defaults = 'UserDefaults' in code or re.search(r'\bdefaults\b', code) is not None
    if not has_user_defaults:
        return resolved, unresolved

    receivers = {'defaults'}
    for typed_match in re.finditer(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*:\s*UserDefaults\b', code):
        receivers.add(typed_match.group(1))
    for init_match in re.finditer(r'\b(?:let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*UserDefaults\b', code):
        receivers.add(init_match.group(1))
    receiver_group = '|'.join(sorted((re.escape(name) for name in receivers), key=len, reverse=True))
    receiver_pattern = rf'(?:UserDefaults(?:\([^)]*\))?(?:\.standard)?|(?:self\.)?(?:{receiver_group}))'

    for match in re.finditer(rf'\b{receiver_pattern}\.register\s*\(\s*defaults\s*:\s*\[', code):
        end = code.find(']', match.end())
        if end < 0:
            unresolved.append('register(defaults: ...)')
        else:
            block = code[match.end():end]
            for key_match in re.finditer(r'"([^"]+)"\s*:', block):
                resolved.append((key_match.group(1), False))

    for match in re.finditer(rf'\b{receiver_pattern}\.([A-Za-z_][A-Za-z0-9_]*)\s*\(', code):
        method = match.group(1)
        if method not in _USERDEFAULTS_METHODS:
            continue
        call_start = match.end()
        # Extract the call's `forKey:` argument within the matching call parentheses.
        depth = 1
        in_str = False
        i = call_start
        n = len(code)
        while i < n and depth > 0:
            c = code[i]
            if in_str:
                if c == '\\' and i + 1 < n:
                    i += 2
                    continue
                if c == '"':
                    in_str = False
            else:
                if c == '"':
                    in_str = True
                elif c == '(':
                    depth += 1
                elif c == ')':
                    depth -= 1
                    if depth == 0:
                        break
            i += 1
        call_args = code[call_start:i]
        fk_match = re.search(r'\bforKey:\s*(.+)$', call_args, re.DOTALL)
        if not fk_match:
            continue
        expr = fk_match.group(1).strip()
        keys = _resolve_swift_key_expression(lookup_code, expr)
        if keys is None:
            unresolved.append(expr)
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
    specs = _discover_manifests(root)
    all_ids = {spec.id for spec in specs}
    errors: list[str] = []

    for spec in specs:
        swift_files = _iter_swift_files(spec.frontend_dir)
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

    for path in _iter_swift_files(root / 'Sources' / 'Core'):
        rel = path.relative_to(root).as_posix()
        keys, unresolved = _scan_swift_user_defaults_keys(path)
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
        for path in _iter_python_files(spec.backend_dir):
            rel = path.relative_to(root).as_posix()
            src = _non_comment_python_text(path)
            if ('trainer_data_root' in src or 'legacy_data_dir' in src) and rel not in allowed_files:
                errors.append(f'{rel}: module {spec.id!r} uses root data dir outside context.data_dir')
            for match in re.finditer(r'\btrainer_data_directory\s*\(\s*[\'"]([^\'"]+)[\'"]', src):
                target_id = match.group(1)
                if target_id != spec.id:
                    errors.append(f'{rel}: module {spec.id!r} accesses foreign data directory {target_id!r}')
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
            src.is_relative_to(mod_dir) or src.is_relative_to(gen_dir / mod_name)
            for src in compiled[mod_name]
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
        (mdir / 'module.json').write_text(json.dumps({
            'schemaVersion': 1,
            'id': gid,
            'displayName': gid.capitalize(),
            'protocolVersion': 1,
            'backend': {'adapter': f'games.{gid}.adapter:{cls}'},
            'frontend': {'sourceDirectory': gdir, 'moduleType': mtype, 'minimumMacOS': '14.0'},
        }), encoding='utf-8')
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
    cdir = root / 'Backend' / 'core'
    cdir.mkdir(parents=True)
    (cdir / 'adapter.py').write_text('class GameAdapter: pass\n', encoding='utf-8')
    tdir = root / 'Tools'
    tdir.mkdir(parents=True)
    (tdir / 'module_support.py').write_text('"""Generic helper"""\n', encoding='utf-8')


with tempfile.TemporaryDirectory(prefix='mgt-isolation-synth-') as tmp:
    synth = Path(tmp)
    _write_synthetic_repo(synth)
    assert check_python_import_boundaries(synth) == []
    assert check_manifest_derived_identities(synth) == []
    assert check_module_storage_keys(synth) == []

    # 3a. Core importing a declared game (absolute + relative + `from games import`) must fail.
    (synth / 'Backend/core/leak.py').write_text('from games import beta\n', encoding='utf-8')
    assert any('shared Python must not import game module' in err for err in check_python_import_boundaries(synth))
    (synth / 'Backend/core/leak.py').write_text('from ..games.alpha import adapter\n', encoding='utf-8')
    assert any('shared Python must not import game module' in err for err in check_python_import_boundaries(synth))
    (synth / 'Backend/core/leak.py').unlink()

    # 3b. Cross-game Python import (`alpha` importing `beta`, relative or string worker) must fail.
    (synth / 'Backend/games/alpha/cross.py').write_text('from ..beta import adapter\n', encoding='utf-8')
    assert any('foreign game' in err for err in check_python_import_boundaries(synth))
    (synth / 'Backend/games/alpha/cross.py').write_text('WORKER = "games.beta.worker"\n', encoding='utf-8')
    assert any('foreign game string' in err for err in check_python_import_boundaries(synth))
    (synth / 'Backend/games/alpha/cross.py').unlink()

    # 3c. Manifest-derived module identity in Core or cross-game must fail even for a new 3rd/arbitrary module.
    (synth / 'Backend/core/ident.py').write_text('NAME = "AlphaGameModule"\n', encoding='utf-8')
    assert any('AlphaGameModule' in err for err in check_manifest_derived_identities(synth))
    (synth / 'Backend/core/ident.py').unlink()

    # 3d. Unprefixed UserDefaults key (and unresolved dynamic key) must fail closed.
    bad_swift = synth / 'Sources/Alpha/BadStore.swift'
    bad_swift.write_text(
        'import Foundation\nfunc f(d: UserDefaults) { d.set(true, forKey: "unprefixedKey") }\n',
        encoding='utf-8',
    )
    assert any('unprefixedKey' in err for err in check_module_storage_keys(synth))
    bad_swift.write_text(
        'import SwiftUI\nstruct V { @AppStorage("beta.stolen") var x = false }\n',
        encoding='utf-8',
    )
    assert any('foreign module key' in err for err in check_module_storage_keys(synth))
    bad_swift.write_text(
        'import Foundation\nfunc f(d: UserDefaults, k: String) { d.set(true, forKey: k) }\n',
        encoding='utf-8',
    )
    assert any('unresolved UserDefaults key' in err for err in check_module_storage_keys(synth))
    bad_swift.unlink()

    # 3e. Root data directory escape in non-Hades2 module must fail.
    (synth / 'Backend/games/alpha/store.py').write_text(
        'from core.log_paths import trainer_data_root\nROOT_DIR = trainer_data_root()\n',
        encoding='utf-8',
    )
    assert any('context.data_dir' in err for err in check_module_storage_keys(synth))
    (synth / 'Backend/games/alpha/store.py').unlink()

    # 3f. WP4.1 allowlist allows existing `shortcut.*` keys in `hades2` only, rejecting unlisted ones.
    assert _is_key_allowed_for_module('shortcut.layoutVersion', False, 'hades2')
    assert not _is_key_allowed_for_module('shortcut.newUnlistedKey', False, 'hades2')
    assert not _is_key_allowed_for_module('shortcut.layoutVersion', False, 'alpha')

print('cross_game_isolation_ok')
