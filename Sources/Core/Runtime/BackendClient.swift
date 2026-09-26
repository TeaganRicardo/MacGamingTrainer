import Foundation

struct BackendProtocolExpectation {
    let gameID: String
    let hostProtocolVersion: Int
    let moduleProtocolVersion: Int
}

struct BackendFailure: Equatable {
    let code: String
    let presentation: String
    let diagnostic: String?
    let recoveryPath: String?
}

struct BackendReply {
    let requestID: String
    let command: String
    let hostProtocolVersion: Int
    let moduleProtocolVersion: Int
    let gameID: String
    let operation: String
    let announceSuccess: Bool
    let success: Bool
    let result: [String: Any]?
    let state: [String: Any]?
    let failure: BackendFailure?
}

/// Game-agnostic request lifecycle around BackendProcess. It owns JSONL request
/// IDs, one-at-a-time ordering, queue coalescing, timeouts and host/module
/// protocol verification. A game model only interprets the opaque result/state.
final class BackendClient {
    private struct Request {
        let id: String
        let command: String
        let params: [String: Any]
        let operation: String
        let coalesceKey: String?
        let announceSuccess: Bool
        let timeout: TimeInterval
        let reply: ((BackendReply) -> Void)?
        let completion: ((Bool) -> Void)?
    }

    private let process: BackendProcess
    private let maxQueueDepth: Int
    private var expectation: BackendProtocolExpectation?
    private var current: Request?
    private var queue: [Request] = []
    private var currentTimeoutWorkItem: DispatchWorkItem?
    private var deliveringReply = false
    private var terminalFailureReported = false
    private var stderrTail = ""

    private var onRequestStarted: ((String, Bool) -> Void)?
    private var onReply: ((BackendReply) -> Void)?
    private var onProtocolMismatch: ((String) -> Void)?
    private var onStderr: ((String) -> Void)?
    private var onLog: ((String) -> Void)?
    private var onTermination: ((Int32, String) -> Void)?
    private var onClientError: ((BackendFailure, Bool) -> Void)?

    init(process: BackendProcess = BackendProcess(), maxQueueDepth: Int = 64) {
        self.process = process
        self.maxQueueDepth = max(1, maxQueueDepth)
    }

    var isRunning: Bool { process.isRunning }
    var isStarted: Bool { process.isStarted }
    var hasInFlightRequest: Bool { current != nil }
    var queuedRequestCount: Int { queue.count }

    func start(
        scriptURL: URL,
        expectation: BackendProtocolExpectation,
        onRequestStarted: @escaping (String, Bool) -> Void,
        onReply: @escaping (BackendReply) -> Void,
        onProtocolMismatch: @escaping (String) -> Void,
        onStderr: @escaping (String) -> Void,
        onLog: @escaping (String) -> Void,
        onTermination: @escaping (Int32, String) -> Void,
        onClientError: @escaping (BackendFailure, Bool) -> Void
    ) throws {
        guard !process.isStarted else { return }
        self.expectation = expectation
        self.onRequestStarted = onRequestStarted
        self.onReply = onReply
        self.onProtocolMismatch = onProtocolMismatch
        self.onStderr = onStderr
        self.onLog = onLog
        self.onTermination = onTermination
        self.onClientError = onClientError
        stderrTail = ""
        deliveringReply = false
        terminalFailureReported = false
        cancelCurrentTimeout()
        current = nil
        queue.removeAll()

        try process.start(
            scriptURL: scriptURL,
            gameID: expectation.gameID,
            onMessage: { [weak self] message in self?.receive(message) },
            onProtocolError: { [weak self] message in self?.protocolViolation(message) },
            onStderr: { [weak self] message in self?.receiveStderr(message) },
            onTermination: { [weak self] status in self?.terminated(status) }
        )
    }

