#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXECUTABLE_REFERENCE_PREFIXES = ("docs/reference/hades2/",)
PORTABLE_TOOL_PATHS = {
    "Tools/check_runtime_revision.py",
    "Tools/discover_linux_tests.py",
    "Tools/run_linux_checks.sh",
}
MODULE_EXACT_PATHS = {
    ".github/workflows/module-build-matrix.yml",
    "ACTIVE_GAME_ID",
    "Backend/core/module_manifest.py",
    "Backend/games/__init__.py",
    "Info.plist",
    "Sources/App.swift",
    "Tools/ci_docs_only.py",
    "Tools/clean_signing_metadata.py",
    "Tools/generate_game_binding.py",
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


def is_executable_reference_data(path: str) -> bool:
    return path.startswith(EXECUTABLE_REFERENCE_PREFIXES) and not path.endswith(".md")


def is_docs_only(paths: list[str]) -> bool:
    normalized = [path.strip() for path in paths if path.strip()]
    if not normalized:
        return False
    return all(
        (path.startswith("docs/") or path.endswith(".md"))
        and not is_executable_reference_data(path)
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
    if path in MODULE_EXACT_PATHS or path.startswith(MODULE_PREFIXES):
        return True
    return path.startswith("Backend/games/") and path.endswith("/module.json")


def is_linux_portable_only(path: str, macos_only_tests: set[str]) -> bool:
    if path.startswith("Backend/"):
        return not path.endswith("/module.json") and not path.endswith(".plist")
    if path.startswith("tests/"):
        return Path(path).name not in macos_only_tests
    if is_executable_reference_data(path):
        return not path.endswith("/ui_terminology.json")
    return path in PORTABLE_TOOL_PATHS


def classify_scope(
    paths: list[str],
    *,
    macos_only_tests: set[str] | None = None,
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

    docs_only = is_docs_only(normalized)
    if docs_only:
        return {
            "docs_only": True,
            "needs_linux": False,
            "needs_macos": False,
            "needs_module": False,
        }

    macos_only = macos_only_tests if macos_only_tests is not None else load_macos_only_tests()
    needs_module = any(needs_module_build_for_path(path) for path in normalized)
    needs_macos = needs_module or any(
        not is_linux_portable_only(path, macos_only)
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
    scope = classify_scope(changed_paths(argv[1], argv[2]))
    for key in ("docs_only", "needs_linux", "needs_macos", "needs_module"):
        print(f"{key}={'true' if scope[key] else 'false'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
