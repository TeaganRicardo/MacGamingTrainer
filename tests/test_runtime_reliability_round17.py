import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
PYTHON = shutil.which("python3")
if not SWIFTC or not PYTHON:
    raise SystemExit("swiftc/python3 required for runtime reliability test")

worker = r'''
import argparse, json, signal, sys, time
p=argparse.ArgumentParser(); p.add_argument('--game', required=True); args=p.parse_args()
game=args.game
if game == 'timeout':
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
for raw in sys.stdin:
    req=json.loads(raw)
    rid=req.get('id','')
    cmd=req.get('command','')
    if game == 'timeout':
        time.sleep(5)
        continue
    if game == 'malformed':
        print('not-json-at-all', flush=True)
        time.sleep(1)
        continue
    if game == 'huge':
        sys.stdout.write('x' * 10000)
        sys.stdout.flush()
        time.sleep(1)
        continue
    if game == 'exit':
        sys.exit(7)
    def reply(reply_id):
        print(json.dumps({
            'type':'result', 'id':reply_id, 'protocolVersion':6,
            'moduleProtocolVersion':1, 'gameID':game, 'ok':True,
            'result':{'command':cmd}
        }), flush=True)
    if game == 'wrong_then_right':
        reply('wrong-id')
        time.sleep(0.05)
        reply(rid)
        continue
    if cmd == 'hold':
        time.sleep(0.20)
    elif cmd == 'first':
        time.sleep(0.05)
    reply(rid)
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

final class Probe {
    let client: BackendClient
    var replies: [String] = []
    var errors: [String] = []
    var terminations: [Int32] = []
    var completions: [String: [Bool]] = [:]

    init(python: String, worker: String, game: String, maxBuffer: Int = 1_048_576, queueDepth: Int = 64) throws {
        let process = BackendProcess(
            executableURL: URL(fileURLWithPath: python),
            argumentsPrefix: ["-u"],
            maxStdoutBufferBytes: maxBuffer,
            forceKillDelay: 0.10
        )
        client = BackendClient(process: process, maxQueueDepth: queueDepth)
        try client.start(
            scriptURL: URL(fileURLWithPath: worker),
            expectation: BackendProtocolExpectation(gameID: game, hostProtocolVersion: 6, moduleProtocolVersion: 1),
            onRequestStarted: { _, _ in },
            onReply: { [weak self] reply in self?.replies.append(reply.command) },
            onProtocolMismatch: { [weak self] message in self?.errors.append("mismatch:" + message) },
            onStderr: { _ in },
            onLog: { _ in },
            onTermination: { [weak self] status, _ in self?.terminations.append(status) },
            onClientError: { [weak self] failure, _ in self?.errors.append(failure.presentation) }
        )
    }

    func send(_ command: String, timeout: TimeInterval = 1.0, completion: ((Bool) -> Void)? = nil) {
        client.send(command, operation: command, timeout: timeout, completion: completion)
    }

    func stopAndWait() {
        client.stop()
        _ = waitUntil(2.0) { !self.client.isStarted }
    }
}

let args = CommandLine.arguments
if args.count != 3 { fail("expected python + worker") }
let python = args[1], worker = args[2]

// A hung worker must time out, fail the request, stop, and eventually be killed
// even though the child explicitly ignores SIGTERM.
do {
    let p = try Probe(python: python, worker: worker, game: "timeout")
    var result: Bool? = nil
    p.send("hang", timeout: 0.15) { result = $0 }
    if !waitUntil(1.5, { result != nil && !p.terminations.isEmpty }) { fail("timeout did not resolve/terminate") }
    if result != false { fail("timeout completion must be false") }
    if !p.errors.contains(where: { $0.contains("未响应") }) { fail("timeout error missing") }
    if p.client.isStarted { fail("timed-out backend still marked started") }
}

// Malformed stdout must fail immediately instead of leaving current busy until timeout.
do {
    let p = try Probe(python: python, worker: worker, game: "malformed")
    var result: Bool? = nil
    p.send("bad", timeout: 1.0) { result = $0 }
    if !waitUntil(1.0, { result != nil && !p.terminations.isEmpty }) { fail("malformed stdout did not fail") }
    if result != false || !p.errors.contains(where: { $0.contains("通信协议错误") }) { fail("malformed stdout semantics wrong") }
}

// A wrong request ID is ignored; the correct reply can still complete the request.
do {
    let p = try Probe(python: python, worker: worker, game: "wrong_then_right")
    var result: Bool? = nil
    p.send("probe", timeout: 1.0) { result = $0 }
    if !waitUntil(1.0, { result != nil }) { fail("correct reply after wrong id not accepted") }
    if result != true || p.replies != ["probe"] { fail("wrong-id handling corrupted active request") }
    p.stopAndWait()
}

// Completion callbacks may enqueue follow-up work, but cannot cut in front of
// requests that were already queued before the first reply.
do {
    let p = try Probe(python: python, worker: worker, game: "ordering")
    var done = 0
    p.send("first") { ok in
        if !ok { fail("first failed") }
        p.send("third") { if $0 { done += 1 } }
        done += 1
    }
    p.send("second") { if $0 { done += 1 } }
    if !waitUntil(2.0, { done == 3 }) { fail("ordered requests did not finish") }
    if p.replies != ["first", "second", "third"] { fail("completion jumped queue: \(p.replies)") }
    p.stopAndWait()
}

// Queue overflow rejects only the new request and leaves accepted work ordered.
do {
    let p = try Probe(python: python, worker: worker, game: "queue", queueDepth: 2)
    var accepted = 0
    var rejected: Bool? = nil
    p.send("hold") { if $0 { accepted += 1 } }
    p.send("q1") { if $0 { accepted += 1 } }
    p.send("q2") { if $0 { accepted += 1 } }
    p.send("q3") { rejected = $0 }
    if !waitUntil(0.5, { rejected != nil }) || rejected != false { fail("queue overflow not rejected") }
    if !p.errors.contains(where: { $0.contains("队列已满") }) { fail("queue overflow error missing") }
    if !waitUntil(2.0, { accepted == 3 }) { fail("accepted queue work did not finish") }
    p.stopAndWait()
}

// Child exit while a request is active fails the request and reports termination.
do {
    let p = try Probe(python: python, worker: worker, game: "exit")
    var result: Bool? = nil
    p.send("exit") { result = $0 }
    if !waitUntil(1.0, { result != nil && !p.terminations.isEmpty }) { fail("process exit did not resolve request") }
    if result != false { fail("process-exit completion must fail") }
}

// A runaway stdout line is bounded and treated as protocol corruption.
do {
    let p = try Probe(python: python, worker: worker, game: "huge", maxBuffer: 4096)
    var result: Bool? = nil
    p.send("huge", timeout: 1.0) { result = $0 }
    if !waitUntil(1.0, { result != nil && !p.terminations.isEmpty }) { fail("stdout overflow did not fail") }
    if result != false || !p.errors.contains(where: { $0.contains("stdout") }) { fail("stdout overflow semantics wrong") }
}

print("runtime_reliability_round17_ok")
'''

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    worker_path = td / "fake_backend.py"
    main_path = td / "main.swift"
    binary = td / "runtime_test"
    worker_path.write_text(textwrap.dedent(worker))
    main_path.write_text(textwrap.dedent(harness))
    subprocess.run([
        SWIFTC,
        str(ROOT / "Sources/Core/Runtime/BackendProcess.swift"),
        str(ROOT / "Sources/Core/Runtime/BackendClient.swift"),
        str(main_path),
        "-o", str(binary),
    ], check=True, cwd=ROOT)
    proc = subprocess.run([str(binary), PYTHON, str(worker_path)], cwd=ROOT, text=True, capture_output=True, timeout=20)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    print(proc.stdout.strip())
