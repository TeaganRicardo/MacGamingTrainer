import os
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
session_source = (ROOT / 'Sources/Core/Runtime/TrainerBackendSession.swift').read_text(encoding='utf-8')
assert '后端已退出（状态 \\(exitStatus)）' not in session_source
assert '后端退出 status=\\(exitStatus)' in session_source
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
    if command in {'crash', 'quit-crash'}:
        sys.exit(7)
    if command == 'hang':
        time.sleep(5)
        continue
    if command == 'slow':
        time.sleep(0.20)
    if command == 'unknown-reply':
        print(json.dumps({'type':'result', 'id':req['id'], 'protocolVersion':6,
            'moduleProtocolVersion':5, 'gameID':args.game, 'ok':False,
            'error':{'code':'outcome_unknown', 'presentation':'host.backend.error.outcomeUnknown'}}), flush=True)
        continue
    print(json.dumps({
        'type':'result', 'id':req.get('id',''), 'protocolVersion':6,
        'moduleProtocolVersion':5, 'gameID':args.game, 'ok':True,
        'result':{'command':command}
    }), flush=True)
    if command == 'receipt-then-exit':
        sys.exit(7)
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

// Normal requests must tolerate worker cold-start variance. The 0.15s hung-
// worker request below is the timeout behavior under test and remains short.
let requestTimeout: TimeInterval = 6.0
let waitBudget: TimeInterval = 4.0

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
let session = TrainerBackendSession(client: BackendClient(process: backendProcess, maxQueueDepth: 1))
var states: [TrainerBackendStatus] = []
var payloadCommands: [String] = []
var hostLogs: [String] = []
var backendLogs: [String] = []

try session.start(
    descriptor: descriptor,
    backendScriptURL: URL(fileURLWithPath: worker),
    applyPayload: { payload in
        if let command = payload["command"] as? String { payloadCommands.append(command) }
    },
    resetGameState: {},
    log: { hostLogs.append($0) },
    onStatusChange: { states.append($0) },
    backendLog: { backendLogs.append($0) }
)
if !session.currentStatus.backendAvailable { fail("backend not available after start") }

func waitForRecovery(after stateIndex: Int, notice: String) {
    var sawUnavailable = false
    let ok = waitUntil(waitBudget) {
        if states.dropFirst(stateIndex).contains(where: { !$0.backendAvailable }) { sawUnavailable = true }
        return sawUnavailable && session.currentStatus.backendAvailable && session.currentStatus.notice.contains(notice) && !session.currentStatus.busy
    }
    if !ok { fail("recovery did not complete: \(notice) status=\(session.currentStatus)") }
}

// A hard child crash is recovered globally without any module-specific restart code.
// Per-request start is execution evidence, not acceptance/queueing evidence.
do {
    var events: [String] = []
    session.send("slow", operation: "slow", timeout: requestTimeout,
                 started: { events.append("start-slow") },
                 completion: { _ in events.append("finish-slow") })
    session.send("queued", operation: "queued", timeout: requestTimeout,
                 started: { events.append("start-queued") },
                 completion: { _ in events.append("finish-queued") })
    if events != ["start-slow"] { fail("queued request was reported started before execution: \(events)") }
    var rejectedStarted = false
    var rejectedCompletion: Bool? = nil
    session.send("overflow", operation: "overflow", timeout: requestTimeout,
                 started: { rejectedStarted = true }, completion: { rejectedCompletion = $0 })
    if rejectedStarted || rejectedCompletion != false { fail("queue-full request started or retained its completion") }
    if !session.currentStatus.busy || session.currentStatus.errorCode != "backend_queue_full" {
        fail("queue-full rejection hid the active request: \(session.currentStatus)")
    }
    if !waitUntil(waitBudget, { events.count == 4 }) { fail("request start/completion callbacks did not settle") }
    if events != ["start-slow", "finish-slow", "start-queued", "finish-queued"] {
        fail("request start/completion callbacks changed FIFO order: \(events)")
    }
}

