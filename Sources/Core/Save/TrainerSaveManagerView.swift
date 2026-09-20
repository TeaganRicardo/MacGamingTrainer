import SwiftUI

struct TrainerSaveManagerView: View {
    @ObservedObject var model: TrainerSaveManagerModel
    @Environment(\.dismiss) private var dismiss
    @Environment(\.trainerTheme) private var theme

    @State private var selectedIDs: Set<String> = []
    @State private var editingID: String?
    @State private var renameText = ""
    @FocusState private var renameFocused: Bool
    @State private var restoreCandidate: TrainerSaveSnapshot?
    @State private var preserveCurrent = true
    @State private var deleteIDs: Set<String> = []
    @State private var confirmDelete = false

    var body: some View {
        TrainerSheetScaffold(title: "存档管理", icon: "externaldrive.fill", width: 760) {
            if model.busy { ProgressView().controlSize(.small) }
            Button { model.reveal() } label: { Label("打开存档目录", systemImage: "folder") }
                .disabled(model.busy)
            Button { model.refresh() } label: { Label("刷新", systemImage: "arrow.clockwise") }
                .disabled(model.busy)
        } content: {
            if let pending = model.pendingRestore {
                TrainerInlineNotice(color: theme.deferred) {
                    HStack(spacing: 10) {
                        Image(systemName: "clock.arrow.circlepath")
                        Text(pendingRestoreText(pending))
                            .font(.caption)
                            .foregroundStyle(theme.deferred)
                        Spacer()
                        Button("取消") { model.cancelStaged() }
                            .controlSize(.small)
                            .disabled(model.busy)
                    }
                }
            }

            if !model.error.isEmpty {
                TrainerMessageBanner(text: model.error, icon: "exclamationmark.triangle", color: theme.warning)
            } else if !model.notice.isEmpty {
                TrainerMessageBanner(text: model.notice, icon: "checkmark.circle", color: theme.success)
            }

            HStack(spacing: 10) {
                Button { model.backup() } label: {
                    Label("创建备份", systemImage: "plus")
                }
                .buttonStyle(.borderedProminent)
                .disabled(model.busy)

                Spacer()

                if !selectedIDs.isEmpty {
                    Text("已选 \(selectedIDs.count) 项")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Button(role: .destructive) {
                        deleteIDs = selectedIDs
                        confirmDelete = true
                    } label: {
                        Label("删除所选", systemImage: "trash")
                    }
                    .disabled(model.busy)
                }
            }

            ScrollView {
                LazyVStack(spacing: 8) {
                    if model.snapshots.isEmpty {
                        TrainerEmptyState(text: "暂无存档备份。")
                    }
                    ForEach(model.snapshots) { snapshot in
                        snapshotRow(snapshot)
                    }
                }
            }
            .frame(minHeight: 300, maxHeight: 520)
        } footer: {
            HStack {
                Spacer()
                Button("完成") { dismiss() }
                    .keyboardShortcut(.defaultAction)
                    .disabled(model.busy)
            }
        }
        .interactiveDismissDisabled(model.busy)
        .sheet(item: $restoreCandidate) { snapshot in
            TrainerSaveRestoreConfirmationView(
                snapshot: snapshot,
                preserveCurrent: $preserveCurrent,
                onCancel: { restoreCandidate = nil },
                onRestore: {
                    model.restore(id: snapshot.id, preserveCurrent: preserveCurrent)
                    restoreCandidate = nil
                }
            )
            .trainerTheme(theme)
        }
        .alert(deleteTitle, isPresented: $confirmDelete) {
            Button("取消", role: .cancel) { deleteIDs.removeAll() }
            Button("永久删除", role: .destructive) {
                let ids = deleteIDs
                selectedIDs.subtract(ids)
                deleteIDs.removeAll()
                model.delete(ids: ids)
            }
        } message: {
            Text(deleteIDs.count > 1 ? "将永久删除所选的 \(deleteIDs.count) 个备份。此操作不会修改当前游戏存档。" : "将永久删除该备份。此操作不会修改当前游戏存档。")
        }
        .onChange(of: renameFocused) { wasFocused, isFocused in
            if wasFocused && !isFocused { commitRename() }
        }
        .onChange(of: model.snapshots.map(\.id), initial: true) { _, ids in
            let current = Set(ids)
            selectedIDs.formIntersection(current)
            if let editingID, !current.contains(editingID) {
                cancelRename()
            }
        }
    }

