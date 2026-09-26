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
    raise SystemExit("swiftc/python3 required for Save Manager behavior tests")

worker = r'''
import argparse, json, pathlib, sys, time
p=argparse.ArgumentParser(); p.add_argument('--game', required=True); args=p.parse_args()
for raw in sys.stdin:
    req=json.loads(raw)
    command=req.get('command','')
    params=req.get('params',{})
    recovery=pathlib.Path.home()/'Library/Application Support/MacGamingTrainer/test/transactions/.rollback-fixture'
    result={'snapshots': [], 'pendingRestore': None, 'recoveryPaths': [str(recovery)]}
    if command == 'core.save.list':
        time.sleep(0.10)
    elif command == 'core.save.backup':
        time.sleep(0.55)
    elif command == 'core.save.delete':
        snapshot_id=params.get('snapshotId')
        time.sleep(0.45 if snapshot_id == 'b' else 0.05)
        result['operation']={'deleted': True, 'id': snapshot_id}
    elif command == 'core.save.open_folder':
        if params.get('snapshotId') == 'error':
            print(json.dumps({
                'type':'result','id':req['id'],'protocolVersion':6,
                'moduleProtocolVersion':5,'gameID':args.game,'ok':False,
                'error':{'code':'unsafe_storage','message':'后端拒绝显示存档'},
                'result':{'folder':str(pathlib.Path(__file__).parent)},
            }), flush=True)
            continue
        result['folder']=str(pathlib.Path(__file__).parent)
    print(json.dumps({
        'type':'result','id':req['id'],'protocolVersion':6,
        'moduleProtocolVersion':5,'gameID':args.game,'ok':True,'result':result,
    }), flush=True)
'''

lifecycle_harness = r'''
import Foundation
import Combine

struct GameModuleDescriptor {
    let backendGameID: String
    let expectedHostProtocolVersion: Int
    let expectedModuleProtocolVersion: Int
}

func fail(_ message: String) -> Never {
    fputs(message, stderr)
    fputc(10, stderr)
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
        if args.count != 4 { fail("expected python + worker + recovery fixture") }
        let process = BackendProcess(
            executableURL: URL(fileURLWithPath: args[1]),
            argumentsPrefix: ["-u"],
            forceKillDelay: 0.10
        )
        let session = TrainerBackendSession(client: BackendClient(process: process))
        let descriptor = GameModuleDescriptor(
            backendGameID: "test",
            expectedHostProtocolVersion: 6,
            expectedModuleProtocolVersion: 5
        )
        var dispatchedDeletes = 0
        try session.start(
            descriptor: descriptor,
            backendScriptURL: URL(fileURLWithPath: args[2]),
            applyPayload: { _ in },
            resetGameState: {},
            log: { message in
                if message.hasPrefix("请求 core.save.delete ·") { dispatchedDeletes += 1 }
            },
            onStatusChange: { _ in }
        )
        let model = TrainerSaveManagerModel(session: session)
        model.refresh()
        model.backup()
        if !model.busy { fail("concurrent Save requests did not enter busy state") }
        RunLoop.current.run(until: Date().addingTimeInterval(0.25))
        if !model.busy { fail("busy cleared while a concurrent Save request was still pending") }
        if !waitUntil(2.0, { !model.busy }) { fail("concurrent Save requests did not finish") }
        let recoveryPath = args[3]
        if model.recoveryPaths != [recoveryPath] { fail("alternate HOME hid a valid recovery copy") }
        if TrainerSavePathValidator.validatedDirectoryURL(for: recoveryPath)?.path != recoveryPath {
            fail("alternate HOME rejected a valid directory reveal")
        }

        var trackingDeleteChain = false
        var prematureIdle = false
        var trackingQueuedRequest = false
        var idleWhileQueued = false
        let observation = model.$busy.sink { value in
            if trackingDeleteChain && !value { prematureIdle = true }
            if trackingQueuedRequest && !value { idleWhileQueued = true }
        }
        trackingDeleteChain = true
        model.delete(ids: Set(["b", "a"]))
        if !waitUntil(1.0, { dispatchedDeletes == 2 }) {
            fail("second delete request did not start")
        }
        if prematureIdle { fail("busy published idle between recursive delete requests") }
        if !model.busy { fail("recursive delete chain became idle before its last request completed") }
        trackingDeleteChain = false
        model.refresh() // Queue another request behind the final delete.
        trackingQueuedRequest = true
        if !waitUntil(2.0, { model.notice.contains("2") }) {
            fail("recursive delete chain did not finish coherently")
        }
        trackingQueuedRequest = false
        if idleWhileQueued { fail("busy published idle while a queued Save request was still pending") }
        if !model.busy { fail("busy cleared while a queued Save request was still pending") }
        if !waitUntil(2.0, { !model.busy }) { fail("queued Save request did not finish") }
        observation.cancel()

        model.reveal(id: "error")
        if !waitUntil(2.0, { !model.busy }) { fail("failed reveal did not finish") }
        if model.error != "后端拒绝显示存档" { fail("failed reveal masked backend error") }
        model.reveal(id: "unsafe")
        if !waitUntil(2.0, { !model.busy }) { fail("unsafe reveal did not finish") }
        if model.error != "后端返回的存档目录无效或不安全。" {
            fail("unsafe backend folder was not rejected")
        }

        model.backup()
        model.refresh()
        if !model.busy { fail("concurrent Save requests did not start before restart") }
        session.restart()
        if model.busy { fail("restarting the backend left cancelled Save requests busy") }
        if !model.error.contains("存档操作未完成") { fail("restart did not surface request failure") }
        if !waitUntil(3.0, { session.currentStatus.notice == "后端已重启" && session.isRunning }) {
            fail("backend did not recover after restart")
        }
        model.refresh()
        if !waitUntil(2.0, { !model.busy }) { fail("Save requests did not recover after restart") }
        model.backup()
        if !model.busy { fail("backup did not start before stop") }
        session.stop()
        _ = waitUntil(1.0) { !session.isStarted }
        if model.busy { fail("stopping the backend left Save busy") }
        if !model.error.contains("存档操作未完成") { fail("stopped request did not surface failure") }
        print("core_save_manager_lifecycle_u01_ok")
    }
}
'''

