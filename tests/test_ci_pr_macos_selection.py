"""PR behavior coverage follows actual consumers and fails missing module ownership."""
import json
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Tools"))
from ci_docs_only import classify_scope, current_app_resource_sources, current_reference_prefixes
from select_macos_pr_tests import PR_DEFERRED, load_routing

ROUTING = load_routing()
TESTS = ROUTING.tests

assert ROUTING.relevant_tests([]) == sorted(TESTS)
assert ROUTING.selection([])["selected"] == sorted(TESTS - PR_DEFERRED.keys())
assert ROUTING.selection(["README.md"]) == {
    "relevant": [], "selected": [], "deferred": {}, "requirements": {"lua52_native": False},
}
assert ROUTING.relevant_tests(["tests/fixtures/swift/InMemoryDefaults.swift"]) == sorted(TESTS)
assert set(PR_DEFERRED) <= TESTS
for test in TESTS:
    assert test in ROUTING.relevant_tests([f"tests/{test}"]), test

# A new product module needs only its own smoke entry. Transitive Swift
# compilation inputs are selected even when nobody has added a file mapping.
with tempfile.TemporaryDirectory(prefix="mgt-derived-routing-") as directory:
    project = Path(directory)

    def write(relative, content=""):
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    write("app.json", json.dumps({"modules": ["alpha", "beta"]}))
    for game in ("alpha", "beta", "parked"):
        write(f"Backend/games/{game}/module.json", json.dumps({
            "id": game, "frontend": {"sourceDirectory": f"Sources/{game}"},
        }))
        write(f"Sources/{game}/Module.swift")
        write(f'tests/journeys/test_{game}_frontend.py', 'MGT_PLATFORM = "macos"\n')

    write("tests/helpers/native.py",
          'from swift_test_compiler import compile_swift_test as build\n'
          'from games.beta import runtime_probe\n'
          'build(games=("beta",))\n')
    write("Backend/games/beta/runtime_probe.py", "def probe(): return True\n")
    write("Backend/core/server.py", "# portable server\n")
    write("tests/helpers/server_harness.py", 'SERVER = "Backend/core/server.py"\n')
    write("tests/test_consumer.py",
          'MGT_PLATFORM = "macos"\nfrom helpers import native, server_harness\n')
    reclassified = write("tests/other/test_alpha_frontend.py", 'raise AssertionError("no test imports")\n')
    write("Sources/Explicit.swift")
    write("tests/test_explicit_sources.py",
          'MGT_PLATFORM = "macos"\nfrom pathlib import Path\n'
          'from swift_test_compiler import SwiftModule, compile_swift_test\n'
          'compile_swift_test(modules=[SwiftModule("Fixture", [Path("Sources/Explicit.swift")])])\n')
    removed_core_path = "Sources/Core/FutureOrRemoved.swift"
    fixture = load_routing(project, changed=[removed_core_path])
    assert fixture.relevant_tests([removed_core_path]) == [
        "journeys/test_alpha_frontend.py", "journeys/test_beta_frontend.py", "test_consumer.py",
    ]
    assert fixture.relevant_tests(["Sources/beta/Module.swift"]) == [
        "journeys/test_beta_frontend.py", "test_consumer.py",
    ]
    assert fixture.relevant_tests(["Backend/games/beta/module.json"]) == [
        "journeys/test_beta_frontend.py", "test_consumer.py",
    ]
    assert fixture.relevant_tests(["Sources/parked/Module.swift"]) == ["journeys/test_parked_frontend.py"]
    assert fixture.relevant_tests(["Sources/Explicit.swift"]) == ["test_explicit_sources.py"]
    assert fixture.relevant_tests(["tests/helpers/native.py"]) == ["test_consumer.py"]
    assert fixture.relevant_tests(["Backend/games/beta/runtime_probe.py"]) == ["test_consumer.py"]
    assert fixture.relevant_tests(["Backend/core/server.py"]) == []
    assert fixture.relevant_tests(["tests/other/test_alpha_frontend.py"]) == []
    reclassified.write_text('MGT_PLATFORM = "macos"\n', encoding="utf-8")
    assert load_routing(project).relevant_tests(["tests/other/test_alpha_frontend.py"]) == [
        "other/test_alpha_frontend.py",
    ]

