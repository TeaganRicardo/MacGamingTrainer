"""The PR selector is bounded by declared tests, and unknown diffs fail closed."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Tools"))
from select_macos_pr_tests import selected_tests

TESTS = {
    "test_multi_game_contexts.py",
    "test_reference_fixture_session_integration.py",
    "test_global_hotkey_routing.py",
    "test_hades_frontend.py",
    "test_hades2_view_state_flow.py",
    "test_build_signing_metadata_macos.py",
    "test_hades2_save_editor_frontend.py",
    "test_mapped_slider_interaction.py",
    "test_hades2_lldb_breakpoint_lifetime.py",
    "test_trainer_text_field_appearance.py",
    "test_trainer_search_field_appearance.py",
    "test_runtime_text_edit_completion.py",
    "test_viewport_feedback.py",
    "test_trainer_tool_windows.py",
}
SOURCES = {"hades": "Sources/Hades/", "hades2": "Sources/Hades2/"}

assert selected_tests([], TESTS, SOURCES) == sorted(TESTS)
assert selected_tests(["README.md"], TESTS, SOURCES) == []
assert selected_tests(["Backend/games/hades2/adapter.py"], TESTS, SOURCES) == []
for path in ("Sources/Hades2/Hades2View.swift", "Sources/Hades2/Hades2Model.swift"):
    assert selected_tests([path], TESTS, SOURCES) == sorted({
        "test_hades2_view_state_flow.py", "test_runtime_text_edit_completion.py", "test_multi_game_contexts.py",
    })
for path in ("Sources/Hades/HadesTrainerView.swift", "Sources/Hades/HadesWorkbenchNavigation.swift",
             "Sources/Hades/HadesModule.swift"):
    assert selected_tests([path], TESTS, SOURCES) == sorted({"test_hades_frontend.py", "test_multi_game_contexts.py"})
for path in ("Sources/Hades2/Views/Hades2HostActions.swift", "Sources/Hades2/Services/Hades2WorkbenchNavigation.swift",
             "Sources/Hades2/Hades2Module.swift"):
    assert selected_tests([path], TESTS, SOURCES) == sorted({"test_hades2_view_state_flow.py", "test_multi_game_contexts.py"})
assert selected_tests(["Sources/Hades/HadesBoonLifecycle.swift"], TESTS, SOURCES) == ["test_hades_frontend.py"]
assert selected_tests(["Sources/Hades2/Views/Hades2SaveEditorView.swift"], TESTS, SOURCES) == sorted({
    "test_hades2_view_state_flow.py", "test_hades2_save_editor_frontend.py",
})
assert selected_tests(["Sources/Core/Host/TrainerHost.swift"], TESTS, SOURCES) == sorted({
    "test_multi_game_contexts.py", "test_reference_fixture_session_integration.py", "test_global_hotkey_routing.py"
})
for path in ("Sources/Core/UI/TrainerSectionNavigation.swift", "Sources/Core/UI/TrainerSectionScroll.swift"):
    assert selected_tests([path], TESTS, SOURCES) == sorted({
        "test_multi_game_contexts.py", "test_reference_fixture_session_integration.py", "test_global_hotkey_routing.py"
    })
for path in ("Sources/Core/UI/Primitives/TrainerMappedSlider.swift", "Sources/Core/UI/Primitives/TrainerSliderMapping.swift"):
    assert selected_tests([path], TESTS, SOURCES) == sorted({
        "test_multi_game_contexts.py", "test_reference_fixture_session_integration.py",
        "test_global_hotkey_routing.py", "test_mapped_slider_interaction.py",
    })
for path in ("Sources/Core/UI/Primitives/TrainerTextField.swift", "Sources/Core/UI/Primitives/TrainerField.swift",
             "Sources/Core/UI/Components/TrainerResourceControls.swift"):
    assert selected_tests([path], TESTS, SOURCES) == sorted({
        "test_multi_game_contexts.py", "test_reference_fixture_session_integration.py", "test_global_hotkey_routing.py",
        "test_trainer_text_field_appearance.py", "test_runtime_text_edit_completion.py", "test_hades_frontend.py",
    })
assert selected_tests(["Sources/Core/UI/Components/TrainerSearchField.swift"], TESTS, SOURCES) == sorted({
    "test_multi_game_contexts.py", "test_reference_fixture_session_integration.py", "test_global_hotkey_routing.py",
    "test_trainer_search_field_appearance.py", "test_hades_frontend.py", "test_hades2_view_state_flow.py",
})
assert selected_tests(["tests/test_hades2_save_editor_frontend.py"], TESTS, SOURCES) == [
    "test_hades2_save_editor_frontend.py"
]
for path in (
    "tests/hades2_lldb_worker_support.py", "tests/hades2_lldb_fixture.py",
    "tests/hades2_debugserver_owner.py", "Tools/profile_hades2_operations.py",
):
    assert selected_tests([path], TESTS, SOURCES) == ["test_hades2_lldb_breakpoint_lifetime.py"]
assert selected_tests(["Tools/macos_test_dependencies.json"], TESTS, SOURCES) == sorted({
    "test_multi_game_contexts.py",
    "test_hades2_lldb_breakpoint_lifetime.py", "test_hades_frontend.py", "test_hades2_view_state_flow.py",
    "test_runtime_text_edit_completion.py", "test_trainer_text_field_appearance.py",
})
assert selected_tests(["tests/real_module_navigation_harness.py"], TESTS, SOURCES) == ["test_multi_game_contexts.py"]
for path in ("tests/management_ui_harness.py", "tests/visual_hierarchy_harness.py", "tests/disclosure_ui_harness.py", "tests/feedback_ui_harness.py", "tests/search_ui_harness.py", "tests/sheet_ui_harness.py"):
    assert selected_tests([path], TESTS, SOURCES) == sorted({
        "test_hades_frontend.py", "test_hades2_view_state_flow.py",
    })
assert selected_tests(["Sources/Core/UI/TrainerToolWindows.swift"], TESTS, SOURCES) == sorted({
    "test_multi_game_contexts.py", "test_reference_fixture_session_integration.py",
    "test_global_hotkey_routing.py", "test_trainer_tool_windows.py",
})
assert selected_tests(["tests/native_picker_harness.py"], TESTS, SOURCES) == sorted({
    "test_hades_frontend.py", "test_runtime_text_edit_completion.py", "test_trainer_text_field_appearance.py",
})
for path in (
    "Sources/Core/UI/TrainerMotion.swift",
    "Sources/Core/UI/TrainerWorkbenchSearch.swift",
    "Sources/Core/UI/Components/TrainerWorkbenchSearchField.swift",
    "Sources/Core/UI/Primitives/TrainerToggleControl.swift",
    "Sources/Core/UI/Components/TrainerFeatureControls.swift",
    "Sources/Core/UI/TrainerShell.swift",
    "Sources/Core/UI/StatusComponents.swift",
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
    assert selected_tests([path], TESTS, SOURCES) == sorted({
        "test_multi_game_contexts.py", "test_reference_fixture_session_integration.py",
        "test_global_hotkey_routing.py", "test_hades_frontend.py", "test_hades2_view_state_flow.py",
    })
assert selected_tests(["Sources/Core/UI/TrainerTheme.swift"], TESTS, SOURCES) == sorted({
    "test_multi_game_contexts.py", "test_reference_fixture_session_integration.py",
    "test_global_hotkey_routing.py", "test_hades_frontend.py", "test_hades2_view_state_flow.py",
    "test_trainer_text_field_appearance.py",
})
for path in (
    "Sources/Core/UI/TrainerFeedbackOverlay.swift", "Sources/Core/UI/TrainerFeedbackTiming.swift",
    "Sources/Core/UI/TrainerSidebar.swift", "Sources/Core/UI/Components/TrainerStatusControls.swift",
):
    assert selected_tests([path], TESTS, SOURCES) == sorted({
        "test_multi_game_contexts.py", "test_reference_fixture_session_integration.py",
        "test_global_hotkey_routing.py", "test_hades_frontend.py", "test_hades2_view_state_flow.py",
        "test_viewport_feedback.py",
    })
assert selected_tests(["tests/slider_ui_harness.py"], TESTS, SOURCES) == sorted({
    "test_hades_frontend.py", "test_hades2_view_state_flow.py",
})
assert selected_tests(["tests/test_debugserver_ownership.py"], TESTS, SOURCES) == []
assert selected_tests(["Tools/macos_only_tests.txt"], TESTS, SOURCES) == sorted(TESTS)
assert selected_tests(["tests/fixtures/swift/InMemoryDefaults.swift"], TESTS, SOURCES) == sorted(TESTS)
assert selected_tests(["Native/ProcessTimeWarp/ProcessTimeWarp.c"], TESTS, SOURCES) == [
    "test_build_signing_metadata_macos.py"
]
assert selected_tests(["Sources/FutureGame/SomeView.swift"], TESTS, SOURCES) == []
# Future modules without a named smoke test receive generic multi-context coverage.
assert selected_tests(["Sources/FutureGame/SomeView.swift"], TESTS, {
    **SOURCES, "future": "Sources/FutureGame/"
}) == ["test_multi_game_contexts.py"]

print("ci_pr_macos_selection_ok")
