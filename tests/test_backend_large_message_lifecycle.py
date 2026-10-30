"""Real pipe/file framing, admission failure, write deadline and worker isolation."""
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which('swiftc')
if not SWIFTC:
    raise SystemExit('swiftc required')

WORKER = r'''
import json, os, pathlib, signal, struct, sys, time
directory = pathlib.Path(os.environ['MGT_JSONL_SESSION_V1'])
with (pathlib.Path(__file__).parent / 'sessions.jsonl').open('a') as log:
    log.write(json.dumps(str(directory)) + '\n')
if pathlib.Path(__file__).name == 'blocked.py':
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    child = os.fork()
    if child == 0:
        os.closerange(3, os.sysconf('SC_OPEN_MAX'))
        time.sleep(30)
        os._exit(0)
    (pathlib.Path(__file__).parent / 'child').write_text(str(child))
    (pathlib.Path(__file__).parent / 'ready').write_text('ready')
    time.sleep(30)
    raise SystemExit(0)
sys.path.insert(0, BACKEND_PATH)
from core.adapter import GameAdapter, GameAdapterContext
import core.server as server
class Fixture(GameAdapter):
    def __init__(self):
        super().__init__(GameAdapterContext('fixture', 'Fixture', 1, None, {}))
        self.calls = 0
    def dispatch(self, command, params, request_id):
        self.calls += 1
        result = {'payload': params.get('payload'), 'calls': self.calls}
        if 'numbers' in params:
            result['numbers'] = params['numbers']
            result['numberBits'] = [format(struct.unpack('>Q', struct.pack('>d', value))[0], 'x')
                                    for value in params['numbers']]
            result['negativeZero'] = -0.0
        return result
    def close(self):
        pass
server.available_games = lambda: []
server.create_adapter = lambda game_id: Fixture()
server.main()
'''

