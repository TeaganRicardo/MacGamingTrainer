from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
if not SWIFTC:
    raise SystemExit("swiftc required for Hades2RunLogWatcher test")

main_source = r"""
import Foundation

if !Hades2RunLogRefreshGate.shouldConsume(
    pending: true, connected: true, backendAvailable: true, busy: false, exiting: false
) {
    fatalError("a pending run-log signal must refresh even when the previous GUI snapshot was ready")
}
if Hades2RunLogRefreshGate.shouldConsume(
    pending: false, connected: true, backendAvailable: true, busy: false, exiting: false
) {
    fatalError("no pending run-log signal must mean no refresh")
}
if Hades2RunLogRefreshGate.shouldConsume(
    pending: true, connected: false, backendAvailable: true, busy: false, exiting: false
) {
    fatalError("detached trainer must not cross the Lua boundary")
}
if Hades2RunLogRefreshGate.shouldConsume(
    pending: true, connected: true, backendAvailable: true, busy: true, exiting: false
) {
    fatalError("busy trainer must defer the run-log refresh")
}
if Hades2RunLogRefreshGate.shouldConsume(
    pending: true, connected: true, backendAvailable: false, busy: false, exiting: false
) {
    fatalError("unavailable backend must defer the run-log refresh")
}
if Hades2RunLogRefreshGate.shouldConsume(
    pending: true, connected: true, backendAvailable: true, busy: false, exiting: true
) {
    fatalError("exiting trainer must not refresh")
}

let fileManager = FileManager.default
let directory = fileManager.homeDirectoryForCurrentUser
    .appendingPathComponent("Library/Application Support/Supergiant Games/Hades II", isDirectory: true)
let logURL = directory.appendingPathComponent("Hades II.log")

try? fileManager.removeItem(at: directory)
try fileManager.createDirectory(at: directory, withIntermediateDirectories: true)
try Data("seed\n".utf8).write(to: logURL)

var signalCount = 0
let watcher = Hades2RunLogWatcher {
    signalCount += 1
}
watcher.start()

let setupDeadline = Date().addingTimeInterval(0.35)
while Date() < setupDeadline {
    RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.01))
}

let handle = try FileHandle(forWritingTo: logURL)
try handle.seekToEnd()
try handle.write(contentsOf: Data("2026-09-19 [MainThread] World.cpp INFO| World::Begin()  -> Hub_PreRun\n".utf8))
try handle.synchronize()
try handle.close()

let deadline = Date().addingTimeInterval(2.0)
while signalCount < 1 && Date() < deadline {
    RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.01))
}
if signalCount < 1 {
    fatalError("appending a World::Begin line did not trigger the watcher")
}

// Hades may replace the log between launches. The watcher must follow the new
// inode and consume only new content from that replacement.
let rotatedURL = directory.appendingPathComponent("Hades II.log.previous")
try? fileManager.removeItem(at: rotatedURL)
try fileManager.moveItem(at: logURL, to: rotatedURL)
try Data("new session\n".utf8).write(to: logURL)

let rotationSettleDeadline = Date().addingTimeInterval(0.5)
while Date() < rotationSettleDeadline {
    RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.01))
}

let replacement = try FileHandle(forWritingTo: logURL)
try replacement.seekToEnd()
try replacement.write(contentsOf: Data("2026-09-19 [MainThread] World.cpp INFO| Finished loadScreen onExit (0.100 seconds)\n".utf8))
try replacement.synchronize()
try replacement.close()

let replacementDeadline = Date().addingTimeInterval(2.0)
while signalCount < 2 && Date() < replacementDeadline {
    RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.01))
}
if signalCount < 2 {
    fatalError("replacing the Hades log lost subsequent readiness signals")
}

// Truncation without inode replacement is another ordinary logger behavior.
let truncating = try FileHandle(forWritingTo: logURL)
try truncating.truncate(atOffset: 0)
try truncating.write(contentsOf: Data("2026-09-19 [MainThread] World.cpp INFO| World::Begin() Hub_PreRun -> F_Opening03\n".utf8))
try truncating.synchronize()
try truncating.close()

let truncationDeadline = Date().addingTimeInterval(2.0)
while signalCount < 3 && Date() < truncationDeadline {
    RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.01))
}

watcher.stop()
if signalCount < 3 {
    fatalError("truncating the Hades log lost subsequent readiness signals")
}
print("hades2_run_log_watcher_ok")
"""

with tempfile.TemporaryDirectory(prefix="mgt-hades2-log-watcher-") as td:
    td = Path(td)
    main = td / "main.swift"
    binary = td / "watcher_test"
    main.write_text(textwrap.dedent(main_source), encoding="utf-8")
    subprocess.run([
        SWIFTC,
        str(ROOT / "Sources/Hades2/Services/Hades2RunLogRefreshGate.swift"),
        str(ROOT / "Sources/Hades2/Services/Hades2RunLogWatcher.swift"),
        str(main),
        "-o", str(binary),
    ], check=True, cwd=ROOT)
    proc = subprocess.run([str(binary)], cwd=ROOT, text=True, capture_output=True, timeout=10)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    print(proc.stdout.strip())
