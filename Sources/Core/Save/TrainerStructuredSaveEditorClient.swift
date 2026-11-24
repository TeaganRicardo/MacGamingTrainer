import Combine
import Foundation

/// Owns the structured Save Editor workspace lifetime, reply validation,
/// concurrency locks, abandoned open cleanup, and recovery/unknown-outcome state
/// around `TrainerBackendSession`.
@MainActor
package final class TrainerStructuredSaveEditorClient: ObservableObject {
    package enum LockKind: Equatable {
        case none
        case workspace
        case entry(String)
    }

    package enum RequestLock: Equatable {
        case workspace
        case entry(String, workspaceID: String?, baseline: String?)
    }

    package struct TransportFailure: Equatable {
        package let token: TrainerTextToken
        package let outcomeUnknown: Bool
    }

    @Published package private(set) var workspaceID: String?
    @Published package private(set) var baselineGeneration: String?
    @Published package private(set) var recoveryPath: String?
    @Published package private(set) var activeLocks: [UUID: RequestLock] = [:]

    package let session: TrainerBackendSession
    package let requests = TrainerSaveEditorReplyCoordinator()
    private let closeCommand: String
    private let closeTimeout: TimeInterval
    private var lifecycleObserver: UUID?

    package var onLifecycleExpired: (() -> Void)?

    package var busy: Bool { !activeLocks.isEmpty }

    package var hasWorkspaceLock: Bool {
        activeLocks.values.contains {
            if case .workspace = $0 { return true }
            return false
        }
    }

    package var documentCurrent: Bool {
        requests.owns(workspaceID: workspaceID, baselineGeneration: baselineGeneration)
    }

    package var documentBackendGeneration: UUID? { requests.documentBackendGeneration }
    package var backendLifecycleID: UUID { session.lifecycleID }

    package init(
        session: TrainerBackendSession,
        closeCommand: String = "save_editor_close",
        closeTimeout: TimeInterval = 10.0
    ) {
        self.session = session
        self.closeCommand = closeCommand
        self.closeTimeout = closeTimeout
        requests.observeBackendGeneration(session.lifecycleID)
        lifecycleObserver = session.observeLifecycle { [weak self] generation in
            guard let self, self.requests.observeBackendGeneration(generation) else { return }
            self.activeLocks.removeAll()
            self.onLifecycleExpired?()
        }
    }

    isolated deinit {
        if let lifecycleObserver {
            session.removeLifecycleObserver(lifecycleObserver)
        }
    }

    package func owns(workspaceID: String? = nil, baseline: String? = nil) -> Bool {
        requests.owns(
            workspaceID: workspaceID ?? self.workspaceID,
            baselineGeneration: baseline ?? baselineGeneration
        )
    }

    package func canEditEntry(_ entryID: String, baseline: String) -> Bool {
        guard owns(baseline: baseline) else { return false }
        return activeLocks.values.allSatisfy { lock in
            switch lock {
            case .workspace:
                return false
            case .entry(let identifier, let lockedWorkspace, let lockedBaseline):
                // An older workspace's completion cannot grant an exemption
                // to fields in a replacement document, even if IDs repeat.
                return lockedWorkspace == workspaceID
                    && lockedBaseline == baselineGeneration
                    && identifier != entryID
            }
        }
    }

    package func bind(workspaceID: String, baselineGeneration: String) {
        requests.bind(workspaceID: workspaceID, baselineGeneration: baselineGeneration)
        self.workspaceID = workspaceID
        self.baselineGeneration = baselineGeneration
    }

    package func invalidateDocument() {
        requests.invalidateDocument()
    }

    package func invalidate(_ lane: TrainerSaveEditorReplyCoordinator.Lane) {
        requests.invalidate(lane)
    }

    package func clearRecoveryPath() {
        recoveryPath = nil
    }

    package func recordRecoveryPath(_ path: String?) {
        if let path, !path.isEmpty {
            recoveryPath = path
        }
    }

    package func releaseWorkspace(_ identifier: String) {
        session.send(
            closeCommand,
            params: ["workspaceId": identifier],
            operation: "host.done",
            announceSuccess: false,
            timeout: closeTimeout,
            requiresTrustedTarget: false
        )
    }

    package func releasePreviousWorkspace(_ identifier: String?, capturedGeneration: UUID?) {
        guard capturedGeneration == session.lifecycleID,
              let identifier,
              identifier != workspaceID else { return }
        releaseWorkspace(identifier)
    }

    package func retireAndClose() {
        if let workspaceID, requests.documentBackendGeneration == session.lifecycleID {
            releaseWorkspace(workspaceID)
        }
        activeLocks.removeAll()
        requests.retire()
        workspaceID = nil
        baselineGeneration = nil
        recoveryPath = nil
    }

    package func send(
        _ command: String,
        params: [String: Any] = [:],
        operation: String,
        announceSuccess: Bool = false,
        timeout: TimeInterval = 30.0,
        requiresTrustedTarget: Bool = false,
        bindsWorkspace: Bool = true,
        explicitWorkspaceID: String? = nil,
        sendBaseline: Bool = false,
        explicitBaseline: String? = nil,
        draftEntryIDs: [String]? = nil,
        lock: LockKind = .workspace,
        lane: TrainerSaveEditorReplyCoordinator.Lane? = nil,
        isOpenCommand: Bool = false,
        isApplyCommand: Bool = false,
        invalidatesReview: Bool = false,
        onExpired: (() -> Void)? = nil,
        onReply: @escaping (BackendReply) -> Void,
        onTransportFailure: ((TransportFailure) -> Void)? = nil,
        onCompletion: ((Bool) -> Void)? = nil
    ) {
        let targetWS = bindsWorkspace ? (explicitWorkspaceID ?? workspaceID) : nil
        let targetGen = bindsWorkspace ? (explicitBaseline ?? baselineGeneration) : nil
        if bindsWorkspace, !requests.owns(workspaceID: targetWS, baselineGeneration: targetGen) {
            onExpired?()
            onCompletion?(false)
            return
        }
        if invalidatesReview {
            requests.invalidate(.review)
        }
        let ticket = isOpenCommand
            ? requests.beginNewDocumentRead()
            : requests.capture(lane, bindsDocument: bindsWorkspace)
        let capturedLifecycle = session.lifecycleID
        let requestID = UUID()
        switch lock {
        case .none:
            break
        case .workspace:
            activeLocks[requestID] = .workspace
        case .entry(let entryID):
            activeLocks[requestID] = .entry(entryID, workspaceID: targetWS, baseline: targetGen)
        }

        var payload = params
        if let targetWS { payload["workspaceId"] = targetWS }
        if sendBaseline, let targetGen { payload["baselineGeneration"] = targetGen }
        if let draftEntryIDs { payload["draftEntryIds"] = draftEntryIDs }

        session.send(
            command,
            params: payload,
            operation: operation,
            announceSuccess: announceSuccess,
            timeout: timeout,
            requiresTrustedTarget: requiresTrustedTarget,
            reply: { [weak self] reply in
                guard let self else { return }
                let accepts = self.requests.accepts(ticket)
                let stillMatches = !bindsWorkspace
                    || (self.workspaceID == targetWS && (!sendBaseline || self.baselineGeneration == targetGen))
                guard accepts, stillMatches else {
                    if isOpenCommand,
                       self.session.lifecycleID == capturedLifecycle,
                       reply.success,
                       let abandoned = reply.result?["workspaceId"] as? String,
                       abandoned != self.workspaceID {
                        self.releaseWorkspace(abandoned)
                    }
                    return
                }
                if !reply.success, let path = reply.failure?.recoveryPath, !path.isEmpty {
                    self.recoveryPath = path
                }
                onReply(reply)
            },
            failed: { [weak self] failure in
                guard let self, self.requests.accepts(ticket) else { return }
                let key = failure.outcomeUnknown
                    ? (isApplyCommand ? "host.save.error.applyUnconfirmed" : "host.save.error.incomplete")
                    : "host.backend.error.notSent"
                if isApplyCommand, failure.outcomeUnknown {
                    self.requests.invalidateDocument()
                }
                onTransportFailure?(TransportFailure(token: TrainerTextToken(key: key), outcomeUnknown: failure.outcomeUnknown))
            },
            completion: { [weak self] _ in
                guard let self else { return }
                if lock != .none {
                    self.activeLocks.removeValue(forKey: requestID)
                }
                onCompletion?(self.requests.accepts(ticket))
            }
        )
    }

    package static func decode<T: Decodable>(_ type: T.Type, from object: [String: Any]) -> T? {
        guard JSONSerialization.isValidJSONObject(object),
              let data = try? JSONSerialization.data(withJSONObject: object) else { return nil }
        return try? JSONDecoder().decode(T.self, from: data)
    }
}
