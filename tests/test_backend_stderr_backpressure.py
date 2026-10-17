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
    raise SystemExit("swiftc/python3 required for backend stderr backpressure test")

worker = r"""
import argparse
import sys

p = argparse.ArgumentParser()
p.add_argument("--game", required=True)
p.parse_args()

sys.stderr.write("X" * 4_000_000)
sys.stderr.flush()
"""

harness = r"""
import Foundation

func fail(_ message: String) -> Never {
    fputs("FAIL: \(message)\n", stderr)
    exit(1)
}

guard CommandLine.arguments.count == 3 else { fail("expected python + worker") }
let process = BackendProcess(
    executableURL: URL(fileURLWithPath: CommandLine.arguments[1]),
    argumentsPrefix: ["-u"],
    maxStdoutBufferBytes: 1_048_576,
    maxStderrBufferBytes: 65_536,
    forceKillDelay: 0.10
)

var deliveredBytes = 0
var callbackCount = 0
var sawOverflowMarker = false
var terminated = false

try process.start(
    scriptURL: URL(fileURLWithPath: CommandLine.arguments[2]),
    gameID: "stderr-fixture",
    onMessage: { _ in },
    onProtocolError: { _ in },
    onStderr: { message in
        callbackCount += 1
        deliveredBytes += message.utf8.count
        if message.contains("stderr overflow droppedBytes=") {
            sawOverflowMarker = true
        }
    },
    onTermination: { _ in terminated = true }
)

// Intentionally block the main queue while the child emits a multi-megabyte
// burst. BackendProcess must coalesce and bound pending stderr rather than
// enqueueing one unbounded main-thread closure per pipe read.
Thread.sleep(forTimeInterval: 1.0)

// Diagnostics export runs on the main thread. An explicit flush must be able
// to drain the stderr queue before the normal scheduled main-thread delivery.
process.flushStderr { message in
    callbackCount += 1
    deliveredBytes += message.utf8.count
    if message.contains("stderr overflow droppedBytes=") {
        sawOverflowMarker = true
    }
}
if callbackCount != 1 { fail("explicit stderr flush did not deliver exactly once") }

let deadline = Date().addingTimeInterval(3.0)
while Date() < deadline && !terminated {
    RunLoop.current.run(until: Date().addingTimeInterval(0.01))
}
if !terminated { fail("stderr fixture did not terminate") }
if deliveredBytes > 70_000 {
    fail("pending stderr exceeded configured bound: \(deliveredBytes)")
}
if callbackCount > 2 {
    fail("stderr burst was not coalesced: callbacks=\(callbackCount)")
}
if !sawOverflowMarker {
    fail("stderr truncation was not made explicit")
}

print("backend_stderr_backpressure_ok")
"""

with tempfile.TemporaryDirectory(prefix="mgt-backend-stderr-") as td:
    td = Path(td)
    worker_path = td / "worker.py"
    main_path = td / "main.swift"
    binary = td / "stderr_test"
    worker_path.write_text(textwrap.dedent(worker), encoding="utf-8")
    main_path.write_text(textwrap.dedent(harness), encoding="utf-8")
    subprocess.run([
        SWIFTC,
        str(ROOT / "Sources/Core/Runtime/BackendProcess.swift"),
        str(main_path),
        "-o", str(binary),
    ], check=True, cwd=ROOT)
    proc = subprocess.run(
        [str(binary), PYTHON, str(worker_path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=10,
        env=os.environ.copy(),
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    print(proc.stdout.strip())