do {
    let startIndex = states.count
    let workerGeneration = session.lifecycleID
    var crashCompletion: Bool? = nil
    session.send("crash", operation: "crash", timeout: requestTimeout, completion: { crashCompletion = $0 })
    waitForRecovery(after: startIndex, notice: "host.backend.notice.recovered")
    if crashCompletion != false { fail("crash request completion must fail") }
    if session.currentStatus.errorCode != "outcome_unknown" {
        fail("worker recovery erased the unknown in-flight action result: \(session.currentStatus)")
    }
    if !session.currentStatus.requiresTargetRestart { fail("crashed in-flight action did not constrain its target") }
    if session.lifecycleID == workerGeneration { fail("recovery reused the departed worker generation") }
    var rejected: Bool? = nil
    var rejectedStarted = false
    session.send("rejected-after-crash", operation: "unsafe", started: { rejectedStarted = true }, completion: { rejected = $0 })
    if rejected != false || rejectedStarted { fail("same-target work crossed the unknown outcome gate") }
    if hostLogs.contains(where: { $0.contains("后端退出 status=") }) {
        fail("backend termination evidence leaked into the Host stream")
    }
    if !backendLogs.contains(where: { $0.contains("后端退出 status=") }) {
        fail("backend termination evidence did not reach the Backend stream")
    }
    var ping: Bool? = nil
    session.send("ping-after-crash", operation: "ping", timeout: requestTimeout,
                 requiresTrustedTarget: false, completion: { ping = $0 })
    if !waitUntil(waitBudget, { ping != nil }) || ping != true { fail("recovered backend cannot accept request") }
    if session.currentStatus.errorCode != "outcome_unknown" { fail("safe request hid the unresolved action") }
    session.targetLifetimeChanged()
    if session.currentStatus.requiresTargetRestart || session.currentStatus.errorCode != nil {
        fail("definitive new target lifetime did not release its predecessor's gate")
    }
}

// A timeout is outcome-unknown: stop/recover the worker but never replay the request.
do {
    let startIndex = states.count
    var hangCompletion: Bool? = nil
    var hangFailure: BackendFailure?
    session.send("hang", operation: "hang", timeout: 0.15, failed: { hangFailure = $0 }, completion: { hangCompletion = $0 })
    var queuedStarted = false
    var queuedCompletion: Bool? = nil
    var queuedFailure: BackendFailure?
    session.send("cancelled-on-timeout", operation: "cancelled", timeout: requestTimeout,
                 started: { queuedStarted = true }, failed: { queuedFailure = $0 }, completion: { queuedCompletion = $0 })
    waitForRecovery(after: startIndex, notice: "host.backend.notice.recovered")
    if hangCompletion != false { fail("timeout request completion must fail") }
    if queuedStarted || queuedCompletion != false { fail("terminal cancellation started or retained a queued request") }
    if hangFailure?.outcomeUnknown != true || queuedFailure?.outcomeUnknown != false {
        fail("active unknown action and unsent queued work lost their separate outcomes")
    }
    var ping: Bool? = nil
    session.send("ping-after-timeout", operation: "ping", timeout: requestTimeout,
                 requiresTrustedTarget: false, completion: { ping = $0 })
    if !waitUntil(waitBudget, { ping != nil }) || ping != true { fail("timeout recovery backend cannot accept request") }
    if session.currentStatus.errorCode != "outcome_unknown" || !session.currentStatus.requiresTargetRestart {
        fail("timeout recovery lost the unknown action or its target constraint")
    }
}

// Explicit restart works while the worker is already running; no focus/UI round trip is required by the runtime layer.
do {
    let startIndex = states.count
    session.restart()
    waitForRecovery(after: startIndex, notice: "host.backend.notice.restarted")
    if !session.currentStatus.requiresTargetRestart { fail("manual worker restart released target trust") }
    session.targetLifetimeChanged()
    var ping: Bool? = nil
    session.send("ping-after-manual", operation: "ping", timeout: requestTimeout, completion: { ping = $0 })
    if !waitUntil(waitBudget, { ping != nil }) || ping != true { fail("manual restart backend cannot accept request") }
}

