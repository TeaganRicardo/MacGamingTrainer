"""Derive macOS test consumers from their Python imports and file inputs."""
from __future__ import annotations

import ast
import re
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Iterable

from module_inventory import MODULES_RELATIVE
from product_support import CORE_SWIFT_SOURCES
from test_inventory import (
    ROOT,
    declarations,
    declared_prerequisites,
    discover_module_test_prerequisites,
    discover_test_inventory,
    load_macos_only_tests,
    prerequisite_path,
)

PATH_LITERAL = re.compile(r"[\w.-]+(?:/[\w.-]+)*")
SUPPORT_ROOTS = ("tests", "Tools")
FILE_ROOTS = (*SUPPORT_ROOTS, "Backend", "Sources", "Resources", "Native", "ContractFixtures", "docs", ".github")
# Pure-Python Backend modules covered by Linux contracts even when imported or
# invoked by a macOS harness or helper, keeping pure-Python protocol, server,
# save-codec, and game-adapter changes on the Linux fast path (see
# tests/test_ci_docs_only.py).
PORTABLE_BACKEND_IMPORTS = frozenset({
    "Backend/core/__init__.py",
    "Backend/core/adapter.py",
    "Backend/core/errors.py",
    "Backend/core/lz4_block.py",
    "Backend/core/module_manifest.py",
    "Backend/core/operation_profile.py",
    "Backend/core/protocol.py",
    "Backend/core/registry.py",
    "Backend/core/save_service.py",
    "Backend/core/server.py",
    "Backend/core/structured_save_edit.py",
    "Backend/games/__init__.py",
    "Backend/games/hades2/__init__.py",
    "Backend/games/hades2/adapter.py",
    "Backend/games/hades2/command_contract.py",
    "Backend/games/hades2/save_document.py",
    "Backend/games/hades2/save_provider.py",
    "Backend/games/hades2/save_workspace.py",
})
# Exercise both a native build fixture and a Host journey when their runner changes.
MACOS_RUNNER_PATHS = frozenset({
    "Tools/run_macos_checks.sh",
    "Tools/select_macos_pr_tests.py",
    "Tools/test_inputs.py",
    "Tools/test_inventory.py",
})
MACOS_RUNNER_SMOKE = frozenset({"test_build_signing_metadata_macos.py", "test_multi_game_context_state.py"})


