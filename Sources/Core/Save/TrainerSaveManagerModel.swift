import AppKit
import Combine
import Foundation

final class TrainerSaveManagerModel: ObservableObject {
    @Published private(set) var snapshots: [TrainerSaveSnapshot] = []
    @Published private(set) var pendingRestore: TrainerPendingRestore?
    @Published private(set) var recoveryPaths: [String] = []
    @Published private(set) var busy = false
    @Published private(set) var error = ""
    @Published private(set) var errorArguments: [String] = []
    @Published private(set) var notice = ""
    @Published private(set) var noticeArguments: [String] = []

    private let session: TrainerBackendSession
    private var activeRequestTokens: Set<UUID> = []

    init(session: TrainerBackendSession) {
        self.session = session
    }

    func refresh() {
        request("core.save.list", operation: "host.save.operation.refresh", successNotice: nil)
    }

    func backup(name: String? = nil) {
        var params: [String: Any] = [:]
        if let name, !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            params["name"] = name
        }
        request("core.save.backup", params: params, operation: "host.save.operation.create", successNotice: "host.save.notice.created")
    }

    func rename(id: String, name: String, completion: ((Bool) -> Void)? = nil) {
        let clean = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !id.isEmpty, !clean.isEmpty else {
            completion?(false)
            return
        }
        request(
            "core.save.rename",
            params: ["snapshotId": id, "name": clean],
            operation: "host.save.operation.rename",
            successNotice: "host.save.notice.renamed",
            onComplete: completion
        )
    }

    func delete(ids: Set<String>) {
        let ordered = ids.filter { !$0.isEmpty }.sorted()
        guard !ordered.isEmpty else { return }
        deleteNext(ordered, deleted: 0)
    }

    func revealRecoveryCopies() {
        let urls = recoveryPaths.compactMap {
            TrainerSavePathValidator.validatedLocalURL(for: $0)
        }
        guard !urls.isEmpty else { return }
        NSWorkspace.shared.activateFileViewerSelecting(urls)
    }

    func reveal(id: String? = nil) {
        var params: [String: Any] = [:]
        if let id { params["snapshotId"] = id }
        request(
            "core.save.open_folder",
            params: params,
            operation: id == nil ? "host.save.operation.openFolder" : "host.save.operation.show",
            successNotice: nil
        ) { [weak self] reply in
            guard let self else { return }
            guard reply.success else { return }
            guard let path = reply.result?["folder"] as? String,
                  let url = TrainerSavePathValidator.validatedDirectoryURL(for: path) else {
                self.setError("host.save.error.invalidFolder")
                return
            }
            if id == nil {
                NSWorkspace.shared.open(url)
            } else {
                NSWorkspace.shared.activateFileViewerSelecting([url])
            }
        }
    }

    func restore(id: String, preserveCurrent: Bool) {
        guard !id.isEmpty else { return }
        request(
            "core.save.restore",
            params: ["snapshotId": id, "preserveCurrent": preserveCurrent],
            operation: "host.save.operation.restore",
            successNotice: "host.save.notice.restoreSubmitted"
        )
    }

    func cancelStaged() {
        request(
            "core.save.cancel_staged",
            operation: "host.save.operation.cancelPending",
            successNotice: "host.save.notice.pendingCancelled"
        )
    }

    func applyStagedIfPossible() {
        request(
            "core.save.apply_staged",
            operation: "host.save.operation.applyPending",
            successNotice: nil
        ) { [weak self] reply in
            guard let operation = reply.result?["operation"] as? [String: Any],
                  operation["applied"] as? Bool == true else { return }
            self?.setNotice("host.save.notice.pendingApplied")
        }
    }

    private func deleteNext(_ ids: [String], deleted: Int) {
        guard let first = ids.first else {
            if deleted == 1 {
                setNotice("host.save.notice.deletedOne")
            } else {
                setNotice("host.save.notice.deletedMany", arguments: [String(deleted)])
            }
            return
        }
        request(
            "core.save.delete",
            params: ["snapshotId": first],
            operation: "host.save.operation.delete",
            successNotice: nil,
            onComplete: { [weak self] success in
                guard let self, success else { return }
                self.deleteNext(Array(ids.dropFirst()), deleted: deleted + 1)
            }
        )
    }

    private func request(
        _ command: String,
        params: [String: Any] = [:],
        operation: String,
        successNotice: String?,
        onReply: ((BackendReply) -> Void)? = nil,
        onComplete: ((Bool) -> Void)? = nil
    ) {
        guard session.isRunning else {
            setError("host.save.error.backendUnavailable")
            onComplete?(false)
            return
        }
        let requestLifecycleID = session.lifecycleID
        let token = UUID()
        activeRequestTokens.insert(token)
        busy = true
        error = ""
        errorArguments = []
        notice = ""
        noticeArguments = []
        var receivedReply = false
        session.send(
            command,
            params: params,
            operation: operation,
            announceSuccess: false,
            timeout: 15,
            reply: { [weak self] reply in
                guard let self,
                      self.session.lifecycleID == requestLifecycleID,
                      self.activeRequestTokens.contains(token) else { return }
                receivedReply = true
                self.consume(reply)
                onReply?(reply)
                if reply.success, let successNotice {
                    self.setNotice(successNotice)
                }
            },
            completion: { [weak self] success in
                guard let self,
                      self.session.lifecycleID == requestLifecycleID,
                      self.activeRequestTokens.remove(token) != nil else { return }
                if !success, !receivedReply, self.error.isEmpty {
                    self.setError("host.save.error.incomplete")
                }
                onComplete?(success)
                self.busy = !self.activeRequestTokens.isEmpty
            }
        )
    }

    private func setError(_ key: String, arguments: [String] = []) {
        error = key
        errorArguments = arguments
    }

    private func setNotice(_ key: String, arguments: [String] = []) {
        notice = key
        noticeArguments = arguments
    }

    private func consume(_ reply: BackendReply) {
        guard reply.success else {
            guard let failure = reply.failure else {
                setError("host.save.error.failed")
                return
            }
            switch failure.code {
            case "save_busy":
                setError("host.save.error.busy")
            case "save_not_found":
                setError("host.save.error.notFound")
            case "save_unsupported":
                setError("host.save.error.unsupported")
            case "staged_unavailable":
                setError("host.save.error.stagedUnavailable")
            case "staged_indeterminate":
                setError("host.save.error.stagedIndeterminate")
            case "save_unsafe":
                setError("host.save.error.unsafe")
            case "snapshot_invalid":
                setError("host.save.error.invalidSnapshot")
            case "restore_failed":
                setError("host.save.error.restoreFailed")
            case "rollback_failed":
                let recoveryPath = failure.recoveryPath?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                if recoveryPath.isEmpty {
                    setError("host.save.error.restoreFailed")
                } else {
                    setError("host.save.error.rollbackFailed", arguments: [recoveryPath])
                }
            default:
                setError("host.save.error.failed")
            }
            return
        }
        guard let result = reply.result else { return }
        if let rows = result["snapshots"] as? [[String: Any]] {
            snapshots = rows.compactMap(TrainerSaveSnapshot.init(row:))
        }
        recoveryPaths = (result["recoveryPaths"] as? [String] ?? [])
            .compactMap { TrainerSavePathValidator.validatedLocalURL(for: $0)?.path }
        if let pending = result["pendingRestore"] as? [String: Any] {
            pendingRestore = TrainerPendingRestore(row: pending)
        } else {
            pendingRestore = nil
        }
    }
}
}
