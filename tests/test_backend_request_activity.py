import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
PYTHON = shutil.which("python3")
if not SWIFTC or not PYTHON:
    raise SystemExit("swiftc/python3 required for backend request activity test")


WORKER = r'''
import argparse, json, sys, time
p = argparse.ArgumentParser()
p.add_argument('--game', required=True)
game = p.parse_args().game
for raw in sys.stdin:
    request = json.loads(raw)
    command = request['command']
    if command == 'hang':
        time.sleep(10)
        continue
    if command == 'exit':
        sys.exit(7)
    if command == 'malformed':
        print('not-json', flush=True)
        continue
    if command == 'hold':
        time.sleep(0.1)
    print(json.dumps({
        'type': 'result', 'id': request['id'], 'gameID': game,
        'protocolVersion': 99 if command == 'mismatch' else 6,
        'moduleProtocolVersion': 1, 'ok': command != 'failure',
        'result': {'command': command},
    }), flush=True)
'''


HARNESS = r'''
import Foundation

func require(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() {
        fputs("FAIL: \(message)\n", stderr)
        exit(1)
    }
}

func waitUntil(_ predicate: () -> Bool) -> Bool {
    let deadline = Date().addingTimeInterval(4)
    while Date() < deadline {
        if predicate() { return true }
        RunLoop.current.run(until: Date().addingTimeInterval(0.01))
    }
    return predicate()
}

final class Activities {
    var begun = 0
    var active = Set<Int>()
    var events: [String] = []

    func begin() -> BackendRequestActivity {
        require(active.isEmpty, "request activities overlap")
        begun += 1
        let id = begun
        active.insert(id)
        events.append("begin\(id)")
        return BackendRequestActivity {
            require(self.active.remove(id) != nil, "activity ended more than once")
            self.events.append("end\(id)")
        }
    }
}

final class Probe {
    let activities = Activities()
    let client: BackendClient
    var replies: [String] = []
    var errors: [String] = []
    var terminations: [Int32] = []

    init(python: String, worker: String) throws {
        let tracker = activities
        client = BackendClient(
            process: BackendProcess(
                executableURL: URL(fileURLWithPath: python),
                forceKillDelay: 0.1
            ),
            beginRequestActivity: { tracker.begin() }
        )
        try client.start(
            scriptURL: URL(fileURLWithPath: worker),
            expectation: BackendProtocolExpectation(gameID: "fixture", hostProtocolVersion: 6, moduleProtocolVersion: 1),
            onRequestStarted: { _, _ in require(tracker.active.count == 1, "started before activity") },
            onReply: { [weak self] reply in
                require(tracker.active.isEmpty, "reply delivered before activity ended")
                self?.replies.append(reply.command)
            },
            onProtocolMismatch: { [weak self] _ in
                require(tracker.active.isEmpty, "mismatch delivered before activity ended")
                self?.errors.append("protocol_mismatch")
            },
            onStderr: { _ in }, onLog: { _ in },
            onTermination: { [weak self] status, _ in
                require(tracker.active.isEmpty, "termination delivered before activity ended")
                self?.terminations.append(status)
            },
            onClientError: { [weak self] failure, _ in
                require(tracker.active.isEmpty, "terminal error delivered before activity ended")
                self?.errors.append(failure.code)
            }
        )
        require(tracker.begun == 0, "starting idle backend acquired an activity")
    }

    func stopAndWait() {
        client.stop()
        require(waitUntil { !client.isStarted }, "backend did not terminate")
        require(activities.active.isEmpty, "activity survived stop")
    }
}

let args = CommandLine.arguments
require(args.count == 3, "expected python and temporary worker")

// Queued/coalesced work owns no activity. Replies release before callbacks;
// reentrant work waits behind the queue and receives a fresh activity.
do {
    let p = try Probe(python: args[1], worker: args[2])
    var completed = 0, replaced = 0
    p.client.send("hold", operation: "hold", started: {
        require(p.activities.active.count == 1, "request started without activity")
    }, reply: { _ in
        p.client.send("follow", operation: "follow", completion: { if $0 { completed += 1 } })
    }, completion: { if $0 { completed += 1 } })
    p.client.send("reply", operation: "old", coalesceKey: "queued", completion: { if !$0 { replaced += 1 } })
    p.client.send("reply", operation: "new", coalesceKey: "queued", completion: { if $0 { completed += 1 } })
    require(p.activities.begun == 1 && p.client.queuedRequestCount == 1 && replaced == 1, "queue acquired activity")
    require(waitUntil { completed == 3 }, "queued replies did not finish")
    require(p.replies == ["hold", "reply", "follow"], "activity changed reply ordering")
    require(p.activities.events == ["begin1", "end1", "begin2", "end2", "begin3", "end3"], "activity lifecycle wrong")
    p.client.send("failure", operation: "failure")
    require(waitUntil { p.replies.count == 4 }, "failed reply missing")
    require(p.activities.active.isEmpty && p.activities.begun == 4, "failed reply retained activity")
    p.stopAndWait()
}

// stop fails active and queued requests and later process termination must not
// release the already-finished activity again.
do {
    let p = try Probe(python: args[1], worker: args[2])
    var failed = 0
    p.client.send("hang", operation: "hang", completion: { if !$0 { failed += 1 } })
    p.client.send("reply", operation: "queued", completion: { if !$0 { failed += 1 } })
    p.client.stop()
    require(failed == 2 && p.activities.events == ["begin1", "end1"], "stop leaked/duplicated activity")
    p.stopAndWait()
    require(p.activities.events == ["begin1", "end1"], "termination double-ended activity")
}

// All terminal sources use the same owner boundary. The short timeout tests
// lifecycle expiry only; normal replies retain the production default budget.
for (command, expectedError) in [("hang", "backend_timeout"), ("malformed", "backend_protocol_error"), ("mismatch", "protocol_mismatch"), ("exit", "")] {
    let p = try Probe(python: args[1], worker: args[2])
    var failed = false
    p.client.send(command, operation: command, timeout: command == "hang" ? 0.1 : 6, completion: { failed = !$0 })
    require(waitUntil { failed && !p.client.isStarted }, "terminal request did not finish: \(command)")
    require(expectedError.isEmpty || p.errors.contains(expectedError), "wrong terminal source: \(command)")
    require(p.activities.events == ["begin1", "end1"], "terminal activity leaked/duplicated: \(command)")
}

// JSON serialization fails after dispatch acquired activity, before the worker
// receives a request. It must end exactly once even when the child then exits.
do {
    let p = try Probe(python: args[1], worker: args[2])
    var failed = false
    p.client.send("reply", params: ["invalid": NSObject()], operation: "send-failure", completion: { failed = !$0 })
    require(failed && p.errors.contains("backend_send_failed"), "send failure not reached")
    require(p.activities.events == ["begin1", "end1"], "send failure retained activity")
    p.stopAndWait()
    require(p.activities.events == ["begin1", "end1"], "send failure double-ended activity")
}

print("backend_request_activity_ok")
'''


with tempfile.TemporaryDirectory(prefix="mgt-request-activity-") as directory:
    directory = Path(directory)
    worker = directory / "worker.py"
    main = directory / "main.swift"
    binary = directory / "activity-test"
    worker.write_text(WORKER)
    main.write_text(HARNESS)
    subprocess.run([
        SWIFTC,
        str(ROOT / "Sources/Core/Runtime/BackendProcess.swift"),
        str(ROOT / "Sources/Core/Runtime/BackendClient.swift"),
        str(main), "-o", str(binary),
    ], check=True, cwd=ROOT)
    result = subprocess.run([str(binary), PYTHON, str(worker)], cwd=ROOT, capture_output=True, text=True, timeout=25)
    if result.returncode:
        print(result.stdout)
        print(result.stderr)
        raise SystemExit(result.returncode)
    print(result.stdout.strip())
