import os
import shutil
import signal
import subprocess
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
PYTHON = shutil.which("python3")
if not SWIFTC or not PYTHON:
    raise SystemExit("swiftc/python3 required for backend pipe lifetime test")

worker = r'''
import argparse, json, os, signal, sys, time
from pathlib import Path
from threading import Event, Thread

p = argparse.ArgumentParser()
p.add_argument('--game', required=True)
mode = p.parse_args().game
if mode in {'inherited', 'continuous'}:
    child = os.fork()
    if child == 0:
        # Retain stdio, not Foundation's private process-exit socket.
        os.closerange(3, os.sysconf('SC_OPEN_MAX'))
        if mode == 'continuous':
            while not Path(__file__ + '.write').exists():
                time.sleep(0.001)
            started = Event()
            def write_forever():
                try:
                    while True:
                        os.write(2, b'x' * 65536)
                        started.set()
                except BrokenPipeError:
                    pass
            for _ in range(4):
                Thread(target=write_forever, daemon=True).start()
            started.wait()
            Path(__file__ + '.writing').touch()
        time.sleep(60)
        os._exit(0)
    with Path(__file__ + '.child').open('a') as stream:
        stream.write(str(child) + '\n')
    print(json.dumps({'mode': mode, 'child': child}), flush=True)
    sys.stderr.write('tail-' + mode + '\n')
    sys.stderr.flush()
    if mode == 'continuous':
        Path(__file__ + '.write').touch()
        while not Path(__file__ + '.writing').exists():
            time.sleep(0.001)
    os._exit(7)
if mode == 'stop':
    def ignore_term(*_):
        sys.stderr.write('tail-stop\n')
        sys.stderr.flush()
    signal.signal(signal.SIGTERM, ignore_term)
    print(json.dumps({'mode': mode}), flush=True)
    while True:
        time.sleep(1)
for sequence in range(32):
    print(json.dumps({'mode': mode, 'sequence': sequence, 'payload': 'x' * 512}))
sys.stdout.flush()
sys.stderr.write('tail-' + mode + '\n')
sys.stderr.flush()
os._exit(7)
'''

harness = r'''
import Foundation
#if canImport(Darwin)
import Darwin
#elseif canImport(Glibc)
import Glibc
#endif

func fail(_ message: String) -> Never {
    fputs("FAIL: \(message)\n", stderr)
    exit(1)
}
func waitUntil(_ predicate: () -> Bool) -> Bool {
    let deadline = Date().addingTimeInterval(4)
    while Date() < deadline {
        if predicate() { return true }
        RunLoop.current.run(until: Date().addingTimeInterval(0.01))
    }
    return predicate()
}

let python = CommandLine.arguments[1], worker = CommandLine.arguments[2]
let process = BackendProcess(executableURL: URL(fileURLWithPath: python), forceKillDelay: 0.1)
var inheritedChildren = [Int32]()
defer { for child in inheritedChildren { _ = kill(child, SIGKILL) } }

// Reuse the same owner immediately after each termination. All callbacks must
// belong to that start, with complete stdout/stderr preceding termination.
var modes = ["exit", "inherited", "restart", "stop", "after-stop"]
modes.insert("continuous", at: 3)
for mode in modes {
    var messages = [[String: Any]]()
    var stderrText = ""
    var terminated = false
    var stopSent = false
    try process.start(
        scriptURL: URL(fileURLWithPath: worker), gameID: mode,
        onMessage: { message in
            if terminated { fail("stdout delivered after termination: \(mode)") }
            if message["mode"] as? String != mode { fail("stdout crossed process lifetime") }
            messages.append(message)
            if mode == "stop" && !stopSent {
                stopSent = true
                process.stop()
            }
        },
        onProtocolError: { fail($0) },
        onStderr: { message in
            if terminated { fail("stderr delivered after termination: \(mode)") }
            stderrText += message
        },
        onTermination: { status in
            if !stderrText.contains("tail-" + mode) { fail("stderr tail missing: \(mode)") }
            if mode == "inherited" || mode == "continuous" {
                guard let child = messages.first?["child"] as? Int32 else { fail("child identity missing") }
                inheritedChildren.append(child)
                if kill(child, 0) != 0 { fail("inherited writer closed before termination") }
            } else if mode != "stop" {
                if messages.compactMap({ $0["sequence"] as? Int }) != Array(0..<32) {
                    fail("rapid-exit stdout tail missing: \(mode)")
                }
            }
            if status != (mode == "stop" ? SIGKILL : 7) { fail("unexpected termination status") }
            terminated = true
        }
    )
    if !waitUntil({ terminated }) { fail("termination blocked by pipe writer: \(mode)") }
    if process.isStarted { fail("old process still owned after termination") }
}

// Readers installed before a failed spawn must also unwind, without needing EOF
// from the still-owned parent-side pipe writer.
let missing = BackendProcess(executableURL: URL(fileURLWithPath: worker + ".missing"))
do {
    try missing.start(scriptURL: URL(fileURLWithPath: worker), gameID: "missing",
        onMessage: { _ in fail("failed spawn produced a message") },
        onProtocolError: { fail($0) }, onStderr: { _ in },
        onTermination: { _ in fail("failed spawn reported termination") })
    fail("missing executable started")
} catch {
    if missing.isStarted { fail("failed spawn retained process ownership") }
}
print("backend_pipe_lifetime_ok")
'''

with tempfile.TemporaryDirectory(prefix="mgt-backend-pipe-") as directory:
    directory = Path(directory)
    worker_path = directory / "worker.py"
    main_path = directory / "main.swift"
    binary = directory / "pipe_test"
    worker_path.write_text(textwrap.dedent(worker), encoding="utf-8")
    main_path.write_text(textwrap.dedent(harness), encoding="utf-8")
    subprocess.run([
        SWIFTC, str(ROOT / "Sources/Core/Runtime/BackendProcess.swift"),
        str(main_path), "-o", str(binary),
    ], check=True, cwd=ROOT)
    try:
        result = subprocess.run(
            [str(binary), PYTHON, str(worker_path)], cwd=ROOT,
            capture_output=True, text=True, timeout=25,
        )
        if result.returncode:
            print(result.stdout)
            print(result.stderr)
            raise SystemExit(result.returncode)
        print(result.stdout.strip())
    finally:
        child_path = Path(str(worker_path) + ".child")
        if child_path.exists():
            for child in child_path.read_text().splitlines():
                try:
                    os.kill(int(child), signal.SIGKILL)
                except ProcessLookupError:
                    pass
