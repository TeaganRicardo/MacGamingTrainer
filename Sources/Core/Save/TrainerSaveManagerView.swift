import SwiftUI

struct TrainerSaveManagerView: View {
    @ObservedObject var model: TrainerSaveManagerModel
    @Environment(\.dismiss) private var dismiss
    @Environment(\.trainerTheme) private var theme
    @EnvironmentObject private var localization: TrainerLocalizationStore

    @State private var selectedIDs: Set<String> = []
    @State private var editingID: String?
    @State private var renameText = ""
    @State private var pendingRenameNames: [String: String] = [:]
    @State private var restoreCandidate: TrainerSaveSnapshot?
    @State private var preserveCurrent = true
    @State private var deleteIDs: Set<String> = []
    @State private var confirmDelete = false

    var body: some View {
        TrainerSheetScaffold(title: localization.localized("host.saveManagement"), icon: "externaldrive.fill", width: 780) {
            if model.busy { ProgressView() }
            Button { model.reveal() } label: { Label(localization.localized("host.save.openFolder"), systemImage: "folder") }
                .disabled(model.busy)
            Button { model.refresh() } label: { Label(localization.localized("host.refresh"), systemImage: "arrow.clockwise") }
                .disabled(model.busy)
            TrainerPrimaryActionButton(
                title: localization.localized("host.save.createBackup"),
                systemImage: "plus",
                enabled: !model.busy,
                action: { model.backup() }
            )
        } content: {
            if let pending = model.pendingRestore {
                TrainerInlineNotice(color: pending.indeterminate ? theme.warning : theme.deferred) {
                    HStack(spacing: 10) {
                        Image(systemName: "clock.arrow.circlepath")
                        Text(pendingRestoreText(pending))
                            .font(.caption)
                            .foregroundStyle(pending.indeterminate ? theme.warning : theme.deferred)
                        Spacer()
                        Button(localization.localized(pending.indeterminate ? "host.clearStatus" : "host.cancel")) { model.cancelStaged() }
                            .disabled(model.busy)
                    }
                }
            }

            if !model.recoveryPaths.isEmpty {
                TrainerInlineNotice(color: theme.warning) {
                    HStack(alignment: .top, spacing: 10) {
                        Image(systemName: "exclamationmark.triangle")
                        VStack(alignment: .leading, spacing: 4) {
                            Text(localization.localized("host.save.recoveryCopiesWarning"))
                                .font(.caption)
                                .foregroundStyle(theme.warning)
                            Text(model.recoveryPaths.joined(separator: "\n"))
                                .font(.system(.caption2, design: .monospaced))
                                .foregroundStyle(.secondary)
                                .textSelection(.enabled)
                        }
                        Spacer()
                        Button(localization.localized("host.show")) { model.revealRecoveryCopies() }
                            .disabled(model.busy)
                    }
                }
            }

            if !model.error.isEmpty {
                TrainerMessageBanner(text: localization.presentation(model.error, arguments: model.errorArguments), icon: "exclamationmark.triangle", color: theme.warning)
            } else if !model.notice.isEmpty {
                TrainerMessageBanner(text: localization.presentation(model.notice, arguments: model.noticeArguments), icon: "checkmark.circle", color: theme.success)
            }

            TrainerSection(title: localization.localized("host.save.history"), icon: "clock.arrow.circlepath") {
                if !selectedIDs.isEmpty {
                    selectionActions
                }

                ScrollView {
                    if model.snapshots.isEmpty {
                        VStack(spacing: 1) {
                            TrainerRow {
                                TrainerEmptyState(text: localization.localized("host.save.empty"))
                            }
                        }
                        .trainerGroupedRows()
                    } else {
                        LazyVStack(spacing: 1) {
                            ForEach(model.snapshots) { snapshot in
                                snapshotRow(snapshot)
                            }
                        }
                        .trainerGroupedRows()
                    }
                }
                .frame(minHeight: 320, maxHeight: 540)
            }
        } footer: {
            HStack {
                Spacer()
                TrainerPrimaryActionButton(
                    title: localization.localized("host.done"),
                    enabled: !model.busy,
                    action: dismiss.callAsFunction
                )
                .keyboardShortcut(.defaultAction)
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
            Button(localization.localized("host.cancel"), role: .cancel) { deleteIDs.removeAll() }
            Button(localization.localized("host.deletePermanently"), role: .destructive) {
                let ids = deleteIDs
                selectedIDs.subtract(ids)
                deleteIDs.removeAll()
                model.delete(ids: ids)
            }
        } message: {
            Text(deleteIDs.count > 1 ? localization.localized("host.save.deleteSelectedMessage", arguments: [String(deleteIDs.count)]) : localization.localized("host.save.deleteOneMessage"))
        }
        .onChange(of: model.snapshots.map(\.id), initial: true) { _, ids in
            let current = Set(ids)
            selectedIDs.formIntersection(current)
            pendingRenameNames = pendingRenameNames.filter { current.contains($0.key) }
            if let editingID, !current.contains(editingID) {
                cancelRename()
            }
        }
    }

    private var selectionActions: some View {
        HStack(spacing: 10) {
            Text(localization.localized("host.selectedCount", arguments: [String(selectedIDs.count)]))
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            Button(role: .destructive) {
                deleteIDs = selectedIDs
                confirmDelete = true
            } label: {
                Label(localization.localized("host.deleteSelected"), systemImage: "trash")
            }
            .disabled(model.busy)
        }
        .trainerPanel(padding: 14)
    }

    @ViewBuilder
    private func snapshotRow(_ snapshot: TrainerSaveSnapshot) -> some View {
        TrainerRow(minimumHeight: 82, opacity: snapshot.valid ? 1 : 0.72) {
            HStack(alignment: .center, spacing: 14) {
                TrainerSelectionControl(
                    selected: selectedIDs.contains(snapshot.id),
                    enabled: !model.busy,
                    helpText: localization.localized("host.save.bulkSelectionHelp")
                ) {
                    toggleSelection(snapshot.id)
                }

                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 8) {
                        if editingID == snapshot.id {
                            TrainerInlineNameEditor(
                                text: $renameText,
                                placeholder: localization.localized("host.save.namePlaceholder"),
                                onCommit: commitRename,
                                onCancel: cancelRename
                            )
                        } else {
                            Text(displayName(for: snapshot))
                                .font(.headline.weight(.semibold))
                                .lineLimit(1)
                                .onTapGesture(count: 2) { beginRename(snapshot) }
                                .help(localization.localized("host.save.doubleClickRename"))
                        }
                        if snapshot.hot {
                            TrainerPillBadge(text: localization.localized("host.save.hotBackup"), color: theme.info)
                        }
                    }

                    HStack(spacing: 6) {
                        if !snapshot.createdAt.isEmpty {
                            Text(snapshot.createdAt.replacingOccurrences(of: "T", with: " "))
                            Text("·")
                        }
                        Text(localization.localized("host.save.fileCount", arguments: [String(snapshot.fileCount)]))
                    }
                    .font(.caption)
                    .foregroundStyle(.secondary)

                    let localizedDetails = snapshot.displayDetails(for: localization.language.rawValue)
                    if !localizedDetails.isEmpty {
                        Text(localizedDetails.joined(separator: " · "))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                    }

                    if !snapshot.valid {
                        Text(localization.localized("host.save.invalidBackup"))
                            .font(.caption)
                            .foregroundStyle(theme.warning)
                            .lineLimit(2)
                    }
                }

                Spacer(minLength: 12)

                Button(localization.localized("host.restore")) {
                    preserveCurrent = true
                    restoreCandidate = snapshot
                }
                .buttonStyle(.bordered)
                .disabled(model.busy || !snapshot.valid)

                TrainerOverflowMenu(enabled: !model.busy) {
                    Button {
                        beginRename(snapshot)
                    } label: {
                        Label(localization.localized("host.rename"), systemImage: "pencil")
                    }
                    Button {
                        model.reveal(id: snapshot.id)
                    } label: {
                        Label(localization.localized("host.showInFinder"), systemImage: "folder")
                    }
                    Divider()
                    Button(role: .destructive) {
                        deleteIDs = [snapshot.id]
                        confirmDelete = true
                    } label: {
                        Label(localization.localized("host.delete"), systemImage: "trash")
                    }
                }
            }
        }
    }

    private var deleteTitle: String {
        localization.localized(deleteIDs.count > 1 ? "host.save.deleteSelectedTitle" : "host.save.deleteTitle")
    }

    private func pendingRestoreText(_ pending: TrainerPendingRestore) -> String {
        if pending.indeterminate {
            return localization.localized("host.save.pendingIndeterminate")
        }
        let name = model.snapshots.first(where: { $0.id == pending.snapshotID })?
            .displayName(for: localization.language.rawValue) ?? pending.snapshotID
        return localization.localized("host.save.pendingWaiting", arguments: [name])
    }

    private func toggleSelection(_ id: String) {
        if selectedIDs.contains(id) {
            selectedIDs.remove(id)
        } else {
            selectedIDs.insert(id)
        }
    }

    private func displayName(for snapshot: TrainerSaveSnapshot) -> String {
        pendingRenameNames[snapshot.id] ?? snapshot.displayName(for: localization.language.rawValue)
    }

    private func beginRename(_ snapshot: TrainerSaveSnapshot) {
        editingID = snapshot.id
        renameText = displayName(for: snapshot)
    }

    private func commitRename() {
        guard let id = editingID else { return }
        let clean = renameText.trimmingCharacters(in: .whitespacesAndNewlines)
        let current = model.snapshots.first(where: { $0.id == id })
        editingID = nil
        renameText = ""
        guard !clean.isEmpty,
              clean != current.map({ displayName(for: $0) }) else { return }

        pendingRenameNames[id] = clean
        model.rename(id: id, name: clean) { _ in
            pendingRenameNames.removeValue(forKey: id)
        }
    }

    private func cancelRename() {
        editingID = nil
        renameText = ""
    }
}

