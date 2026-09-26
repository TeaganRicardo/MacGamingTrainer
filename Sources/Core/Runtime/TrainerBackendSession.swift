import Foundation

struct TrainerBackendStatus: Equatable {
    var backendAvailable = false
    var backendProtocolVersion: Int?
    var backendModuleProtocolVersion: Int?
    var protocolCompatible = true
    var busy = false
    var operation = ""
    var errorCode: String?
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
    private(set) var lifecycleID = UUID()
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
        lifecycleID = UUID()
        let scriptURL: URL
        do {
            scriptURL = try resolveScriptURL(backendScriptURL)
        } catch {
            publishStartupFailure(error, log: log, onStatusChange: onStatusChange)
            throw error
        }
        configuration = Configuration(
            descriptor: descriptor,
            scriptURL: scriptURL,
            applyPayload: applyPayload,
            resetGameState: resetGameState,
            log: log,
            onStatusChange: onStatusChange
        )
        automaticRecoveryAttempts = 0
        do {
            try startClient(clearStatus: true, recoveryNotice: nil)
        } catch {
            publishStartupFailure(error, log: log, onStatusChange: onStatusChange)
            throw error
        }
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
        client.send(
            command,
            params: params,
            operation: operation,
            coalesceKey: coalesceKey,
            announceSuccess: announceSuccess,
            timeout: timeout,
            reply: reply,
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
            $0.errorCode = nil
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

    private func publishStartupFailure(
        _ error: Error,
        log: (String) -> Void,
        onStatusChange: (TrainerBackendStatus) -> Void
    ) {
        let failure = BackendFailure(
            code: "backend_start_failed",
            presentation: "无法启动后端，请查看日志。",
            diagnostic: error.localizedDescription,
            recoveryPath: nil
        )
        var next = status
        next.backendAvailable = false
        next.busy = false
        next.errorCode = failure.code
        next.error = failure.presentation
        status = next
        onStatusChange(next)
        log("后端启动失败 [\(failure.code)]：\(failure.diagnostic ?? failure.presentation)")
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
                    $0.errorCode = nil
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
                let coreOwned = reply.command.hasPrefix("core.")
                if reply.success {
                    if !coreOwned, let result = reply.result { configuration.applyPayload(result) }
                    if reply.announceSuccess { self.updateStatus { $0.notice = "\(reply.operation)完成" } }
                } else {
                    if !coreOwned, let state = reply.state { configuration.applyPayload(state) }
                    let failure = reply.failure ?? BackendFailure(
                        code: "operation_failed",
                        presentation: "操作失败，请查看日志。",
                        diagnostic: nil,
                        recoveryPath: nil
                    )
                    self.updateStatus {
                        $0.errorCode = failure.code
                        $0.error = failure.presentation
                    }
                    let diagnostic = failure.diagnostic ?? failure.presentation
                    configuration.log("\(reply.operation)失败 [\(failure.code)]：\(diagnostic)")
                }
            },
            onProtocolMismatch: { [weak self] failure in
                self?.cancelRecovery()
                self?.updateStatus {
                    $0.protocolCompatible = false
                    $0.backendAvailable = false
                    $0.busy = false
                    $0.errorCode = failure.code
                    $0.error = failure.presentation
                }
                let diagnostic = failure.diagnostic ?? failure.presentation
                configuration.log("协议不兼容 [\(failure.code)]：\(diagnostic)")
            },
            onStderr: { clean in configuration.log("BACKEND: \(clean)") },
            onLog: configuration.log,
            onTermination: { [weak self] exitStatus, stderrTail in
                self?.handleTermination(status: exitStatus, stderrTail: stderrTail)
            },
            onClientError: { [weak self] failure, terminal in
                guard let self else { return }
                let diagnostic = failure.diagnostic ?? failure.presentation
                if terminal {
                    configuration.log("后端通信终止 [\(failure.code)]：\(diagnostic)")
                    self.updateStatus {
                        $0.busy = true
                        $0.operation = "恢复后端"
                        $0.errorCode = nil
                        $0.error = ""
                        $0.notice = "后端通信异常，正在自动恢复"
                    }
                } else {
                    configuration.log("后端通信错误 [\(failure.code)]：\(diagnostic)")
                    self.updateStatus {
                        $0.busy = false
                        $0.errorCode = failure.code
                        $0.error = failure.presentation
                    }
                }
            }
        )
        updateStatus {
            $0.backendAvailable = true
            $0.busy = false
            $0.operation = ""
            $0.errorCode = nil
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
                $0.errorCode = "backend_terminated"
                $0.error = "后端已退出。游戏内修改可能仍然生效。"
            }
        }
        configuration.resetGameState()
        let terminationDiagnostic = stderrTail.isEmpty ? "none" : stderrTail
        configuration.log("后端退出 status=\(exitStatus) recovery=\(willRecover) stderr=\(terminationDiagnostic)")

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
                        $0.errorCode = "backend_recovery_failed"
                        $0.error = "无法恢复后端，请查看日志。"
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