path_harness = r'''
import Foundation

func fail(_ message: String) -> Never {
    fputs(message, stderr)
    fputc(10, stderr)
    exit(1)
}

func expect(_ accepted: Bool, _ message: String) {
    if !accepted { fail(message) }
}

@main
struct Runner {
    static func main() throws {
        let args = CommandLine.arguments
        if args.count != 3 { fail("expected fixture root + outside directory") }
        let root = URL(fileURLWithPath: args[1], isDirectory: true)
        let outside = URL(fileURLWithPath: args[2], isDirectory: true)
        let manager = FileManager.default
        let insideDirectory = root.appendingPathComponent("inside", isDirectory: true)
        let insideFile = insideDirectory.appendingPathComponent("save.dat")
        try manager.createDirectory(at: insideDirectory, withIntermediateDirectories: true)
        try Data("fixture".utf8).write(to: insideFile)
        let escapedDirectory = root.appendingPathComponent("escape", isDirectory: true)
        try manager.createDirectory(at: outside.appendingPathComponent("secret"), withIntermediateDirectories: true)
        try manager.createSymbolicLink(at: escapedDirectory, withDestinationURL: outside)
        let similarRoot = root.deletingLastPathComponent().appendingPathComponent("trainer-data-extra")
        try manager.createDirectory(at: similarRoot, withIntermediateDirectories: true)
        let specialFile = insideDirectory.appendingPathComponent("save #1.dat")
        try Data("fixture".utf8).write(to: specialFile)

        expect(
            TrainerSavePathValidator.validatedLocalURL(for: insideDirectory.path, under: root)?.path == insideDirectory.path,
            "root-contained local directory should be accepted"
        )
        expect(
            TrainerSavePathValidator.validatedLocalURL(for: insideFile.path, under: root)?.path == insideFile.path,
            "root-contained local file should be accepted"
        )
        expect(
            TrainerSavePathValidator.validatedLocalURL(for: specialFile.path, under: root)?.path == specialFile.path,
            "scheme-less paths containing spaces and # should be accepted"
        )
        expect(
            TrainerSavePathValidator.validatedLocalURL(for: insideDirectory.absoluteString, under: root) != nil,
            "local file URL should be accepted"
        )
        expect(
            TrainerSavePathValidator.validatedLocalURL(for: outside.path, under: root) == nil,
            "absolute path outside trainer data root must be rejected"
        )
        expect(
            TrainerSavePathValidator.validatedLocalURL(for: similarRoot.path, under: root) == nil,
            "sibling with matching root prefix must not pass containment"
        )
        expect(
            TrainerSavePathValidator.validatedLocalURL(for: root.appendingPathComponent("../outside").path, under: root) == nil,
            "lexical traversal outside trainer data root must be rejected"
        )
        expect(
            TrainerSavePathValidator.validatedLocalURL(for: escapedDirectory.appendingPathComponent("secret").path, under: root) == nil,
            "symlink escape from trainer data root must be rejected"
        )
        expect(
            TrainerSavePathValidator.validatedLocalURL(for: "https://example.invalid/save", under: root) == nil,
            "non-file URL scheme must be rejected"
        )
        expect(
            TrainerSavePathValidator.validatedLocalURL(for: "file://remote.invalid/" + insideFile.path, under: root) == nil,
            "remote file URL must be rejected"
        )
        expect(
            TrainerSavePathValidator.validatedLocalURL(for: "relative/save", under: root) == nil,
            "relative paths must be rejected"
        )
        expect(
            TrainerSavePathValidator.validatedLocalURL(for: root.appendingPathComponent("missing").path, under: root) == nil,
            "nonexistent paths must be rejected"
        )
        expect(
            TrainerSavePathValidator.validatedDirectoryURL(for: insideFile.path, under: root) == nil,
            "regular file must not pass directory-only reveal validation"
        )
        print("core_save_manager_path_validation_u02_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix="mgt-save-manager-behavior-") as td:
    base = Path(td)
    worker_path = base / "worker.py"
    main_path = base / "lifecycle.swift"
    binary = base / "lifecycle"
    worker_path.write_text(textwrap.dedent(worker), encoding="utf-8")
    main_path.write_text(textwrap.dedent(lifecycle_harness), encoding="utf-8")
    home = base / "effective-home"
    recovery = home / "Library/Application Support/MacGamingTrainer/test/transactions/.rollback-fixture"
    recovery.mkdir(parents=True)
    environment = os.environ.copy()
    environment["HOME"] = str(home)
    subprocess.run([
        SWIFTC, "-parse-as-library",
        str(ROOT / "Sources/Core/Runtime/BackendProcess.swift"),
        str(ROOT / "Sources/Core/Runtime/BackendClient.swift"),
        str(ROOT / "Sources/Core/Runtime/TrainerBackendSession.swift"),
        str(ROOT / "Sources/Core/Save/TrainerSaveTypes.swift"),
        str(ROOT / "Sources/Core/Save/TrainerSavePathValidator.swift"),
        str(ROOT / "Sources/Core/Save/TrainerSaveManagerModel.swift"),
        str(main_path), "-framework", "AppKit", "-o", str(binary),
    ], check=True, cwd=ROOT)
    proc = subprocess.run(
        [str(binary), PYTHON, str(worker_path), str(recovery)],
        cwd=ROOT, env=environment, text=True, capture_output=True, timeout=12
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    print(proc.stdout.strip())

with tempfile.TemporaryDirectory(prefix="mgt-save-path-validation-") as td:
    base = Path(td)
    root = base / "trainer-data"
    outside = base / "outside"
    root.mkdir()
    outside.mkdir()
    main_path = base / "path_validation.swift"
    binary = base / "path_validation"
    main_path.write_text(textwrap.dedent(path_harness), encoding="utf-8")
    subprocess.run([
        SWIFTC, "-parse-as-library",
        str(ROOT / "Sources/Core/Save/TrainerSavePathValidator.swift"),
        str(main_path), "-o", str(binary),
    ], check=True, cwd=ROOT)
    proc = subprocess.run(
        [str(binary), str(root), str(outside)],
        cwd=ROOT, text=True, capture_output=True, timeout=5
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    print(proc.stdout.strip())
