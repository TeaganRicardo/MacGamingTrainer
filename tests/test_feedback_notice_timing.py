import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
if not SWIFTC:
    raise SystemExit("swiftc required for feedback timing behavior")

harness = r'''
import Foundation

func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fatalError(message) }
}

var timing = TrainerFeedbackTiming()
let first = UUID()
let second = UUID()
check(timing.currentID == nil, "empty feedback should have no timer")
check(timing.show(first, at: 10), "new feedback should request one announcement")
check(!timing.show(first, at: 12), "same event must not restart or announce twice")
timing.advance(first, at: 13.99)
check(!timing.isFading, "feedback must remain readable for four seconds")
timing.advance(first, at: 14)
check(timing.isFading, "readable interval should begin the fade")
timing.advance(first, at: 14.24)
check(timing.currentID == first, "fade should retain its identity until complete")
timing.advance(first, at: 14.25)
check(timing.currentID == nil, "feedback should disappear after the fade")

check(timing.show(first, at: 100), "later feedback should show")
check(timing.show(second, at: 102), "new event should replace, without queueing")
timing.advance(first, at: 999)
check(timing.currentID == second && !timing.isFading, "stale timer dismissed newer feedback")
timing.advance(second, at: 105.99)
check(!timing.isFading, "replacement did not receive a full readable interval")
timing.advance(second, at: 106)
check(timing.isFading, "replacement fade did not begin")
timing.advance(second, at: 106.25)
check(timing.currentID == nil, "replacement feedback was retained indefinitely")

for index in 0..<1000 {
    _ = timing.show(UUID(), at: Double(index))
}
timing.clear()
check(timing.currentID == nil && !timing.isFading, "clear must discard only presentation timing")
print("feedback_notice_timing_ok")
'''

with tempfile.TemporaryDirectory(prefix="mgt-feedback-timing-") as td:
    td = Path(td)
    main = td / "main.swift"
    binary = td / "feedback_timing"
    main.write_text(textwrap.dedent(harness))
    subprocess.run([
        SWIFTC,
        str(ROOT / "Sources/Core/UI/TrainerFeedbackTiming.swift"),
        str(main), "-o", str(binary),
    ], check=True, cwd=ROOT)
    subprocess.run([str(binary)], check=True, cwd=ROOT, timeout=10)
