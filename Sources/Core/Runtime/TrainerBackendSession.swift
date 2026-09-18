import Foundation

struct TrainerBackendStatus: Equatable {
    var backendAvailable = false
    var backendProtocolVersion: Int?
    var backendModuleProtocolVersion: Int?
    var protocolCompatible = true
    var busy = false
    var operation = ""
    var error = ""
    var notice = ""
}

/// Runtime service around BackendClient. It is intentionally not ObservableObject:
/// presentation models own observable state and receive immutable status values
/// through `onStatusChange`.
///
/// Backend lifecycle recovery lives here instead of in a game module. An
/// unexpected worker exit gets a bounded restart attempt; once the worker is
/// back, the host-level target-process coordinator decides whether to reconnect
/// the active game. No window activation and no process polling are involved.
final class TrainerBackendSession {
    private struct Configuration {
        let descriptor: GameModuleDescriptor
        let scriptURL: URL
        let applyPayload: ([String: Any]) -> Void
        let resetGameState: () -> Void
        let log: (String) -> Void
        let onStatusChange: (TrainerBackendStatus) -> Void
    }

    private let client: BackendClient
    private var status = TrainerBackendStatus()
    private var configuration: Configuration?
    private var suppressTerminationError = false
    private var restartPending = false
    private var recoveryWorkItem: DispatchWorkItem?
    private var automaticRecoveryAttempts = 0
    private let maximumAutomaticRecoveryAttempts = 2

    init(client: BackendClient = BackendClient()) {
        self.client = client
    }

    var isRunning: Bool { client.isRunning }
    var isStarted: Bool { client.isStarted }
    var currentStatus: TrainerBackendStatus { status }

    func start(
        descriptor: GameModuleDescriptor,
        backendScriptURL: URL? = nil,
        applyPayload: @escaping ([String: Any]) -> Void,
        resetGameState: @escaping () -> Void,
        log: @escaping (String) -> Void,
        onStatusChange: @escaping (TrainerBackendStatus) -> Void
    ) throws {
        guard !client.isStarted else { return }
        let scriptURL = try resolveScriptURL(backendScriptURL)
        configuration = Configuration(
            descriptor: descriptor,
            scriptURL: scriptURL,
            applyPayload: applyPayload,
            resetGameState: resetGameState,
            log: log,
            onStatusChange: onStatusChange
        )
        automaticRecoveryAttempts = 0
        try startClient(clearStatus: true, recoveryNotice: nil)
    }

    func send(
        _ command: String,
        params: [String: Any] = [:],
        operation: String,
        coalesceKey: String? = nil,
        announceSuccess: Bool = true,
        timeout: TimeInterval = 6.0,
        completion: ((Bool) -> Void)? = nil
    ) {
        client.send(
            command,
            params: params,
            operation: operation,
            coalesceKey: coalesceKey,
            announceSuccess: announceSuccess,
            timeout: timeout,
            completion: completion
        )
    }

    /// Restarts the worker in one action even when it is currently running.
    /// The old process remains owned until its termination callback fires, so a
    /// replacement worker cannot race the old stdout/LLDB state.
    func restart() {
        guard configuration != nil else { return }
        cancelRecovery()
        restartPending = true
        suppressTerminationError = true
        updateStatus {
            $0.busy = true
            $0.operation = "重启后端"
            $0.error = ""
            $0.notice = ""
        }
        if client.isStarted {
            client.stop()
        } else {
            restartPending = false
            suppressTerminationError = false
            scheduleRecovery(manual: true)
        }
    }

    func stop(suppressTerminationError: Bool = true) {
        cancelRecovery()
        restartPending = false
        self.suppressTerminationError = suppressTerminationError
        client.stop()
    }

    func markUnavailable(_ message: String) {
        updateStatus {
            $0.backendAvailable = false
            $0.busy = false
            $0.error = message
        }
    }

    private func resolveScriptURL(_ backendScriptURL: URL?) throws -> URL {
        let scriptURL: URL
        if let backendScriptURL {
            scriptURL = backendScriptURL
        } else {
            guard let resourceURL = Bundle.main.resourceURL else {
                throw NSError(domain: "TrainerBackendSession", code: 1, userInfo: [NSLocalizedDescriptionKey: "App Resources directory is unavailable."])
            }
            scriptURL = resourceURL.appendingPathComponent("Backend/core/server.py")
        }
        guard FileManager.default.fileExists(atPath: scriptURL.path) else {
            throw NSError(domain: "TrainerBackendSession", code: 2, userInfo: [NSLocalizedDescriptionKey: "Backend entrypoint is missing: \(scriptURL.path)"])
        }
        return scriptURL
    }

