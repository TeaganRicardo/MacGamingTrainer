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

from ci_docs_only import (
    MACOS_TEST_DEPENDENCIES, MACOS_TEST_DEPENDENCIES_PATH,
    ROOT, changed_paths, load_macos_only_tests,
)
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
        if path == MACOS_TEST_DEPENDENCIES_PATH:
            chosen.update(MACOS_TEST_DEPENDENCIES)
        chosen.update(name for name, dependencies in MACOS_TEST_DEPENDENCIES.items() if path in dependencies)
        if path.startswith("tests/") and path.endswith((".swift", ".c", ".h", ".m", ".mm", ".plist", ".so", ".dylib")):
            # These fixtures are shared across native behavior tests; a narrow
            # name match would miss consumers and provide false confidence.
            return sorted(tests)
        if path.startswith("tests/") and Path(path).name in tests:
            chosen.add(Path(path).name)
        if path.startswith("Sources/Core/") or path == "Sources/App.swift":
            chosen.update(SHARED_SMOKE)
        if path in (
            "Sources/Hades/HadesTrainerView.swift", "Sources/Hades/HadesWorkbenchNavigation.swift",
            "Sources/Hades/HadesModule.swift", "Sources/Hades2/Hades2View.swift",
            "Sources/Hades2/Views/Hades2HostActions.swift", "Sources/Hades2/Services/Hades2WorkbenchNavigation.swift",
            "Sources/Hades2/Hades2Module.swift", "Sources/Hades2/Hades2Model.swift",
        ):
            # These adapters own the section IDs, reveal handlers and native
            # targets exercised together by the real two-module Host journey.
            chosen.add("test_multi_game_contexts.py")
        if path in ("Sources/Core/UI/Primitives/TrainerMappedSlider.swift", "Sources/Core/UI/Primitives/TrainerSliderMapping.swift"):
            chosen.add("test_mapped_slider_interaction.py")
        if path in (
            "Sources/Core/UI/Primitives/TrainerTextField.swift", "Sources/Core/UI/Primitives/TrainerField.swift",
            "Sources/Core/UI/Components/TrainerResourceControls.swift",
        ):
            chosen.update(("test_trainer_text_field_appearance.py", "test_runtime_text_edit_completion.py", "test_hades_frontend.py"))
        if path == "Sources/Core/UI/TrainerTheme.swift":
            chosen.add("test_trainer_text_field_appearance.py")
        if path == "Sources/Core/UI/Components/TrainerSearchField.swift":
            chosen.add("test_trainer_search_field_appearance.py")
        if path in ("Sources/Hades2/Hades2View.swift", "Sources/Hades2/Hades2Model.swift"):
            chosen.add("test_runtime_text_edit_completion.py")
        if path in (
            "Sources/Core/UI/TrainerMotion.swift",
            "Sources/Core/UI/TrainerWorkbenchSearch.swift",
            "Sources/Core/UI/Components/TrainerSearchField.swift",
            "Sources/Core/UI/Components/TrainerWorkbenchSearchField.swift",
            "Sources/Core/UI/Primitives/TrainerToggleControl.swift",
            "Sources/Core/UI/Components/TrainerFeatureControls.swift",
            "Sources/Core/UI/TrainerTheme.swift", "Sources/Core/UI/TrainerShell.swift",
            "Sources/Core/UI/TrainerSidebar.swift", "Sources/Core/UI/StatusComponents.swift",
            "Sources/Core/UI/Primitives/TrainerRow.swift", "Sources/Core/UI/Primitives/TrainerCard.swift",
            "Sources/Core/UI/Components/TrainerDisclosure.swift",
            "Sources/Core/UI/Components/TrainerMetricGrid.swift",
            "Sources/Core/UI/Components/TrainerListControls.swift",
            "Sources/Core/UI/Components/TrainerSheetScaffold.swift",
            "Sources/Core/UI/Components/TrainerSheetLifetime.swift",
            "Sources/Core/UI/Components/TrainerProfileManagerView.swift",
            "Sources/Core/UI/Components/TrainerDiagnosticsView.swift",
            "Sources/Core/UI/Components/TrainerShortcutSettingsView.swift",
        ):
            chosen.update(("test_hades_frontend.py", "test_hades2_view_state_flow.py"))
        if path in ("Sources/Core/UI/TrainerFeedbackOverlay.swift", "Sources/Core/UI/TrainerFeedbackTiming.swift",
                    "Sources/Core/UI/TrainerSidebar.swift", "Sources/Core/UI/Components/TrainerStatusControls.swift"):
            chosen.update(("test_viewport_feedback.py", "test_hades_frontend.py", "test_hades2_view_state_flow.py"))
        if path == "Sources/Core/UI/TrainerToolWindows.swift":
            chosen.add("test_trainer_tool_windows.py")
        if path.startswith("ContractFixtures/reference_module/"):
            chosen.add("test_reference_fixture_session_integration.py")
        if path in ("Sources/Hades2/Views/Hades2SaveEditorView.swift", "Sources/Hades2/Hades2SaveEditorModel.swift"):
            chosen.add("test_hades2_save_editor_frontend.py")
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