// A trustworthy action receipt precedes exit; recovery retains its success.
do {
    let startIndex = states.count
    var receipt: Bool? = nil
    session.send("receipt-then-exit", operation: "receipt", completion: { receipt = $0 })
    waitForRecovery(after: startIndex, notice: "host.backend.notice.recovered")
    if receipt != true || session.currentStatus.requiresTargetRestart || session.currentStatus.errorCode != nil {
        fail("a confirmed action was reclassified by the later worker exit")
    }
    var encodeFailure: BackendFailure?
    var encodeCompletion: Bool?
    session.send("invalid-before-write", params: ["value": Double.nan], operation: "invalid",
        failed: { encodeFailure = $0 }, completion: { encodeCompletion = $0 })
    if !waitUntil(waitBudget, { encodeCompletion != nil }) || encodeCompletion != false
        || encodeFailure?.outcomeUnknown != false || session.currentStatus.requiresTargetRestart {
        fail("a pre-write encoding rejection became an unknown target action")
    }
}

// Quit freezes recovery before finalization without cancelling an existing
// write or dropping its completion. Subsequent restart requests are inert.
do {
    let startIndex = states.count
    var unknownDone: Bool?
    var queuedDone: Bool?
    var queuedStarted = false
    session.send("unknown-reply", operation: "unknown", completion: { unknownDone = $0 })
    session.send("queued-after-unknown", operation: "must-not-run",
        started: { queuedStarted = true }, completion: { queuedDone = $0 })
    waitForRecovery(after: startIndex, notice: "host.backend.notice.recovered")
    if unknownDone != false || queuedDone != false || queuedStarted || !session.currentStatus.requiresTargetRestart {
        fail("a nonterminal module unknown-outcome reply let queued runtime work execute")
    }
    session.targetLifetimeChanged()
}

do {
    var writeFinished: Bool? = nil
    session.send("slow-before-quit", operation: "write", completion: { writeFinished = $0 })
    session.beginTermination()
    let generation = session.lifecycleID
    session.restart()
    if !waitUntil(waitBudget, { writeFinished != nil }) || writeFinished != true {
        fail("quit freeze dropped the in-flight result")
    }
    if session.lifecycleID != generation { fail("quit freeze allowed a worker restart") }
}

// An exit already scheduled for recovery cannot resurrect a terminating context.
let quitting = TrainerBackendSession(client: BackendClient(process: BackendProcess(
    executableURL: URL(fileURLWithPath: ProcessInfo.processInfo.environment["MGT_DEV8_PYTHON"]!), forceKillDelay: 0.10)))
try quitting.start(descriptor: descriptor, backendScriptURL: URL(fileURLWithPath: worker), applyPayload: { _ in },
    resetGameState: {}, log: { _ in }, onStatusChange: { state in
        if !state.backendAvailable && state.busy { quitting.beginTermination() }
    })
quitting.send("quit-crash", operation: "quit-crash")
if !waitUntil(waitBudget, { !quitting.isStarted && !quitting.currentStatus.busy }) { fail("quit recovery did not settle") }
let quitGeneration = quitting.lifecycleID
quitting.restart()
_ = waitUntil(0.5) { quitting.isStarted }
if quitting.isStarted || quitting.lifecycleID != quitGeneration { fail("queued recovery restarted a terminating worker") }

session.stop()
_ = waitUntil(2.0) { !session.isStarted }

// Sending after the worker is already unavailable has no termination event
// left to own a recovery transition. It must settle as a terminal unavailable
// failure instead of latching the Host in a recovering/busy presentation.
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
    if unavailable.backendAvailable { fail("stopped backend reported available after terminal send") }
    if unavailable.busy { fail("unavailable send latched busy without a recovery owner") }
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
        str(ROOT / 'Sources/Core/Runtime/TrainerJSON.swift'), str(ROOT / 'Sources/Core/Runtime/BackendProcess.swift'),
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
    if 'ping-after-stop' in commands:
        raise AssertionError(f'unavailable request reached a stopped worker: {commands!r}')
    if 'rejected-after-crash' in commands:
        raise AssertionError(f'same-target request reached recovered worker: {commands!r}')
    if 'invalid-before-write' in commands:
        raise AssertionError(f'encoding rejection reached worker: {commands!r}')
    if 'queued-after-unknown' in commands or commands.count('unknown-reply') != 1:
        raise AssertionError(f'unknown reply replayed or released queued target work: {commands!r}')
    for required in ('ping-after-crash', 'ping-after-timeout', 'ping-after-manual'):
        if commands.count(required) != 1:
            raise AssertionError(f'missing/duplicate post-recovery request {required}: {commands!r}')
    print(proc.stdout.strip())
