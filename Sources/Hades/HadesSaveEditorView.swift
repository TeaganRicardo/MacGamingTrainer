import AppKit
import SwiftUI

struct HadesSaveEditorView: View {
    @StateObject private var model: HadesSaveEditorModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.trainerCloseToolWindow) private var closeWindow
    @State private var confirmingRead = false

    init(model: HadesSaveEditorModel) { _model = StateObject(wrappedValue: model) }
    private func text(_ key: String) -> String { HadesGameModule.resolveText(key: key, localization: localization) }
    private var hasReview: Bool { model.review.count > 0 }

    private enum ResultPhase: Equatable { case source, loading, empty, content }

    private var resultPhase: ResultPhase {
        if model.workspaceID == nil { return model.busy || model.queryLoading ? .loading : .source }
        if model.rows.isEmpty { return model.queryLoading ? .loading : .empty }
        return .content
    }

    var body: some View {
        VStack(spacing: 0) {
            headerBar
            Divider()
            documentBar
            documentContext
            failuresNotice
            recoveryNotice
            Divider()
            workbenchBar
            saveScopeContext
            Divider()
            TrainerSaveEditorWorkspace(
                identity: model.workspaceID.map(AnyHashable.init),
                hasReview: hasReview,
                busy: model.busy,
                showsPaging: model.total > HadesSaveEditorModel.pageSize
            ) {
                results
            } paging: {
                paging
            } review: {
                changes
            }
            VStack(spacing: 0) {
                if let receipt = model.receipt {
                    Divider()
                    applied(receipt).transition(.opacity)
                }
            }
            .animation(TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion),
                       value: model.receipt?.installedSHA256)
        }
        .trainerSaveEditorWindow()
        .animation(TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion),
                   value: model.failures.keys.sorted())
        .animation(TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion),
                   value: model.recoveryPath)
        .onAppear { model.open(language: localization.language) }
        .onChange(of: localization.language) { _, value in model.setLanguage(value) }
        .onChange(of: model.search) { _, _ in model.searchChanged() }
        .onChange(of: model.review.count) { _, count in
            if count > 0 || model.receipt == nil { announce(text("hades.saveEditor.changes") + " (\(count))") }
        }
        .onChange(of: model.receipt?.installedSHA256) { _, receipt in
            if receipt != nil { announce(text("hades.saveEditor.applied")) }
        }
        .onChange(of: model.selectedSourceID) { _, identifier in
            guard !identifier.isEmpty, identifier != loadedSourceID else { return }
            if model.busy {
                if model.workspaceID != nil { model.selectedSourceID = loadedSourceID }
                return
            }
            guard model.sources.contains(where: { $0.id == identifier }) else {
                model.selectedSourceID = loadedSourceID
                return
            }
            if model.review.count > 0 { confirmingRead = true }
            else { model.openSelection() }
        }
        .confirmationDialog(text("hades.saveEditor.readConfirm"), isPresented: $confirmingRead) {
            Button(text("hades.saveEditor.read"), role: .destructive, action: model.openSelection)
            Button(text("host.cancel"), role: .cancel) { model.selectedSourceID = loadedSourceID }
        }
        .sheet(item: Binding(
            get: { model.editingRow },
            set: { next in
                if next == nil, let current = model.editingRow {
                    model.discardDraft(current, workspace: model.workspaceID)
                }
            }
        )) { row in
            HadesSaveTypedEditor(model: model, row: row, workspace: model.workspaceID, forceTyped: model.editingTyped)
        }
    }

    private func announce(_ message: String) {
        NSAccessibility.post(element: NSApplication.shared, notification: .announcementRequested,
            userInfo: [.announcement: message, .priority: NSAccessibilityPriorityLevel.medium.rawValue])
    }

    private var loadedSourceID: String { model.source?.id ?? "" }

    private var sourceOptions: [TrainerSaveEditorDocumentOption] {
        model.sources.map { .init(id: $0.id, title: $0.label) }
    }

    private var targetOptions: [TrainerSaveEditorDocumentOption] {
        model.targets.map { .init(id: $0.id, title: $0.label) }
    }

    private func requestCurrentSourceRead() {
        guard !model.busy, !loadedSourceID.isEmpty else { return }
        model.selectedSourceID = loadedSourceID
        if model.review.count > 0 { confirmingRead = true }
        else { model.openSelection() }
    }

    private var headerBar: some View {
        TrainerSaveEditorWindowHeader(
            title: text("hades.saveEditor.title"),
            subtitle: model.source.map { $0.snapshotId ?? $0.relativePath },
            busy: model.busy || model.queryLoading,
            refreshTitle: text("hades.saveEditor.read"),
            refreshEnabled: !model.busy && loadedSourceID != ""
                && model.sources.contains(where: { $0.id == loadedSourceID }),
            doneTitle: text("host.done"),
            doneEnabled: !model.busy,
            onRefresh: requestCurrentSourceRead,
            onDone: { closeWindow?() }
        )
    }

    private var documentBar: some View {
        TrainerSaveEditorDocumentBar(
            sourceLabel: text("hades.saveEditor.source"),
            sourcePlaceholder: text("hades.saveEditor.selectSource"),
            sourceSelection: $model.selectedSourceID,
            sources: sourceOptions,
            sourceEnabled: !model.busy,
            sourceRefreshTitle: text("host.refresh"),
            onRefreshSources: { model.refreshInventory() },
            targetLabel: text("hades.saveEditor.target"),
            targetPlaceholder: text("hades.saveEditor.selectTarget"),
            targetSelection: Binding(
                get: { model.selectedTargetID },
                set: { model.selectTarget($0, baseline: model.baselineGeneration) }
            ),
            targets: targetOptions,
            targetEnabled: !model.busy && model.canEditRows && model.source != nil
        )
    }

    private var workbenchBar: some View {
        TrainerSaveEditorWorkbenchBar(
            search: $model.search,
            searchPlaceholder: text("hades.saveEditor.search"),
            clearLabel: text("host.search.clear"),
            searchEnabled: model.workspaceID != nil && !model.busy,
            loading: model.queryLoading,
            onSubmit: { model.query() }
        ) {
            saveScopePicker
        } trailing: {
            Button {
                model.query(offset: model.offset)
            } label: {
                Image(systemName: TrainerSemanticIcon.Concept.refresh)
            }
            .buttonStyle(.borderless)
            .disabled(model.workspaceID == nil || model.busy)
            .help(text("hades.saveEditor.refreshRows"))
            .accessibilityLabel(text("hades.saveEditor.refreshRows"))
        }
    }

    @ViewBuilder
    private var failuresNotice: some View {
        if !model.failures.isEmpty {
            TrainerInlineNotice(color: theme.warning, foreground: theme.warning) {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(model.failures.keys.sorted(), id: \.self) { key in
                        if let failure = model.failures[key] {
                            Text(localization.string(failure))
                                .font(.caption)
                                .foregroundStyle(theme.warning)
                                .fixedSize(horizontal: false, vertical: true)
                                .contentTransition(.opacity)
                                .animation(TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion), value: failure)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(.horizontal, theme.rowHorizontalPadding)
            .padding(.top, theme.controlPadding)
            .transition(.opacity)
        }
    }

    @ViewBuilder
    private var recoveryNotice: some View {
        if let recovery = model.recoveryPath {
            TrainerInlineNotice(color: theme.warning, foreground: theme.warning) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(text("hades.saveEditor.recovery"))
                        .font(.caption)
                        .foregroundStyle(theme.warning)
                        .fixedSize(horizontal: false, vertical: true)
                    Text(recovery)
                        .font(.caption.monospaced())
                        .textSelection(.enabled)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(.horizontal, theme.rowHorizontalPadding)
            .padding(.top, theme.controlPadding)
            .transition(.opacity)
        }
    }

    @ViewBuilder
    private var documentContext: some View {
        if let source = model.source {
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .firstTextBaseline) {
                    Text(text(source.kind == "managedBackup"
                        ? "hades.saveEditor.backupSource" : "hades.saveEditor.currentSource"))
                        .font(.caption.weight(.semibold))
                    Text((source.snapshotId.map { $0 + " · " } ?? "") + source.id)
                        .font(.caption)
                        .textSelection(.enabled)
                    Spacer()
                }
                Text("SHA-256 · " + model.sourceSHA256)
                    .font(.caption2.monospaced())
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
            }
            .padding(.horizontal, theme.rowHorizontalPadding)
            .padding(.bottom, theme.inlineRowVerticalPadding)
        } else if model.sources.isEmpty && !model.busy {
            TrainerEmptyState(text: text("hades.saveEditor.noSources"))
        }
    }

    private var saveScopePicker: some View {
        Picker(
            text("hades.saveEditor.domain"),
            selection: Binding(get: { model.domain }, set: model.selectDomain)
        ) {
            ForEach(model.domains) { Text(text($0.titleKey)).tag($0) }
        }
        .labelsHidden()
        .trainerPicker(.rowValue,
            state: model.workspaceID == nil || model.busy ? .unavailable : .interactive)
    }

    @ViewBuilder
    private var saveScopeContext: some View {
        if model.parentID != nil {
            HStack(spacing: theme.compactControlSpacing) {
                Button(text(model.domain.titleKey)) { model.browse(nil) }
                    .buttonStyle(.borderless)
                ForEach(model.breadcrumbs) { crumb in
                    Image(systemName: "chevron.right")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Button(crumb.name) { model.browse(crumb.id) }
                        .buttonStyle(.borderless)
                }
            }
            .font(.caption)
            .padding(.horizontal, theme.rowHorizontalPadding)
            .padding(.bottom, theme.compactControlSpacing)
        }
        if model.domain == .advanced {
            TrainerInlineNotice(color: theme.warning) {
                Text(text("hades.saveEditor.advancedWarning"))
                    .font(.caption)
                    .foregroundStyle(theme.warning)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(.horizontal, theme.rowHorizontalPadding)
            .padding(.bottom, theme.compactControlSpacing)
        }
    }

    private var owners: [String] {
        var found: [String] = []
        for row in model.rows where !found.contains(row.ownerId) { found.append(row.ownerId) }
        return found
    }
    private var results: some View {
        Group {
            if resultPhase == .source {
                TrainerEmptyState(text: text("hades.saveEditor.selectSource"))
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .transition(.opacity)
            } else if resultPhase == .loading {
                TrainerLoadingIndicator()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .transition(.opacity)
            } else if resultPhase == .empty {
                TrainerEmptyState(text: text("hades.saveEditor.empty"))
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .transition(.opacity)
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: theme.pageSpacing) {
                        TrainerSection(title: text(model.domain.titleKey), icon: model.domain.sectionIcon) {
                            ForEach(owners, id: \.self) { ownerID in
                                let owned = model.rows.filter { $0.ownerId == ownerID }
                                VStack(alignment: .leading, spacing: 0) {
                                    if let owner = owned.first?.owner, !owner.isEmpty {
                                        Text(owner)
                                            .font(.headline)
                                            .accessibilityAddTraits(.isHeader)
                                            .frame(maxWidth: .infinity, alignment: .leading)
                                            .padding(.horizontal, theme.rowHorizontalPadding)
                                            .padding(.vertical, theme.sectionSpacing)
                                            .trainerSurface(.subtle)
                                    }
                                    ForEach(Array(owned.enumerated()), id: \.element.id) { index, row in
                                        if index == 0 || owned[index - 1].groupId != row.groupId {
                                            if !row.group.isEmpty {
                                                Text(row.group)
                                                    .font(.subheadline.weight(.semibold))
                                                    .foregroundStyle(.secondary)
                                                    .accessibilityAddTraits(.isHeader)
                                                    .padding(.horizontal, theme.rowHorizontalPadding)
                                                    .padding(.top, theme.sectionSpacing)
                                            }
                                        }
                                        if index > 0 {
                                            Divider().padding(.horizontal, theme.rowHorizontalPadding)
                                        }
                                        HadesSaveEditorField(model: model, row: row, workspace: model.workspaceID)
                                    }
                                }
                                .trainerSurface(.panel, cornerRadius: theme.panelCornerRadius)
                                .trainerGroupedRows()
                            }
                        }
                    }
                    .padding(.horizontal, theme.rowHorizontalPadding)
                    .padding(.vertical, theme.sectionSpacing)
                }
            }
        }
        .animation(TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion), value: resultPhase)
    }

    private var paging: some View {
        TrainerSaveEditorPagingBar(
            summary: "\(model.total == 0 ? 0 : model.offset + 1)–\(min(model.total, model.offset + model.pageLimit)) / \(model.total)",
            previousTitle: text("hades.saveEditor.previous"),
            nextTitle: text("hades.saveEditor.next"),
            canPrevious: model.canPreviousPage,
            canNext: model.canNextPage,
            onPrevious: model.previousPage,
            onNext: model.nextPage
        )
    }
    private var changes: some View {
        let baseline = model.review.baselineGeneration
        return VStack(alignment: .leading, spacing: theme.controlPadding) {
            HStack {
                Text(text("hades.saveEditor.changes") + " (\(model.review.count))").font(.headline)
                Spacer()
                TrainerSecondaryActionButton(
                    title: text("hades.saveEditor.discard"),
                    enabled: !model.busy && model.canEditRows,
                    widthRole: .sheet
                ) {
                    model.cancel(baseline: baseline)
                }
                TrainerPrimaryActionButton(
                    title: text("hades.apply"),
                    enabled: model.canApply,
                    widthRole: .sheet
                ) {
                    model.apply(baseline: baseline)
                }
            }
            ScrollView {
                VStack(alignment: .leading, spacing: theme.compactControlSpacing) {
                    ForEach(model.review.actions) { action in
                        TrainerListCard {
                            VStack(alignment: .leading, spacing: theme.compactControlSpacing / 2) {
                                HStack(alignment: .firstTextBaseline, spacing: theme.compactControlSpacing) {
                                    Text(action.name).font(.subheadline.weight(.semibold))
                                    Spacer()
                                    TrainerSecondaryActionButton(
                                        title: text("hades.saveEditor.revise"),
                                        enabled: !model.busy && model.canEditRows,
                                        widthRole: .sheet
                                    ) {
                                        model.detail(action.id, baseline: baseline)
                                    }
                                    Button {
                                        model.unstage(action.id, baseline: baseline)
                                    } label: {
                                        Image(systemName: TrainerSemanticIcon.Action.remove)
                                    }
                                    .buttonStyle(.borderless)
                                    .help(text("hades.remove"))
                                    .accessibilityLabel(text("hades.remove"))
                                    .accessibilityIdentifier("saveEditor.remove." + action.id)
                                    .disabled(model.busy || !model.canEditRows)
                                }
                                Text(action.before + " → " + action.after)
                                    .font(.caption.monospacedDigit())
                                    .textSelection(.enabled)
                                    .contentTransition(.opacity)
                                    .animation(TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion), value: action.after)
                                ForEach(action.effects) { effect in
                                    Text(effect.name + ": " + effect.before + " → " + effect.after)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                        .textSelection(.enabled)
                                }
                            }
                        }
                    }
                }
            }
        }
        .padding(.horizontal, theme.rowHorizontalPadding)
        .padding(.vertical, theme.inlineRowVerticalPadding)
        .trainerSurface(.panel)
    }
    private func applied(_ receipt: HadesSaveEditorReceipt) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: theme.compactControlSpacing) {
                Image(systemName: TrainerSemanticIcon.Feedback.toastSuccess)
                    .foregroundStyle(theme.success)
                Text(text("hades.saveEditor.applied"))
                    .font(.callout.weight(.semibold))
                Spacer()
            }
            Text(receipt.target.id).font(.caption).textSelection(.enabled)
            Text("SHA-256 · " + receipt.installedSHA256).font(.caption2.monospaced()).textSelection(.enabled)
            if let backup = receipt.previousSnapshotId {
                Text(text("hades.saveEditor.recoverableBackup") + ": " + backup).font(.caption).textSelection(.enabled)
            }
            Text(text(receipt.hot == true ? "hades.saveEditor.hot" : "hades.saveEditor.loadInGame"))
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            if receipt.maintenanceWarning != nil {
                Text(localization.localized("host.save.warning.maintenance")).font(.caption).foregroundStyle(theme.warning)
            }
            if receipt.namingWarning != nil {
                Text(localization.localized("host.save.warning.providerName")).font(.caption).foregroundStyle(theme.warning)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, theme.rowHorizontalPadding)
        .padding(.vertical, theme.inlineRowVerticalPadding)
        .trainerSurface(.panel)
    }
}

