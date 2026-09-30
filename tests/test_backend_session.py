import os
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
session_source = (ROOT / "Sources/Core/Runtime/TrainerBackendSession.swift").read_text(encoding="utf-8")
assert "后端已退出（状态 \\(exitStatus)）" not in session_source
assert "后端退出 status=\\(exitStatus)" in session_source

SWIFTC = shutil.which("swiftc")
PYTHON = shutil.which("python3")
if not SWIFTC or not PYTHON:
    raise SystemExit("swiftc/python3 required for backend session test")

worker = r"""
import argparse, json, os, sys, time

parser = argparse.ArgumentParser()
parser.add_argument("--game", required=True)
args = parser.parse_args()
log_path = os.environ.get("MGT_BACKEND_SESSION_LOG")

def record(command):
    if not log_path:
        return
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write(command + "\n")
        handle.flush()

for raw in sys.stdin:
    request = json.loads(raw)
    command = request.get("command", "")
    record(command)

    if command == "crash":
        sys.exit(7)
    if command == "hang":
        time.sleep(5)
        continue
    if command == "fail":
        print(json.dumps({
            "type": "result",
            "id": request.get("id", ""),
            "protocolVersion": 6,
            "moduleProtocolVersion": 5,
            "gameID": args.game,
            "ok": False,
            "error": {
                "code": "fixture_failure",
                "presentation": "Visible failure",
                "diagnostic": "developer detail",
                "recoveryPath": "/tmp/recovery-copy",
            },
        }), flush=True)
        continue

    if command == "core.save.list":
        result = {"snapshots": [{"id": "snap-1"}]}
    else:
        result = {"connected": True, "command": command}

    print(json.dumps({
        "type": "result",
        "id": request.get("id", ""),
        "protocolVersion": 6,
        "moduleProtocolVersion": 5,
        "gameID": args.game,
        "ok": True,
        "result": result,
    }), flush=True)
"""

harness = r"""
import Foundation

struct GameModuleDescriptor {
    let backendGameID: String
    let expectedHostProtocolVersion: Int
    let expectedModuleProtocolVersion: Int
}

func fail(_ message: String) -> Never {
    fputs("FAIL: \(message)\n", stderr)
    exit(1)
}

func waitUntil(_ seconds: TimeInterval, _ predicate: @escaping () -> Bool) -> Bool {
    let deadline = Date().addingTimeInterval(seconds)
    while Date() < deadline {
        if predicate() { return true }
        RunLoop.current.run(until: Date().addingTimeInterval(0.01))
    }
    return predicate()
}

let args = CommandLine.arguments
if args.count != 2 { fail("expected worker path") }
let worker = args[1]
let descriptor = GameModuleDescriptor(
    backendGameID: "test",
    expectedHostProtocolVersion: 6,
    expectedModuleProtocolVersion: 5
)
let backendProcess = BackendProcess(
    executableURL: URL(fileURLWithPath: ProcessInfo.processInfo.environment["MGT_BACKEND_SESSION_PYTHON"]!),
    argumentsPrefix: ["-u"],
    maxStdoutBufferBytes: 1_048_576,
    forceKillDelay: 0.10
)
let session = TrainerBackendSession(client: BackendClient(process: backendProcess))
var states: [TrainerBackendStatus] = []
var appliedPayloads: [[String: Any]] = []

try session.start(
    descriptor: descriptor,
    backendScriptURL: URL(fileURLWithPath: worker),
    applyPayload: { appliedPayloads.append($0) },
    resetGameState: {},
    log: { _ in },
    onStatusChange: { states.append($0) }
)
if !session.currentStatus.backendAvailable { fail("backend not available after start") }

// Core request-specific replies are delivered before completion and never leak
// through the game payload projection.
do {
    var events: [String] = []
    var snapshots = 0
    session.send(
        "core.save.list",
        operation: "list",
        reply: { reply in
            snapshots = (reply.result?["snapshots"] as? [[String: Any]])?.count ?? 0
            events.append("reply")
        },
        completion: { ok in
            if !ok { fail("core request failed") }
            events.append("completion")
        }
    )
    if !waitUntil(1.0, { events.count == 2 }) { fail("core callback did not complete") }
    if events != ["reply", "completion"] { fail("reply/completion order changed: \(events)") }
    if snapshots != 1 { fail("request-specific reply did not receive Core payload") }
    if !appliedPayloads.isEmpty { fail("Core payload leaked into game applyPayload") }
}

// Structured backend failures remain available to request-specific callbacks.
do {
    var failureReply: BackendReply? = nil
    var failureDone: Bool? = nil
    session.send(
        "fail",
        operation: "failure",
        reply: { failureReply = $0 },
        completion: { failureDone = $0 }
    )
    if !waitUntil(1.0, { failureReply != nil && failureDone != nil }) {
        fail("failure callback did not complete")
    }
    if failureDone != false { fail("failure completion unexpectedly succeeded") }
    guard let failure = failureReply?.failure else { fail("failure value missing") }
    if failure.code != "fixture_failure" { fail("wrong failure code") }
    if failure.presentation != "Visible failure" { fail("wrong failure presentation") }
    if failure.diagnostic != "developer detail" { fail("wrong failure diagnostic") }
    if failure.recoveryPath != "/tmp/recovery-copy" { fail("wrong recovery path") }
}

// Ordinary game payloads still flow through applyPayload.
do {
    var gameDone = false
    session.send("status", operation: "status", completion: { ok in gameDone = ok })
    if !waitUntil(1.0, { gameDone && appliedPayloads.count == 1 }) {
        fail("game payload was not applied")
    }
    if appliedPayloads[0]["connected"] as? Bool != true { fail("wrong game payload") }
    if appliedPayloads[0]["command"] as? String != "status" { fail("wrong game command payload") }
}

func waitForRecovery(after stateIndex: Int, notice: String) {
    var sawUnavailable = false
    let ok = waitUntil(3.0) {
        if states.dropFirst(stateIndex).contains(where: { !$0.backendAvailable }) {
            sawUnavailable = true
        }
        return sawUnavailable
            && session.currentStatus.backendAvailable
            && session.currentStatus.notice.contains(notice)
            && !session.currentStatus.busy
    }
    if !ok { fail("recovery did not complete: \(notice) status=\(session.currentStatus)") }
}

// A hard child crash is recovered globally without module-specific restart code.
do {
    let startIndex = states.count
    var crashCompletion: Bool? = nil
    session.send("crash", operation: "crash", timeout: 1.0, completion: { crashCompletion = $0 })
    waitForRecovery(after: startIndex, notice: "host.backend.notice.recovered")
    if crashCompletion != false { fail("crash request completion must fail") }

    var ping: Bool? = nil
    session.send("ping-after-crash", operation: "ping", timeout: 1.0, completion: { ping = $0 })
    if !waitUntil(1.0, { ping != nil }) || ping != true {
        fail("recovered backend cannot accept request")
    }
}

// A timeout is outcome-unknown: recover the worker but never replay the request.
do {
    let startIndex = states.count
    var hangCompletion: Bool? = nil
    session.send("hang", operation: "hang", timeout: 0.15, completion: { hangCompletion = $0 })
    waitForRecovery(after: startIndex, notice: "host.backend.notice.recovered")
    if hangCompletion != false { fail("timeout request completion must fail") }

    var ping: Bool? = nil
    session.send("ping-after-timeout", operation: "ping", timeout: 1.0, completion: { ping = $0 })
    if !waitUntil(1.0, { ping != nil }) || ping != true {
        fail("timeout recovery backend cannot accept request")
    }
}

// Explicit restart works while the worker is already running.
do {
    let startIndex = states.count
    session.restart()
    waitForRecovery(after: startIndex, notice: "host.backend.notice.restarted")

    var ping: Bool? = nil
    session.send("ping-after-manual", operation: "ping", timeout: 1.0, completion: { ping = $0 })
    if !waitUntil(1.0, { ping != nil }) || ping != true {
        fail("manual restart backend cannot accept request")
    }
}

session.stop()
_ = waitUntil(2.0) { !session.isStarted }

// Sending after the worker is unavailable settles terminally without latching
// a recovery state that has no owner.
do {
    var unavailableCompletion: Bool? = nil
    session.send(
        "ping-after-stop",
        operation: "ping",
        timeout: 1.0,
        completion: { unavailableCompletion = $0 }
    )
    if !waitUntil(1.0, { unavailableCompletion != nil }) || unavailableCompletion != false {
        fail("unavailable send must fail exactly once")
    }
    let unavailable = session.currentStatus
    if unavailable.backendAvailable { fail("stopped backend reported available") }
    if unavailable.busy { fail("unavailable send latched busy") }
    if unavailable.errorCode != "backend_unavailable" {
        fail("unavailable send lost stable error code: \(String(describing: unavailable.errorCode))")
    }
    if unavailable.error != "host.backend.error.unavailable" {
        fail("unavailable send lost Host presentation key: \(unavailable.error)")
    }
    if !unavailable.operation.key.isEmpty {
        fail("unavailable send retained a recovery operation: \(unavailable.operation.key)")
    }
    if unavailable.notice == "host.backend.notice.recovering" {
        fail("unavailable send advertised recovery with no scheduled transition")
    }
}

print("backend_session_ok")
"""

