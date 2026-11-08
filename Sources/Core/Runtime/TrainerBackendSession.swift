import Foundation

struct TrainerBackendStatus: Equatable {
    var backendAvailable = false
    var backendProtocolVersion: Int?
    var backendModuleProtocolVersion: Int?
    var protocolCompatible = true
    var requiresTargetRestart = false
    var busy = false
    /// Language-neutral operation identity shown while a request is in flight.
    var operation = TrainerTextToken(key: "")
    var errorCode: String?
    /// Error keys are stored with their arguments so the owning module can render
    /// the sentence in the Host's live language.
    var error = ""
    var errorArguments: [String] = []
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
        let backendLog: (String) -> Void
        let onStatusChange: (TrainerBackendStatus) -> Void
    }

    private let client: BackendClient
    private var status = TrainerBackendStatus()
    private(set) var lifecycleID = UUID() {
        didSet { Array(lifecycleObservers.values).forEach { $0(lifecycleID) } }
    }
    private var lifecycleObservers: [UUID: (UUID) -> Void] = [:]
    private var configuration: Configuration?
    private var suppressTerminationError = false
    private var restartPending = false
    private var recoveryWorkItem: DispatchWorkItem?
    private var automaticRecoveryAttempts = 0
    private let maximumAutomaticRecoveryAttempts = 2
    private var terminationRequested = false
    private var targetLifetimeID = UUID()
    private var activeRequestTargetLifetimeID: UUID?
    private var activeRequestRequiresTrustedTarget = true
    private var uncertainFailure: BackendFailure?
    private var untrustedTargetLifetimeID: UUID?

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
        onStatusChange: @escaping (TrainerBackendStatus) -> Void,
        backendLog: ((String) -> Void)? = nil
    ) throws {
        guard !terminationRequested, !client.isStarted else { return }
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
            backendLog: backendLog ?? log,
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
        operationArguments: [String] = [],
        coalesceKey: String? = nil,
        announceSuccess: Bool = true,
        timeout: TimeInterval = 6.0,
        requiresTrustedTarget: Bool = true,
        started: (() -> Void)? = nil,
        reply: ((BackendReply) -> Void)? = nil,
        failed: ((BackendFailure) -> Void)? = nil,
        completion: ((Bool) -> Void)? = nil
    ) {
        guard !requiresTrustedTarget || untrustedTargetLifetimeID != targetLifetimeID else {
            configuration?.log("目标进程的操作结果尚未确认；等待新的目标进程后再执行 \(command)。")
            failed?(BackendFailure(code: "backend_cancelled", presentation: "host.backend.error.targetRestartRequired",
                diagnostic: nil, recoveryPath: nil, presentationArguments: []))
            completion?(false)
            return
        }
        client.send(
            command,
            params: params,
            operation: operation,
            operationArguments: operationArguments,
            coalesceKey: coalesceKey,
            announceSuccess: announceSuccess,
            timeout: timeout,
            started: { [weak self] in
                self?.activeRequestTargetLifetimeID = self?.targetLifetimeID
                self?.activeRequestRequiresTrustedTarget = requiresTrustedTarget
                started?()
            },
            reply: reply,
            failed: failed,
            completion: completion
        )
    }

    /// Restarts the worker in one action even when it is currently running.
    /// The old process remains owned until its termination callback fires, so a
    /// replacement worker cannot race the old stdout/LLDB state.
    func restart() {
        guard !terminationRequested, configuration != nil else { return }
        cancelRecovery()
        restartPending = true
        suppressTerminationError = true
        updateStatus {
            $0.busy = true
            $0.operation = TrainerTextToken(key: "host.restartBackend")
            $0.errorCode = nil
            $0.error = ""
            $0.errorArguments = []
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

    /// Drain backend stderr already buffered by the process before exporting
    /// diagnostics. Backend restart/reconnect state is otherwise unchanged.
    func flushDiagnostics() {
        client.flushStderr()
    }

    func stop(suppressTerminationError: Bool = true) {
        cancelRecovery()
        restartPending = false
        self.suppressTerminationError = suppressTerminationError
        client.stop()
    }

    func beginTermination() {
        terminationRequested = true
        cancelRecovery()
        restartPending = false
        updateStatus {
            $0.busy = client.hasInFlightRequest
            if !$0.busy { $0.operation = TrainerTextToken(key: "") }
        }
    }

    func observeLifecycle(_ observer: @escaping (UUID) -> Void) -> UUID {
        let id = UUID()
        lifecycleObservers[id] = observer
        return id
    }

    func removeLifecycleObserver(_ id: UUID) {
        lifecycleObservers.removeValue(forKey: id)
    }

    /// Only definitive target-lifetime evidence releases a runtime trust gate.
    /// A new worker, activation, or the same PID does not establish that evidence.
    func targetLifetimeChanged() {
        targetLifetimeID = UUID()
        untrustedTargetLifetimeID = nil
        if uncertainFailure != nil {
            uncertainFailure = nil
            updateStatus {
                $0.errorCode = nil
                $0.error = ""
                $0.errorArguments = []
            }
        }
    }

    private func preserveUnknownOutcome(_ failure: BackendFailure) {
        guard failure.outcomeUnknown else { return }
        if uncertainFailure == nil { uncertainFailure = failure }
        if activeRequestRequiresTrustedTarget, activeRequestTargetLifetimeID == targetLifetimeID {
            untrustedTargetLifetimeID = targetLifetimeID
        }
    }

    private func publishStartupFailure(
        _ error: Error,
        log: (String) -> Void,
        onStatusChange: (TrainerBackendStatus) -> Void
    ) {
        let failure = BackendFailure(
            code: "backend_start_failed",
            presentation: "host.backend.error.startFailed",
            diagnostic: error.localizedDescription,
            recoveryPath: nil,
            presentationArguments: []
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
        guard !terminationRequested, !client.isStarted else { return }
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
                    $0.errorArguments = []
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
                if let failure = reply.failure { self.preserveUnknownOutcome(failure) }
                func apply(_ payload: [String: Any]) {
                    let started = BackendOperationProfile.enabled ? BackendOperationProfile.now() : 0
                    configuration.applyPayload(payload)
                    BackendOperationProfile.emit("host.payload_apply", id: reply.requestID, command: reply.command,
                        seconds: BackendOperationProfile.now() - started, log: configuration.log)
                }
                let coreOwned = reply.command.hasPrefix("core.")
                if reply.success {
                    if !coreOwned, let result = reply.result { apply(result) }
                    if reply.announceSuccess { self.updateStatus { $0.notice = "host.backend.notice.completed" } }
                } else {
                    if !coreOwned, let state = reply.state { apply(state) }
                    let failure = reply.failure ?? BackendFailure(
                        code: "operation_failed",
                        presentation: "host.backend.error.operationFailed",
                        diagnostic: nil,
                        recoveryPath: nil,
                        presentationArguments: []
                    )
                    self.updateStatus {
                        $0.errorCode = failure.code
                        $0.error = coreOwned ? "host.backend.error.operationFailed" : failure.presentation
                        $0.errorArguments = coreOwned ? [] : failure.presentationArguments
                    }
                    let diagnostic = failure.diagnostic ?? failure.presentation
                    configuration.backendLog("\(reply.operation.key)失败 [\(failure.code)]：\(diagnostic)")
                }
            },
            onProtocolMismatch: { [weak self] failure in
                self?.preserveUnknownOutcome(failure)
                self?.cancelRecovery()
                self?.updateStatus {
                    $0.protocolCompatible = false
                    $0.backendAvailable = false
                    $0.busy = false
                    $0.errorCode = failure.code
                    $0.error = "host.backend.error.protocolMismatch"
                }
                let diagnostic = failure.diagnostic ?? failure.presentation
                configuration.backendLog("协议不兼容 [\(failure.code)]：\(diagnostic)")
            },
            onStderr: { clean in configuration.backendLog(clean) },
            onLog: configuration.log,
            onTermination: { [weak self] exitStatus, _ in
                self?.handleTermination(status: exitStatus)
            },
            onClientError: { [weak self] failure, terminal in
                guard let self else { return }
                self.preserveUnknownOutcome(failure)
                let diagnostic = failure.diagnostic ?? failure.presentation
                if terminal {
                    configuration.backendLog("后端通信终止 [\(failure.code)]：\(diagnostic)")
                    let recoveryOwned = self.client.isStarted
                        || self.recoveryWorkItem != nil
                        || self.restartPending
                    self.updateStatus {
                        if recoveryOwned {
                            $0.busy = true
                            $0.operation = TrainerTextToken(key: "host.backend.operation.recover")
                            $0.errorCode = nil
                            $0.error = ""
                            $0.errorArguments = []
                            $0.notice = "host.backend.notice.recovering"
                        } else {
                            $0.backendAvailable = false
                            $0.backendProtocolVersion = nil
                            $0.backendModuleProtocolVersion = nil
                            $0.busy = false
                            $0.operation = TrainerTextToken(key: "")
                            $0.errorCode = failure.code
                            $0.error = self.hostClientFailurePresentation(failure)
                            $0.errorArguments = []
                            $0.notice = ""
                        }
                    }
                } else {
                    configuration.backendLog("后端通信错误 [\(failure.code)]：\(diagnostic)")
                    self.updateStatus {
                        $0.busy = self.client.hasInFlightRequest
                        $0.errorCode = failure.code
                        $0.error = self.hostClientFailurePresentation(failure)
                    }
                }
            }
        )
        lifecycleID = UUID()
        updateStatus {
            $0.backendAvailable = true
            $0.busy = false
            $0.operation = TrainerTextToken(key: "")
            $0.errorCode = nil
            $0.error = ""
            $0.errorArguments = []
            if let recoveryNotice { $0.notice = recoveryNotice }
        }
    }

    private func handleTermination(status exitStatus: Int32) {
        guard let configuration else { return }
        lifecycleID = UUID()
        let mismatch = !status.protocolCompatible
        let manualRestart = restartPending
        restartPending = false
        let automaticRecovery = !manualRestart
            && !suppressTerminationError
            && !mismatch
            && automaticRecoveryAttempts < maximumAutomaticRecoveryAttempts
        let willRecover = !terminationRequested && (manualRestart || automaticRecovery)

        updateStatus {
            $0.backendAvailable = false
            $0.backendProtocolVersion = nil
            $0.backendModuleProtocolVersion = nil
            if !mismatch { $0.protocolCompatible = true }
            $0.busy = willRecover
            $0.operation = TrainerTextToken(key: willRecover ? "host.backend.operation.recover" : "")
            if !willRecover && !suppressTerminationError && !mismatch {
                $0.errorCode = "backend_terminated"
                $0.error = "host.backend.error.terminated"
            }
        }
        configuration.resetGameState()
        configuration.backendLog(
            "后端退出 status=\(exitStatus) recovery=\(willRecover)"
        )

        suppressTerminationError = false
        if willRecover {
            scheduleRecovery(manual: manualRestart)
        }
    }

    private func scheduleRecovery(manual: Bool) {
        guard !terminationRequested, configuration != nil else { return }
        cancelRecovery()
        if !manual { automaticRecoveryAttempts += 1 }
        let attempt = automaticRecoveryAttempts
        let delay: TimeInterval = manual ? 0.05 : (attempt <= 1 ? 0.25 : 0.8)
        let item = DispatchWorkItem { [weak self] in
            guard let self else { return }
            self.recoveryWorkItem = nil
            guard !self.terminationRequested else { return }
            do {
                try self.startClient(clearStatus: false, recoveryNotice: manual ? "host.backend.notice.restarted" : "host.backend.notice.recovered")
            } catch {
                self.configuration?.log("后端恢复启动失败：\(error.localizedDescription)")
                if !manual && self.automaticRecoveryAttempts < self.maximumAutomaticRecoveryAttempts {
                    self.scheduleRecovery(manual: false)
                } else {
                    self.updateStatus {
                        $0.backendAvailable = false
                        $0.busy = false
                        $0.operation = TrainerTextToken(key: "")
                        $0.errorCode = "backend_recovery_failed"
                        $0.error = "host.backend.error.recoveryFailed"
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

    private func hostClientFailurePresentation(_ failure: BackendFailure) -> String {
        switch failure.code {
        case "backend_unavailable":
            return "host.backend.error.unavailable"
        case "backend_queue_full":
            return "host.backend.error.queueFull"
        case "backend_send_failed":
            return "host.backend.error.sendFailed"
        case "protocol_mismatch":
            return "host.backend.error.protocolMismatch"
        case "backend_timeout":
            return "host.backend.error.timeout"
        case "backend_protocol_error":
            return "host.backend.error.protocolError"
        default:
            return "host.backend.error.operationFailed"
        }
    }

    private func updateStatus(_ change: (inout TrainerBackendStatus) -> Void) {
        var next = status
        change(&next)
        setStatus(next)
    }

    private func setStatus(_ value: TrainerBackendStatus) {
        var next = value
        next.requiresTargetRestart = untrustedTargetLifetimeID == targetLifetimeID
        if let uncertainFailure {
            next.errorCode = "outcome_unknown"
            next.error = uncertainFailure.code == "outcome_unknown" ? uncertainFailure.presentation :
                (next.requiresTargetRestart ? "host.backend.error.targetOutcomeUnknown" : "host.backend.error.outcomeUnknown")
            next.errorArguments = uncertainFailure.code == "outcome_unknown" ? uncertainFailure.presentationArguments : []
        }
        status = next
        configuration?.onStatusChange(next)
    }
}
