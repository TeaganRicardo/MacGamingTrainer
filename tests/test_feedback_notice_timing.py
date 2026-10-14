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
check(timing.show(first, duration: TrainerFeedbackTiming.ordinaryDuration, at: 10), "new feedback should request one announcement")
check(!timing.show(first, duration: TrainerFeedbackTiming.ordinaryDuration, at: 12), "same event must not restart or announce twice")
timing.advance(first, at: 15.99)
check(!timing.isFading, "feedback must remain readable for six seconds")
timing.advance(first, at: 16)
check(timing.isFading, "readable interval should begin the fade")
timing.advance(first, at: 16.24)
check(timing.currentID == first, "fade should retain its identity until complete")
timing.advance(first, at: 16.25)
check(timing.currentID == nil, "feedback should disappear after the fade")

check(timing.show(first, duration: TrainerFeedbackTiming.ordinaryDuration, at: 100), "later feedback should show")
check(timing.show(second, duration: TrainerFeedbackTiming.ordinaryDuration, at: 102), "new event should replace, without queueing")
timing.advance(first, at: 999)
check(timing.currentID == second && !timing.isFading, "stale timer dismissed newer feedback")
timing.advance(second, at: 107.99)
check(!timing.isFading, "replacement did not receive a full readable interval")
timing.advance(second, at: 108)
check(timing.isFading, "replacement fade did not begin")
timing.advance(second, at: 108.25)
check(timing.currentID == nil, "replacement feedback was retained indefinitely")

check(timing.show(first, duration: TrainerFeedbackTiming.errorDuration, at: 200), "error should show")
timing.advance(first, at: 207.99)
check(!timing.isFading, "error needs eight readable seconds")
timing.pause(first, at: 207.99)
timing.advance(first, at: 1000)
check(timing.currentID == first && !timing.isFading, "details interaction did not pause the error")
timing.resume(first, at: 210.99)
timing.advance(first, at: 210.99)
check(!timing.isFading, "resume lost the remaining readable interval")
timing.advance(first, at: 211.25)
check(timing.currentID == nil, "resumed error did not expire")
_ = timing.show(first, duration: 8, at: 300)
timing.pause(first, at: 302)
_ = timing.show(second, duration: 6, at: 303)
timing.resume(first, at: 500)
timing.advance(second, at: 309.25)
check(timing.currentID == nil, "old details interaction paused a replacement")

for index in 0..<1000 {
    _ = timing.show(UUID(), duration: TrainerFeedbackTiming.ordinaryDuration, at: Double(index))
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