private struct HadesSaveEditorField: View {
    @ObservedObject var model: HadesSaveEditorModel
    let row: HadesSaveEditorRow
    let workspace: String?
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme
    @State private var draft: String?
    @State private var focused = false

    private func text(_ key: String) -> String { HadesGameModule.resolveText(key: key, localization: localization) }
    private var pending: HadesSaveEditorReview.Action? { model.review.actions.first { $0.id == row.id } }
    private var value: HadesSaveValue? {
        pending?.operation == "set" ? (pending?.typedValue ?? row.typedValue) : row.typedValue
    }
    private var displayValue: String { pending?.after ?? row.displayValue }
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            TrainerLabeledControlRow(
                title: row.name,
                icon: row.hasChildren ? TrainerSemanticIcon.Tool.saveFolder : TrainerSemanticIcon.Action.rename,
                tint: theme.accent,
                emphasized: pending != nil
            ) {
                controls
                if model.domain == .advanced && hasNativeControl {
                    TrainerSecondaryActionButton(
                        title: text("hades.saveEditor.editTyped"),
                        enabled: model.canEdit(row),
                        widthRole: .sheet
                    ) {
                        model.detail(row.id, typed: true, baseline: row.baselineGeneration)
                    }
                    .accessibilityLabel(text("hades.saveEditor.editTyped") + " " + row.name)
                }
                if row.hasChildren {
                    Button {
                        model.browse(row.id, baseline: row.baselineGeneration)
                    } label: {
                        Image(systemName: "chevron.right")
                    }
                    .buttonStyle(.borderless)
                    .help(text("hades.saveEditor.browse"))
                    .accessibilityLabel(text("hades.saveEditor.browse") + " " + row.name)
                }
                if row.operations.contains("unset") {
                    TrainerOverflowMenu(enabled: model.canEdit(row)) {
                        Button(text("hades.saveEditor.unset"), role: .destructive) {
                            model.stage(row.id, operation: "unset", workspace: workspace, baseline: row.baselineGeneration)
                        }
                    }
                }
            }.disabled(!model.canEdit(row))
            if let lines = row.content {
                ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
                    VStack(alignment: .leading, spacing: 3) {
                        if !line.speaker.isEmpty { Text(line.speaker).font(.caption.weight(.semibold)) }
                        Text(line.text).font(.callout).fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, theme.rowHorizontalPadding)
                }
            }
            if case .some(.string(let content)) = value, content.count > 80 || content.contains("\n") {
                Text(content)
                    .font(.caption)
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, theme.rowHorizontalPadding)
            }
            if let warning = row.warning, !warning.isEmpty {
                Text(warning)
                    .font(.caption)
                    .foregroundStyle(theme.warning)
                    .padding(.horizontal, theme.rowHorizontalPadding)
                    .padding(.bottom, theme.compactControlSpacing)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .onChange(of: model.editRevision) { _, _ in if !focused && !model.hasFailedDraft(row) { draft = nil } }
    }
    private var hasNativeControl: Bool {
        if row.choices?.isEmpty == false { return true }
        switch value {
        case .some(.boolean), .some(.number), .some(.string): return true
        default: return false
        }
    }
    @ViewBuilder private var controls: some View {
        if let choices = row.choices, !choices.isEmpty {
            Picker(row.name, selection: Binding(get: { choices.firstIndex(where: { $0.value == value }) ?? -1 }, set: { index in
                if choices.indices.contains(index) { model.stage(row.id, operation: "set", value: choices[index].value.object, workspace: workspace, baseline: row.baselineGeneration) }
            })) {
                Text(displayValue).tag(-1)
                ForEach(choices.indices, id: \.self) { Text(choices[$0].name).tag($0) }
            }.labelsHidden().trainerPicker(.rowValue, state: model.canEdit(row) ? .interactive : .unavailable)
        } else if case .some(.boolean(let enabled)) = value {
            TrainerToggleControl(
                title: row.name,
                isOn: enabled,
                enabled: model.canEdit(row),
                helpText: row.name
            ) { newValue in
                model.stage(row.id, operation: "set", value: HadesSaveValue.boolean(newValue).object, workspace: workspace, baseline: row.baselineGeneration)
            }
        } else if let scalar = value?.scalarText {
            TrainerTextField(title: row.name, text: Binding(get: { draft ?? scalar }, set: { draft = $0 }),
                onEditingChanged: {
                    focused = $0
                    model.editingChanged(row.id, baseline: row.baselineGeneration, active: $0)
                }, onCommit: { completed in
                    guard completed.changed else {
                        // A review update can remove this row's staged value
                        // while its native draft remains focused. On unchanged
                        // completion, resume the latest acknowledged value;
                        // failed drafts still belong to the user's correction.
                        return model.hasFailedDraft(row) ? completed.text : (value?.scalarText ?? completed.text)
                    }
                    return model.commit(row, text: completed.text, workspace: workspace)
                })
                .frame(width: row.valueType == "number" ? 155 : 280)
        } else {
            Text(displayValue).font(.caption).lineLimit(3).textSelection(.enabled).frame(maxWidth: 220, alignment: .trailing)
            TrainerSecondaryActionButton(
                title: text("hades.saveEditor.editTyped"),
                enabled: model.canEdit(row),
                widthRole: .sheet
            ) {
                model.detail(row.id, baseline: row.baselineGeneration)
            }
        }
    }
}

