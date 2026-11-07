"""One watchdog per named journey and verified profile; expiry is not a failed assertion.

The policy exists so that a slow-but-correct native journey, a stalled process
and an unmet semantic predicate stay three different outcomes. These checks are
portable: they never require AppKit or a hosted runner.
"""
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
sys.path.insert(0, str(TESTS))

from macos_fixture_policy import (
    HOSTED_PROFILE, JOURNEY_BUDGETS, LOCAL_MINIMUM_SECONDS, LOCAL_PROFILE,
    MAXIMUM_BUDGET_SECONDS, PROFILE_VARIABLE,
    FixtureBudget, FixturePolicyError, FixtureWatchdogExpired,
    resolve_budget, resolve_profile, run_watchdog,
)

HOSTED = {"GITHUB_ACTIONS": "true", PROFILE_VARIABLE: HOSTED_PROFILE, "RUNNER_ARCH": "ARM64"}

# Every native fixture that launches a bounded worker, and the journeys it owns.
CONSUMERS = {
    "test_hades_frontend.py": (
        "hades.save_editor", "hades.recovery", "hades.management",
        "hades.slider", "hades.hierarchy", "hades.disclosure", "hades.search",
    ),
    "test_hades2_view_state_flow.py": (
        "hades2.hierarchy", "hades2.slider", "hades2.disclosure",
        "hades2.search", "hades2.state_flow",
    ),
    "test_hades2_save_editor_frontend.py": ("hades2.save_editor",),
    "test_hades2_model_flow.py": ("hades2.live_trait_flow",),
    "test_runtime_text_edit_completion.py": ("runtime_text_edit.completion",),
    "real_module_navigation_harness.py": (
        "multi_game_navigation.startup", "multi_game_navigation.journey",
    ),
    'test_trainer_text_field_appearance.py': ('native.trainer_text_field_appearance',),
    'test_trainer_search_field_appearance.py': ('native.trainer_search_field_appearance',),
    'test_core_save_batch_delete_round20.py': ('native.core_save_batch_delete_round20',),
    'test_core_save_rename_completion_round24.py': ('native.core_save_rename_completion_round24',),
    'test_core_save_manager_lifecycle_u01_u02.py': ('native.core_save_manager_lifecycle_u01_u02.1', 'native.core_save_manager_lifecycle_u01_u02.2'),
    'test_hades2_run_log_watcher.py': ('native.hades2_run_log_watcher',),
    'test_trainer_log_session_lifecycle.py': ('native.trainer_log_session_lifecycle',),
    'test_backend_stderr_liveness.py': ('native.backend_stderr_liveness',),
    'test_disclosure_settle_classification.py': ('native.disclosure_settle_classification',),
    'test_viewport_feedback.py': ('native.viewport_feedback',),
    'test_hades2_force_enable_rerolls_frontend.py': ('native.hades2_force_enable_rerolls_frontend',),
    'test_hades2_gathering_frontend.py': ('native.hades2_gathering_frontend',),
    'test_hades2_chaos_gate_frontend.py': ('native.hades2_chaos_gate_frontend',),
    'test_hades2_save_editor_player_journey.py': ('native.hades2_save_editor_player_journey',),
    'test_hades2_advanced_save_frontend.py': ('native.hades2_advanced_save_frontend',),
    'test_hades2_save_record_frontend.py': ('native.hades2_save_record_frontend',),
    'test_reference_fixture_session_integration.py': ('native.reference_fixture_session_integration', 'reference_fixture.suffix_identity'),
    'test_trainer_tool_windows.py': ('native.trainer_tool_windows',),
    'test_hades2_repeated_actions_frontend.py': ('native.hades2_repeated_actions_frontend',),
    'test_host_target_ownership.py': ('native.host_target_ownership',),
    'test_core_save_retention_controls.py': ('native.core_save_retention_controls',),
    'test_mapped_slider_interaction.py': ('native.mapped_slider_interaction',),
    'test_hades2_save_container_frontend.py': ('native.hades2_save_container_frontend',),
    'multi_game_context_harness.py': ('multi_game.context_state', 'multi_game.context_navigation'),
    'test_native_effect_query_macos.py': ('native_effect_query.image_identity',),
}

# --- Profile resolution -------------------------------------------------------

