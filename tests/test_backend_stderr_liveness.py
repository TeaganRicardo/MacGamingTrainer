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

harness = r"""
import Foundation

func fail(_ message: String) -> Never {
    fputs("FAIL: \(message)\n", stderr)
    exit(1)
}
guard CommandLine.arguments.count == 3 else { fail("expected python + worker") }

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
"""

with tempfile.TemporaryDirectory(prefix="mgt-stderr-liveness-") as path:
    temp = Path(path)
    worker_path = temp / "worker.py"
    harness_path = temp / "main.swift"
    binary = temp / "stderr_liveness"
    worker_path.write_text(textwrap.dedent(worker), encoding="utf-8")
    harness_path.write_text(textwrap.dedent(harness), encoding="utf-8")
    subprocess.run([
        SWIFTC,
        str(ROOT / "Sources/Core/Runtime/BackendProcess.swift"),
        str(harness_path),
        "-o", str(binary),
    ], cwd=ROOT, check=True)
    try:
        result = subprocess.run(
            [str(binary), PYTHON, str(worker_path)],
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
