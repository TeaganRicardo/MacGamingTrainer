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
}
SOURCES = {"hades": "Sources/Hades/", "hades2": "Sources/Hades2/"}

assert selected_tests([], TESTS, SOURCES) == sorted(TESTS)
assert selected_tests(["README.md"], TESTS, SOURCES) == []
assert selected_tests(["Backend/games/hades2/adapter.py"], TESTS, SOURCES) == []
assert selected_tests(["Sources/Hades2/Hades2View.swift"], TESTS, SOURCES) == ["test_hades2_view_state_flow.py"]
assert selected_tests(["Sources/Hades/HadesTrainerView.swift"], TESTS, SOURCES) == ["test_hades_frontend.py"]
assert selected_tests(["Sources/Core/Host/TrainerHost.swift"], TESTS, SOURCES) == sorted({
    "test_multi_game_contexts.py", "test_reference_fixture_session_integration.py", "test_global_hotkey_routing.py"
})
for path in ("Sources/Core/UI/Primitives/TrainerMappedSlider.swift", "Sources/Core/UI/Primitives/TrainerSliderMapping.swift"):
    assert selected_tests([path], TESTS, SOURCES) == sorted({
        "test_multi_game_contexts.py", "test_reference_fixture_session_integration.py",
        "test_global_hotkey_routing.py", "test_mapped_slider_interaction.py",
    })
assert selected_tests(["tests/test_hades2_save_editor_frontend.py"], TESTS, SOURCES) == [
    "test_hades2_save_editor_frontend.py"
]
for path in (
    "tests/hades2_lldb_worker_support.py", "tests/hades2_lldb_fixture.py",
    "tests/hades2_debugserver_owner.py", "Tools/profile_hades2_operations.py",
):
    assert selected_tests([path], TESTS, SOURCES) == ["test_hades2_lldb_breakpoint_lifetime.py"]
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
