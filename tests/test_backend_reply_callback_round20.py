import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path
from swift_test_compiler import SWIFT_CORE_MODULE, SwiftModule, compile_swift_test

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
    if command == 'fail':
        print(json.dumps({
            'type':'result','id':req['id'],'protocolVersion':6,
            'moduleProtocolVersion':5,'gameID':args.game,'ok':False,
            'error': {
                'code':'fixture_failure',
                'presentation':'Visible failure',
                'diagnostic':'developer detail',
                'recoveryPath':'/tmp/recovery-copy',
            },
        }), flush=True)
        continue
    result = {'snapshots':[{'id':'snap-1'}]} if command == 'core.save.list' else {'connected':True}
    print(json.dumps({
        'type':'result','id':req['id'],'protocolVersion':6,
        'moduleProtocolVersion':5,'gameID':args.game,'ok':True,'result':result,
    }), flush=True)
'''

# Stands in for Core's GameModuleDescriptor (Host/TrainerGameModule.swift),
# which TrainerBackendSession reads; it compiles into TrainerCore.
descriptor_stub = r'''
package struct GameModuleDescriptor {
    package let id: String
    package let expectedHostProtocolVersion: Int
    package let expectedModuleProtocolVersion: Int

    package init(id: String, expectedHostProtocolVersion: Int, expectedModuleProtocolVersion: Int) {
        self.id = id
        self.expectedHostProtocolVersion = expectedHostProtocolVersion
        self.expectedModuleProtocolVersion = expectedModuleProtocolVersion
    }
}
'''

harness = r'''
import Foundation

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

// A fresh Python worker may spend meaningful time starting under load. These
// waits observe callback ordering, not startup latency, so keep startup noise
// outside the assertion budget.
let waitBudget: TimeInterval = 4.0

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
            id: "test",
            expectedHostProtocolVersion: 6,
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
        if !waitUntil(waitBudget, { events.count == 2 }) { fail("core callback did not complete") }
        if events != ["reply", "completion"] { fail("reply/completion order changed: \(events)") }
        if snapshots != 1 { fail("request-specific reply did not receive Core payload") }
        if !applied.isEmpty { fail("Core payload leaked into game applyPayload") }

        var failureReply: BackendReply? = nil
        var failureDone: Bool? = nil
        session.send(
            "fail",
            operation: "failure",
            reply: { failureReply = $0 },
            completion: { failureDone = $0 }
        )
        if !waitUntil(waitBudget, { failureReply != nil && failureDone != nil }) { fail("failure callback did not complete") }
        if failureDone != false { fail("failure completion unexpectedly succeeded") }
        guard let failure = failureReply?.failure else { fail("failure value missing") }
        if failure.code != "fixture_failure" { fail("wrong failure code") }
        if failure.presentation != "Visible failure" { fail("wrong failure presentation") }
        if failure.diagnostic != "developer detail" { fail("wrong failure diagnostic") }
        if failure.recoveryPath != "/tmp/recovery-copy" { fail("wrong recovery path") }

        var gameDone = false
        session.send("status", operation: "status", completion: { ok in gameDone = ok })
        if !waitUntil(waitBudget, { gameDone && applied.count == 1 }) { fail("game payload was not applied") }
        if applied[0]["connected"] as? Bool != true { fail("wrong game payload") }

        session.stop()
        _ = waitUntil(waitBudget) { !session.isStarted }
        print("backend_reply_callback_round20_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix="mgt-reply-round20-") as td:
    td = Path(td)
    worker_path = td / "worker.py"
    main_path = td / "main.swift"
    stub_path = td / "GameModuleDescriptorStub.swift"
    binary = td / "reply_test"
    worker_path.write_text(textwrap.dedent(worker), encoding="utf-8")
    main_path.write_text(textwrap.dedent(harness), encoding="utf-8")
    stub_path.write_text(descriptor_stub, encoding="utf-8")
    # Portable: the Linux lane has no SwiftUI/AppKit, so this compiles only these
    # Foundation-level files and a stub for GameModuleDescriptor.
    compile_swift_test(
        modules=[SwiftModule(SWIFT_CORE_MODULE, [
            ROOT / "Sources/Core/Runtime/TrainerJSON.swift", ROOT / "Sources/Core/Runtime/BackendProcess.swift",
            ROOT / "Sources/Core/Runtime/BackendClient.swift",
            ROOT / "Sources/Core/Runtime/TrainerBackendSession.swift",
            stub_path,
        ])],
        harness_sources=[main_path], output=binary, swiftc=SWIFTC, cwd=ROOT,
    )
    proc = subprocess.run([str(binary), PYTHON, str(worker_path)], cwd=ROOT, text=True, capture_output=True, timeout=10)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    print(proc.stdout.strip())
