import os
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which('swiftc')
PYTHON = shutil.which('python3')
if not SWIFTC or not PYTHON:
    raise SystemExit('swiftc/python3 required for backend session recovery test')

worker = r'''
import argparse, json, os, sys, time
p=argparse.ArgumentParser(); p.add_argument('--game', required=True); args=p.parse_args()
log_path=os.environ.get('MGT_DEV8_WORKER_LOG')

def record(command):
    if not log_path:
        return
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(command + '\n')
        f.flush()

for raw in sys.stdin:
    req=json.loads(raw)
    command=req.get('command','')
    record(command)
    if command == 'crash':
        sys.exit(7)
    if command == 'hang':
        time.sleep(5)
        continue
    print(json.dumps({
        'type':'result', 'id':req.get('id',''), 'protocolVersion':6,
        'moduleProtocolVersion':5, 'gameID':args.game, 'ok':True,
        'result':{'command':command}
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
if args.count != 2 { fail("expected worker path") }
let worker = args[1]
let descriptor = GameModuleDescriptor(backendGameID: "test", expectedHostProtocolVersion: 6, expectedModuleProtocolVersion: 5)
let backendProcess = BackendProcess(
    executableURL: URL(fileURLWithPath: ProcessInfo.processInfo.environment["MGT_DEV8_PYTHON"]!),
    argumentsPrefix: ["-u"],
    maxStdoutBufferBytes: 1_048_576,
    forceKillDelay: 0.10
)
let session = TrainerBackendSession(client: BackendClient(process: backendProcess))
var states: [TrainerBackendStatus] = []
var payloadCommands: [String] = []

try session.start(
    descriptor: descriptor,
    backendScriptURL: URL(fileURLWithPath: worker),
    applyPayload: { payload in
        if let command = payload["command"] as? String { payloadCommands.append(command) }
    },
    resetGameState: {},
    log: { _ in },
    onStatusChange: { states.append($0) }
)
if !session.currentStatus.backendAvailable { fail("backend not available after start") }

func waitForRecovery(after stateIndex: Int, notice: String) {
    var sawUnavailable = false
    let ok = waitUntil(3.0) {
        if states.dropFirst(stateIndex).contains(where: { !$0.backendAvailable }) { sawUnavailable = true }
        return sawUnavailable && session.currentStatus.backendAvailable && session.currentStatus.notice.contains(notice) && !session.currentStatus.busy
    }
    if !ok { fail("recovery did not complete: \(notice) status=\(session.currentStatus)") }
}

// A hard child crash is recovered globally without any module-specific restart code.
do {
    let startIndex = states.count
    var crashCompletion: Bool? = nil
    session.send("crash", operation: "crash", timeout: 1.0, completion: { crashCompletion = $0 })
    waitForRecovery(after: startIndex, notice: "后端已自动恢复")
    if crashCompletion != false { fail("crash request completion must fail") }
    var ping: Bool? = nil
    session.send("ping-after-crash", operation: "ping", timeout: 1.0, completion: { ping = $0 })
    if !waitUntil(1.0, { ping != nil }) || ping != true { fail("recovered backend cannot accept request") }
}

// A timeout is outcome-unknown: stop/recover the worker but never replay the request.
do {
    let startIndex = states.count
    var hangCompletion: Bool? = nil
    session.send("hang", operation: "hang", timeout: 0.15, completion: { hangCompletion = $0 })
    waitForRecovery(after: startIndex, notice: "后端已自动恢复")
    if hangCompletion != false { fail("timeout request completion must fail") }
    var ping: Bool? = nil
    session.send("ping-after-timeout", operation: "ping", timeout: 1.0, completion: { ping = $0 })
    if !waitUntil(1.0, { ping != nil }) || ping != true { fail("timeout recovery backend cannot accept request") }
}

// Explicit restart works while the worker is already running; no focus/UI round trip is required by the runtime layer.
do {
    let startIndex = states.count
    session.restart()
    waitForRecovery(after: startIndex, notice: "后端已重启")
    var ping: Bool? = nil
    session.send("ping-after-manual", operation: "ping", timeout: 1.0, completion: { ping = $0 })
    if !waitUntil(1.0, { ping != nil }) || ping != true { fail("manual restart backend cannot accept request") }
}

session.stop()
_ = waitUntil(2.0) { !session.isStarted }
print("backend_session_recovery_dev8_ok")
'''

with tempfile.TemporaryDirectory(prefix='mgt-dev8-session-') as td:
    td = Path(td)
    worker_path = td / 'fake_backend.py'
    main_path = td / 'main.swift'
    binary = td / 'session_test'
    command_log = td / 'commands.log'
    worker_path.write_text(textwrap.dedent(worker), encoding='utf-8')
    main_path.write_text(textwrap.dedent(harness), encoding='utf-8')
    subprocess.run([
        SWIFTC,
        str(ROOT / 'Sources/Core/Runtime/BackendProcess.swift'),
        str(ROOT / 'Sources/Core/Runtime/BackendClient.swift'),
        str(ROOT / 'Sources/Core/Runtime/TrainerBackendSession.swift'),
        str(main_path),
        '-o', str(binary),
    ], check=True, cwd=ROOT)
    env = os.environ.copy()
    env['MGT_DEV8_WORKER_LOG'] = str(command_log)
    env['MGT_DEV8_PYTHON'] = PYTHON
    proc = subprocess.run([str(binary), str(worker_path)], cwd=ROOT, text=True, capture_output=True, timeout=20, env=env)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    commands = command_log.read_text(encoding='utf-8').splitlines()
    if commands.count('hang') != 1:
        raise AssertionError(f'outcome-unknown timeout request was replayed: {commands!r}')
    if commands.count('crash') != 1:
        raise AssertionError(f'crash request was replayed: {commands!r}')
    for required in ('ping-after-crash', 'ping-after-timeout', 'ping-after-manual'):
        if commands.count(required) != 1:
            raise AssertionError(f'missing/duplicate post-recovery request {required}: {commands!r}')
    print(proc.stdout.strip())
