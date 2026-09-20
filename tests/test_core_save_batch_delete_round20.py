from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
PYTHON = shutil.which("python3")
if not SWIFTC or not PYTHON:
    raise SystemExit("swiftc/python3 required for batch delete test")

worker = r'''
import argparse, json, sys, time
p=argparse.ArgumentParser(); p.add_argument('--game', required=True); args=p.parse_args()
for raw in sys.stdin:
    req=json.loads(raw)
    command=req.get('command','')
    params=req.get('params',{})
    if command == 'core.save.delete':
        snapshot_id=params.get('snapshotId')
        time.sleep(0.05 if snapshot_id == 'a' else 0.45)
        result={'operation':{'deleted':True,'id':snapshot_id},'snapshots':[],'pendingRestore':None}
    else:
        result={'snapshots':[],'pendingRestore':None}
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
try session.start(
    descriptor: descriptor,
    backendScriptURL: URL(fileURLWithPath: args[2]),
    applyPayload: { _ in },
    resetGameState: {},
    log: { _ in },
    onStatusChange: { _ in }
)
let model = TrainerSaveManagerModel(session: session)
model.delete(ids: Set(["b", "a"]))
if !model.busy { fail("batch delete did not enter busy state") }

RunLoop.current.run(until: Date().addingTimeInterval(0.20))
if !model.busy { fail("batch delete became idle between queued deletions") }
if !model.notice.isEmpty { fail("batch delete announced completion too early") }

if !waitUntil(2.0, { !model.busy && model.notice.contains("2") }) {
    fail("batch delete did not finish coherently: busy=\(model.busy) notice=\(model.notice)")
}
session.stop()
_ = waitUntil(1.0) { !session.isStarted }
print("core_save_batch_delete_round20_ok")
'''

with tempfile.TemporaryDirectory(prefix="mgt-save-batch-delete-") as td:
    td=Path(td)
    worker_path=td/"worker.py"
    main_path=td/"main.swift"
    binary=td/"batch_delete"
    worker_path.write_text(textwrap.dedent(worker), encoding="utf-8")
    main_path.write_text(textwrap.dedent(harness), encoding="utf-8")
    subprocess.run([
        SWIFTC,
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