def path_tail(node: ast.AST) -> list[str]:
    """Literal portion of a Path / 'directory' / 'file' expression."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        tail = path_tail(node.right)
        return path_tail(node.left) + tail if tail else []
    return []


def declared_inputs(tree: ast.Module, source: str) -> tuple[str, ...]:
    values = declarations(tree, "MGT_INPUTS")
    if not values:
        return ()
    message = f"{source}: MGT_INPUTS must be a literal list of repository-relative paths"
    if len(values) != 1 or not isinstance(values[0], (ast.List, ast.Tuple)):
        raise ValueError(message)
    paths = []
    for element in values[0].elts:
        if not isinstance(element, ast.Constant) or not isinstance(element.value, str):
            raise ValueError(message)
        value = element.value
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or path == PurePosixPath("."):
            raise ValueError(message)
        if value not in (path.as_posix(), path.as_posix() + "/"):
            raise ValueError(message)
        paths.append(value)
    return tuple(paths)


def compiled_layout_inputs(tree: ast.Module, source_dirs: dict[str, str]) -> set[str]:
    """Find source directories and generated-binding inputs of Swift compiler calls."""
    compiler_names = set()
    compiler_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in {"swift_test_compiler", "tests.swift_test_compiler"}:
            compiler_names.update(alias.asname or alias.name for alias in node.names
                                  if alias.name == "compile_swift_test")
        elif isinstance(node, ast.Import):
            compiler_modules.update(alias.asname or alias.name for alias in node.names
                                    if alias.name in {"swift_test_compiler", "tests.swift_test_compiler"})
    used = set()
    used_games = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        named_call = isinstance(callee, ast.Name) and callee.id in compiler_names
        module_call = (
            isinstance(callee, ast.Attribute) and callee.attr == "compile_swift_test"
            and isinstance(callee.value, ast.Name) and callee.value.id in compiler_modules
        )
        if not (named_call or module_call):
            continue
        args = {keyword.arg: keyword.value for keyword in node.keywords}
        if "modules" in args and not (
            isinstance(args["modules"], ast.Constant) and args["modules"].value is None
        ):
            # Explicit modules list their source files at the call site.
            continue
        checkout = args.get("checkout")
        if checkout is not None and not (isinstance(checkout, ast.Name) and checkout.id in {"ROOT", "root"}):
            # A scratch checkout must declare inputs copied from the real tree.
            continue
        used.add(f"{CORE_SWIFT_SOURCES}/")
        if None in args:
            used_games.update(source_dirs)
        if "games" in args:
            try:
                games = ast.literal_eval(args["games"])
            except (ValueError, SyntaxError):
                used_games.update(source_dirs)
                continue
            if isinstance(games, (list, tuple)) and all(
                isinstance(game, str) and game in source_dirs for game in games
            ):
                used_games.update(games)
            else:
                used_games.update(source_dirs)
    for game in used_games:
        used.update((source_dirs[game], (MODULES_RELATIVE / game / "module.json").as_posix()))
    return used


def affected_tests(paths: Iterable[str], dependencies: dict[str, frozenset[str]]) -> set[str]:
    changed = set(paths)
    return {
        name for name, inputs in dependencies.items()
        if changed.intersection(inputs) or any(
            path.startswith(prefix) for prefix in inputs if prefix.endswith("/") for path in changed
        )
    }


def is_native_fixture(path: str) -> bool:
    # Shared native fixture sources can be pulled in indirectly by the harness.
    return path.startswith("tests/") and path.endswith((".swift", ".c", ".h", ".m", ".mm", ".plist", ".so", ".dylib"))


def load_test_dependency_graph(
    root: Path = ROOT,
    *,
    tests: Iterable[str],
    changed_paths: Iterable[str] = (),
    source_dirs: dict[str, str] | None = None,
    include_runner_smoke: bool = False,
) -> tuple[dict[str, frozenset[str]], dict[str, frozenset[str]]]:
    """Return (inputs, prerequisites) for each requested entrypoint under tests/."""
    changed = set(changed_paths)

    @lru_cache(maxsize=None)
    def exists(path: str) -> bool:
        return path in changed or (root / path).is_file()

    def imported_files(tree: ast.Module, source: PurePosixPath) -> set[str]:
        found = set()
        roots = (*SUPPORT_ROOTS, "Backend") if source.parts and source.parts[0] == "tests" else SUPPORT_ROOTS
        search_path = (source.parent, *map(PurePosixPath, roots), PurePosixPath("."))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
                bases = search_path
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = [module] if module else []
                names += [".".join(filter(None, (module, alias.name)))
                          for alias in node.names if alias.name != "*"]
                if node.level:
                    bases = (source.parents[node.level - 1],) if node.level <= len(source.parents) else ()
                else:
                    bases = search_path
            else:
                continue
            for name in names:
                for base in bases:
                    stem = (base / name.replace(".", "/")).as_posix()
                    candidates = (f"{stem}.py", f"{stem}/__init__.py")
                    match = next((path for path in candidates if exists(path)), None)
                    if match:
                        found.add(match)
                        for parent in PurePosixPath(stem).parents:
                            initializer = (parent / "__init__.py").as_posix()
                            if parent == base:
                                break
                            if exists(initializer):
                                found.add(initializer)
                        break
        return {path for path in found if path not in PORTABLE_BACKEND_IMPORTS}

    def named_files(tree: ast.Module, source: PurePosixPath) -> set[str]:
        found = set()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Constant, ast.BinOp)):
                continue
            relative = "/".join(path_tail(node))
            if not PATH_LITERAL.fullmatch(relative):
                continue
            path = PurePosixPath(relative)
            if not path.parts or ".." in path.parts:
                continue
            candidates = [source.parent / path, PurePosixPath("tests") / path]
            if path.parts[0] == "Backend" and path.suffix == ".py" and relative in PORTABLE_BACKEND_IMPORTS:
                continue  # Pure-Python portable modules are covered by Linux contracts.
            if path.parts[0] in FILE_ROOTS or relative in {"build.sh", "Info.plist"}:
                candidates.append(path)
            found.update(candidate.as_posix() for candidate in candidates if exists(candidate.as_posix()))
        return found

    @lru_cache(maxsize=None)
    def swift_sources(directory: str) -> frozenset[str]:
        prefix = directory.rstrip("/") + "/"
        return frozenset(
            path.relative_to(root).as_posix()
            for path in (root / directory).rglob("*.swift") if path.is_file()
        ) | frozenset(path for path in changed if path.startswith(prefix) and path.endswith(".swift"))

    @lru_cache(maxsize=None)
    def direct_inputs(path: str) -> tuple[set[str], set[str], tuple[str, ...]]:
        if not (root / path).is_file():
            return set(), set(), ()
        tree = ast.parse((root / path).read_text(encoding="utf-8"), filename=path)
        declared = declared_inputs(tree, path)
        for input_path in declared:
            if input_path.endswith("/"):
                present = (root / input_path).is_dir()
            else:
                present = (root / input_path).is_file()
            if not present:
                raise ValueError(f"{path}: missing declared macOS test input {input_path}")
        prereqs = declared_prerequisites(tree, path, root=root)
        source = PurePosixPath(path)
        imports = imported_files(tree, source)
        named = named_files(tree, source)
        inputs = imports | named | set(declared) | {prerequisite_path(prereq) for prereq in prereqs}
        if source_dirs is not None:
            for compiled in compiled_layout_inputs(tree, source_dirs):
                if compiled.endswith("/"):
                    inputs.update(swift_sources(compiled))
                else:
                    inputs.add(compiled)
        helpers = {
            helper for helper in (named - set(declared)) | imports
            if helper.endswith(".py") and helper.startswith(("tests/", "Tools/"))
        }
        return inputs, helpers, prereqs

    result: dict[str, frozenset[str]] = {}
    prerequisites: dict[str, frozenset[str]] = {}
    for name in sorted(tests):
        entry = f"tests/{name}"
        inputs: set[str] = set()
        prereqs: set[str] = set()
        work = [entry]
        seen = {entry}
        while work:
            found, helpers, direct_prereqs = direct_inputs(work.pop())
            inputs.update(found)
            prereqs.update(direct_prereqs)
            work.extend(helpers - seen)
            seen.update(helpers)
        if include_runner_smoke and name in MACOS_RUNNER_SMOKE:
            inputs.update(MACOS_RUNNER_PATHS)
        result[name] = frozenset(inputs - {entry})
        prerequisites[name] = frozenset(prereqs)
    return result, prerequisites


def load_macos_test_dependencies_and_prerequisites(
    root: Path = ROOT, *, changed_paths: Iterable[str] = (),
    source_dirs: dict[str, str] | None = None,
) -> tuple[dict[str, frozenset[str]], dict[str, frozenset[str]]]:
    """Return (inputs, prerequisites) for each macOS test entrypoint."""
    return load_test_dependency_graph(
        root,
        tests=load_macos_only_tests(root),
        changed_paths=changed_paths,
        source_dirs=source_dirs,
        include_runner_smoke=True,
    )


def load_macos_test_dependencies(
    root: Path = ROOT, *, changed_paths: Iterable[str] = (),
    source_dirs: dict[str, str] | None = None,
) -> dict[str, frozenset[str]]:
    """Return the input paths of each native entrypoint, including indirect helpers.

    Pure-Python Backend modules listed in PORTABLE_BACKEND_IMPORTS remain
    Linux-owned unless explicitly declared in MGT_INPUTS. Any other Backend
    module imported or referenced by a test or its tests/ helpers is derived
    automatically, alongside indirect runtime/data inputs declared in
    MGT_INPUTS (where a trailing slash denotes a directory input) and
    MGT_PREREQUISITES scripts. When the product's source directories are
    supplied, include the sources compiled by Swift harnesses.
    """
    dependencies, _ = load_macos_test_dependencies_and_prerequisites(
        root, changed_paths=changed_paths, source_dirs=source_dirs,
    )
    return dependencies


def load_portable_test_prerequisites(root: Path = ROOT) -> tuple[str, ...]:
    """Return declared CI prerequisites across portable tests and module manifests."""
    portable_tests = [
        name for name, platform in discover_test_inventory(root).items()
        if platform is None
    ]
    _, test_prereqs = load_test_dependency_graph(root, tests=portable_tests)
    declared: set[str] = set()
    for items in test_prereqs.values():
        declared.update(items)
    for items in discover_module_test_prerequisites(root).values():
        declared.update(items)
    return tuple(sorted(declared))
