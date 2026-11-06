"""The disclosure settle classifier reports three outcomes and fails the third.

Phase C of #670 requires that a deliberately unsatisfied predicate still fails
and that a deadline settle is distinguishable from an immediate or event-loop
settle. This compiles the harness's own classifier against a stub pump, so the
negative case is executable rather than asserted from source text.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent

if sys.platform != "darwin":
    raise SystemExit("macOS-only disclosure settle classification")

SWIFTC = shutil.which("swiftc")
if not SWIFTC:
    raise SystemExit("swiftc required")

harness = (TESTS / "disclosure_ui_harness.py").read_text(encoding="utf-8")
start = harness.index("struct DisclosureWaitResult {")
end_marker = 'return record("deadline", condition())\n}\n'
end = harness.index(end_marker) + len(end_marker)
helper = harness[start:end]
assert "func disclosureSettleWait(" in helper, "settle classifier moved out of the harness"

PROGRAM = '''
import Foundation

@MainActor
func disclosureLifetimePump(_ seconds: TimeInterval) {
    RunLoop.current.run(until: Date().addingTimeInterval(seconds))
}

''' + helper + '''
@main
struct Driver {
    @MainActor
    static func main() {
        var ticks = 0
        let immediate = disclosureSettleWait("immediate", timeout: 1) { true }
        let eventLoop = disclosureSettleWait("event-loop", timeout: 1) {
            ticks += 1
            return ticks >= 2
        }
        let never = disclosureSettleWait("never", timeout: 0.2) { false }
        print("disclosure_settle_classification immediate=\\(immediate.settle)/\\(immediate.satisfied)"
              + " event_loop=\\(eventLoop.settle)/\\(eventLoop.satisfied)"
              + " deadline=\\(never.settle)/\\(never.satisfied)")
        precondition(immediate.settle == "immediate" && immediate.satisfied)
        precondition(eventLoop.settle == "event-loop" && eventLoop.satisfied)
        precondition(never.settle == "deadline" && !never.satisfied,
                     "an unsatisfied predicate was reported as settled")
        precondition(never.milliseconds >= 150,
                     "a deadline settle must consume its timeout")
        print("disclosure_settle_classification_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix="mgt-disclosure-settle-") as directory:
    source = Path(directory) / "Driver.swift"
    binary = Path(directory) / "classify"
    source.write_text(PROGRAM, encoding="utf-8")
    subprocess.run([SWIFTC, "-parse-as-library", str(source), "-o", str(binary)],
                   check=True, cwd=ROOT)
    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        raise SystemExit(result.returncode)
    assert "disclosure_settle_classification_ok" in result.stdout, result.stdout
    assert "immediate=immediate/true" in result.stdout, result.stdout
    assert "event_loop=event-loop/true" in result.stdout, result.stdout
    assert "deadline=deadline/false" in result.stdout, result.stdout
    print(result.stdout.strip())

print("disclosure_settle_classification_test_ok")
