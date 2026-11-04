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
            TrainerSaveEditorWindowHeader(
                title: text("hades.saveEditor.title"),
                busy: model.busy || model.queryLoading,
                refreshTitle: text("hades.saveEditor.read"),
                refreshEnabled: !model.busy && loadedSourceID != ""
                    && model.sources.contains(where: { $0.id == loadedSourceID }),
                doneTitle: text("host.done"),
                doneEnabled: !model.busy,
                onRefresh: requestCurrentSourceRead,
                onDone: { closeWindow?() }
            )
            Divider()
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
            documentContext
            if !model.failures.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(model.failures.keys.sorted(), id: \.self) { key in
                        if let failure = model.failures[key] {
                            Text(localization.string(failure)).font(.caption).foregroundStyle(theme.warning)
                                .fixedSize(horizontal: false, vertical: true)
                                .contentTransition(.opacity)
                                .animation(TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion), value: failure)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, theme.rowHorizontalPadding)
                .padding(.top, theme.controlPadding)
                .transition(.opacity)
            }
            if let recovery = model.recoveryPath {
                VStack(alignment: .leading, spacing: 4) {
                    Text(text("hades.saveEditor.recovery")).foregroundStyle(theme.warning)
                    Text(recovery).font(.caption.monospaced()).textSelection(.enabled)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, theme.rowHorizontalPadding)
                .padding(.top, theme.controlPadding)
                .transition(.opacity)
            }
            Divider()
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
        .sheet(item: Binding(get: { model.editingRow }, set: { if $0 == nil { model.dismissDetail() } })) { row in
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
            HStack(spacing: 6) {
                Button(text(model.domain.titleKey)) { model.browse(nil) }
                ForEach(model.breadcrumbs) { crumb in
                    Image(systemName: "chevron.right")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Button(crumb.name) { model.browse(crumb.id) }
                }
            }
            .font(.caption)
            .padding(.horizontal, theme.rowHorizontalPadding)
            .padding(.bottom, theme.compactControlSpacing)
        }
        if model.domain == .advanced {
            Text(text("hades.saveEditor.advancedWarning"))
                .font(.caption)
                .foregroundStyle(theme.warning)
                .fixedSize(horizontal: false, vertical: true)
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
        ScrollView {
            LazyVStack(alignment: .leading, spacing: theme.controlPadding) {
                if model.rows.isEmpty && !model.queryLoading {
                    TrainerEmptyState(text: text("hades.saveEditor.empty"))
                        .transition(.opacity)
                }
                ForEach(owners, id: \.self) { ownerID in
                    TrainerListCard {
                        VStack(alignment: .leading, spacing: 0) {
                            let owned = model.rows.filter { $0.ownerId == ownerID }
                            if let owner = owned.first?.owner, !owner.isEmpty {
                                Text(owner).font(.headline).padding(theme.controlPadding).accessibilityAddTraits(.isHeader)
                            }
                            ForEach(Array(owned.enumerated()), id: \.element.id) { index, row in
                                if index == 0 || owned[index - 1].groupId != row.groupId {
                                    if !row.group.isEmpty {
                                        Text(row.group).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                                            .padding(.horizontal, theme.controlPadding).padding(.top, theme.controlPadding)
                                            .accessibilityAddTraits(.isHeader)
                                    }
                                }
                                HadesSaveEditorField(model: model, row: row, workspace: model.workspaceID)
                                if index < owned.count - 1 { Divider() }
                            }
                        }
                    }
                }
            }.padding(theme.rowHorizontalPadding)
        }
        .overlay {
            if model.rows.isEmpty && model.queryLoading {
                ProgressView().controlSize(.small).allowsHitTesting(false).transition(.opacity)
            }
        }
        .animation(TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion), value: model.rows.isEmpty && model.queryLoading)
    }
    private var paging: some View {
        HStack {
            Button(text("hades.saveEditor.previous"), action: model.previousPage)
                .disabled(model.offset == 0 || model.queryLoading)
            Text("\(model.offset + 1)–\(min(model.total, model.offset + model.pageLimit)) / \(model.total)")
                .font(.caption.monospacedDigit())
            Button(text("hades.saveEditor.next"), action: model.nextPage)
                .disabled(model.offset + model.pageLimit >= model.total || model.queryLoading)
            Spacer()
        }
    }
    private var changes: some View {
        let baseline = model.review.baselineGeneration
        return VStack(alignment: .leading, spacing: theme.controlPadding) {
            HStack {
                Text(text("hades.saveEditor.changes") + " (\(model.review.count))").font(.headline)
                Spacer()
                Button(text("hades.saveEditor.discard")) { model.cancel(baseline: baseline) }.disabled(model.busy || !model.canEditRows)
                TrainerPrimaryActionButton(title: text("hades.apply"), systemImage: TrainerSemanticIcon.Action.apply, enabled: model.canApply, widthRole: .sheet) { model.apply(baseline: baseline) }
            }
            ScrollView {
                VStack(alignment: .leading, spacing: theme.controlPadding) {
                    ForEach(model.review.actions) { action in
                        TrainerListCard {
                            VStack(alignment: .leading, spacing: 5) {
                                HStack(alignment: .firstTextBaseline) {
                                    Text(action.name).font(.subheadline.weight(.semibold))
                                    Spacer()
                                    Button(text("hades.saveEditor.revise")) { model.detail(action.id, baseline: baseline) }.disabled(model.busy || !model.canEditRows)
                                    Button(text("hades.remove")) { model.unstage(action.id, baseline: baseline) }.disabled(model.busy || !model.canEditRows)
                                }
                                Text(action.before + " → " + action.after).font(.caption).textSelection(.enabled)
                                    .contentTransition(.opacity)
                                    .animation(TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion), value: action.after)
                                ForEach(action.effects) { effect in
                                    Text(effect.name + ": " + effect.before + " → " + effect.after)
                                        .font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                                }
                            }
                        }
                    }
                }
            }
        }.padding(theme.rowHorizontalPadding)
    }
    private func applied(_ receipt: HadesSaveEditorReceipt) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Label(text("hades.saveEditor.applied"),
                    systemImage: "checkmark.circle.fill").foregroundStyle(theme.success)
                Spacer()
            }
            Text(receipt.target.id).font(.caption).textSelection(.enabled)
            Text("SHA-256 · " + receipt.installedSHA256).font(.caption2.monospaced()).textSelection(.enabled)
            if let backup = receipt.previousSnapshotId {
                Text(text("hades.saveEditor.recoverableBackup") + ": " + backup).font(.caption).textSelection(.enabled)
            }
            Text(text(receipt.hot == true ? "hades.saveEditor.hot" : "hades.saveEditor.loadInGame"))
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }.padding(theme.rowHorizontalPadding)
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
            TrainerLabeledControlRow(title: row.name, icon: row.hasChildren ? "folder" : "pencil", tint: theme.accent,
                                     emphasized: pending != nil) {
                controls
                if model.domain == .advanced && hasNativeControl {
                    Button(text("hades.saveEditor.editTyped")) { model.detail(row.id, typed: true, baseline: row.baselineGeneration) }
                        .accessibilityLabel(text("hades.saveEditor.editTyped") + " " + row.name)
                }
                if row.hasChildren { Button { model.browse(row.id, baseline: row.baselineGeneration) } label: { Image(systemName: "chevron.right") }
                    .help(text("hades.saveEditor.browse")).accessibilityLabel(text("hades.saveEditor.browse") + " " + row.name) }
                if row.operations.contains("unset") {
                    Menu {
                        Button(text("hades.saveEditor.unset"), role: .destructive) {
                            model.stage(row.id, operation: "unset", workspace: workspace, baseline: row.baselineGeneration)
                        }
                    } label: { Image(systemName: "ellipsis") }.menuStyle(.borderlessButton).fixedSize()
                }
            }.disabled(!model.canEdit(row))
            if let lines = row.content {
                ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
                    VStack(alignment: .leading, spacing: 3) {
                        if !line.speaker.isEmpty { Text(line.speaker).font(.caption.weight(.semibold)) }
                        Text(line.text).font(.callout).fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
                    }.frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, theme.controlPadding)
                }
            }
            if case .some(.string(let content)) = value, content.count > 80 || content.contains("\n") {
                Text(content).font(.caption).textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true).padding(.horizontal, theme.controlPadding)
            }
            if let warning = row.warning, !warning.isEmpty {
                Text(warning).font(.caption).foregroundStyle(theme.warning)
                    .padding(.horizontal, theme.controlPadding).padding(.bottom, 5)
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
            }.labelsHidden().trainerPicker(.rowValue)
        } else if case .some(.boolean(let enabled)) = value {
            Toggle(row.name, isOn: Binding(get: { enabled }, set: {
                model.stage(row.id, operation: "set", value: HadesSaveValue.boolean($0).object, workspace: workspace, baseline: row.baselineGeneration)
            })).labelsHidden().toggleStyle(.switch).controlSize(.small)
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
            Button(text("hades.saveEditor.editTyped")) { model.detail(row.id, baseline: row.baselineGeneration) }
        }
    }
}