    private func startClient(clearStatus: Bool, recoveryNotice: String?) throws {
        guard let configuration else {
            throw NSError(domain: "TrainerBackendSession", code: 3, userInfo: [NSLocalizedDescriptionKey: "Backend session has no start configuration."])
        }
        guard !client.isStarted else { return }
        suppressTerminationError = false
        if clearStatus { setStatus(TrainerBackendStatus()) }

        try client.start(
            scriptURL: configuration.scriptURL,
            expectation: BackendProtocolExpectation(
                gameID: configuration.descriptor.backendGameID,
                hostProtocolVersion: configuration.descriptor.expectedHostProtocolVersion,
                moduleProtocolVersion: configuration.descriptor.expectedModuleProtocolVersion
            ),
            onRequestStarted: { [weak self] title, announceSuccess in
                self?.updateStatus {
                    $0.busy = true
                    $0.operation = title
                    $0.error = ""
                    if announceSuccess { $0.notice = "" }
                }
            },
            onReply: { [weak self] reply in
                guard let self else { return }
                if reply.success { self.automaticRecoveryAttempts = 0 }
                self.updateStatus {
                    $0.backendProtocolVersion = reply.hostProtocolVersion
                    $0.backendModuleProtocolVersion = reply.moduleProtocolVersion
                    $0.protocolCompatible = true
                    $0.busy = false
                }
                if reply.success {
                    if let result = reply.result { configuration.applyPayload(result) }
                    if reply.announceSuccess { self.updateStatus { $0.notice = "\(reply.operation)完成" } }
                } else {
                    if let state = reply.state { configuration.applyPayload(state) }
                    let message = reply.errorMessage ?? "操作失败，请查看日志。"
                    self.updateStatus { $0.error = message }
                    configuration.log("\(reply.operation)失败 [\(reply.errorCode ?? "unknown")]：\(message)")
                }
            },
            onProtocolMismatch: { [weak self] message in
                self?.cancelRecovery()
                self?.updateStatus {
                    $0.protocolCompatible = false
                    $0.backendAvailable = false
                    $0.busy = false
                    $0.error = message + " 请使用同一发布包重新构建 App。"
                }
                configuration.log("协议不兼容：\(message)")
            },
            onStderr: { clean in configuration.log("BACKEND: \(clean)") },
            onLog: configuration.log,
            onTermination: { [weak self] exitStatus, stderrTail in
                self?.handleTermination(status: exitStatus, stderrTail: stderrTail)
            },
            onClientError: { [weak self] message, terminal in
                guard let self else { return }
                if terminal {
                    configuration.log("后端通信终止：\(message)")
                    self.updateStatus {
                        $0.busy = true
                        $0.operation = "恢复后端"
                        $0.error = ""
                        $0.notice = "后端通信异常，正在自动恢复"
                    }
                } else {
                    self.updateStatus {
                        $0.busy = false
                        $0.error = message
                    }
                }
            }
        )
        updateStatus {
            $0.backendAvailable = true
            $0.busy = false
            $0.operation = ""
            $0.error = ""
            if let recoveryNotice { $0.notice = recoveryNotice }
        }
    }

    private func handleTermination(status exitStatus: Int32, stderrTail: String) {
        guard let configuration else { return }
        let mismatch = !status.protocolCompatible
        let manualRestart = restartPending
        restartPending = false
        let automaticRecovery = !manualRestart
            && !suppressTerminationError
            && !mismatch
            && automaticRecoveryAttempts < maximumAutomaticRecoveryAttempts
        let willRecover = manualRestart || automaticRecovery

        updateStatus {
            $0.backendAvailable = false
            $0.backendProtocolVersion = nil
            $0.backendModuleProtocolVersion = nil
            if !mismatch { $0.protocolCompatible = true }
            $0.busy = willRecover
            $0.operation = willRecover ? "恢复后端" : ""
            if !willRecover && !suppressTerminationError && !mismatch {
                let suffix = stderrTail.isEmpty ? "" : "\n\n后端输出：\n\(stderrTail)"
                $0.error = "后端已退出（状态 \(exitStatus)）。游戏内修改可能仍然生效。\(suffix)"
            }
        }
        configuration.resetGameState()
        configuration.log("后端退出 status=\(exitStatus) recovery=\(willRecover)")

        suppressTerminationError = false
        if willRecover {
            scheduleRecovery(manual: manualRestart)
        }
    }

    private func scheduleRecovery(manual: Bool) {
        guard configuration != nil else { return }
        cancelRecovery()
        if !manual { automaticRecoveryAttempts += 1 }
        let attempt = automaticRecoveryAttempts
        let delay: TimeInterval = manual ? 0.05 : (attempt <= 1 ? 0.25 : 0.8)
        let item = DispatchWorkItem { [weak self] in
            guard let self else { return }
            self.recoveryWorkItem = nil
            do {
                try self.startClient(clearStatus: false, recoveryNotice: manual ? "后端已重启" : "后端已自动恢复")
            } catch {
                self.configuration?.log("后端恢复启动失败：\(error.localizedDescription)")
                if !manual && self.automaticRecoveryAttempts < self.maximumAutomaticRecoveryAttempts {
                    self.scheduleRecovery(manual: false)
                } else {
                    self.updateStatus {
                        $0.backendAvailable = false
                        $0.busy = false
                        $0.operation = ""
                        $0.error = "无法恢复后端：\(error.localizedDescription)"
                    }
                }
            }
        }
        recoveryWorkItem = item
        DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: item)
    }

    private func cancelRecovery() {
        recoveryWorkItem?.cancel()
        recoveryWorkItem = nil
    }

    private func updateStatus(_ change: (inout TrainerBackendStatus) -> Void) {
        var next = status
        change(&next)
        setStatus(next)
    }

    private func setStatus(_ next: TrainerBackendStatus) {
        status = next
        configuration?.onStatusChange(next)
    }
}