private struct TrainerSaveRestoreConfirmationView: View {
    @EnvironmentObject private var localization: TrainerLocalizationStore
    let snapshot: TrainerSaveSnapshot
    @Binding var preserveCurrent: Bool
    let onCancel: () -> Void
    let onRestore: () -> Void

    var body: some View {
        TrainerSheetScaffold(title: localization.localized("host.save.restoreTitle"), icon: "arrow.counterclockwise", width: 460) {
            EmptyView()
        } content: {
            TrainerSection(title: localization.localized("host.save.restoreOptions"), icon: "arrow.counterclockwise") {
                VStack(spacing: 1) {
                    TrainerRow {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(snapshot.displayName(for: localization.language.rawValue))
                                .font(.headline.weight(.semibold))
                            Text(localization.localized("host.save.restoreExplanation"))
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    TrainerRow {
                        TrainerCheckboxControl(
                            title: localization.localized("host.save.preserveCurrent"),
                            isOn: preserveCurrent,
                            onChange: { preserveCurrent = $0 }
                        )
                    }
                }
                .trainerGroupedRows()
            }
        } footer: {
            HStack {
                Spacer()
                Button(localization.localized("host.cancel"), action: onCancel)
                TrainerPrimaryActionButton(title: localization.localized("host.restore"), action: onRestore)
            }
        }
    }
}
