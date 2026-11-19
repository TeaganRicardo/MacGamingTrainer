#!/usr/bin/env python3
"""Choose a bounded macOS PR smoke suite; full coverage belongs to release dispatch.

The inventory is the single source for available macOS tests. Only a few shared
ownership boundaries are mapped here; new modules use convention-based smoke
selection and always retain the product compiler check.
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from ci_docs_only import (
    MACOS_TEST_DEPENDENCIES, MACOS_TEST_DEPENDENCIES_PATH,
    ROOT, changed_paths, load_macos_only_tests,
)
from module_inventory import discover_module_ids

SHARED_SMOKE = (
    "test_multi_game_contexts.py",
    "test_multi_game_context_state.py",
    "test_reference_fixture_session_integration.py",
    "test_global_hotkey_routing.py",
)
BUILD_SMOKE = "test_build_signing_metadata_macos.py"
# Core Save tests share TrainerSaveManagerModel/Validator/ReplyCoordinator/Types.
_CORE_SAVE_MANAGER_TESTS = (
    "test_core_save_batch_delete_round20.py",
    "test_core_save_manager_lifecycle_u01_u02.py",
    "test_core_save_rename_completion_round24.py",
)
_CORE_SHARED_UI_TESTS = (
    "test_hades_frontend.py",
    "test_hades2_view_state_flow.py",
)
_TEXT_INPUT_TESTS = (
    "test_trainer_text_field_appearance.py",
    "test_runtime_text_edit_completion.py",
    "test_hades_frontend.py",
)
_HADES2_SAVE_EDITOR_TESTS = (
    "test_hades2_save_editor_frontend.py",
    "test_hades2_save_editor_player_journey.py",
    "test_hades2_save_record_frontend.py",
    "test_hades2_save_container_frontend.py",
    "test_hades2_advanced_save_frontend.py",
)
_HADES2_MANAGEMENT_TESTS = (
    "test_hades2_repeated_actions_frontend.py",
)

# Explicit ownership table: keeps specialized macOS suites reachable from the
# exact production files they exercise without widening unrelated PRs.
EXACT_PATH_TESTS: dict[str, tuple[str, ...]] = {
    # Shared Core Host/Runtime behavior owners
    "Sources/Core/Host/TrainerLocalization.swift": ("test_host_localization_behavior.py",),
    "Sources/Core/Host/TrainerApplicationStartup.swift": ("test_host_target_ownership.py",),
    "Sources/Core/Host/TrainerGameContext.swift": ("test_host_target_ownership.py",),
    "Sources/Core/Host/TrainerTargetOwnership.swift": ("test_host_target_ownership.py",),
    "Sources/Core/Runtime/TrainerTargetProcessMonitor.swift": ("test_host_target_ownership.py",),
    "Sources/Core/Runtime/TrainerLogSink.swift": ("test_trainer_log_session_lifecycle.py",),
    "Sources/Core/Runtime/BackendProcess.swift": ("test_backend_stderr_liveness.py",),
    "Sources/Core/Runtime/BackendClient.swift": ("test_core_save_manager_lifecycle_u01_u02.py",),
    "Sources/Core/Runtime/TrainerBackendSession.swift": ("test_core_save_manager_lifecycle_u01_u02.py",),
    "Sources/Core/Host/TrainerConnectionPolicy.swift": ("test_hades2_run_log_watcher.py",),

    # Shared Core Save management owners
    "Sources/Core/Save/TrainerSaveEditorReplyCoordinator.swift": _CORE_SAVE_MANAGER_TESTS,
    "Sources/Core/Save/TrainerSavePathValidator.swift": _CORE_SAVE_MANAGER_TESTS,
    "Sources/Core/Save/TrainerSaveTypes.swift": _CORE_SAVE_MANAGER_TESTS,
    "Sources/Core/Save/TrainerSaveManagerModel.swift": (
        *_CORE_SAVE_MANAGER_TESTS,
        "test_core_save_retention_controls.py",
    ),
    "Sources/Core/Save/TrainerSaveManagerView.swift": ("test_core_save_retention_controls.py",),
    "Sources/Core/Save/TrainerSaveRetentionSettings.swift": ("test_core_save_retention_controls.py",),

    # Shared Core UI owners
    "Sources/Core/UI/Primitives/TrainerMappedSlider.swift": ("test_mapped_slider_interaction.py",),
    "Sources/Core/UI/Primitives/TrainerSliderMapping.swift": ("test_mapped_slider_interaction.py",),
    "Sources/Core/UI/Primitives/TrainerTextField.swift": _TEXT_INPUT_TESTS,
    "Sources/Core/UI/Primitives/TrainerField.swift": _TEXT_INPUT_TESTS,
    "Sources/Core/UI/Components/TrainerResourceControls.swift": _TEXT_INPUT_TESTS,
    "Sources/Core/UI/TrainerTheme.swift": ("test_trainer_text_field_appearance.py", *_CORE_SHARED_UI_TESTS),
    "Sources/Core/UI/Components/TrainerSearchField.swift": ("test_trainer_search_field_appearance.py", *_CORE_SHARED_UI_TESTS),
    "Sources/Core/UI/TrainerMotion.swift": _CORE_SHARED_UI_TESTS,
    "Sources/Core/UI/TrainerWorkbenchSearch.swift": _CORE_SHARED_UI_TESTS,
    "Sources/Core/UI/Components/TrainerWorkbenchSearchField.swift": _CORE_SHARED_UI_TESTS,
    "Sources/Core/UI/Primitives/TrainerToggleControl.swift": _CORE_SHARED_UI_TESTS,
    "Sources/Core/UI/Components/TrainerFeatureControls.swift": _CORE_SHARED_UI_TESTS,
    "Sources/Core/UI/TrainerShell.swift": _CORE_SHARED_UI_TESTS,
    "Sources/Core/UI/StatusComponents.swift": (*_CORE_SHARED_UI_TESTS, "test_cross_module_geometry_macos.py"),
    "Sources/Core/UI/Primitives/TrainerRow.swift": (*_CORE_SHARED_UI_TESTS, "test_cross_module_geometry_macos.py"),
    "Sources/Core/UI/Primitives/TrainerCard.swift": (*_CORE_SHARED_UI_TESTS, "test_cross_module_geometry_macos.py"),
    "Sources/Core/UI/Components/TrainerDisclosure.swift": _CORE_SHARED_UI_TESTS,
    "Sources/Core/UI/Components/TrainerMetricGrid.swift": (*_CORE_SHARED_UI_TESTS, "test_cross_module_geometry_macos.py"),
    "Sources/Core/UI/Components/TrainerStatControls.swift": (*_CORE_SHARED_UI_TESTS, "test_cross_module_geometry_macos.py"),
    "Sources/Core/UI/Components/TrainerListControls.swift": _CORE_SHARED_UI_TESTS,
    # Rendered owners of shortcut badges, picker-action rows and shortcut capture.
    "Sources/Core/UI/Primitives/TrainerBadge.swift": _CORE_SHARED_UI_TESTS,
    "Sources/Core/UI/TrainerPickerActionLayout.swift": _CORE_SHARED_UI_TESTS,
    "Sources/Core/UI/Components/TrainerDualPickerActionRow.swift": _CORE_SHARED_UI_TESTS,
    "Sources/Core/Input/TrainerShortcutCapture.swift": _CORE_SHARED_UI_TESTS,
    "Sources/Core/UI/Components/TrainerSheetScaffold.swift": (
        *_CORE_SHARED_UI_TESTS,
        "test_hades_save_editor_frontend.py",
        "test_hades2_advanced_save_frontend.py",
    ),
    "Sources/Core/UI/Components/TrainerSheetLifetime.swift": _CORE_SHARED_UI_TESTS,
    "Sources/Core/UI/Components/TrainerSaveEditorShell.swift": (
        "test_hades_save_editor_frontend.py",
        "test_hades2_save_editor_frontend.py",
    ),
    "Sources/Core/UI/Components/TrainerProfileManagerView.swift": _CORE_SHARED_UI_TESTS,
    "Sources/Core/UI/Components/TrainerDiagnosticsView.swift": _CORE_SHARED_UI_TESTS,
    "Sources/Core/UI/Components/TrainerShortcutSettingsView.swift": _CORE_SHARED_UI_TESTS,
    "Sources/Core/UI/TrainerFeedbackOverlay.swift": ("test_viewport_feedback.py", *_CORE_SHARED_UI_TESTS),
    "Sources/Core/UI/TrainerFeedbackTiming.swift": ("test_viewport_feedback.py", *_CORE_SHARED_UI_TESTS),
    "Sources/Core/UI/TrainerSidebar.swift": ("test_viewport_feedback.py", *_CORE_SHARED_UI_TESTS),
    "Sources/Core/UI/Components/TrainerStatusControls.swift": ("test_viewport_feedback.py", *_CORE_SHARED_UI_TESTS),
    "Sources/Core/UI/TrainerToolWindows.swift": ("test_trainer_tool_windows.py",),

    # Two-module Host & reveal owners
    "Sources/Hades/HadesTrainerView.swift": ("test_multi_game_contexts.py", "test_cross_module_geometry_macos.py"),
    "Sources/Hades/HadesSaveEditorView.swift": ("test_hades_save_editor_frontend.py",),
    "Sources/Hades/HadesSaveEditorModel.swift": ("test_hades_save_editor_frontend.py",),
    "Sources/Hades/HadesTypes.swift": ("test_hades_shortcut_semantics.py",),
    "Sources/Hades/HadesRoomsPanel.swift": ("test_hades_shortcut_semantics.py",),
    "Sources/Hades/HadesWorkbenchNavigation.swift": ("test_multi_game_contexts.py", "test_hades_shortcut_semantics.py"),
    "Sources/Hades/HadesModule.swift": ("test_multi_game_contexts.py", "test_hades_shortcut_semantics.py"),
    "Sources/Hades2/Hades2Module.swift": ("test_multi_game_contexts.py",),
    "Sources/Hades2/Services/Hades2WorkbenchNavigation.swift": ("test_multi_game_contexts.py",),
    "Sources/Hades2/Hades2View.swift": ("test_multi_game_contexts.py", "test_runtime_text_edit_completion.py", "test_cross_module_geometry_macos.py"),
    "Sources/Hades2/Hades2Model.swift": (
        "test_multi_game_contexts.py",
        "test_runtime_text_edit_completion.py",
        "test_hades2_backend_state_cleanup.py",
    ),
    "Sources/Hades2/Hades2BackendState.swift": ("test_hades2_backend_state_cleanup.py",),
    "Sources/Hades2/Hades2API.swift": ("test_hades2_backend_state_cleanup.py",),
    "Sources/Hades2/Hades2Types.swift": ("test_hades2_backend_state_cleanup.py",),

    # Hades II specialized views & services
    "Sources/Hades2/Services/Hades2RunLogWatcher.swift": ("test_hades2_run_log_watcher.py",),
    "Sources/Hades2/Services/Hades2RunLogRefreshGate.swift": ("test_hades2_run_log_watcher.py",),
    "Sources/Hades2/Views/Hades2ChaosGatePanel.swift": ("test_hades2_chaos_gate_frontend.py",),
    "Sources/Hades2/Views/Hades2GatheringPanel.swift": ("test_hades2_gathering_frontend.py",),
    "Sources/Hades2/Views/Hades2OccurrenceSetting.swift": (
        "test_hades2_chaos_gate_frontend.py",
        "test_hades2_gathering_frontend.py",
    ),
    "Sources/Hades2/Views/Hades2BoonRarityPanel.swift": ("test_hades2_force_enable_rerolls_frontend.py",),
    "Sources/Hades2/Presentation/Hades2FeaturePresentation.swift": (
        "test_hades2_chaos_gate_frontend.py",
        "test_hades2_gathering_frontend.py",
        "test_hades2_force_enable_rerolls_frontend.py",
    ),
    "Sources/Hades2/Generated/Hades2Feature.generated.swift": (
        "test_hades2_chaos_gate_frontend.py",
        "test_hades2_gathering_frontend.py",
        "test_hades2_force_enable_rerolls_frontend.py",
    ),
    "Sources/Hades2/Views/Hades2ManagementViews.swift": _HADES2_MANAGEMENT_TESTS,
    "Sources/Hades2/Services/Hades2ManagementActions.swift": _HADES2_MANAGEMENT_TESTS,
    "Sources/Hades2/Views/Hades2OperationFeedback.swift": _HADES2_MANAGEMENT_TESTS,
    "Sources/Hades2/Views/Hades2HostActions.swift": (
        "test_multi_game_contexts.py",
        *_HADES2_MANAGEMENT_TESTS,
    ),
    "Sources/Hades2/Generated/Hades2Command.generated.swift": _HADES2_MANAGEMENT_TESTS,
    "Sources/Hades2/Views/Hades2SaveEditorView.swift": _HADES2_SAVE_EDITOR_TESTS,
    "Sources/Hades2/Hades2SaveEditorModel.swift": _HADES2_SAVE_EDITOR_TESTS,
    "Sources/Hades2/Hades2SaveAdvancedValue.swift": ("test_hades2_advanced_save_frontend.py",),
    "Sources/Hades2/Views/Hades2SaveAdvancedValueView.swift": ("test_hades2_advanced_save_frontend.py",),
    "Sources/Hades2/Views/Hades2SaveEditorEntityGrouping.swift": ("test_hades2_save_container_frontend.py",),

    # Backend, native, build & workflow smoke owners
    "Backend/games/hades/adapter.py": ("test_hades_process_identity_macos.py",),
    "tests/test_native_effect_query.py": ("test_native_effect_query_macos.py",),
    "build.sh": (BUILD_SMOKE,),
    "Tools/build_module_native.py": (BUILD_SMOKE,),
    "Tools/macos_toolchain_identity.py": (BUILD_SMOKE,),
    "Tools/verify_module_build.py": (BUILD_SMOKE,),
    "Tools/write_build_provenance.py": (BUILD_SMOKE,),
    "Tools/verify_build_provenance.py": (BUILD_SMOKE,),
    "Backend/games/hades/trainer-entitlements.plist": (BUILD_SMOKE,),
    "Backend/games/hades2/trainer-entitlements.plist": (BUILD_SMOKE,),
    "docs/reference/hades2/1.143476-25481925/ui_terminology.json": ("test_hades2_model_flow.py",),
    "Tools/generate_game_binding.py": ("test_hades2_model_flow.py", "test_reference_fixture_session_integration.py"),
    # Swift test harnesses compile the module layout this owns.
    "Tools/product_support.py": ("test_hades2_model_flow.py", "test_reference_fixture_session_integration.py"),
    "Tools/module_support.py": ("test_multi_game_context_state.py", "test_reference_fixture_session_integration.py"),
    "Tools/resident_runtime.py": ("test_multi_game_context_state.py", "test_hades2_model_flow.py"),
    "Tools/supported_build.py": ("test_multi_game_context_state.py", "test_hades2_model_flow.py"),
    "Tools/run_macos_checks.sh": ("test_multi_game_context_state.py", BUILD_SMOKE),
    "Tools/select_macos_pr_tests.py": ("test_multi_game_context_state.py", BUILD_SMOKE),
    ".github/workflows/build2-macos.yml": (
        BUILD_SMOKE,
        "test_host_localization_behavior.py",
        "test_native_effect_query_macos.py",
    ),
}

PREFIX_TESTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Resources/Localization/", ("test_host_localization_behavior.py",)),
    ("Sources/Core/Save/", ("test_core_save_manager_lifecycle_u01_u02.py",)),
    ("ContractFixtures/reference_module/", ("test_reference_fixture_session_integration.py",)),
    ("Backend/games/hades2/native/", ("test_native_effect_query_macos.py",)),
    ("Native/", (BUILD_SMOKE,)),
)

# Journeys that assert native focus, key-window and foreground activation state.
# A hosted runner cannot guarantee that a background test process becomes the
# active application, and macOS activation is cooperative: the wait then expires
# even though the product is correct. They stay in the convergence inventory and
# run against an exact SHA there (explicit dispatch, and nightly on main);
# gating every PR on them only produced non-deterministic red results.
@dataclass(frozen=True)
class Deferral:
    """Why a native journey is absent from the PR lane, and who verifies it."""

    reason: str
    verification_owner: str


CONVERGENCE_OWNER = "Build 2 macOS convergence: workflow_dispatch on the exact SHA, and nightly on main"

PR_DEFERRED: dict[str, Deferral] = {
    "test_hades2_view_state_flow.py": Deferral(
        reason="asserts native focus, key-window and foreground activation",
        verification_owner=CONVERGENCE_OWNER,
    ),
    "test_multi_game_contexts.py": Deferral(
        reason="drives two real module adapters through foreground activation",
        verification_owner=CONVERGENCE_OWNER,
    ),
    "test_runtime_text_edit_completion.py": Deferral(
        reason="requires a focused native field editor in the foreground",
        verification_owner=CONVERGENCE_OWNER,
    ),
}


def source_directories(root: Path = ROOT) -> dict[str, str]:
    result = {}
    for game_id in discover_module_ids(root):
        manifest = json.loads((root / "Backend/games" / game_id / "module.json").read_text(encoding="utf-8"))
        source = manifest.get("frontend", {}).get("sourceDirectory")
        if not isinstance(source, str) or not source.startswith("Sources/"):
            raise ValueError(f"{game_id}: missing frontend sourceDirectory")
        result[game_id] = source.rstrip("/") + "/"
    return result


def metadata_test_changes(base_sha: str, head_sha: str, paths: list[str],
                          cwd: Path = ROOT) -> dict[str, set[str]]:
    metadata_paths = {"Tools/macos_only_tests.txt", MACOS_TEST_DEPENDENCIES_PATH} & set(paths)
    if not metadata_paths:
        return {}
    base = subprocess.check_output(["git", "merge-base", base_sha, head_sha], cwd=cwd, text=True).strip()
    changes = {}
    for path in sorted(metadata_paths):
        before, after = (subprocess.check_output(["git", "show", f"{ref}:{path}"], cwd=cwd, text=True)
                         for ref in (base, head_sha))
        if path == "Tools/macos_only_tests.txt":
            changes[path] = set(after.split()) - set(before.split())
        else:
            old, new = json.loads(before), json.loads(after)
            changes[path] = {name for name in old.keys() | new.keys() if old.get(name) != new.get(name)}
    return changes


def selected_tests(paths: list[str], tests: set[str], sources: dict[str, str],
                   metadata_changes: dict[str, set[str]] | None = None) -> list[str]:
    if not paths:
        return sorted(tests)  # Unknown change scope must never quietly skip tests.

    chosen: set[str] = set()
    for path in paths:
        if path == MACOS_TEST_DEPENDENCIES_PATH:
            changed = metadata_changes.get(path) if metadata_changes is not None else None
            chosen.update(MACOS_TEST_DEPENDENCIES if changed is None else changed & tests)
        chosen.update(name for name, dependencies in MACOS_TEST_DEPENDENCIES.items() if path in dependencies)
        if path.startswith("tests/") and path.endswith((".swift", ".c", ".h", ".m", ".mm", ".plist", ".so", ".dylib")):
            # These fixtures are shared across native behavior tests; a narrow
            # name match would miss consumers and provide false confidence.
            return sorted(tests)
        if path.startswith("tests/") and Path(path).name in tests:
            chosen.add(Path(path).name)
        if path.startswith("Sources/Core/") or path == "Sources/App.swift":
            chosen.update(SHARED_SMOKE)
        if path in EXACT_PATH_TESTS:
            chosen.update(EXACT_PATH_TESTS[path])
        for prefix, mapped in PREFIX_TESTS:
            if path.startswith(prefix):
                chosen.update(mapped)
        if path == "Tools/macos_only_tests.txt":
            changed = metadata_changes.get(path) if metadata_changes is not None else None
            if changed is None:
                return sorted(tests)
            chosen.update(changed)
        for game_id, source_prefix in sources.items():
            if not path.startswith(source_prefix):
                continue
            module_tests = {name for name in (
                f"test_{game_id}_model_flow.py",
                f"test_{game_id}_view_state_flow.py",
                f"test_{game_id}_frontend.py",
            ) if name in tests}
            if not module_tests:
                raise ValueError(f"{game_id}: no macOS behavior smoke entry in the inventory")
            if not module_tests - PR_DEFERRED.keys():
                raise ValueError(f"{game_id}: every module behavior smoke entry is deferred; declare a stable PR owner")
            chosen.update(module_tests)
    missing = chosen - tests
    if missing:
        raise ValueError(f"macOS smoke tests missing from inventory: {sorted(missing)}")
    return sorted(chosen)


def smoke_selection(paths: list[str], tests: set[str], sources: dict[str, str],
                    metadata_changes: dict[str, set[str]] | None = None) -> dict:
    relevant = selected_tests(paths, tests, sources, metadata_changes)
    deferred = {name: asdict(PR_DEFERRED[name]) for name in relevant if name in PR_DEFERRED}
    selected = [name for name in relevant if name not in deferred]
    return {
        "relevant": relevant,
        "selected": selected,
        "deferred": deferred,
        "requirements": {"lua52_native": any(
            "tests/lua_native_prerequisites.py" in MACOS_TEST_DEPENDENCIES.get(name, ())
            for name in selected
        )},
    }


def pr_smoke_tests(paths: list[str], tests: set[str], sources: dict[str, str]) -> list[str]:
    """Bounded PR suite with a stable behavior owner for every changed module."""
    return smoke_selection(paths, tests, sources)["selected"]


def main(argv: list[str]) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_sha")
    parser.add_argument("head_sha")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv[1:])
    try:
        paths = changed_paths(args.base_sha, args.head_sha)
        changes = metadata_test_changes(args.base_sha, args.head_sha, paths)
        selection = smoke_selection(paths, load_macos_only_tests(), source_directories(), changes)
        if args.output:
            args.output.write_text(json.dumps(selection, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"macOS PR selection failed: {exc}", file=sys.stderr)
        return 2
    print("\n".join(selection["selected"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
