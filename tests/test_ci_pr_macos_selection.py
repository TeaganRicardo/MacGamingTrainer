"""PR behavior coverage follows actual consumers and fails missing module ownership."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Tools"))
from ci_docs_only import (
    MACOS_TEST_DEPENDENCIES,
    classify_scope,
    current_app_resource_sources,
    current_reference_prefixes,
    load_macos_only_tests,
)
from select_macos_pr_tests import PR_DEFERRED, metadata_test_changes, pr_smoke_tests, selected_tests, smoke_selection

TESTS = load_macos_only_tests()
SOURCES = {"hades": "Sources/Hades/", "hades2": "Sources/Hades2/"}
SHARED = {"test_multi_game_contexts.py", "test_multi_game_context_state.py",
          "test_reference_fixture_session_integration.py", "test_global_hotkey_routing.py"}

assert selected_tests([], TESTS, SOURCES) == sorted(TESTS)
assert selected_tests(["README.md"], TESTS, SOURCES) == []
for module, prefix in SOURCES.items():
    stable = "test_hades_frontend.py" if module == "hades" else "test_hades2_model_flow.py"
    for source in (ROOT / prefix).rglob("*.swift"):
        result = smoke_selection([source.relative_to(ROOT).as_posix()], TESTS, SOURCES)
        assert stable in result["selected"], source

for path in ("Sources/Core/Host/TrainerHost.swift", "Sources/Core/UI/TrainerSectionNavigation.swift",
             "Sources/Core/UI/TrainerSectionScroll.swift"):
    assert SHARED <= set(selected_tests([path], TESTS, SOURCES)), path

for helper in {path for paths in MACOS_TEST_DEPENDENCIES.values() for path in paths}:
    expected = {test for test, paths in MACOS_TEST_DEPENDENCIES.items() if helper in paths}
    assert expected <= set(selected_tests([helper], TESTS, SOURCES)), helper
# These were observed missing edges: changing the shared helper used to run
# none of these actual native consumers. Exercise the real selector result.
for helper, consumers in (
    ("tests/room_picker_alignment_harness.py", {"test_hades_frontend.py", "test_hades2_view_state_flow.py"}),
    ("tests/fixtures/hades2/save_editor_player_journey.py", {
        "test_hades2_save_editor_player_journey.py", "test_hades2_advanced_save_frontend.py",
        "test_hades2_save_record_frontend.py", "test_hades2_save_container_frontend.py",
    }),
):
    assert consumers <= set(selected_tests([helper], TESTS, SOURCES)), helper

assert selected_tests(["Tools/profile_hades2_operations.py"], TESTS, SOURCES) == []
assert set(MACOS_TEST_DEPENDENCIES) <= set(selected_tests(["Tools/macos_test_dependencies.json"], TESTS, SOURCES))

for path, owner in (
    ("Sources/Core/UI/Primitives/TrainerMappedSlider.swift", "test_mapped_slider_interaction.py"),
    ("Sources/Core/UI/Primitives/TrainerTextField.swift", "test_trainer_text_field_appearance.py"),
    ("Sources/Core/UI/Components/TrainerSearchField.swift", "test_trainer_search_field_appearance.py"),
    ("Sources/Core/UI/TrainerFeedbackOverlay.swift", "test_viewport_feedback.py"),
    ("Sources/Core/UI/TrainerToolWindows.swift", "test_trainer_tool_windows.py"),
    ("Sources/Hades2/Views/Hades2SaveEditorView.swift", "test_hades2_save_editor_frontend.py"),
    ("Sources/Hades2/Hades2SaveEditorModel.swift", "test_hades2_save_editor_frontend.py"),
    ("ContractFixtures/reference_module/backend/adapter.py", "test_reference_fixture_session_integration.py"),
    ("Backend/games/hades/adapter.py", "test_hades_process_identity_macos.py"),
    ("Backend/games/hades2/native/EffectBlockQuery.c", "test_native_effect_query_macos.py"),
    ("Native/ProcessTimeWarp/ProcessTimeWarp.c", "test_build_signing_metadata_macos.py"),
    ("Tools/select_macos_pr_tests.py", "test_multi_game_context_state.py"),
):
    assert owner in pr_smoke_tests([path], TESTS, SOURCES), (path, owner)

assert selected_tests(["tests/fixtures/swift/InMemoryDefaults.swift"], TESTS, SOURCES) == sorted(TESTS)
assert selected_tests(["Tools/macos_only_tests.txt"], TESTS, SOURCES) == sorted(TESTS)
assert selected_tests(["tests/test_debugserver_ownership.py"], TESTS, SOURCES) == []
for name in TESTS:
    assert name in selected_tests(["tests/" + name], TESTS, SOURCES), name

# Adding one inventory entry or dependency must not select all older native
# journeys. Keep the diff based on the same merge base as source selection.
with tempfile.TemporaryDirectory(prefix="mgt-native-selection-delta-") as directory:
    project = Path(directory)
    (project / "Tools").mkdir()
    inventory = project / "Tools/macos_only_tests.txt"
    dependencies = project / "Tools/macos_test_dependencies.json"
    inventory.write_text("test_hades_frontend.py\n")
    dependencies.write_text(json.dumps({"test_hades_frontend.py": ["tests/old_helper.py"]}))
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=project, check=True)
    subprocess.run(["git", "config", "user.name", "Fixture"], cwd=project, check=True)
    def commit(message):
        subprocess.run(["git", "add", "."], cwd=project, check=True)
        subprocess.run(["git", "commit", "-qm", message], cwd=project, check=True)
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=project, text=True).strip()
    base = commit("base native ownership")
    added = "test_hades2_model_flow.py"
    inventory.write_text(inventory.read_text() + added + "\n")
    dependencies.write_text(json.dumps({"test_hades_frontend.py": ["tests/old_helper.py"],
                                        added: ["tests/new_helper.py"]}))
    head = commit("add one native owner")
    paths = ["Tools/macos_only_tests.txt", "Tools/macos_test_dependencies.json"]
    delta = metadata_test_changes(base, head, paths, project)
    assert selected_tests(paths, TESTS, SOURCES, delta) == [added]
    # Inventory removal moves responsibility to portable discovery; it does not
    # justify running every unrelated native suite.
    inventory.write_text("test_hades_frontend.py\n")
    removed = commit("remove native owner")
    assert selected_tests([paths[0]], TESTS - {added}, SOURCES,
                          metadata_test_changes(head, removed, [paths[0]], project)) == []
    # A real helper/source change keeps all its existing consumers even when
    # the same PR adds a new native owner.
    mixed = selected_tests(paths + ["tests/room_picker_alignment_harness.py"], TESTS, SOURCES, delta)
    assert {added, "test_hades_frontend.py", "test_hades2_view_state_flow.py"} <= set(mixed)

# A registered module cannot borrow a different game's coverage or have every
# one of its own entries removed by the foreground deferral policy.
for module, tests in (("third_probe", TESTS),
                      ("hades2", TESTS - {"test_hades2_model_flow.py"})):
    sources = {module: "Sources/ThirdProbe/" if module == "third_probe" else SOURCES[module]}
    try:
        pr_smoke_tests([sources[module] + "SomeView.swift"], tests, sources)
    except ValueError as error:
        assert module in str(error) and "smoke" in str(error), error
    else:
        raise AssertionError(f"missing or fully deferred {module} behavior passed")

empty = smoke_selection(["README.md"], TESTS, SOURCES)
assert empty == {"relevant": [], "selected": [], "deferred": {}, "requirements": {"lua52_native": False}}
assert smoke_selection(["Backend/games/hades2/native/EffectBlockQuery.c"], TESTS, SOURCES)["requirements"]["lua52_native"]
result = smoke_selection(["Sources/Hades2/Hades2View.swift"], TESTS, SOURCES)
assert "test_hades2_model_flow.py" in result["selected"]
assert set(result["deferred"]) == {"test_hades2_view_state_flow.py", "test_multi_game_contexts.py", "test_runtime_text_edit_completion.py"}
assert set(result["relevant"]) == set(result["selected"]) | set(result["deferred"])
for name, detail in result["deferred"].items():
    assert name in TESTS and detail["reason"] and "workflow_dispatch" in detail["verification_owner"]
assert set(PR_DEFERRED) <= TESTS
assert pr_smoke_tests([], TESTS, SOURCES) == sorted(TESTS - PR_DEFERRED.keys())

# Newly wired Backend, Host, Localization, Hades II panel, and workflow routes.
expected_routes = {
    "Resources/Localization/zh-CN.lproj/Host.strings": {"test_host_localization_behavior.py"},
    "Sources/Core/Host/TrainerLocalization.swift": {"test_host_localization_behavior.py"},
    "Sources/Core/Host/TrainerTargetOwnership.swift": {"test_host_target_ownership.py"},
    "Sources/Core/Runtime/TrainerLogSink.swift": {"test_trainer_log_session_lifecycle.py"},
    "Sources/Core/Runtime/BackendProcess.swift": {"test_backend_stderr_liveness.py"},
    "Sources/Core/Save/TrainerSaveRetentionSettings.swift": {"test_core_save_retention_controls.py"},
    "Sources/Core/UI/Components/TrainerSaveEditorShell.swift": {
        "test_hades_save_editor_frontend.py",
        "test_hades2_save_editor_frontend.py",
    },
    "Sources/Hades/HadesSaveEditorView.swift": {"test_hades_save_editor_frontend.py"},
    "Sources/Hades2/Services/Hades2RunLogWatcher.swift": {"test_hades2_run_log_watcher.py"},
    "Sources/Hades2/Views/Hades2ChaosGatePanel.swift": {"test_hades2_chaos_gate_frontend.py"},
    "Sources/Hades2/Views/Hades2GatheringPanel.swift": {"test_hades2_gathering_frontend.py"},
    "Sources/Hades2/Views/Hades2BoonRarityPanel.swift": {"test_hades2_force_enable_rerolls_frontend.py"},
    "Sources/Hades2/Views/Hades2ManagementViews.swift": {"test_hades2_repeated_actions_frontend.py"},
    "Sources/Hades2/Hades2BackendState.swift": {"test_hades2_backend_state_cleanup.py"},
    "Backend/core/target_probe.py": {"test_core_save_target_probe_macos.py"},
    "Backend/games/hades2/transport.py": {"test_hades2_lldb_breakpoint_lifetime.py"},
    "Backend/debugger/lldb_time_warp.py": {"test_hades2_lldb_breakpoint_lifetime.py"},
    ".github/workflows/build2-macos.yml": {
        "test_build_signing_metadata_macos.py",
        "test_host_localization_behavior.py",
        "test_native_effect_query_macos.py",
    },
    "Tools/generate_game_binding.py": {"test_hades2_model_flow.py", "test_reference_fixture_session_integration.py"},
    "docs/reference/hades2/1.143476-25481925/ui_terminology.json": {"test_hades2_model_flow.py"},
}
for changed_path, required_tests in expected_routes.items():
    chosen = set(pr_smoke_tests([changed_path], TESTS, SOURCES))
    assert required_tests <= chosen, (changed_path, required_tests, chosen)
assert smoke_selection([".github/workflows/build2-macos.yml"], TESTS, SOURCES)["requirements"]["lua52_native"] is True

# Every macOS inventory entry must be reachable from real non-test/helper files
# (not only metadata edits to macos_only_tests.txt or macos_test_dependencies.json).
tracked_non_test = [
    path for path in subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()
    if not path.startswith("tests/") and path not in ("Tools/macos_only_tests.txt", "Tools/macos_test_dependencies.json")
]
reachable = set()
for path in tracked_non_test:
    reachable.update(selected_tests([path], TESTS, SOURCES))
# test_disclosure_settle_classification.py tests tests/disclosure_ui_harness.py directly.
reachable.update(selected_tests(["tests/disclosure_ui_harness.py"], TESTS, SOURCES))
assert TESTS - reachable == set(), sorted(TESTS - reachable)

# Every needs_macos=True non-test file must either select >=1 PR macOS test
# or fall into an explicit non-behavior category (build/version metadata,
# packaging assets, profiling fixtures, or Linux-contracted generators/schemas).
_REFS = current_reference_prefixes(ROOT)
_RES = current_app_resource_sources(ROOT)
# Packaged data read only by the portable backend: Linux tests own its behavior
# and build.sh refuses a product whose declared app resource is not packaged.
_HADES2_REFERENCE = json.loads((ROOT / "Backend/games/hades2/module.json").read_text(
    encoding="utf-8"))["supportedBuild"]["referenceDirectory"]
_NON_BEHAVIOR_MACOS_EXACT = frozenset({
    _HADES2_REFERENCE + "/installed_source_hashes.json",
    ".gitignore",
    "AppIcon.icns",
    "ContractFixtures/host_protocol_v6.json",
    "Info.plist",
    "LICENSE",
    "Tools/hades2_profile_workloads.py",
    "Tools/module_inventory.py",
    "Tools/product_support.py",
    "Tools/python_runtime.json",
    "Tools/validate_game_module.py",
    "app.json",
})
_NON_BEHAVIOR_MACOS_PREFIXES = (
    "Resources/Assets.xcassets/",
    "Tools/fixtures/",
    "Tools/generate_",
)
unexplained_zero_test = []
for path in sorted(set(tracked_non_test)):
    scope = classify_scope([path], macos_only_tests=TESTS, reference_prefixes=_REFS, app_resource_sources=_RES)
    if not scope["needs_macos"] or pr_smoke_tests([path], TESTS, SOURCES):
        continue
    if (
        path in _NON_BEHAVIOR_MACOS_EXACT
        or path.startswith(_NON_BEHAVIOR_MACOS_PREFIXES)
        or (path.startswith("Backend/games/") and path.endswith("/module.json"))
    ):
        continue
    unexplained_zero_test.append(path)
assert not unexplained_zero_test, f"needs_macos files without PR test or exemption: {unexplained_zero_test}"

print("ci_pr_macos_selection_ok")