with tempfile.TemporaryDirectory(prefix="mgt-backend-session-") as temporary:
    temporary = Path(temporary)
    worker_path = temporary / "fake_backend.py"
    main_path = temporary / "main.swift"
    binary = temporary / "session-test"
    command_log = temporary / "commands.log"

    worker_path.write_text(textwrap.dedent(worker), encoding="utf-8")
    main_path.write_text(textwrap.dedent(harness), encoding="utf-8")
    subprocess.run([
        SWIFTC,
        str(ROOT / "Sources/Core/Runtime/BackendProcess.swift"),
        str(ROOT / "Sources/Core/Runtime/BackendClient.swift"),
        str(ROOT / "Sources/Core/Runtime/TrainerBackendSession.swift"),
        str(main_path),
        "-o",
        str(binary),
    ], check=True, cwd=ROOT)

    env = os.environ.copy()
    env["MGT_BACKEND_SESSION_LOG"] = str(command_log)
    env["MGT_BACKEND_SESSION_PYTHON"] = PYTHON
    process = subprocess.run(
        [str(binary), str(worker_path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=20,
        env=env,
    )
    if process.returncode != 0:
        print(process.stdout)
        print(process.stderr)
        raise SystemExit(process.returncode)

    commands = command_log.read_text(encoding="utf-8").splitlines()
    if commands.count("hang") != 1:
        raise AssertionError(f"outcome-unknown timeout request was replayed: {commands!r}")
    if commands.count("crash") != 1:
        raise AssertionError(f"crash request was replayed: {commands!r}")
    if "ping-after-stop" in commands:
        raise AssertionError(f"unavailable request reached a stopped worker: {commands!r}")
    for required in ("ping-after-crash", "ping-after-timeout", "ping-after-manual"):
        if commands.count(required) != 1:
            raise AssertionError(f"missing/duplicate post-recovery request {required}: {commands!r}")
    if commands.count("core.save.list") != 1 or commands.count("fail") != 1 or commands.count("status") != 1:
        raise AssertionError(f"callback/routing commands were not exercised exactly once: {commands!r}")

    print(process.stdout.strip())
