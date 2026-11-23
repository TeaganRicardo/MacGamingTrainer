#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path, PurePosixPath

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
from test_inputs import MACOS_RUNNER_PATHS, affected_tests, is_native_fixture, load_macos_test_dependencies
from test_inventory import load_macos_only_tests

# Explicit portable Tools/ scripts and config files that never compile, package,
# sign, or select toolchains for the distributed App. Game-owned tooling under
# Tools/games/<id>/ and CI prerequisite installers under Tools/ci_prerequisites/
# are also portable unless a macOS test declares them; any other Tools/ file
# fails closed to the macOS build.
PORTABLE_TOOL_PATHS = frozenset({
    "pyproject.toml",
    "Tools/check_runtime_revision.py",
    "Tools/ci_docs_only.py",
    "Tools/discover_linux_tests.py",
    # The mutation audit runs only in Build 2 macOS convergence; a PR that edits
    # it has no macOS work to verify (tests/test_mutation_gate_contract.py is
    # portable).
    "Tools/mutation_gate.py",
    "Tools/python_static_requirements.txt",
    "Tools/release_tag.py",
    "Tools/run_linux_checks.sh",
    "Tools/summarize_macos_coverage.py",
    *MACOS_RUNNER_PATHS,
})
# Only native/module composition boundaries need the reference-fixture compiler lane.
# Pure Backend implementation and game-owned Swift changes are verified by their
# owning lanes; invoking a second macOS app build adds no isolation evidence.
MODULE_EXACT_PATHS = {
    ".github/workflows/module-build-matrix.yml",
    ".python-version",
    "app.json",
    "Tools/build_module_native.py",
    "Tools/clean_signing_metadata.py",
    "Tools/generate_game_binding.py",
    "Tools/generate_module_commands.py",
    "Tools/macos_toolchain_identity.py",
    "Tools/module_inventory.py",
    "Tools/module_support.py",
    "Tools/package_app.py",
    "Tools/product_support.py",
    "Tools/publish_module_build.py",
    "Tools/supported_build.py",
    "Tools/swift_module_layout.py",
    "Tools/verify_module_build.py",
    "Tools/python_runtime.json",
    "build.sh",
}
MODULE_PREFIXES = (
    "ContractFixtures/reference_module/",
    "Sources/Core/",
    "Native/",
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


def needs_module_build_for_path(path: str) -> bool:
    return (
        path in MODULE_EXACT_PATHS
        or path == "Sources/App.swift"
        or path.startswith(MODULE_PREFIXES)
    )


def needs_module_full_build_for_path(path: str) -> bool:
    if path.startswith("Sources/Core/") and path.endswith(".swift"):
        return False
    return needs_module_build_for_path(path)


def _is_portable_input(
    path: str,
    macos_only_tests: set[str],
    reference_prefixes: tuple[str, ...] | None,
    app_resource_sources: tuple[str, ...],
) -> bool:
    """Whether the file itself is consumed only by portable code."""
    if path.endswith(".md"):
        # Documentation never compiles, links, signs or packages the product.
        # Treating it as a build input forced the full unified build onto every
        # mixed docs+code pull request.
        return True
    if path.startswith("Backend/"):
        # Portable Backend source is explicitly typed. An unrecognized or
        # native input must not silently become Linux-only.
        if "/native/" in path or path.endswith(("module.json", ".plist")):
            return False
        return path.endswith((".py", ".lua", ".json", ".csv", ".txt", ".md"))
    if path.startswith("tests/"):
        # Shared Swift/native fixtures are inputs to macOS behavioral harnesses.
        return not is_native_fixture(path) and path.removeprefix("tests/") not in macos_only_tests
    if path.startswith(".github/workflows/"):
        # A change to Build 2's own execution recipe must exercise the real
        # macOS product; the separate module-matrix workflow owns its lane.
        return path != ".github/workflows/build2-macos.yml"
    if path in PORTABLE_TOOL_PATHS:
        return True
    parts = PurePosixPath(path).parts
    if len(parts) >= 4 and parts[:2] == ("Tools", "games"):
        return True
    if len(parts) == 3 and parts[:2] == ("Tools", "ci_prerequisites") and path.endswith(".sh"):
        return True
    if path.startswith("Tools/"):
        return False
    if is_executable_reference_data(path, reference_prefixes):
        return path not in app_resource_sources
    return False


def needs_build_for_path(
    path: str,
    macos_only_tests: set[str],
    reference_prefixes: tuple[str, ...] | None = None,
    app_resource_sources: tuple[str, ...] = (),
) -> bool:
    # Workflow files describe CI orchestration. Their own changed job graph is
    # exercised by the PR workflow, while Linux contracts pin the product-build
    # invocations. Product recipe inputs remain owned by build/tool paths below.
    if path.startswith(("tests/", ".github/workflows/")):
        return False
    # Declaring a file as a native-test dependency selects that test; the file
    # remains whatever product input it is.
    return needs_module_build_for_path(path) or not _is_portable_input(
        path, macos_only_tests, reference_prefixes, app_resource_sources
    )


def needs_full_build_for_path(
    path: str,
    macos_only_tests: set[str],
    reference_prefixes: tuple[str, ...] | None = None,
    app_resource_sources: tuple[str, ...] = (),
) -> bool:
    # Ordinary game/Core Swift sources share the product typecheck preflight.
    # The entrypoint, native/link inputs, manifests, packaged resources and
    # build tooling must still compile/link/sign the actual App on every PR.
    if path.startswith("Sources/") and path.endswith(".swift") and path != "Sources/App.swift":
        return False
    return needs_build_for_path(
        path, macos_only_tests, reference_prefixes, app_resource_sources
    )


def classify_scope(
    paths: list[str],
    *,
    root: Path = ROOT,
    macos_only_tests: set[str] | None = None,
    test_dependencies: dict[str, frozenset[str]] | None = None,
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
            "needs_module_full_build": True,
            "needs_build": True,
            "needs_full_build": True,
        }

    if reference_prefixes is None:
        reference_prefixes = current_reference_prefixes(root)
    documentation = is_docs_only(normalized, reference_prefixes=reference_prefixes)
    macos_only = macos_only_tests if macos_only_tests is not None else load_macos_only_tests(root)
    packaged_resources = (
        app_resource_sources
        if app_resource_sources is not None
        else current_app_resource_sources(root)
    )
    needs_module = not documentation and any(needs_module_build_for_path(path) for path in normalized)
    needs_macos = not documentation and any(
        (needs_module_build_for_path(path) and not path.startswith(".github/workflows/"))
        or not _is_portable_input(
            path,
            macos_only,
            reference_prefixes,
            packaged_resources,
        )
        for path in normalized
    )
    if not needs_macos:
        dependencies = test_dependencies
        if dependencies is None:
            dependencies = load_macos_test_dependencies(root, changed_paths=normalized)
        needs_macos = bool(affected_tests(normalized, dependencies))

    needs_module_full_build = not documentation and any(
        needs_module_full_build_for_path(path) for path in normalized
    )

    return {
        "docs_only": documentation and not needs_macos,
        "needs_linux": True,
        "needs_macos": needs_macos,
        "needs_module": needs_module,
        "needs_module_full_build": needs_module_full_build,
        "needs_build": not documentation and any(
            needs_build_for_path(path, macos_only, reference_prefixes, packaged_resources)
            for path in normalized
        ),
        "needs_full_build": not documentation and any(
            needs_full_build_for_path(path, macos_only, reference_prefixes, packaged_resources)
            for path in normalized
        ),
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
    except (ModuleInventoryError, OSError, SyntaxError, ValueError, subprocess.SubprocessError) as error:
        print(f"ci scope: {error}", file=sys.stderr)
        return 2
    for key in (
        "docs_only",
        "needs_linux",
        "needs_macos",
        "needs_module",
        "needs_module_full_build",
        "needs_build",
        "needs_full_build",
    ):
        print(f"{key}={'true' if scope[key] else 'false'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