private struct HadesSaveJSONEditor: NSViewRepresentable {
    let title: String
    @Binding var text: String
    @Binding var focused: Bool
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
        if view.string != text { view.string = text }
        view.isEditable = enabled
        view.isSelectable = enabled
        view.setAccessibilityLabel(title)
        if !enabled || !focused, view.window?.firstResponder === view { view.window?.makeFirstResponder(nil) }
    }
    static func dismantleNSView(_ scroll: NSScrollView, coordinator: Coordinator) {
        let view = scroll.documentView as! TextView
        view.focusChanged = nil
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
        VStack(alignment: .leading, spacing: 12) {
            Text(row.name).font(.headline)
            if !row.owner.isEmpty { Text(row.owner + " · " + row.group).font(.caption).foregroundStyle(.secondary) }
            if native {
                HadesSaveEditorField(model: model, row: row, workspace: workspace)
            } else {
                if let warning = row.warning { Text(warning).font(.caption).foregroundStyle(theme.warning) }
                Text(text("hades.saveEditor.advancedWarning")).font(.caption).foregroundStyle(theme.warning)
                Text(text("hades.saveEditor.typedHelp")).font(.caption).fixedSize(horizontal: false, vertical: true)
                if row.operations.contains("append") {
                    Toggle(text("hades.saveEditor.append"), isOn: Binding(get: { append }, set: { appending in
                        append = appending; editingKey = false
                        json = appending ? HadesSaveValue.string("").json
                            : ((action?.operation == "set" ? action?.typedValue : nil) ?? row.typedValue ?? .null).json
                        initial = json
                    })).disabled(staging)
                }
                if append {
                    Text(text("hades.saveEditor.key")).font(.caption)
                    HadesSaveJSONEditor(title: text("hades.saveEditor.key"), text: $appendKey, focused: $editingKey)
                        .frame(height: 70).overlay(RoundedRectangle(cornerRadius: 6).stroke(theme.accent.opacity(0.35)))
                        .disabled(staging)
                }
                HadesSaveJSONEditor(title: row.name, text: $json, focused: $editing)
                    .frame(minHeight: 280).overlay(RoundedRectangle(cornerRadius: 6).stroke(theme.accent.opacity(0.35)))
                    .disabled(staging)
                    .onChange(of: editing) { old, current in
                        if old && !current && !discarding { commit() }
                        model.editingChanged(row.id, baseline: row.baselineGeneration, active: current)
                    }
            }
            if !valid { Text(text("hades.saveEditor.invalidValue")).font(.caption).foregroundStyle(theme.warning) }
            if let failure = model.failures[row.id] { Text(localization.string(failure)).font(.caption).foregroundStyle(theme.warning) }
            HStack {
                Button(text("host.cancel"), role: .cancel) {
                    guard !model.busy else { return }
                    discarding = true; editing = false; editingKey = false
                    model.discardDraft(row, workspace: workspace)
                }.disabled(model.busy)
                if action != nil {
                    Button(text("hades.remove")) {
                        guard !model.busy else { return }
                        discarding = true; editing = false; editingKey = false; staging = true
                        model.unstage(row.id, baseline: row.baselineGeneration) { accepted in
                            staging = false
                            if accepted { model.discardDraft(row, workspace: workspace) }
                            else { discarding = false }
                        }
                    }.disabled(model.busy || staging)
                }
                Spacer()
                Button(text("host.done")) {
                    guard !model.busy else { return }
                    if native {
                        if !model.hasFailedDraft(row) { model.dismissDetail() }
                    } else { commit(closeWhenAccepted: true) }
                    editing = false; editingKey = false
                }.disabled(model.busy || staging)
            }
        }.padding(20).frame(width: 700)
        .disabled(!model.canEdit(row))
        .trainerDismissTextEditingOnClickAway()
        .onChange(of: editingKey) { _, active in
            model.editingChanged(row.id + ":key", baseline: row.baselineGeneration, active: active)
        }
        .onAppear {
            append = action?.operation == "append"
            appendKey = action?.typedKey?.json ?? appendKey
            json = (action?.typedValue ?? row.typedValue ?? .null).json
            initial = json; initialKey = appendKey; initialAppend = append
        }
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