private struct HadesSaveJSONEditor: NSViewRepresentable {
    let title: String
    @Binding var text: String
    @Binding var focused: Bool
    var onCancel: (() -> Void)? = nil
    @Environment(\.isEnabled) private var enabled

    final class ScrollView: NSScrollView {
        override func tile() {
            super.tile()
            guard let view = documentView as? NSTextView else { return }
            let minimum = NSSize(width: 0, height: contentSize.height)
            if view.minSize != minimum { view.minSize = minimum }
            let size = NSSize(width: contentSize.width, height: max(view.frame.height, contentSize.height))
            if view.frame.size != size { view.setFrameSize(size) }
        }
    }
    final class TextView: NSTextView {
        var focusChanged: ((Bool) -> Void)?
        var onCancel: (() -> Void)?
        override func becomeFirstResponder() -> Bool {
            guard isEditable && isSelectable else { return false }
            let accepted = super.becomeFirstResponder()
            if accepted { focusChanged?(true) }
            return accepted
        }
        override func resignFirstResponder() -> Bool {
            let accepted = super.resignFirstResponder()
            if accepted { focusChanged?(false) }
            return accepted
        }
        override func cancelOperation(_ sender: Any?) {
            if !hasMarkedText(), let onCancel {
                onCancel()
                return
            }
            super.cancelOperation(sender)
        }
    }
    final class Coordinator: NSObject, NSTextViewDelegate {
        var parent: HadesSaveJSONEditor
        init(_ parent: HadesSaveJSONEditor) { self.parent = parent }
        func focusChanged(_ focused: Bool) {
            if parent.focused != focused { parent.focused = focused }
        }
        func textDidChange(_ notification: Notification) {
            guard let view = notification.object as? NSTextView else { return }
            parent.text = view.string
        }
        func textView(_ textView: NSTextView, doCommandBy commandSelector: Selector) -> Bool {
            if commandSelector == #selector(NSResponder.cancelOperation(_:)), !textView.hasMarkedText(),
               let cancel = parent.onCancel {
                cancel()
                return true
            }
            return false
        }
    }
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeNSView(context: Context) -> NSScrollView {
        let scroll = ScrollView()
        scroll.hasVerticalScroller = true
        scroll.autohidesScrollers = true
        scroll.borderType = .noBorder
        let view = TextView(frame: scroll.contentView.bounds)
        view.delegate = context.coordinator
        view.focusChanged = { [weak coordinator = context.coordinator] in coordinator?.focusChanged($0) }
        view.onCancel = onCancel
        view.isRichText = false
        view.importsGraphics = false
        view.isAutomaticQuoteSubstitutionEnabled = false
        view.isAutomaticDashSubstitutionEnabled = false
        view.isAutomaticTextReplacementEnabled = false
        view.isAutomaticSpellingCorrectionEnabled = false
        view.allowsUndo = true
        view.font = .monospacedSystemFont(ofSize: NSFont.systemFontSize, weight: .regular)
        view.isVerticallyResizable = true
        view.isHorizontallyResizable = false
        view.autoresizingMask = [.width]
        view.maxSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        view.textContainer?.containerSize = NSSize(width: scroll.contentSize.width, height: CGFloat.greatestFiniteMagnitude)
        view.textContainer?.widthTracksTextView = true
        view.textContainerInset = NSSize(width: 6, height: 6)
        view.string = text
        view.isEditable = enabled
        view.isSelectable = enabled
        view.setAccessibilityLabel(title)
        scroll.documentView = view
        return scroll
    }
    func updateNSView(_ scroll: NSScrollView, context: Context) {
        context.coordinator.parent = self
        let view = scroll.documentView as! TextView
        view.onCancel = onCancel
        if view.string != text { view.string = text }
        view.isEditable = enabled
        view.isSelectable = enabled
        view.setAccessibilityLabel(title)
        if !enabled || !focused, view.window?.firstResponder === view { view.window?.makeFirstResponder(nil) }
    }
    static func dismantleNSView(_ scroll: NSScrollView, coordinator: Coordinator) {
        let view = scroll.documentView as! TextView
        view.focusChanged = nil
        view.onCancel = nil
        view.delegate = nil
    }
}