    @ViewBuilder
    private func snapshotRow(_ snapshot: TrainerSaveSnapshot) -> some View {
        TrainerListCard {
            HStack(alignment: .top, spacing: 12) {
                Button {
                    toggleSelection(snapshot.id)
                } label: {
                    Image(systemName: selectedIDs.contains(snapshot.id) ? "checkmark.square.fill" : "square")
                        .foregroundStyle(selectedIDs.contains(snapshot.id) ? theme.accent : .secondary)
                }
                .buttonStyle(.plain)
                .disabled(model.busy)
                .help("选择以进行批量管理")

                VStack(alignment: .leading, spacing: 5) {
                    HStack(spacing: 8) {
                        if editingID == snapshot.id {
                            TextField("存档名称", text: $renameText)
                                .textFieldStyle(.plain)
                                .font(.subheadline.weight(.semibold))
                                .focused($renameFocused)
                                .onSubmit { commitRename() }
                                .onExitCommand { cancelRename() }
                        } else {
                            Text(snapshot.name)
                                .font(.subheadline.weight(.semibold))
                                .lineLimit(1)
                                .onTapGesture(count: 2) { beginRename(snapshot) }
                                .help("双击重命名")
                        }
                        if snapshot.hot {
                            TrainerPillBadge(text: "热备份", color: theme.info)
                        }
                    }

                    HStack(spacing: 5) {
                        if !snapshot.createdAt.isEmpty {
                            Text(snapshot.createdAt.replacingOccurrences(of: "T", with: " "))
                        }
                        Text("\(snapshot.fileCount) 个文件")
                    }
                    .font(.caption)
                    .foregroundStyle(.secondary)

                    if !snapshot.nameDetails.isEmpty {
                        Text(snapshot.nameDetails.joined(separator: " · "))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                    }

                    if !snapshot.valid {
                        Text(snapshot.error.isEmpty ? "备份校验失败，无法恢复" : snapshot.error)
                            .font(.caption)
                            .foregroundStyle(theme.warning)
                            .lineLimit(2)
                    }
                }

                Spacer(minLength: 12)

                Button("恢复") {
                    preserveCurrent = true
                    restoreCandidate = snapshot
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(model.busy || !snapshot.valid)

                Menu {
                    Button {
                        model.reveal(id: snapshot.id)
                    } label: {
                        Label("在 Finder 中显示", systemImage: "folder")
                    }
                    Divider()
                    Button(role: .destructive) {
                        deleteIDs = [snapshot.id]
                        confirmDelete = true
                    } label: {
                        Label("删除", systemImage: "trash")
                    }
                } label: {
                    Image(systemName: "ellipsis.circle")
                }
                .menuStyle(.borderlessButton)
                .fixedSize()
                .disabled(model.busy)
            }
        }
    }

    private var deleteTitle: String {
        deleteIDs.count > 1 ? "删除所选存档？" : "删除存档？"
    }

    private func pendingRestoreText(_ pending: TrainerPendingRestore) -> String {
        let name = model.snapshots.first(where: { $0.id == pending.snapshotID })?.name ?? pending.snapshotID
        return "“\(name)”等待游戏退出后恢复。"
    }

    private func toggleSelection(_ id: String) {
        if selectedIDs.contains(id) {
            selectedIDs.remove(id)
        } else {
            selectedIDs.insert(id)
        }
    }

    private func beginRename(_ snapshot: TrainerSaveSnapshot) {
        editingID = snapshot.id
        renameText = snapshot.name
        DispatchQueue.main.async { renameFocused = true }
    }

    private func commitRename() {
        guard let id = editingID else { return }
        let clean = renameText.trimmingCharacters(in: .whitespacesAndNewlines)
        editingID = nil
        renameFocused = false
        guard !clean.isEmpty,
              clean != model.snapshots.first(where: { $0.id == id })?.name else { return }
        model.rename(id: id, name: clean)
    }

    private func cancelRename() {
        editingID = nil
        renameText = ""
        renameFocused = false
    }
}

private struct TrainerSaveRestoreConfirmationView: View {
    let snapshot: TrainerSaveSnapshot
    @Binding var preserveCurrent: Bool
    let onCancel: () -> Void
    let onRestore: () -> Void

    var body: some View {
        TrainerSheetScaffold(title: "恢复存档", icon: "arrow.counterclockwise", width: 440) {
            EmptyView()
        } content: {
            Text("将恢复“\(snapshot.name)”。")
                .font(.headline)
            Text("Trainer 会自动决定立即恢复、热替换或等待游戏退出；无需手动判断文件是否被占用。")
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Toggle("恢复前保留当前存档", isOn: $preserveCurrent)
        } footer: {
            HStack {
                Spacer()
                Button("取消", action: onCancel)
                Button("恢复", action: onRestore)
                    .buttonStyle(.borderedProminent)
            }
        }
    }
}
