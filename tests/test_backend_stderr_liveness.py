"""Backend stderr read/flush must remain live with an open, quiet worker."""
import os
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
PYTHON = shutil.which("python3")
if not SWIFTC or not PYTHON:
    raise SystemExit("swiftc and python3 required")

# The worker writes more than one pipe buffer, then remains alive but quiet.
# A readability callback can be queued more than once for the same bytes.
# After the first callback drains them, the next read must NOT block.
worker = r"""
import argparse
import os
import signal
import time

p = argparse.ArgumentParser()
p.add_argument("--game", required=True)
p.parse_args()
signal.signal(signal.SIGTERM, signal.SIG_IGN)
for _ in range(64):
    os.write(2, b"L" * 4096)
time.sleep(30)
"""

backpressure_worker = r"""
import argparse
import json
import os
import sys

p = argparse.ArgumentParser()
p.add_argument("--game", required=True)
p.parse_args()
os.write(1, b'{"ready":true}\n')
for line in sys.stdin:
    if json.loads(line)["stream"] == "stdout":
        os.write(1, b'{"received":true}\n')
    else:
        os.write(2, b"one diagnostic\n")
"""

harness = r"""
import Foundation

func fail(_ message: String) -> Never {
    fputs("FAIL: \(message)\n", stderr)
    exit(1)
}
guard CommandLine.arguments.count == 4 else { fail("expected python + two workers") }

let backend = BackendProcess(
    executableURL: URL(fileURLWithPath: CommandLine.arguments[1]),
    maxStderrBufferBytes: 8_192,
    forceKillDelay: 0.1
)
var terminated = false
var delivered = [String]()
try backend.start(
    scriptURL: URL(fileURLWithPath: CommandLine.arguments[2]),
    gameID: "quiet-worker",
    onMessage: { _ in },
    onProtocolError: { fail("unexpected stdout protocol error: \($0)") },
    onStderr: { message in
        if message.utf8.count > 10_000 { fail("one stderr delivery exceeded its buffer budget") }
        delivered.append(message)
    },
    onTermination: { _ in terminated = true }
)

// Keep main blocked while the worker produces a burst: readiness callbacks
// can accumulate on the serial queue, and the worker then remains alive.
Thread.sleep(forTimeInterval: 0.5)
fputs("PHASE:before-flush\n", stderr)
backend.flushStderr { message in
    if message.utf8.count > 10_000 { fail("flushed stderr exceeded its buffer budget") }
    delivered.append(message)
}
fputs("PHASE:after-flush\n", stderr)
if delivered.isEmpty { fail("stderr burst was not delivered") }

backend.stop()
fputs("PHASE:after-stop\n", stderr)
let deadline = Date().addingTimeInterval(3)
while Date() < deadline && !terminated {
    RunLoop.current.run(until: Date().addingTimeInterval(0.01))
}
if !terminated { fail("persistent worker did not stop") }
print("backend_stderr_liveness_ok")

let probe = BackendProcess(executableURL: URL(fileURLWithPath: CommandLine.arguments[1]))
var ready = false
var replies = 0
var diagnostics = 0
var probeTerminated = false
try probe.start(
    scriptURL: URL(fileURLWithPath: CommandLine.arguments[3]),
    gameID: "backpressure-worker",
    onMessage: { message in
        if message["ready"] as? Bool == true { ready = true }
        if message["received"] as? Bool == true { replies += 1 }
    },
    onProtocolError: { fail("unexpected probe protocol error: \($0)") },
    onStderr: { _ in diagnostics += 1 },
    onTermination: { _ in probeTerminated = true }
)
func waitForProbe(_ reason: String, _ condition: () -> Bool) {
    let limit = Date().addingTimeInterval(3)
    while !condition() && Date() < limit {
        RunLoop.current.run(until: Date().addingTimeInterval(0.01))
    }
    if !condition() { fail(reason) }
}
waitForProbe("probe worker did not start") { ready }
var readAttempts = [Int]()
for index in 0..<3 {
    if index == 2 { probe.flushStderr { _ in } }
    let entered = DispatchSemaphore(value: 0)
    let release = DispatchSemaphore(value: 0)
    probe.holdReadsForTest(entered: entered, release: release)
    entered.wait()
    try probe.send(["stream": index == 0 ? "stdout" : "stderr"])
    // A finite stdout/stderr burst arrives while its consumer is occupied.
    // Readiness delivery must not enqueue unbounded work for those same bytes.
    Thread.sleep(forTimeInterval: 0.2)
    release.signal()
    readAttempts.append(probe.readAttemptsForTest())
    waitForProbe("probe delivery was starved behind readiness callbacks") {
        index == 0 ? replies == 1 : diagnostics == index
    }
}
probe.stop()
waitForProbe("probe worker did not stop") { probeTerminated }
if readAttempts.contains(where: { $0 > 8 }) {
    fail("readiness callbacks multiplied a finite burst: \(readAttempts)")
}
print("backend_readability_backpressure_ok readAttempts=\(readAttempts)")
"""

with tempfile.TemporaryDirectory(prefix="mgt-stderr-liveness-") as path:
    temp = Path(path)
    worker_path = temp / "worker.py"
    backpressure_path = temp / "backpressure.py"
    harness_path = temp / "main.swift"
    binary = temp / "stderr_liveness"
    worker_path.write_text(textwrap.dedent(worker), encoding="utf-8")
    backpressure_path.write_text(textwrap.dedent(backpressure_worker), encoding="utf-8")
    # Instrument only the compiled fixture copy, preserving the production API.
    production = (ROOT / "Sources/Core/Runtime/BackendProcess.swift").read_text()
    counter_anchor = "    private var buffer = Data()"
    read_anchor = "    private func readPipeIfReadableLocked(_ handle: FileHandle) -> Data? {"
    assert production.count(counter_anchor) == production.count(read_anchor) == 1
    production = production.replace(counter_anchor, counter_anchor + "\n    private var testReadAttempts = 0")
    production = production.replace(read_anchor, read_anchor + "\n        testReadAttempts += 1")
    probe_extension = r"""
extension BackendProcess {
    func holdReadsForTest(entered: DispatchSemaphore, release: DispatchSemaphore) {
        readQueue.async {
            self.testReadAttempts = 0
            entered.signal()
            release.wait()
        }
    }
    func readAttemptsForTest() -> Int { readQueue.sync { testReadAttempts } }
}
"""
    harness_path.write_text(production + probe_extension + textwrap.dedent(harness), encoding="utf-8")
    subprocess.run([
        SWIFTC,
        str(harness_path),
        "-o", str(binary),
    ], cwd=ROOT, check=True)
    try:
        result = subprocess.run(
            [str(binary), PYTHON, str(worker_path), str(backpressure_path)],
            cwd=ROOT, env=os.environ.copy(),
            capture_output=True, text=True, timeout=8,
        )
    except subprocess.TimeoutExpired as exc:
        print("BackendProcess liveness deadlock (last captured phases):")
        print((exc.stderr or b"").decode("utf-8", errors="replace"))
        raise
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        raise SystemExit(result.returncode)
    print(result.stdout.strip())
