from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
PYTHON = shutil.which("python3")
if not SWIFTC or not PYTHON:
    raise SystemExit("swiftc/python3 required for backend reply callback test")

worker = r'''
import argparse, json, sys
p=argparse.ArgumentParser(); p.add_argument('--game', required=True); args=p.parse_args()
for raw in sys.stdin:
    req=json.loads(raw)
    command=req['command']
    result = {'snapshots':[{'id':'snap-1'}]} if command == 'core.save.list' else {'connected':True}
    print(json.dumps({
        'type':'result','id':req['id'],'protocolVersion':5,
        'moduleProtocolVersion':5,'gameID':args.game,'ok':True,'result':result,
    }), flush=True)
'''

harness = r'''
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

@main
struct Main {
    static func main() throws {
        let args = CommandLine.arguments
        if args.count != 3 { fail("expected python + worker") }
        let process = BackendProcess(
            executableURL: URL(fileURLWithPath: args[1]),
            argumentsPrefix: ["-u"],
            forceKillDelay: 0.10
        )
        let session = TrainerBackendSession(client: BackendClient(process: process))
        let descriptor = GameModuleDescriptor(
            backendGameID: "test",
            expectedHostProtocolVersion: 5,
            expectedModuleProtocolVersion: 5
        )

        var applied: [[String: Any]] = []
        try session.start(
            descriptor: descriptor,
            backendScriptURL: URL(fileURLWithPath: args[2]),
            applyPayload: { applied.append($0) },
            resetGameState: {},
            log: { _ in },
            onStatusChange: { _ in }
        )

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
        if !applied.isEmpty { fail("Core payload leaked into game applyPayload") }

        var gameDone = false
        session.send("status", operation: "status", completion: { ok in gameDone = ok })
        if !waitUntil(1.0, { gameDone && applied.count == 1 }) { fail("game payload was not applied") }
        if applied[0]["connected"] as? Bool != true { fail("wrong game payload") }

        session.stop()
        _ = waitUntil(1.0) { !session.isStarted }
        print("backend_reply_callback_round20_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix="mgt-reply-round20-") as td:
    td = Path(td)
    worker_path = td / "worker.py"
    main_path = td / "main.swift"
    binary = td / "reply_test"
    worker_path.write_text(textwrap.dedent(worker), encoding="utf-8")
    main_path.write_text(textwrap.dedent(harness), encoding="utf-8")
    subprocess.run([
        SWIFTC,
        "-parse-as-library",
        str(ROOT / "Sources/Core/Runtime/BackendProcess.swift"),
        str(ROOT / "Sources/Core/Runtime/BackendClient.swift"),
        str(ROOT / "Sources/Core/Runtime/TrainerBackendSession.swift"),
        str(main_path),
        "-o", str(binary),
    ], check=True, cwd=ROOT)
    proc = subprocess.run([str(binary), PYTHON, str(worker_path)], cwd=ROOT, text=True, capture_output=True, timeout=10)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    print(proc.stdout.strip())
