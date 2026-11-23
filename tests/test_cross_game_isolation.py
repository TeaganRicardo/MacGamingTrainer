"""Games stay isolated: Swift module graph, Python imports, and per-game storage keys and data folders."""

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

_FINDER_DUPLICATE_RE = re.compile(r'^(.+) [2-9]\d*$')


@dataclass(frozen=True)
class ModuleSpec:
    id: str
    frontend_dir: Path
    module_type: str
    backend_dir: Path
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
                frontend_dir=frontend_dir,
                module_type=frontend.get('moduleType', ''),
                backend_dir=backend_dir,
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


_SWIFT_TOKENS = re.compile(r'"""[\s\S]*?"""|"(?:\\.|[^"\\\n])*"|//[^\n]*|/\*[\s\S]*?\*/')


def _strip_swift_comments(source: str) -> str:
    return _SWIFT_TOKENS.sub(lambda m: ' ' if m.group(0).startswith('/') else m.group(0), source)


_SHORTCUT_STORAGE_CALL_RE = re.compile(r'TrainerShortcutStorage(?:\s*<[^>]+>)?\s*\(')
_SHORTCUT_STORAGE_RE = re.compile(
    r'TrainerShortcutStorage(?:\s*<[^>]+>)?\s*\(\s*moduleID\s*:\s*("([^"]+)"|([A-Za-z_][A-Za-z0-9_]*)\.descriptor\.id)'
)


def check_module_storage_keys(root: Path) -> list[str]:
    """Enforce TrainerShortcutStorage moduleID ownership and Python context.data_dir isolation."""
    tracked = _git_tracked_paths(root)
    specs = _discover_manifests(root)
    errors: list[str] = []

    for spec in specs:
        for path in _iter_swift_files(spec.frontend_dir, root, tracked):
            rel = path.relative_to(root).as_posix()
            code = _strip_swift_comments(path.read_text(encoding='utf-8'))
            if '@AppStorage' in code:
                errors.append(f'{rel}: module {spec.id!r} must not use @AppStorage directly')
            for match in _SHORTCUT_STORAGE_CALL_RE.finditer(code):
                scoped = _SHORTCUT_STORAGE_RE.match(code, match.start())
                if scoped is None:
                    errors.append(f'{rel}: TrainerShortcutStorage in module {spec.id!r} must declare a static moduleID')
                    continue
                literal_id, descriptor_type = scoped.group(2), scoped.group(3)
                if literal_id is not None and literal_id != spec.id:
                    errors.append(
                        f'{rel}: TrainerShortcutStorage moduleID {literal_id!r} does not match module {spec.id!r}'
                    )
                elif descriptor_type is not None and descriptor_type != spec.module_type:
                    errors.append(
                        f'{rel}: TrainerShortcutStorage descriptor type {descriptor_type!r} '
                        f'does not match {spec.module_type!r}'
                    )

    # Python data-directory isolation: modules must use context.data_dir (MacGamingTrainer/<game_id>/),
    # never root trainer_data_root() / legacy_data_dir.
    for spec in specs:
        for path in _iter_python_files(spec.backend_dir, root, tracked):
            rel = path.relative_to(root).as_posix()
            src = _non_comment_python_text(path)
            if 'trainer_data_root' in src or 'legacy_data_dir' in src:
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

# 2. Python imports and storage keys stay inside their own game.
assert not check_python_import_boundaries(ROOT), check_python_import_boundaries(ROOT)
assert not check_module_storage_keys(ROOT), check_module_storage_keys(ROOT)

assert not (ROOT / 'Backend/games/reference_fixture').exists()
assert not (ROOT / 'Sources/ReferenceFixture').exists()

print('cross_game_isolation_ok')