    func send(
        _ command: String,
        params: [String: Any] = [:],
        operation: String,
        coalesceKey: String? = nil,
        announceSuccess: Bool = true,
        timeout: TimeInterval = 6.0,
        reply: ((BackendReply) -> Void)? = nil,
        completion: ((Bool) -> Void)? = nil
    ) {
        guard process.isRunning && !terminalFailureReported else {
            onClientError?(BackendFailure(
                code: "backend_unavailable",
                presentation: "后端未运行或正在停止。",
                diagnostic: nil,
                recoveryPath: nil
            ), true)
            completion?(false)
            return
        }
        let request = Request(
            id: UUID().uuidString,
            command: command,
            params: params,
            operation: operation,
            coalesceKey: coalesceKey,
            announceSuccess: announceSuccess,
            timeout: timeout.isFinite && timeout > 0 ? timeout : 6.0,
            reply: reply,
            completion: completion
        )

        if current != nil || deliveringReply {
            enqueue(request)
            return
        }
        dispatch(request)
    }

    func stop() {
        terminalFailureReported = true
        let outstanding = takeOutstandingRequests()
        process.stop()
        complete(outstanding, success: false)
    }

    private func enqueue(_ request: Request) {
        if let key = request.coalesceKey, let index = queue.lastIndex(where: { $0.coalesceKey == key }) {
            let replaced = queue[index]
            queue[index] = request
            replaced.completion?(false)
            onLog?("合并排队 \(request.command) · \(key)")
            return
        }
        guard queue.count < maxQueueDepth else {
            onClientError?(BackendFailure(
                code: "backend_queue_full",
                presentation: "后端请求队列已满，请稍后重试。",
                diagnostic: "queueLimit=\(maxQueueDepth) operation=\(request.operation)",
                recoveryPath: nil
            ), false)
            request.completion?(false)
            return
        }
        queue.append(request)
        onLog?("排队 \(request.command) · \(request.id)")
    }

    private func dispatch(_ request: Request) {
        guard process.isRunning && !terminalFailureReported else {
            terminalFailureReported = true
            let queued = takeQueuedRequests()
            onClientError?(BackendFailure(
                code: "backend_unavailable",
                presentation: "后端未运行或正在停止。",
                diagnostic: nil,
                recoveryPath: nil
            ), true)
            request.completion?(false)
            complete(queued, success: false)
            process.stop()
            return
        }
        do {
            current = request
            onRequestStarted?(request.operation, request.announceSuccess)
            try process.send(["id": request.id, "command": request.command, "params": request.params])
            scheduleTimeout(for: request)
            onLog?("请求 \(request.command) · \(request.id) · timeout=\(String(format: "%.1f", request.timeout))s")
        } catch {
            terminalFailureReported = true
            cancelCurrentTimeout()
            current = nil
            let queued = takeQueuedRequests()
            onClientError?(BackendFailure(
                code: "backend_send_failed",
                presentation: "发送失败；为避免未知执行结果，已停止后端。",
                diagnostic: error.localizedDescription,
                recoveryPath: nil
            ), true)
            process.stop()
            request.completion?(false)
            complete(queued, success: false)
        }
    }