HARNESS = r'''
import Foundation
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif

func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fputs(message + "\n", stderr); exit(1) }
}
func wait(_ message: String, seconds: TimeInterval = 8, until condition: () -> Bool) {
    let deadline = Date().addingTimeInterval(seconds)
    while !condition() && Date() < deadline { RunLoop.current.run(until: Date().addingTimeInterval(0.01)) }
    check(condition(), message)
}
@main struct Main {
    static func main() throws {
        let args = CommandLine.arguments
        let folder = URL(fileURLWithPath: args[2])
        let process = BackendProcess(executableURL: URL(fileURLWithPath: args[1]), forceKillDelay: 0.1)
        let client = BackendClient(process: process)
        var terminated = 0
        var terminalErrors = 0
        var admissionErrors = 0
        func start(_ name: String) throws {
            try client.start(scriptURL: folder.appendingPathComponent(name),
                expectation: BackendProtocolExpectation(gameID: "fixture", hostProtocolVersion: 6, moduleProtocolVersion: 1),
                onRequestStarted: { _, _ in }, onReply: { _ in },
                onProtocolMismatch: { _ in check(false, "unexpected protocol mismatch") },
                onStderr: { _ in }, onLog: { _ in }, onTermination: { _, _ in terminated += 1 },
                onClientError: { _, terminal in if terminal { terminalErrors += 1 } else { admissionErrors += 1 } })
        }
        func sessionDirectories() -> [String] {
            let lines = (try? String(contentsOf: folder.appendingPathComponent("sessions.jsonl"), encoding: .utf8)) ?? ""
            return lines.split(separator: "\n").compactMap {
                (try? JSONSerialization.jsonObject(with: Data($0.utf8), options: [.fragmentsAllowed])) as? String
            }
        }
        try start("worker.py")
        let numbers = [Double("1.2345678901234567e100")!,
                       Double(sign: .plus, exponent: 100, significand: 1),
                       Double(sign: .plus, exponent: 1023, significand: 1)]
        let numberBits = numbers.map { String($0.bitPattern, radix: 16) }
        func checkNumbers(_ result: [String: Any]?, _ path: String) {
            check(result?["numberBits"] as? [String] == numberBits,
                  "\(path) outbound numeric JSON changed IEEE bits in Python")
            guard let echoed = result?["numbers"] as? [NSNumber], echoed.count == numbers.count else {
                check(false, "\(path) reply lost numeric values")
                return
            }
            for (index, value) in echoed.enumerated() {
                check(value.doubleValue.bitPattern == numbers[index].bitPattern,
                      "\(path) inbound numeric JSON changed IEEE bits at index \(index)")
            }
            check((result?["negativeZero"] as? NSNumber)?.doubleValue.bitPattern == (-0.0 as Double).bitPattern,
                  "\(path) inbound numeric JSON lost negative zero")
        }
        let large = String(repeating: "完整 value\u{0}\n", count: 160_000)
        var largeDone: Bool?
        client.send("echo", params: ["payload": large, "numbers": numbers], operation: "large", timeout: 15,
                    reply: { reply in
                        check(reply.result?["payload"] as? String == large, "large request/reply lost bytes")
                        check(reply.result?["calls"] as? Int == 1, "large request executed more than once")
                        checkNumbers(reply.result, "file payload")
                    }, completion: { largeDone = $0 })
        wait("large message did not finish", seconds: 18) { largeDone != nil }
        check(largeDone == true && client.isRunning && terminalErrors == 0, "legal large edit terminated its worker")
        let firstSession = sessionDirectories().first!
        wait("consumed private payload files remained") {
            ((try? FileManager.default.contentsOfDirectory(atPath: firstSession)) ?? []).allSatisfy { !$0.hasPrefix("payload-") }
        }

        var invalidDone: Bool?
        var followingDone: Bool?
        client.send("invalid", params: ["value": Double.nan], operation: "invalid", completion: { invalidDone = $0 })
        client.send("after-invalid", params: ["numbers": numbers], operation: "after-invalid", reply: { reply in
            check(reply.result?["calls"] as? Int == 2, "invalid encoding crossed the request boundary or worker restarted")
            checkNumbers(reply.result, "inline payload")
        }, completion: { followingDone = $0 })
        wait("known admission failure did not release the queue") { invalidDone != nil && followingDone != nil }
        check(invalidDone == false && followingDone == true && admissionErrors == 1 && terminalErrors == 0,
              "known encoding failure destroyed the worker or lost a queued request")
        client.stop()
        wait("first worker did not stop") { !client.isStarted }
        wait("first worker session directory was not reclaimed") { !FileManager.default.fileExists(atPath: firstSession) }

        try start("blocked.py")
        wait("blocked worker was not ready") { FileManager.default.fileExists(atPath: folder.appendingPathComponent("ready").path) }
        let blockedSession = sessionDirectories().last!
        let child = Int32(try String(contentsOf: folder.appendingPathComponent("child"), encoding: .utf8))!
        var timeoutDone: Bool?
        var cancelledDone: Bool?
        var mainStayedResponsive = false
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.03) { mainStayedResponsive = true }
        // Below the inline threshold, but larger than the unconsumed pipe.
        client.send("blocked", params: ["payload": String(repeating: "x", count: 60_000)],
                    operation: "blocked", timeout: 0.2, completion: { timeoutDone = $0 })
        client.send("cancelled", operation: "cancelled", completion: { cancelledDone = $0 })
        wait("request deadline did not cover the blocked pipe write", seconds: 4) { !client.isStarted }
        check(mainStayedResponsive && timeoutDone == false && cancelledDone == false && terminalErrors == 1,
              "blocked write stalled main or did not cancel its original request queue")

        try start("worker.py")
        var finalDone: Bool?
        client.send("new-worker", params: ["payload": large], operation: "new-worker", timeout: 15,
                    reply: { reply in
                        check(reply.result?["payload"] as? String == large && reply.result?["calls"] as? Int == 1,
                              "old writer or callback crossed into the replacement worker")
                    }, completion: { finalDone = $0 })
        wait("replacement worker did not finish its independent request", seconds: 18) { finalDone != nil }
        let finalSession = sessionDirectories().last!
        check(finalDone == true && finalSession != blockedSession && finalSession != firstSession,
              "replacement worker reused a prior session directory")
        wait("blocked worker session outlived its completed write") { !FileManager.default.fileExists(atPath: blockedSession) }
        check(kill(child, 0) == 0, "fixture did not retain original stdin through worker cancellation")
        client.stop()
        wait("replacement worker did not stop") { !client.isStarted }
        wait("replacement directory was not reclaimed") { !FileManager.default.fileExists(atPath: finalSession) }
        check(terminated == 3, "worker termination callback identity changed")
        print("backend_large_message_lifecycle_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix='mgt-large-message-lifecycle-') as temporary:
    folder = Path(temporary)
    source = 'BACKEND_PATH = ' + repr(str(ROOT / 'Backend')) + '\n' + WORKER
    (folder / 'worker.py').write_text(source)
    (folder / 'blocked.py').write_text(source)
    harness = folder / 'main.swift'
    harness.write_text(HARNESS)
    binary = folder / 'lifecycle'
    subprocess.run([SWIFTC, '-parse-as-library', str(ROOT / 'Sources/Core/Runtime/BackendProcess.swift'),
                    str(ROOT / 'Sources/Core/Runtime/BackendClient.swift'), str(harness), '-o', str(binary)],
                   cwd=ROOT, check=True)
    try:
        subprocess.run([str(binary), sys.executable, str(folder)], cwd=ROOT,
                       env=dict(os.environ, HOME=str(folder)), check=True, timeout=55)
    finally:
        child = folder / 'child'
        if child.exists():
            try:
                os.kill(int(child.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
