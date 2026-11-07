"""PR behavior coverage follows actual consumers and fails missing module ownership."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Tools"))
from ci_docs_only import MACOS_TEST_DEPENDENCIES, load_macos_only_tests
from select_macos_pr_tests import PR_DEFERRED, pr_smoke_tests, selected_tests, smoke_selection

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
print("ci_pr_macos_selection_ok")