    private func receive(_ message: [String: Any]) {
        guard let id = message["id"] as? String else {
            protocolViolation("后端结果缺少 request id。")
            return
        }
        guard let request = current, id == request.id else {
            onLog?("忽略未知请求结果 \(id)")
            return
        }
        guard message["type"] as? String == "result" else {
            protocolViolation("请求 \(id) 收到非 result 消息。")
            return
        }
        guard let expectation else {
            protocolViolation("BackendClient 缺少协议期望值。")
            return
        }

        let hostVersion = message["protocolVersion"] as? Int
        let moduleVersion = message["moduleProtocolVersion"] as? Int
        let gameID = message["gameID"] as? String
        guard hostVersion == expectation.hostProtocolVersion,
              moduleVersion == expectation.moduleProtocolVersion,
              gameID == expectation.gameID else {
            terminalFailureReported = true
            cancelCurrentTimeout()
            current = nil
            let queued = takeQueuedRequests()
            process.stop()
            request.completion?(false)
            complete(queued, success: false)
            let actualHost = hostVersion.map(String.init) ?? "未知"
            let actualModule = moduleVersion.map(String.init) ?? "未知"
            let actualGame = gameID ?? "未知"
            onProtocolMismatch?(
                "Backend 协议不兼容（host 需要 v\(expectation.hostProtocolVersion)，当前 \(actualHost)；module 需要 v\(expectation.moduleProtocolVersion)，当前 \(actualModule)；game=\(actualGame)）。"
            )
            return
        }

        let success = message["ok"] as? Bool ?? false
        let detail = message["error"] as? [String: Any]
        let failure: BackendFailure?
        if success {
            failure = nil
        } else {
            failure = BackendFailure(
                code: detail?["code"] as? String ?? "operation_failed",
                presentation: detail?["presentation"] as? String ?? "操作失败，请查看日志。",
                diagnostic: detail?["diagnostic"] as? String,
                recoveryPath: detail?["recoveryPath"] as? String
            )
        }
        let reply = BackendReply(
            requestID: request.id,
            command: request.command,
            hostProtocolVersion: hostVersion!,
            moduleProtocolVersion: moduleVersion!,
            gameID: gameID!,
            operation: request.operation,
            announceSuccess: request.announceSuccess,
            success: success,
            result: message["result"] as? [String: Any],
            state: message["state"] as? [String: Any],
            failure: failure
        )

        cancelCurrentTimeout()
        current = nil
        deliveringReply = true
        onReply?(reply)
        request.reply?(reply)
        request.completion?(success)
        deliveringReply = false
        flushNext()
    }

    private func receiveStderr(_ message: String) {
        let clean = message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else { return }
        stderrTail = String((stderrTail + "\n" + clean).suffix(4000))
        onStderr?(clean)
    }

    private func scheduleTimeout(for request: Request) {
        cancelCurrentTimeout()
        let item = DispatchWorkItem { [weak self] in
            self?.requestTimedOut(id: request.id)
        }
        currentTimeoutWorkItem = item
        DispatchQueue.main.asyncAfter(deadline: .now() + request.timeout, execute: item)
    }

    private func requestTimedOut(id: String) {
        guard !terminalFailureReported, let request = current, request.id == id else { return }
        terminalFailureReported = true
        let outstanding = takeOutstandingRequests()
        onClientError?(BackendFailure(
            code: "backend_timeout",
            presentation: "后端请求「\(request.operation)」超时；为避免未知执行结果，已停止后端。",
            diagnostic: "request=\(request.command) id=\(request.id) timeout=\(String(format: "%.1f", request.timeout))s",
            recoveryPath: nil
        ), true)
        process.stop()
        complete(outstanding, success: false)
    }

    private func protocolViolation(_ message: String) {
        guard !terminalFailureReported else { return }
        terminalFailureReported = true
        let outstanding = takeOutstandingRequests()
        onClientError?(BackendFailure(
            code: "backend_protocol_error",
            presentation: "后端通信协议错误，已停止后端。",
            diagnostic: message,
            recoveryPath: nil
        ), true)
        process.stop()
        complete(outstanding, success: false)
    }

    private func terminated(_ status: Int32) {
        terminalFailureReported = true
        let outstanding = takeOutstandingRequests()
        complete(outstanding, success: false)
        onTermination?(status, stderrTail.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    private func flushNext() {
        guard current == nil, !deliveringReply, !queue.isEmpty else { return }
        dispatch(queue.removeFirst())
    }

    private func cancelCurrentTimeout() {
        currentTimeoutWorkItem?.cancel()
        currentTimeoutWorkItem = nil
    }

    private func takeQueuedRequests() -> [Request] {
        let queued = queue
        queue.removeAll()
        return queued
    }

    private func takeOutstandingRequests() -> [Request] {
        cancelCurrentTimeout()
        var requests: [Request] = []
        if let active = current { requests.append(active) }
        current = nil
        requests.append(contentsOf: takeQueuedRequests())
        deliveringReply = false
        return requests
    }

    private func complete(_ requests: [Request], success: Bool) {
        requests.forEach { $0.completion?(success) }
    }
}
