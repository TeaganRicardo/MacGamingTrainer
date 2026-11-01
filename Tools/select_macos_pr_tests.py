#!/usr/bin/env python3
"""Choose a bounded macOS PR smoke suite; full coverage belongs to release dispatch.

The inventory is the single source for available macOS tests. Only a few shared
ownership boundaries are mapped here; new modules use convention-based smoke
selection and always retain the product compiler check.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from ci_docs_only import MACOS_TEST_DEPENDENCIES, ROOT, changed_paths, load_macos_only_tests
from module_inventory import discover_module_ids

SHARED_SMOKE = (
    "test_multi_game_contexts.py",
    "test_reference_fixture_session_integration.py",
    "test_global_hotkey_routing.py",
)
BUILD_SMOKE = "test_build_signing_metadata_macos.py"


def source_directories(root: Path = ROOT) -> dict[str, str]:
    result = {}
    for game_id in discover_module_ids(root):
        manifest = json.loads((root / "Backend/games" / game_id / "module.json").read_text(encoding="utf-8"))
        source = manifest.get("frontend", {}).get("sourceDirectory")
        if not isinstance(source, str) or not source.startswith("Sources/"):
            raise ValueError(f"{game_id}: missing frontend sourceDirectory")
        result[game_id] = source.rstrip("/") + "/"
    return result


def selected_tests(paths: list[str], tests: set[str], sources: dict[str, str]) -> list[str]:
    if not paths:
        return sorted(tests)  # Unknown change scope must never quietly skip tests.

    chosen: set[str] = set()
    for path in paths:
        chosen.update(name for name, dependencies in MACOS_TEST_DEPENDENCIES.items() if path in dependencies)
        if path.startswith("tests/") and path.endswith((".swift", ".c", ".h", ".m", ".mm", ".plist", ".so", ".dylib")):
            # These fixtures are shared across native behavior tests; a narrow
            # name match would miss consumers and provide false confidence.
            return sorted(tests)
        if path.startswith("tests/") and Path(path).name in tests:
            chosen.add(Path(path).name)
        if path.startswith("Sources/Core/") or path == "Sources/App.swift":
            chosen.update(SHARED_SMOKE)
        if path in ("Sources/Core/UI/Primitives/TrainerMappedSlider.swift", "Sources/Core/UI/Primitives/TrainerSliderMapping.swift"):
            chosen.add("test_mapped_slider_interaction.py")
        if path.startswith("ContractFixtures/reference_module/"):
            chosen.add("test_reference_fixture_session_integration.py")
        if path.startswith("Native/") or path == "build.sh":
            chosen.add(BUILD_SMOKE)
        if path in ("Tools/run_macos_checks.sh", "Tools/select_macos_pr_tests.py"):
            chosen.update(("test_multi_game_contexts.py", BUILD_SMOKE))
        if path == "Tools/macos_only_tests.txt":
            return sorted(tests)
        for game_id, source_prefix in sources.items():
            if not path.startswith(source_prefix):
                continue
            smoke = next((name for name in (
                f"test_{game_id}_view_state_flow.py",
                f"test_{game_id}_frontend.py",
            ) if name in tests), "test_multi_game_contexts.py")
            chosen.add(smoke)
    missing = chosen - tests
    if missing:
        raise ValueError(f"macOS smoke tests missing from inventory: {sorted(missing)}")
    return sorted(chosen)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        raise SystemExit("usage: select_macos_pr_tests.py BASE_SHA HEAD_SHA")
    try:
        paths = changed_paths(argv[1], argv[2])
        names = selected_tests(paths, load_macos_only_tests(), source_directories())
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"macOS PR selection failed: {exc}", file=sys.stderr)
        return 2
    print("\n".join(names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
