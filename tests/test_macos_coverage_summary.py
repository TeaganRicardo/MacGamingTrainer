"""A macOS lane must state its coverage, and timing must never decide it.

Phase D of #670: the summary reports selected / executed / passed / failed /
deferred with a verification owner per deferral, fails closed when the coverage
claim cannot be proved, and treats journey timing as observation only.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(ROOT / "Tools"))

import macos_fixture_policy as policy
import summarize_macos_coverage as summary
from summarize_macos_coverage import CoverageError, coverage, render, timing_summary

IDENTITY = {"source": "af69f2e", "profile": "macos-26", "image": "macos-26/1", "architecture": "ARM64"}
INVENTORY = {
    "test_hades_frontend.py",
    "test_hades2_view_state_flow.py",
    "test_multi_game_contexts.py",
    "test_runtime_text_edit_completion.py",
    "test_hades2_save_editor_frontend.py",
    "test_trainer_text_field_appearance.py",
}
SELECTED = ["test_hades_frontend.py", "test_hades2_save_editor_frontend.py"]
RESULTS = [{"test": "test_hades_frontend.py", "status": "pass"},
           {"test": "test_hades2_save_editor_frontend.py", "status": "fail"}]

# --- Coverage -----------------------------------------------------------------

report = coverage("pr", SELECTED, RESULTS, INVENTORY)
assert report["selected"] == 2 and report["executed"] == 2
assert report["passed"] == 1 and report["failed"] == 1
assert report["deferred"] == 3, report["deferred"]
assert report["not_selected"] == 1, report["not_selected"]
assert report["inventory"] == 6
assert report["deferred_covered"] is True
assert set(report["deferred_tests"]) == set(summary.PR_DEFERRED)

convergence = coverage("convergence", sorted(INVENTORY),
                       [{"test": name, "status": "pass"} for name in sorted(INVENTORY)],
                       INVENTORY)
assert convergence["deferred"] == 0, "convergence must not defer native coverage"
assert convergence["executed"] == convergence["selected"] == 6
assert convergence["not_selected"] == 0

for description, lane, selected, results, inventory in (
    ("empty convergence", "convergence", [], [], INVENTORY),
    ("empty inventory", "convergence", ["test_hades_frontend.py"], [], set()),
    ("undeclared selection", "pr", ["test_unknown.py"], [{"test": "test_unknown.py", "status": "pass"}], INVENTORY),
    ("unselected execution", "pr", SELECTED,
     RESULTS + [{"test": "test_multi_game_contexts.py", "status": "pass"}], INVENTORY),
    ("selected but never executed", "pr", SELECTED, RESULTS[:1], INVENTORY),
):
    try:
        coverage(lane, selected, results, inventory)
    except CoverageError:
        pass
    else:
        raise AssertionError(f"coverage contract accepted {description}")

# A pull request may legitimately affect no macOS behavior; it must say so
# rather than fail or imply that something ran.
empty = coverage("pr", [], [], INVENTORY)
assert empty["selected"] == 0 and empty["executed"] == 0, empty
assert empty["not_selected"] == len(INVENTORY) - 3, empty

# A deferral whose suite left the inventory would hide missing coverage.
try:
    coverage("pr", SELECTED, RESULTS, INVENTORY - {"test_multi_game_contexts.py"})
except CoverageError as error:
    assert "convergence inventory" in str(error), error
else:
    raise AssertionError("a deferred suite missing from the inventory was accepted")

# --- Timing is observation only -----------------------------------------------

records = [
    {"journey": "hades.disclosure", "profile": "macos-26", "budget_seconds": 60.0, "elapsed_seconds": 25.2},
    {"journey": "hades.disclosure", "profile": "macos-26", "budget_seconds": 60.0, "elapsed_seconds": 31.0},
]
baseline = [{"journey": "hades.disclosure", "profile": "macos-26", "budget_seconds": 60.0, "elapsed_seconds": 41.6}]
trend = timing_summary(records, baseline)
assert len(trend) == 1, trend
assert trend[0]["samples"] == 3, trend
assert trend[0]["minimum"] == 25.2 and trend[0]["maximum"] == 41.6, trend
assert trend[0]["median"] == 31.0, trend
assert trend[0]["budget_seconds"] == 60.0, trend

block = render(report, trend, IDENTITY)
for token in ("lane=pr", "profile=macos-26", "source=af69f2e", "image=macos-26/1",
              "selected=2", "executed=2", "passed=1", "failed=1", "deferred=3",
              "not_selected=1", "inventory=6", "deferred_covered=true", "no threshold"):
    assert token in block, token
for name, deferral in summary.PR_DEFERRED.items():
    assert f"deferred {name}" in block, name
    assert deferral.reason in block, name
    assert deferral.verification_owner in block, name
# Timing never becomes a pass/fail statement.
assert "regression" not in block and "FAIL" not in block, block

# --- End to end ---------------------------------------------------------------

with tempfile.TemporaryDirectory(prefix="mgt-coverage-") as directory:
    root = Path(directory)
    selected = root / "selected.txt"
    results = root / "results.tsv"
    timings = root / "timings.jsonl"
    output = root / "coverage.jsonl"
    step = root / "step.md"
    selected.write_text("\n".join(SELECTED) + "\n", encoding="utf-8")
    results.write_text("test_hades_frontend.py\tpass\n"
                       "test_hades2_save_editor_frontend.py\tfail\n", encoding="utf-8")
    timings.write_text(json.dumps(records[0], sort_keys=True) + "\n", encoding="utf-8")
    assert summary.main([
        "--lane", "pr", "--selected", str(selected), "--results", str(results),
        "--timings", str(timings), "--output", str(output), "--summary", str(step),
    ]) == 0
    assert output.exists() and step.exists()
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    kinds = [row["kind"] for row in rows]
    assert kinds[0] == "coverage" and "timing" in kinds and "result" in kinds, kinds
    assert rows[0]["source"] == "af69f2e" or rows[0]["source"] == "local", rows[0]
    assert "macOS coverage" in step.read_text(encoding="utf-8")

    # A lane that cannot prove its deferral coverage fails closed.
    selected.write_text("test_hades_frontend.py\n", encoding="utf-8")
    results.write_text("test_hades_frontend.py\tpass\n", encoding="utf-8")
    assert summary.main([
        "--lane", "pr", "--selected", str(selected), "--results", str(results),
    ]) == 0

    results.write_text("test_hades_frontend.py\tpass\ntest_unknown.py\tpass\n", encoding="utf-8")
    assert summary.main([
        "--lane", "pr", "--selected", str(selected), "--results", str(results),
    ]) == 2

# --- The fixture policy emits the observation it promises ---------------------

with tempfile.TemporaryDirectory(prefix="mgt-timing-") as directory:
    path = Path(directory) / "timings.jsonl"
    environment = {"MGT_FIXTURE_TIMINGS": str(path)}
    policy.run_watchdog([sys.executable, "-c", "print('ok')"],
                        budget=policy.FixtureBudget("test.timing", policy.LOCAL_PROFILE, 10.0),
                        environ=environment, capture_output=True, text=True)
    try:
        policy.run_watchdog([sys.executable, "-c", "import time; time.sleep(30)"],
                            budget=policy.FixtureBudget("test.stall", policy.LOCAL_PROFILE, 0.3),
                            environ=environment, capture_output=True, text=True)
    except policy.FixtureWatchdogExpired:
        pass
    else:
        raise AssertionError("a stalled fixture was reported as a normal exit")
    recorded = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [row["journey"] for row in recorded] == ["test.timing", "test.stall"], recorded
    assert [row["outcome"] for row in recorded] == ["completed", "watchdog_expired"], recorded
    for row in recorded:
        for field in ("journey", "profile", "budget_seconds", "elapsed_seconds",
                      "outcome", "source", "architecture", "image", "image_version"):
            assert field in row, (field, row)
    assert recorded[0]["profile"] == policy.LOCAL_PROFILE
    assert recorded[1]["elapsed_seconds"] >= 0.3, recorded[1]

    # No path configured means no record and no failure.
    policy.run_watchdog([sys.executable, "-c", "print('ok')"],
                        budget=policy.FixtureBudget("test.silent", policy.LOCAL_PROFILE, 10.0),
                        environ={}, capture_output=True, text=True)
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2

# --- The lane and the workflow wire it up -------------------------------------

runner = (ROOT / "Tools/run_macos_checks.sh").read_text(encoding="utf-8")
assert "summarize_macos_coverage.py" in runner
assert 'LANE="pr"' in runner and 'LANE="convergence"' in runner
assert "MGT_FIXTURE_TIMINGS" in runner
assert "macOS coverage summary (exit" in runner, "a coverage violation must fail the lane"

workflow = (ROOT / ".github/workflows/build2-macos.yml").read_text(encoding="utf-8")
assert "MGT_FIXTURE_TIMINGS:" in workflow
assert "MGT_MACOS_COVERAGE_OUTPUT:" in workflow
assert "macos-coverage.jsonl" in workflow
coverage_step = workflow.split("Retain macOS coverage and journey timing evidence", 1)[1]
assert "always()" in coverage_step.split("with:", 1)[0]
assert "if-no-files-found: warn" in coverage_step, "missing evidence must not fail the lane"

print("macos_coverage_summary_ok")
