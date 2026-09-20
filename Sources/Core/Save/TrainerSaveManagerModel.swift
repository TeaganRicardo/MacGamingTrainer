import AppKit
import Combine
import Foundation

final class TrainerSaveManagerModel: ObservableObject {
    @Published private(set) var snapshots: [TrainerSaveSnapshot] = []
    @Published private(set) var pendingRestore: TrainerPendingRestore?
    @Published private(set) var busy = false
    @Published private(set) var error = ""
    @Published private(set) var notice = ""

    private let session: TrainerBackendSession

    init(session: TrainerBackendSession) {
        self.session = session
    }

    func refresh() {
        request("core.save.list", operation: "刷新存档", successNotice: nil)
    }

    func backup(name: String? = nil) {
        var params: [String: Any] = [:]
        if let name, !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            params["name"] = name
        }
        request("core.save.backup", params: params, operation: "创建存档备份", successNotice: "已创建存档备份")
    }

    func rename(id: String, name: String) {
        let clean = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !id.isEmpty, !clean.isEmpty else { return }
        request(
            "core.save.rename",
            params: ["snapshotId": id, "name": clean],
            operation: "重命名存档",
            successNotice: "已重命名存档"
        )
    }

    func delete(ids: Set<String>) {
        let ordered = ids.filter { !$0.isEmpty }.sorted()
        guard !ordered.isEmpty else { return }
        deleteNext(ordered, deleted: 0)
    }

    func reveal(id: String? = nil) {
        var params: [String: Any] = [:]
        if let id { params["snapshotId"] = id }
        request(
            "core.save.open_folder",
            params: params,
            operation: id == nil ? "打开存档目录" : "显示存档",
            successNotice: nil
        ) { reply in
            guard let path = reply.result?["folder"] as? String else { return }
            let url = URL(fileURLWithPath: path)
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
            operation: "恢复存档",
            successNotice: "恢复请求已提交"
        )
    }

    func cancelStaged() {
        request(
            "core.save.cancel_staged",
            operation: "取消等待恢复",
            successNotice: "已取消等待恢复"
        )
    }

    func applyStagedIfPossible() {
        request(
            "core.save.apply_staged",
            operation: "应用等待恢复",
            successNotice: "已应用等待恢复"
        )
    }

    private func deleteNext(_ ids: [String], deleted: Int) {
        guard let first = ids.first else {
            busy = false
            notice = deleted == 1 ? "已删除 1 个存档" : "已删除 \(deleted) 个存档"
            return
        }
        request(
            "core.save.delete",
            params: ["snapshotId": first],
            operation: "删除存档",
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
            error = "后端未运行。"
            return
        }
        busy = true
        error = ""
        notice = ""
        var receivedReply = false
        session.send(
            command,
            params: params,
            operation: operation,
            announceSuccess: false,
            timeout: 15,
            reply: { [weak self] reply in
                guard let self else { return }
                receivedReply = true
                self.consume(reply)
                onReply?(reply)
                if reply.success, let successNotice {
                    self.notice = successNotice
                }
            },
            completion: { [weak self] success in
                guard let self else { return }
                self.busy = false
                if !success, !receivedReply, self.error.isEmpty {
                    self.error = "存档操作未完成。"
                }
                onComplete?(success)
            }
        )
    }

    private func consume(_ reply: BackendReply) {
        guard reply.success else {
            error = reply.errorMessage ?? "存档操作失败。"
            return
        }
        guard let result = reply.result else { return }
        if let rows = result["snapshots"] as? [[String: Any]] {
            snapshots = rows.compactMap(TrainerSaveSnapshot.init(row:))
        }
        if let pending = result["pendingRestore"] as? [String: Any] {
            pendingRestore = TrainerPendingRestore(row: pending)
        } else {
            pendingRestore = nil
        }
    }
}
