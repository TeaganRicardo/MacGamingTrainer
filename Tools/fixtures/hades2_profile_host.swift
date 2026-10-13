import Foundation

struct GameModuleDescriptor {
    let backendGameID: String
    let expectedHostProtocolVersion: Int
    let expectedModuleProtocolVersion: Int
}
let args = CommandLine.arguments
let count = Int(args[3])!
let client = BackendClient(process: BackendProcess(executableURL: URL(fileURLWithPath: args[2])))
let session = TrainerBackendSession(client: client)
var applied = 0
var payload: [String: Any] = [:]
func log(_ text: String) {
    // The diagnostic callback can receive several stderr records in one chunk.
    for line in text.components(separatedBy: .newlines) {
        if let range = line.range(of: "OperationProfile ") {
            print(String(line[range.lowerBound...]))
        }
    }
}
try session.start(descriptor: GameModuleDescriptor(backendGameID: "hades2", expectedHostProtocolVersion: 6,
    expectedModuleProtocolVersion: Int(args[4])!), backendScriptURL: URL(fileURLWithPath: args[1]),
    applyPayload: { value in payload = value; applied += 1 }, resetGameState: {}, log: log, onStatusChange: { _ in })
func wait(_ done: @escaping () -> Bool) {
    let deadline = Date().addingTimeInterval(20)
    while !done() && Date() < deadline { RunLoop.current.run(until: Date().addingTimeInterval(0.001)) }
    precondition(done(), "offline operation timed out")
}
wait { !session.currentStatus.busy && session.currentStatus.backendAvailable }
var sequence = 0
func operation(_ command: String, _ params: [String: Any] = [:], burst: Bool = false, path: String = "setup") {
    sequence += 1
    let label = "sample-\(sequence)"
    let admitted = ProcessInfo.processInfo.systemUptime
    var dispatched = admitted
    var done = false
    session.send(command, params: params, operation: label, announceSuccess: false, timeout: 15,
        started: { dispatched = ProcessInfo.processInfo.systemUptime }, reply: { reply in
            precondition(reply.success, "fixture command failed: \(reply.command) \(String(describing: reply.failure))")
            let record: [String: Any] = ["schema": 1, "component": "harness", "request_id": reply.requestID,
                "command": command, "phase": "harness.host_round_trip", "seconds": ProcessInfo.processInfo.systemUptime - admitted,
                "queue_seconds": dispatched - admitted, "workload": label, "path": path]
            let bytes = try! JSONSerialization.data(withJSONObject: record, options: [.sortedKeys])
            print("OperationProfile " + String(data: bytes, encoding: .utf8)!)
        }, completion: { success in precondition(success); done = true })
    if !burst { wait { done } }
}
operation("status", path: "cold_catalog") // cold materialization/catalogs
for _ in 0..<3 { operation("status", path: "warmup") }
for _ in 0..<count { operation("status", path: "warm_status") }
for index in 0..<count { operation("set_resource", ["resource": "MetaCurrency", "amount": 100 + index], path: "resource_edit") }
operation("set_desired", ["feature": "infiniteHealth", "value": true])
operation("lock_resource", ["resource": "MetaCurrency", "locked": true])
for _ in 0..<3 { operation("status", path: "warmup") }
for _ in 0..<count { operation("status", path: "active_status") }
for _ in 0..<3 { operation("status", burst: true, path: "queued_status") }
wait { !client.hasInFlightRequest && client.queuedRequestCount == 0 }
precondition(applied >= count * 3 + 6)
precondition((payload["currentRunTraits"] as? [Any])?.count == Int(ProcessInfo.processInfo.environment["MGT_PROFILE_TRAITS"]!))
precondition((payload["resources"] as? [Any])?.count ?? 0 >= 2)
session.stop()
// Drain diagnostic delivery already enqueued before termination.
RunLoop.current.run(until: Date().addingTimeInterval(0.03))