# Module smoke coverage is mandatory on game and shared Core changes even if
# an unrelated native fixture is also changed.
for routing, paths, game in (
    (replace(ROUTING, sources={**ROUTING.sources, "missing": "Sources/Missing/"},
             app_modules=(*ROUTING.app_modules, "missing")),
     ["Sources/Core/Example.swift", "tests/fixtures/swift/InMemoryDefaults.swift"], "missing"),
    (replace(ROUTING, tests=TESTS - {"test_hades2_model_flow.py"}),
     ["Sources/Hades2/Example.swift"], "hades2"),
):
    try:
        routing.relevant_tests(paths)
    except ValueError as error:
        assert game in str(error) and "smoke" in str(error), error
    else:
        raise AssertionError(f"missing or fully deferred {game} behavior passed")

# These shared helpers and platform-coupled Backend imports previously missed real native consumers.
for helper, consumers in (
    ("tests/room_picker_alignment_harness.py", {"test_hades_frontend.py", "test_hades2_view_state_flow.py"}),
    ("tests/fixtures/hades2/save_editor_player_journey.py", {
        "test_hades2_save_editor_player_journey.py", "test_hades2_advanced_save_frontend.py",
        "test_hades2_save_record_frontend.py", "test_hades2_save_container_frontend.py",
    }),
    ("Backend/core/save_resolution.py", {
        "test_hades2_save_editor_player_journey.py", "test_hades2_advanced_save_frontend.py",
        "test_hades2_save_record_frontend.py", "test_hades2_save_container_frontend.py",
    }),
):
    assert consumers <= set(ROUTING.relevant_tests([helper])), helper
assert ROUTING.relevant_tests(["Tools/profile_hades2_operations.py"]) == []
assert ROUTING.relevant_tests(["tests/test_debugserver_ownership.py"]) == []

for changed_path, owner in (
    ("Resources/Localization/zh-CN.lproj/Host.strings", "test_host_localization_behavior.py"),
    ("ContractFixtures/reference_module/backend/adapter.py", "test_reference_fixture_session_integration.py"),
    ("Backend/games/hades/adapter.py", "test_hades_process_identity_macos.py"),
    ("Backend/core/target_probe.py", "test_core_save_target_probe_macos.py"),
    ("Backend/games/hades2/transport.py", "test_hades2_lldb_breakpoint_lifetime.py"),
    ("Native/ProcessTimeWarp/ProcessTimeWarp.c", "test_build_signing_metadata_macos.py"),
    ("Tools/select_macos_pr_tests.py", "test_multi_game_context_state.py"),
    ("Tools/product_support.py", "test_core_host_lifecycle_macos.py"),
    ("Tools/generate_game_binding.py", "test_hades2_gathering_frontend.py"),
    ("Backend/games/hades2/module.json", "test_hades2_gathering_frontend.py"),
    ("Backend/games/hades/catalog.json", "test_hades_frontend.py"),
    ("Info.plist", "test_reference_fixture_session_integration.py"),
):
    assert owner in ROUTING.selection([changed_path])["selected"], (changed_path, owner)

result = ROUTING.selection(["Sources/Hades2/Hades2View.swift"])
assert "test_hades2_model_flow.py" in result["selected"]
assert set(result["deferred"]) == {
    "test_hades2_view_state_flow.py", "test_multi_game_contexts.py", "test_runtime_text_edit_completion.py",
}
assert set(result["relevant"]) == set(result["selected"]) | set(result["deferred"])
for name, detail in result["deferred"].items():
    assert name in TESTS and detail["reason"] and "workflow_dispatch" in detail["verification_owner"]

for path in ("Backend/games/hades2/native/EffectBlockQuery.c", ".github/workflows/build2-macos.yml"):
    assert ROUTING.selection([path])["requirements"]["lua52_native"], path

# Every macOS inventory entry must be reachable from real non-test/helper files
# or actual helper files.
tracked_non_test = [
    path for path in subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()
    if not path.startswith("tests/")
]
reachable = set()
for path in tracked_non_test:
    reachable.update(ROUTING.relevant_tests([path]))
# test_disclosure_settle_classification.py tests tests/disclosure_ui_harness.py directly.
reachable.update(ROUTING.relevant_tests(["tests/disclosure_ui_harness.py"]))
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
    scope = classify_scope(
        [path], macos_only_tests=TESTS, test_dependencies=ROUTING.dependencies,
        reference_prefixes=_REFS, app_resource_sources=_RES,
    )
    if not scope["needs_macos"] or ROUTING.selection([path])["selected"]:
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