assert resolve_profile({}) == LOCAL_PROFILE
assert resolve_profile({"GITHUB_ACTIONS": "false"}) == LOCAL_PROFILE
assert resolve_profile(HOSTED) == HOSTED_PROFILE
assert resolve_profile({**HOSTED, "RUNNER_ARCH": ""}) == HOSTED_PROFILE

for unknown in (
    {"GITHUB_ACTIONS": "true"},
    {"GITHUB_ACTIONS": "true", PROFILE_VARIABLE: ""},
    {"GITHUB_ACTIONS": "true", PROFILE_VARIABLE: "macos-26-intel", "RUNNER_ARCH": "X64"},
    {"GITHUB_ACTIONS": "true", PROFILE_VARIABLE: LOCAL_PROFILE},
):
    try:
        resolve_profile(unknown)
    except FixturePolicyError as error:
        assert "profile" in str(error), error
    else:
        raise AssertionError(f"unknown hosted profile accepted: {unknown!r}")

# The product declares arm64 only; a foreign hosted architecture has no budget.
try:
    resolve_profile({**HOSTED, "RUNNER_ARCH": "X64"})
except FixturePolicyError as error:
    assert "ARM64" in str(error), error
else:
    raise AssertionError("x86_64 hosted runner accepted a verified ARM64 budget")

# --- Budget resolution --------------------------------------------------------

for journey, hosted in JOURNEY_BUDGETS.items():
    assert 0 < hosted <= MAXIMUM_BUDGET_SECONDS, journey
    resolved = resolve_budget(journey, HOSTED)
    assert resolved.profile == HOSTED_PROFILE and resolved.seconds == hosted, journey
    local = resolve_budget(journey, {})
    assert local.profile == LOCAL_PROFILE, journey
    assert local.seconds == min(MAXIMUM_BUDGET_SECONDS, max(hosted, LOCAL_MINIMUM_SECONDS)), journey
    assert local.seconds >= hosted, journey
    assert "budget=" in resolved.describe(), journey

try:
    resolve_budget("hades.undeclared", HOSTED)
except FixturePolicyError as error:
    assert "undeclared" in str(error), error
else:
    raise AssertionError("undeclared journey inherited a budget")

# A timeout is containment, not a latency gate: no budget may sit so close to a
# measured journey that ordinary variance reads as a hang.
assert min(JOURNEY_BUDGETS.values()) >= 20, JOURNEY_BUDGETS
assert JOURNEY_BUDGETS["hades.disclosure"] >= 60, "measured 41.6s needs real margin"
assert JOURNEY_BUDGETS["hades2.disclosure"] >= 60, "Hades II shares the Hades I disclosure shape"

# --- Enforcement --------------------------------------------------------------

result = run_watchdog([sys.executable, "-c", "print('fixture_ok')"],
                      budget=FixtureBudget("test.success", LOCAL_PROFILE, 10.0),
                      capture_output=True, text=True)
assert result.returncode == 0 and "fixture_ok" in result.stdout

# A semantic assertion is the fixture's original exit failure. Migrating an
# ordinary subprocess.run(check=True) must retain that failure and diagnostics.
try:
    run_watchdog([sys.executable, "-c", "import sys; print('predicate not met'); sys.exit(3)"],
                 budget=FixtureBudget("test.semantic", LOCAL_PROFILE, 10.0),
                 capture_output=True, text=True, check=True)
except subprocess.CalledProcessError as error:
    assert error.returncode == 3 and "predicate not met" in error.stdout
else:
    raise AssertionError("shared watchdog swallowed a semantic failure")

assert not issubclass(FixtureWatchdogExpired, AssertionError), (
    "a watchdog expiry must never be reported as a semantic assertion failure"
)
assert FixtureWatchdogExpired is not subprocess.TimeoutExpired

started = time.monotonic()
try:
    run_watchdog([sys.executable, "-c", "import time; time.sleep(30)"],
                 budget=FixtureBudget("test.hang", LOCAL_PROFILE, 0.5),
                 capture_output=True, text=True)
except FixtureWatchdogExpired as error:
    elapsed = time.monotonic() - started
    assert error.budget.journey == "test.hang", error
    assert elapsed < 10, elapsed
    assert "budget=0.5s" in str(error), error
else:
    raise AssertionError("a stalled fixture was reported as a normal exit")