private struct HadesSaveTypedEditor: View {
    @ObservedObject var model: HadesSaveEditorModel
    let row: HadesSaveEditorRow
    let workspace: String?
    let forceTyped: Bool
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme
    @State private var json = ""
    @State private var appendKey = "{\"luaType\":\"string\",\"value\":\"\"}"
    @State private var append = false
    @State private var initial = ""
    @State private var initialKey = "{\"luaType\":\"string\",\"value\":\"\"}"
    @State private var initialAppend = false
    @State private var valid = true
    @State private var staging = false
    @State private var closeAfterStage = false
    @State private var discarding = false
    @State private var editing = false
    @State private var editingKey = false
    private func text(_ key: String) -> String { HadesGameModule.resolveText(key: key, localization: localization) }
    private var action: HadesSaveEditorReview.Action? { model.review.actions.first { $0.id == row.id } }
    private var native: Bool {
        if forceTyped { return false }
        if row.choices?.isEmpty == false { return true }
        switch row.typedValue {
        case .some(.boolean), .some(.number), .some(.string): return true
        default: return false
        }
    }
    var body: some View {
        TrainerSheetScaffold(title: row.name, icon: TrainerSemanticIcon.Action.edit, width: 700) {
            if !row.owner.isEmpty {
                Text(row.owner + " · " + row.group)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        } content: {
            VStack(alignment: .leading, spacing: theme.sectionSpacing) {
                if native {
                    HadesSaveEditorField(model: model, row: row, workspace: workspace)
                } else {
                    if let warning = row.warning {
                        Text(warning).font(.caption).foregroundStyle(theme.warning)
                    }
                    TrainerInlineNotice(color: theme.warning) {
                        Text(text("hades.saveEditor.advancedWarning"))
                            .font(.caption)
                            .foregroundStyle(theme.warning)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    Text(text("hades.saveEditor.typedHelp"))
                        .font(.caption)
                        .fixedSize(horizontal: false, vertical: true)
                    if row.operations.contains("append") {
                        TrainerCheckboxControl(
                            title: text("hades.saveEditor.append"),
                            isOn: append,
                            enabled: !staging
                        ) { appending in
                            append = appending; editingKey = false
                            json = appending ? HadesSaveValue.string("").json
                                : ((action?.operation == "set" ? action?.typedValue : nil) ?? row.typedValue ?? .null).json
                            initial = json
                        }
                    }
                    if append {
                        Text(text("hades.saveEditor.key")).font(.caption)
                        HadesSaveJSONEditor(title: text("hades.saveEditor.key"), text: $appendKey, focused: $editingKey, onCancel: finishSheet)
                            .frame(height: 70)
                            .overlay(RoundedRectangle(cornerRadius: theme.compactCornerRadius).stroke(theme.accent.opacity(0.35)))
                            .disabled(staging)
                    }
                    HadesSaveJSONEditor(title: row.name, text: $json, focused: $editing, onCancel: finishSheet)
                        .frame(minHeight: 280)
                        .overlay(RoundedRectangle(cornerRadius: theme.compactCornerRadius).stroke(theme.accent.opacity(0.35)))
                        .disabled(staging)
                        .onChange(of: editing) { old, current in
                            if old && !current && !discarding { commit() }
                            model.editingChanged(row.id, baseline: row.baselineGeneration, active: current)
                        }
                }
                if !valid {
                    TrainerInlineNotice(color: theme.warning) {
                        Text(text("hades.saveEditor.invalidValue"))
                            .font(.caption)
                            .foregroundStyle(theme.warning)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
                if let failure = model.failures[row.id] {
                    TrainerInlineNotice(color: theme.warning) {
                        Text(localization.string(failure))
                            .font(.caption)
                            .foregroundStyle(theme.warning)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
            }
            .disabled(!model.canEdit(row))
        } footer: {
            HStack(spacing: theme.compactControlSpacing) {
                TrainerSecondaryActionButton(
                    title: text("host.cancel"),
                    enabled: !model.busy && !staging,
                    widthRole: .sheet,
                    action: cancelSheet
                )
                if action != nil {
                    TrainerSecondaryActionButton(
                        title: text("hades.remove"),
                        enabled: !model.busy && !staging && model.canEdit(row),
                        widthRole: .sheet
                    ) {
                        guard !model.busy else { return }
                        discarding = true; editing = false; editingKey = false; staging = true
                        model.unstage(row.id, baseline: row.baselineGeneration) { accepted in
                            staging = false
                            if accepted { model.discardDraft(row, workspace: workspace) }
                            else { discarding = false }
                        }
                    }
                }
                Spacer()
                TrainerPrimaryActionButton(
                    title: text("host.done"),
                    enabled: !model.busy && !staging && model.canEdit(row),
                    widthRole: .sheet
                ) {
                    finishSheet()
                }
                .keyboardShortcut(.defaultAction)
            }
        }
        .trainerDismissTextEditingOnClickAway()
        .interactiveDismissDisabled(model.busy || staging)
        .trainerSheetDoneGestures(
            enabled: !model.busy && !staging && model.canEdit(row),
            perform: finishSheet
        )
        .onChange(of: editingKey) { _, active in
            model.editingChanged(row.id + ":key", baseline: row.baselineGeneration, active: active)
        }
        .onDisappear {
            editing = false
            editingKey = false
            model.editingChanged(row.id, baseline: row.baselineGeneration, active: false)
            model.editingChanged(row.id + ":key", baseline: row.baselineGeneration, active: false)
        }
        .onAppear {
            append = action?.operation == "append"
            appendKey = action?.typedKey?.json ?? appendKey
            json = (action?.typedValue ?? row.typedValue ?? .null).json
            initial = json; initialKey = appendKey; initialAppend = append
        }
    }
    private func finishSheet() {
        guard !model.busy && !staging && model.canEdit(row) else { return }
        if native {
            if !model.hasFailedDraft(row) { model.dismissDetail() }
        } else {
            commit(closeWhenAccepted: true)
        }
        editing = false
        editingKey = false
    }

    private func cancelSheet() {
        guard !model.busy && !staging else { return }
        discarding = true
        editing = false
        editingKey = false
        model.discardDraft(row, workspace: workspace)
    }
    private func commit(closeWhenAccepted: Bool = false) {
        if closeWhenAccepted { closeAfterStage = true }
        guard !staging else { return }
        guard json != initial || appendKey != initialKey || append != initialAppend else {
            if closeAfterStage { model.discardDraft(row, workspace: workspace) }; return
        }
        let submittedJSON = json, submittedKey = appendKey, submittedAppend = append
        staging = true
        let enqueued = model.commitJSON(row, text: submittedJSON, appendKey: submittedAppend ? submittedKey : nil, workspace: workspace) { accepted in
            staging = false; valid = accepted
            guard accepted else { closeAfterStage = false; return }
            initial = submittedJSON; initialKey = submittedKey; initialAppend = submittedAppend
            if closeAfterStage && json == submittedJSON && appendKey == submittedKey && append == submittedAppend {
                discarding = true; editing = false; editingKey = false
                model.editingChanged(row.id, baseline: row.baselineGeneration, active: false)
                model.editingChanged(row.id + ":key", baseline: row.baselineGeneration, active: false)
                model.dismissDetail()
            }
            closeAfterStage = false
        }
        if !enqueued { staging = false; valid = false; closeAfterStage = false }
    }
}
