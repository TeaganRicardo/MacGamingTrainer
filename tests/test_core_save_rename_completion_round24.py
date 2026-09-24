import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
PYTHON = shutil.which("python3")
if not SWIFTC or not PYTHON:
    raise SystemExit("swiftc/python3 required")

worker = r'''
import argparse, json, sys
p=argparse.ArgumentParser(); p.add_argument('--game', required=True); args=p.parse_args()
for raw in sys.stdin:
    req=json.loads(raw)
    command=req.get('command','')
    if command == 'core.save.list':
        name='old'
    elif command == 'core.save.rename':
        name=req.get('params',{}).get('name','')
    else:
        name='old'
    print(json.dumps({
        'type':'result','id':req['id'],'protocolVersion':5,
        'moduleProtocolVersion':5,'gameID':args.game,'ok':True,
        'result':{'snapshots':[{
            'id':'snap','name':name,'createdAt':'2026-09-20T15:00:00',
            'fileCount':1,'nameDetails':[],'hot':False,'path':'/tmp/snap',
            'valid':True,'error':''
        }],'pendingRestore':None},
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
struct Runner {
    static func main() throws {
        let args = CommandLine.arguments
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
        try session.start(
            descriptor: descriptor,
            backendScriptURL: URL(fileURLWithPath: args[2]),
            applyPayload: { _ in },
            resetGameState: {},
            log: { _ in },
            onStatusChange: { _ in }
        )
        let model = TrainerSaveManagerModel(session: session)
        model.refresh()
        guard waitUntil(1.0, { model.snapshots.first?.name == "old" && !model.busy }) else {
            fail("initial snapshot did not load")
        }

        var callbackName: String?
        model.rename(id: "snap", name: "new") { _ in
            callbackName = model.snapshots.first?.name
        }
        guard waitUntil(1.0, { callbackName != nil && !model.busy }) else {
            fail("rename completion did not run")
        }
        if callbackName != "new" {
            fail("rename completion ran before updated snapshot was visible: \(callbackName ?? "nil")")
        }
        session.stop()
        _ = waitUntil(1.0) { !session.isStarted }

        // Editing may begin while the backend is alive and commit after the
        // worker exits. The completion must still fire with failure so the
        // View can discard its optimistic pendingRenameNames entry.
        var stoppedCompletion: Bool?
        model.rename(id: "snap", name: "offline") { success in
            stoppedCompletion = success
        }
        guard waitUntil(0.2, { stoppedCompletion != nil }) else {
            fail("rename completion was lost when backend was already stopped")
        }
        if stoppedCompletion != false {
            fail("stopped-backend rename did not fail its completion")
        }
        if model.error != "后端未运行。" {
            fail("stopped-backend rename did not surface the expected model error")
        }

        print("core_save_rename_completion_round24_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix="mgt-save-rename-completion-") as td:
    td=Path(td)
    worker_path=td/"worker.py"
    main_path=td/"main.swift"
    binary=td/"rename_completion"
    worker_path.write_text(textwrap.dedent(worker), encoding="utf-8")
    main_path.write_text(textwrap.dedent(harness), encoding="utf-8")
    subprocess.run([
        SWIFTC,
        "-parse-as-library",
        str(ROOT/"Sources/Core/Runtime/BackendProcess.swift"),
        str(ROOT/"Sources/Core/Runtime/BackendClient.swift"),
        str(ROOT/"Sources/Core/Runtime/TrainerBackendSession.swift"),
        str(ROOT/"Sources/Core/Save/TrainerSaveTypes.swift"),
        str(ROOT/"Sources/Core/Save/TrainerSaveManagerModel.swift"),
        str(main_path),
        "-framework", "AppKit",
        "-o", str(binary),
    ], check=True, cwd=ROOT)
    proc=subprocess.run([str(binary), PYTHON, str(worker_path)], cwd=ROOT, text=True, capture_output=True, timeout=10)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    print(proc.stdout.strip())