# An owned worker must not outlive the watchdog that killed its parent.
with tempfile.TemporaryDirectory(prefix="mgt-watchdog-") as directory:
    pid_file = Path(directory) / "child.pid"
    parent = (
        "import pathlib, subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "pathlib.Path(sys.argv[1]).write_text(str(child.pid))\n"
        "time.sleep(60)\n"
    )
    try:
        run_watchdog([sys.executable, "-c", parent, str(pid_file)],
                     budget=FixtureBudget("test.group", LOCAL_PROFILE, 1.0),
                     capture_output=True, text=True)
    except FixtureWatchdogExpired:
        pass
    else:
        raise AssertionError("parent fixture outlived its watchdog")
    child_pid = int(pid_file.read_text())
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("owned worker survived the watchdog's cleanup")

# A worker that outlives its parent still holds the write end of the pipe. The
# watchdog must report on its own schedule rather than read that pipe to EOF,
# which would make the watchdog the hang it exists to report.
with tempfile.TemporaryDirectory(prefix="mgt-orphan-") as directory:
    pid_file = Path(directory) / "orphan.pid"
    parent = (
        "import pathlib, subprocess, sys\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        "pathlib.Path(sys.argv[1]).write_text(str(child.pid))\n"
        "sys.exit(0)\n"
    )
    started = time.monotonic()
    try:
        run_watchdog([sys.executable, "-c", parent, str(pid_file)],
                     budget=FixtureBudget("test.orphan", LOCAL_PROFILE, 0.5),
                     capture_output=True, text=True)
    except FixtureWatchdogExpired:
        pass
    else:
        raise AssertionError("an orphaned worker holding the pipe was reported as a normal exit")
    waited = time.monotonic() - started
    assert waited < 10, f"the watchdog outlived its budget by {waited:.1f}s"
    orphan = int(pid_file.read_text())
    try:
        os.kill(orphan, signal.SIGKILL)
    except ProcessLookupError:
        pass

# The fixture must keep the harness's process group and session: a new group or
# a detached session changes AppKit activation and made a native journey fail
# its own readiness wait on a source-identical tree.
source = (TESTS / "macos_fixture_policy.py").read_text(encoding="utf-8")
for forbidden in ('kwargs["process_group"]', "start_new_session=True", "os.killpg"):
    assert forbidden not in source, (
        f"the watchdog must not change the fixture's process group or session: {forbidden}"
    )

# --- One policy, no duplicate thresholds --------------------------------------

assert not (TESTS / "macos_test_budget.py").exists(), (
    "the retired global outer-timeout multiplier must not come back"
)
assert not (TESTS / "test_macos_outer_timeout_budget.py").exists()
assert not (TESTS / "test_hades2_save_editor_frontend_budget.py").exists()

declared = set()
for name, journeys in CONSUMERS.items():
    source = (TESTS / name).read_text(encoding="utf-8")
    assert "from macos_fixture_policy import" in source, name
    assert "launch_fixture" in source, name
    assert "scaled_outer_timeout" not in source, name
    assert "MGT_MACOS_OUTER_TIMEOUT_SCALE" not in source, name
    for journey in journeys:
        assert f'"{journey}"' in source or f"'{journey}'" in source, (name, journey)
        declared.add(journey)

assert declared == set(JOURNEY_BUDGETS), (
    "declared journeys and owned journeys diverged: "
    f"{sorted(declared ^ set(JOURNEY_BUDGETS))}"
)

for path in sorted((ROOT / "Tools").rglob("*")) + sorted((ROOT / ".github").rglob("*.yml")):
    if not path.is_file() or path.suffix not in {".py", ".sh", ".yml", ".json", ".txt"}:
        continue
    text = path.read_text(encoding="utf-8", errors="replace")
    assert "MGT_MACOS_OUTER_TIMEOUT_SCALE" not in text, (
        f"{path.relative_to(ROOT)}: no workflow or tool may scale a hard watchdog"
    )

for name in ("build2-macos.yml", "module-build-matrix.yml"):
    workflow = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
    assert f"{PROFILE_VARIABLE}: {HOSTED_PROFILE}" in workflow, (
        f"{name}: hosted jobs must declare the verified profile the policy expects"
    )

print("macos_fixture_policy_ok")
