import AppKit
import SwiftUI

package struct TrainerSaveEditorView: View {
    @StateObject private var model: TrainerSaveEditorModel
    private let titleKey: String

    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.trainerCloseToolWindow) private var closeWindow
    @Environment(\.dismiss) private var dismiss

    @State private var confirmingRead = false

    package init(model: TrainerSaveEditorModel, titleKey: String = "host.saveEditor.title") {
        _model = StateObject(wrappedValue: model)
        self.titleKey = titleKey
    }

    private func text(_ key: String) -> String {
        localization.localized(key)
    }

    private var hasReview: Bool { model.review.count > 0 }
    private var loadedSourceID: String { model.source?.id ?? "" }

    private var resultPhase: TrainerSaveEditorResultPhase {
        if model.workspaceID == nil {
            return model.busy || model.queryLoading ? .loading : .source
        }
        if model.rows.isEmpty {
            return model.queryLoading ? .loading : .empty
        }
        return .content
    }

    package var body: some View {
        VStack(spacing: 0) {
            headerBar
            Divider()
            documentBar
            documentContext
            TrainerSaveEditorFailureBanner(
                failures: model.failures.keys.sorted().compactMap { model.failures[$0] }
            )
            TrainerSaveEditorRecoveryBanner(
                message: text("host.saveEditor.recovery"),
                recoveryPath: model.recoveryPath
            )
            Divider()
            workbenchBar
            Divider()
            TrainerSaveEditorWorkspace(
                identity: model.workspaceID.map(AnyHashable.init),
                hasReview: hasReview,
                busy: model.hasWorkspaceLock,
                showsPaging: model.offset > 0 || model.nextOffset < model.total
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
            .animation(
                TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion),
                value: model.receipt?.installedSHA256
            )
        }
        .trainerSaveEditorWindow()
        .animation(
            TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion),
            value: model.failures.keys.sorted()
        )
        .animation(
            TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion),
            value: model.recoveryPath
        )
        .onAppear { model.open(language: localization.language) }
        .onChange(of: localization.language) { _, value in model.setLanguage(value) }
        .onChange(of: model.search) { _, _ in model.searchChanged() }
        .onChange(of: model.review.count) { _, count in
            if count > 0 || model.receipt == nil {
                TrainerSaveEditorAccessibility.announce(text("host.saveEditor.changes") + " (\(count))")
            }
        }
        .onChange(of: model.receipt?.installedSHA256) { _, sha in
            if sha != nil {
                TrainerSaveEditorAccessibility.announce(text("host.saveEditor.applied"))
            }
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
            if model.review.count > 0 { confirmingRead = true } else { model.openSelection() }
        }
        .confirmationDialog(text("host.saveEditor.readConfirm"), isPresented: $confirmingRead) {
            Button(text("host.saveEditor.read"), role: .destructive, action: model.openSelection)
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
            TrainerSaveJSONSheet(model: model, row: row, workspace: model.workspaceID)
        }
    }

    private var sourceOptions: [TrainerSaveEditorDocumentOption] {
        model.sources.map { .init(id: $0.id, title: $0.displayLabel) }
    }

    private var targetOptions: [TrainerSaveEditorDocumentOption] {
        model.targets.map { .init(id: $0.id, title: $0.displayLabel) }
    }

    private func requestCurrentSourceRead() {
        guard !model.busy, !loadedSourceID.isEmpty else { return }
        model.selectedSourceID = loadedSourceID
        if model.review.count > 0 { confirmingRead = true } else { model.openSelection() }
    }

    private var headerBar: some View {
        TrainerSaveEditorWindowHeader(
            title: text(titleKey),
            subtitle: model.source.map { $0.snapshotId ?? $0.relativePath },
            busy: model.busy || model.queryLoading,
            refreshTitle: text("host.saveEditor.read"),
            refreshEnabled: !model.busy && !loadedSourceID.isEmpty
                && model.sources.contains(where: { $0.id == loadedSourceID }),
            doneTitle: text("host.done"),
            doneEnabled: !model.busy,
            onRefresh: requestCurrentSourceRead,
            onDone: {
                if let closeWindow { closeWindow() } else { dismiss() }
            }
        )
    }

    private var documentBar: some View {
        TrainerSaveEditorDocumentBar(
            sourceLabel: text("host.saveEditor.source"),
            sourcePlaceholder: text("host.saveEditor.selectSource"),
            sourceSelection: $model.selectedSourceID,
            sources: sourceOptions,
            sourceEnabled: !model.busy,
            sourceRefreshTitle: text("host.refresh"),
            onRefreshSources: { model.refreshInventory() },
            targetLabel: text("host.saveEditor.target"),
            targetPlaceholder: text("host.saveEditor.selectTarget"),
            targetSelection: Binding(
                get: { model.selectedTargetID },
                set: { model.selectTarget($0, baseline: model.baselineGeneration) }
            ),
            targets: targetOptions,
            targetEnabled: !model.busy && model.canEditRows && model.source != nil
        )
    }

    @ViewBuilder
    private var documentContext: some View {
        if let source = model.source {
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .firstTextBaseline) {
                    Text(text(source.kind == "managedBackup"
                        ? "host.saveEditor.backupSource"
                        : "host.saveEditor.currentSource"))
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
            TrainerEmptyState(text: text("host.saveEditor.noSources"))
        }
    }

    private var workbenchBar: some View {
        TrainerSaveEditorWorkbenchBar(
            search: $model.search,
            searchPlaceholder: text("host.saveEditor.search"),
            clearLabel: text("host.search.clear"),
            searchEnabled: model.workspaceID != nil && !model.hasWorkspaceLock,
            loading: model.queryLoading,
            onSubmit: { model.query() }
        ) {
            domainPicker
        } trailing: {
            Button {
                model.query(offset: model.offset)
            } label: {
                Image(systemName: TrainerSemanticIcon.Concept.refresh)
            }
            .buttonStyle(.borderless)
            .disabled(model.workspaceID == nil || model.hasWorkspaceLock)
            .help(text("host.saveEditor.refreshRows"))
            .accessibilityLabel(text("host.saveEditor.refreshRows"))
        }
    }

    private var domainPicker: some View {
        Picker(
            text("host.saveEditor.domain"),
            selection: Binding(
                get: { model.selectedDomainID ?? model.domains.first?.id ?? "" },
                set: { model.selectDomain($0) }
            )
        ) {
            ForEach(model.domains) { domain in
                Text(domain.title).tag(domain.id)
            }
        }
        .labelsHidden()
        .trainerPicker(
            .rowValue,
            state: model.workspaceID == nil || model.hasWorkspaceLock || model.domains.isEmpty ? .unavailable : .interactive
        )
    }

    private var owners: [String] {
        var found: [String] = []
        for row in model.rows where !found.contains(row.ownerId) {
            found.append(row.ownerId)
        }
        return found
    }

    private var results: some View {
        TrainerSaveEditorResultContainer(
            phase: resultPhase,
            sourcePrompt: text("host.saveEditor.selectSource"),
            emptyPrompt: text("host.saveEditor.empty")
        ) {
            let domainTitle = model.selectedDomain?.title ?? text("host.saveEditor.domain")
            let domainIcon = model.selectedDomain?.icon ?? TrainerSemanticIcon.Section.inventory
            ScrollView {
                LazyVStack(alignment: .leading, spacing: theme.pageSpacing) {
                    TrainerSection(title: domainTitle, icon: domainIcon) {
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
                                    TrainerSaveEditorFieldRow(model: model, row: row, workspace: model.workspaceID)
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

    private var paging: some View {
        let start = model.total == 0 ? 0 : model.offset + 1
        let end = min(model.total, model.offset + model.rows.count)
        return TrainerSaveEditorPagingBar(
            summary: "\(start)–\(end) / \(model.total)",
            previousTitle: text("host.saveEditor.previous"),
            nextTitle: text("host.saveEditor.next"),
            canPrevious: model.canPreviousPage,
            canNext: model.canNextPage,
            onPrevious: model.previousPage,
            onNext: model.nextPage
        )
    }

    private var changes: some View {
        let baseline = model.review.baselineGeneration
        return VStack(alignment: .leading, spacing: theme.controlPadding) {
            TrainerSaveEditorReviewHeader(
                title: text("host.saveEditor.changes") + " (\(model.review.count))",
                discardTitle: text("host.saveEditor.discard"),
                discardEnabled: !model.busy && model.canEditRows,
                applyTitle: text("host.saveEditor.apply"),
                applyEnabled: model.canApply,
                onDiscard: { model.cancel(baseline: baseline) },
                onApply: { model.apply(baseline: baseline) }
            )
            ScrollView {
                VStack(alignment: .leading, spacing: theme.compactControlSpacing) {
                    ForEach(model.review.actions) { action in
                        TrainerListCard {
                            VStack(alignment: .leading, spacing: theme.compactControlSpacing / 2) {
                                HStack(alignment: .firstTextBaseline, spacing: theme.compactControlSpacing) {
                                    Text(action.name).font(.subheadline.weight(.semibold))
                                    Spacer()
                                    Button {
                                        model.unstage(action.id, baseline: baseline)
                                    } label: {
                                        Image(systemName: TrainerSemanticIcon.Action.remove)
                                    }
                                    .buttonStyle(.borderless)
                                    .help(text("host.saveEditor.remove"))
                                    .accessibilityLabel(text("host.saveEditor.remove"))
                                    .accessibilityIdentifier("saveEditor.remove." + action.id)
                                    .disabled(!model.canEditRows || !model.client.canEditEntry(action.id, baseline: baseline))
                                }
                                Text(action.before + " → " + action.after)
                                    .font(.caption.monospacedDigit())
                                    .textSelection(.enabled)
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

    private func applied(_ receipt: TrainerSaveEditorReceipt) -> some View {
        TrainerSaveEditorReceiptPanel(
            title: text("host.saveEditor.applied"),
            maintenanceWarning: receipt.maintenanceWarning,
            namingWarning: receipt.namingWarning
        ) {
            Text(receipt.target.id).font(.caption).textSelection(.enabled)
            Text("SHA-256 · " + receipt.installedSHA256)
                .font(.caption2.monospaced())
                .textSelection(.enabled)
            if let backup = receipt.previousSnapshotId {
                Text(text("host.saveEditor.recoverableBackup") + ": " + backup)
                    .font(.caption)
                    .textSelection(.enabled)
            }
            Text(text(receipt.runtimeReloaded == true ? "host.saveEditor.runtimeReloaded" :
                      receipt.hot == true ? "host.saveEditor.hot" : "host.saveEditor.loadInGame"))
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

private struct TrainerSaveEditorFieldRow: View {
    @ObservedObject var model: TrainerSaveEditorModel
    let row: TrainerSaveEditorRow
    let workspace: String?

    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme
    @State private var draft: String?
    @State private var focused = false

    private func text(_ key: String) -> String { localization.localized(key) }
    private var pending: TrainerSaveEditorReview.Action? { model.review.actions.first { $0.id == row.id } }
    private var effectiveValue: TrainerSaveEditorJSONValue? {
        pending?.operation == "set" ? (pending?.value ?? row.value) : row.value
    }
    private var displayValue: String { pending?.after ?? row.displayValue }
    private var editable: Bool { model.canEdit(row) }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            TrainerLabeledControlRow(
                title: row.name,
                icon: TrainerSemanticIcon.Action.rename,
                tint: theme.accent,
                emphasized: pending != nil
            ) {
                controls
                if editable && row.operations.contains("unset") {
                    TrainerOverflowMenu(enabled: editable) {
                        Button(text("host.saveEditor.unset"), role: .destructive) {
                            model.stage(row.id, operation: "unset", workspace: workspace, baseline: row.baselineGeneration)
                        }
                    }
                }
            }
            .disabled(!editable)

            if case .some(.string(let content)) = effectiveValue,
               content.count > 80 || content.contains("\n") {
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
        .onChange(of: model.editRevision) { _, _ in
            if !focused && !model.hasFailedDraft(row) { draft = nil }
        }
    }

    @ViewBuilder
    private var controls: some View {
        if !row.editable {
            Text(displayValue)
                .font(.caption.monospacedDigit())
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
        } else if !row.choices.isEmpty {
            Picker(
                row.name,
                selection: Binding(
                    get: { row.choices.firstIndex(where: { $0.value == effectiveValue }) ?? -1 },
                    set: { index in
                        guard row.choices.indices.contains(index) else { return }
                        model.stage(
                            row.id,
                            operation: "set",
                            value: row.choices[index].value.anyObject,
                            workspace: workspace,
                            baseline: row.baselineGeneration
                        )
                    }
                )
            ) {
                Text(displayValue).tag(-1)
                ForEach(row.choices.indices, id: \.self) { index in
                    Text(row.choices[index].name).tag(index)
                }
            }
            .labelsHidden()
            .trainerPicker(.rowValue, state: editable ? .interactive : .unavailable)
        } else if row.valueType == "boolean", case .some(.bool(let enabled)) = effectiveValue {
            TrainerToggleControl(
                title: row.name,
                isOn: enabled,
                enabled: editable,
                helpText: row.name
            ) { newValue in
                model.stage(
                    row.id,
                    operation: "set",
                    value: newValue,
                    workspace: workspace,
                    baseline: row.baselineGeneration
                )
            }
        } else if (row.valueType == "integer" || row.valueType == "number" || row.valueType == "string"),
                  let scalar = effectiveValue?.scalarText {
            TrainerTextField(
                title: row.name,
                text: Binding(get: { draft ?? scalar }, set: { draft = $0 }),
                onEditingChanged: { active in
                    focused = active
                    model.editingChanged(row.id, baseline: row.baselineGeneration, active: active)
                },
                onCommit: { completed in
                    guard completed.changed else {
                        return model.hasFailedDraft(row) ? completed.text : (effectiveValue?.scalarText ?? completed.text)
                    }
                    return model.commitText(row, text: completed.text, workspace: workspace)
                }
            )
            .frame(width: row.valueType == "string" ? 280 : 155)
        } else {
            Text(displayValue)
                .font(.caption)
                .lineLimit(3)
                .textSelection(.enabled)
                .frame(maxWidth: 220, alignment: .trailing)
            TrainerSecondaryActionButton(
                title: text("host.saveEditor.editJson"),
                enabled: editable,
                widthRole: .sheet
            ) {
                model.detail(row.id, baseline: row.baselineGeneration)
            }
        }
    }
}

private struct TrainerSaveJSONEditorView: NSViewRepresentable {
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
        var parent: TrainerSaveJSONEditorView
        init(_ parent: TrainerSaveJSONEditorView) { self.parent = parent }
        func focusChanged(_ focused: Bool) {
            if parent.focused != focused { parent.focused = focused }
        }
        func textDidChange(_ notification: Notification) {
            guard let view = notification.object as? NSTextView else { return }
            parent.text = view.string
        }
        func textView(_ textView: NSTextView, doCommandBy commandSelector: Selector) -> Bool {
            if commandSelector == #selector(NSResponder.cancelOperation(_:)),
               !textView.hasMarkedText(),
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
        if !enabled || !focused, view.window?.firstResponder === view {
            view.window?.makeFirstResponder(nil)
        }
    }

    static func dismantleNSView(_ scroll: NSScrollView, coordinator: Coordinator) {
        let view = scroll.documentView as! TextView
        view.focusChanged = nil
        view.onCancel = nil
        view.delegate = nil
    }
}

private struct TrainerSaveJSONSheet: View {
    @ObservedObject var model: TrainerSaveEditorModel
    let row: TrainerSaveEditorRow
    let workspace: String?

    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme
    @State private var json = ""
    @State private var initial = ""
    @State private var valid = true
    @State private var staging = false
    @State private var closeAfterStage = false
    @State private var discarding = false
    @State private var editing = false

    private func text(_ key: String) -> String { localization.localized(key) }
    private var action: TrainerSaveEditorReview.Action? { model.review.actions.first { $0.id == row.id } }

    var body: some View {
        TrainerSheetScaffold(title: row.name, icon: TrainerSemanticIcon.Action.edit, width: 700) {
            if !row.owner.isEmpty {
                Text(row.owner + " · " + row.group)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        } content: {
            VStack(alignment: .leading, spacing: theme.sectionSpacing) {
                if let warning = row.warning, !warning.isEmpty {
                    Text(warning)
                        .font(.caption)
                        .foregroundStyle(theme.warning)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Text(text("host.saveEditor.jsonHelp"))
                    .font(.caption)
                    .fixedSize(horizontal: false, vertical: true)
                TrainerSaveJSONEditorView(title: row.name, text: $json, focused: $editing, onCancel: finishSheet)
                    .frame(minHeight: 280)
                    .overlay(RoundedRectangle(cornerRadius: theme.compactCornerRadius).stroke(theme.accent.opacity(0.35)))
                    .disabled(staging)
                    .onChange(of: editing) { old, current in
                        if old && !current && !discarding { commit() }
                        model.editingChanged(row.id, baseline: row.baselineGeneration, active: current)
                    }
                if !valid {
                    TrainerInlineNotice(color: theme.warning) {
                        Text(text("host.saveEditor.invalidValue"))
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
                        title: text("host.saveEditor.remove"),
                        enabled: !model.busy && !staging && model.canEdit(row),
                        widthRole: .sheet
                    ) {
                        guard !model.busy else { return }
                        discarding = true
                        editing = false
                        staging = true
                        model.unstage(row.id, baseline: row.baselineGeneration) { accepted in
                            staging = false
                            if accepted { model.discardDraft(row, workspace: workspace) } else { discarding = false }
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
        .onDisappear {
            editing = false
            model.editingChanged(row.id, baseline: row.baselineGeneration, active: false)
        }
        .onAppear {
            let start = (action?.value ?? row.value ?? .null).jsonText
            json = start
            initial = start
        }
    }

    private func finishSheet() {
        guard !model.busy && !staging && model.canEdit(row) else { return }
        commit(closeWhenAccepted: true)
        editing = false
    }

    private func cancelSheet() {
        guard !model.busy && !staging else { return }
        discarding = true
        editing = false
        model.discardDraft(row, workspace: workspace)
    }

    private func commit(closeWhenAccepted: Bool = false) {
        if closeWhenAccepted { closeAfterStage = true }
        guard !staging else { return }
        guard json != initial else {
            if closeAfterStage { model.discardDraft(row, workspace: workspace) }
            return
        }
        let submittedJSON = json
        staging = true
        let enqueued = model.commitJSON(row, text: submittedJSON, workspace: workspace) { accepted in
            staging = false
            valid = accepted
            guard accepted else {
                closeAfterStage = false
                return
            }
            initial = submittedJSON
            if closeAfterStage && json == submittedJSON {
                discarding = true
                editing = false
                model.editingChanged(row.id, baseline: row.baselineGeneration, active: false)
                model.dismissDetail()
            }
            closeAfterStage = false
        }
        if !enqueued {
            staging = false
            valid = false
            closeAfterStage = false
        }
    }
}
