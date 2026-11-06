"""Disclosure readiness is measured per boundary, never asserted as a duration.

Phase C of #670: the six native retirement boundaries report how each predicate
settled. Only the `deadline` mode is a failure, and the failure is still decided
by the harness's own strict precondition, not by the reported time.
"""
from pathlib import Path

TESTS = Path(__file__).resolve().parent
harness = (TESTS / "disclosure_ui_harness.py").read_text(encoding="utf-8")

# Every retirement path is exercised; none may be dropped to shorten the run.
assert ("case ordinaryDisable, reenabled, reenabledEdited, replacedComposition, "
        "cancelledEdit, replacedTarget") in harness

# One shared wait classifies the observation and reports it.
assert "struct DisclosureWaitResult" in harness
assert "func disclosureSettleWait(" in harness
assert 'return record("immediate", true)' in harness
assert 'return record("event-loop", true)' in harness
assert 'return record("deadline", condition())' in harness
assert "disclosure_wait name=\\(name) settle=\\(settle) elapsed_ms=\\(milliseconds)" in harness

# The six boundaries go through it instead of an inline deadline loop.
assert 'let retirement = disclosureSettleWait("retirement:\\(boundary)")' in harness
assert "retirementDeadline" not in harness
assert "boundarySettleCounts[retirement.settle, default: 0] += 1" in harness
assert 'print("disclosure_retirement_boundary_summary boundaries=\\(Boundary.allCases.count)"' in harness

# A deadline settle is still a hard failure at the owning assertion.
assert ("precondition(retirement.satisfied,\n"
        "                     \"native retirement published a stale target or repeated an editing "
        "callback; boundary=\\(boundary)\")") in harness

# No threshold was tightened to make the reporting look better: the wait keeps
# the one-second deadline it had, and readiness is driven by the event loop.
assert "timeout: TimeInterval = 1," in harness
assert "disclosureLifetimePump(0.01)" in harness
for busy_wait in ("Thread.sleep", "usleep", "sleep(for:"):
    assert busy_wait not in harness, f"readiness must not busy-wait: {busy_wait}"

# The strict behavioral assertions this reporting sits between are unchanged.
for assertion in (
    "native retirement revived an obsolete draft or completed an edit; boundary=",
    "replacement reordered the retired and new edit owners",
    "native Escape did not cancel the edit after composition ended",
    "fixture did not replace its marked composition through native input",
    "ordinary disabling published or completed a disclosure-only snapshot",
    "same-identity disclosure did not publish its retained native composition",
    "a later unchanged Return replayed the suspended draft's explicit completion",
):
    assert assertion in harness, assertion

print("disclosure_boundary_readiness_ok")
