#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "Tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from module_inventory import (
    ModuleInventoryError,
    app_resource_sources_for_diff,
    current_app_resource_sources,
    discover_module_ids,
    executable_reference_prefixes,
    module_ids_for_diff,
)
PORTABLE_TOOL_PATHS = {
    "Tools/check_runtime_revision.py",
    "Tools/discover_linux_tests.py",
    "Tools/module_inventory.py",
    "Tools/run_linux_checks.sh",
}
BACKEND_MODULE_BOUNDARY_PATHS = {
    "Backend/core/__init__.py",
    "Backend/core/adapter.py",
    "Backend/core/game_spec.py",
    "Backend/core/module_manifest.py",
    "Backend/core/protocol.py",
    "Backend/core/registry.py",
    "Backend/core/server.py",
}
MODULE_EXACT_PATHS = {
    ".github/workflows/module-build-matrix.yml",
    "ACTIVE_GAME_ID",
    "Backend/games/__init__.py",
    "Info.plist",
    "Sources/App.swift",
    "Tools/ci_docs_only.py",
    "Tools/clean_signing_metadata.py",
    "Tools/generate_game_binding.py",
    "Tools/module_inventory.py",
    "Tools/module_support.py",
    "Tools/publish_module_build.py",
    "Tools/validate_game_module.py",
    "Tools/verify_module_build.py",
    "build.sh",
}
MODULE_PREFIXES = (
    "ContractFixtures/reference_module/",
    "Sources/Core/",
)


def current_reference_prefixes(root: Path = ROOT) -> tuple[str, ...]:
    return executable_reference_prefixes(discover_module_ids(root))


def is_executable_reference_data(
    path: str,
    reference_prefixes: tuple[str, ...] | None = None,
) -> bool:
    prefixes = reference_prefixes if reference_prefixes is not None else current_reference_prefixes()
    return path.startswith(prefixes) and not path.endswith(".md")


def is_docs_only(
    paths: list[str],
    *,
    reference_prefixes: tuple[str, ...] | None = None,
) -> bool:
    normalized = [path.strip() for path in paths if path.strip()]
    if not normalized:
        return False
    return all(
        (path.startswith("docs/") or path.endswith(".md"))
        and not is_executable_reference_data(path, reference_prefixes)
        for path in normalized
    )


def load_macos_only_tests(root: Path = ROOT) -> set[str]:
    source = root / "Tools/macos_only_tests.txt"
    return {
        line.strip()
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def needs_module_build_for_path(path: str) -> bool:
    if (
        path in BACKEND_MODULE_BOUNDARY_PATHS
        or path in MODULE_EXACT_PATHS
        or path.startswith(MODULE_PREFIXES)
    ):
        return True
    return path.startswith("Backend/games/") and path.endswith("/module.json")


def is_linux_portable_only(
    path: str,
    macos_only_tests: set[str],
    reference_prefixes: tuple[str, ...] | None = None,
    app_resource_sources: tuple[str, ...] = (),
) -> bool:
    if path.startswith("Backend/"):
        return not path.endswith("/module.json") and not path.endswith(".plist")
    if path.startswith("tests/"):
        return Path(path).name not in macos_only_tests
    if is_executable_reference_data(path, reference_prefixes):
        return path not in app_resource_sources
    return path in PORTABLE_TOOL_PATHS


def classify_scope(
    paths: list[str],
    *,
    macos_only_tests: set[str] | None = None,
    reference_prefixes: tuple[str, ...] | None = None,
    app_resource_sources: tuple[str, ...] | None = None,
) -> dict[str, bool]:
    normalized = [path.strip() for path in paths if path.strip()]
    if not normalized:
        # Missing/unknown diff scope must fail closed.
        return {
            "docs_only": False,
            "needs_linux": True,
            "needs_macos": True,
            "needs_module": True,
        }

    docs_only = is_docs_only(normalized, reference_prefixes=reference_prefixes)
    if docs_only:
        return {
            "docs_only": True,
            "needs_linux": False,
            "needs_macos": False,
            "needs_module": False,
        }

    macos_only = macos_only_tests if macos_only_tests is not None else load_macos_only_tests()
    packaged_resources = (
        app_resource_sources
        if app_resource_sources is not None
        else current_app_resource_sources()
    )
    needs_module = any(needs_module_build_for_path(path) for path in normalized)
    needs_macos = needs_module or any(
        not is_linux_portable_only(
            path,
            macos_only,
            reference_prefixes,
            packaged_resources,
        )
        for path in normalized
    )
    return {
        "docs_only": False,
        "needs_linux": True,
        "needs_macos": needs_macos,
        "needs_module": needs_module,
    }


def changed_paths(base_sha: str, head_sha: str, cwd: Path | None = None) -> list[str]:
    if not base_sha or not head_sha or set(base_sha) == {"0"}:
        return []
    merge_base = subprocess.run(
        ["git", "merge-base", base_sha, head_sha],
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    if not merge_base:
        raise RuntimeError("unable to resolve merge-base for CI change scope")
    result = subprocess.run(
        ["git", "diff", "--no-renames", "--name-only", merge_base, head_sha, "--"],
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        raise SystemExit("usage: ci_docs_only.py BASE_SHA HEAD_SHA")
    base_sha, head_sha = argv[1:]
    try:
        paths = changed_paths(base_sha, head_sha, ROOT)
        if paths:
            module_ids = module_ids_for_diff(base_sha, head_sha, ROOT)
            packaged_resources = app_resource_sources_for_diff(base_sha, head_sha, ROOT)
        else:
            # Missing/unknown scope already routes every lane below; use the
            # checkout inventory only to keep reference classification defined.
            module_ids = discover_module_ids(ROOT)
            packaged_resources = current_app_resource_sources(ROOT)
        prefixes = executable_reference_prefixes(module_ids)
        scope = classify_scope(
            paths,
            reference_prefixes=prefixes,
            app_resource_sources=packaged_resources,
        )
    except (ModuleInventoryError, OSError, subprocess.SubprocessError) as error:
        print(f"ci scope: {error}", file=sys.stderr)
        return 2
    for key in ("docs_only", "needs_linux", "needs_macos", "needs_module"):
        print(f"{key}={'true' if scope[key] else 'false'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
