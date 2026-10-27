import SwiftUI

struct HadesSaveEditorView: View {
    @StateObject private var model: HadesSaveEditorModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme
    @Environment(\.trainerCloseToolWindow) private var closeWindow
    @State private var confirmingRead = false

    init(model: HadesSaveEditorModel) { _model = StateObject(wrappedValue: model) }
    private func text(_ key: String) -> String { HadesGameModule.resolveText(key: key, localization: localization) }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            selection
            if !model.failures.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(model.failures.keys.sorted(), id: \.self) { key in
                        if let failure = model.failures[key] {
                            Text(localization.string(failure)).font(.caption).foregroundStyle(theme.warning)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }.frame(maxWidth: .infinity, alignment: .leading).padding(theme.controlPadding)
            }
            if let recovery = model.recoveryPath {
                VStack(alignment: .leading, spacing: 4) {
                    Text(text("hades.saveEditor.recovery")).foregroundStyle(theme.warning)
                    Text(recovery).font(.caption.monospaced()).textSelection(.enabled)
                }.frame(maxWidth: .infinity, alignment: .leading).padding(theme.controlPadding)
            }
            Divider()
            toolbar
            Divider()
            results
                .id(model.workspaceID)
                .frame(minHeight: 300, idealHeight: model.review.count > 0 ? 350 : 500, maxHeight: .infinity)
            if model.total > HadesSaveEditorModel.pageSize { Divider(); paging }
            if model.review.count > 0 { Divider(); changes.frame(height: 215) }
            if let receipt = model.receipt { Divider(); applied(receipt) }
        }
        .frame(minWidth: 880, idealWidth: 980, minHeight: 700, idealHeight: 850)
        .trainerSurface(.canvas)
        .trainerDismissTextEditingOnClickAway()
        .onAppear { model.open(language: localization.language) }
        .onChange(of: localization.language) { _, value in model.setLanguage(value) }
        .onChange(of: model.search) { _, _ in model.searchChanged() }
        .confirmationDialog(text("hades.saveEditor.readConfirm"), isPresented: $confirmingRead) {
            Button(text("hades.saveEditor.read"), role: .destructive, action: model.openSelection)
            Button(text("host.cancel"), role: .cancel) {}
        }
        .sheet(item: Binding(get: { model.editingRow }, set: { if $0 == nil { model.dismissDetail() } })) { row in
            HadesSaveTypedEditor(model: model, row: row, workspace: model.workspaceID, forceTyped: model.editingTyped)
        }
    }
    private var header: some View {
        HStack(spacing: theme.controlPadding) {
            Image(systemName: "externaldrive.badge.gearshape").foregroundStyle(theme.accent)
            Text(text("hades.saveEditor.title")).font(.title3.weight(.semibold))
            if model.busy || model.queryLoading { ProgressView().controlSize(.small) }
            Spacer()
            Button(text("host.done")) { closeWindow?() }.disabled(model.busy)
        }.padding(theme.rowHorizontalPadding)
    }
    private var selection: some View {
        VStack(alignment: .leading, spacing: theme.controlPadding) {
            HStack {
                Picker(text("hades.saveEditor.source"), selection: $model.selectedSourceID) {
                    Text(text("hades.saveEditor.selectSource")).tag("")
                    ForEach(model.sources) { Text($0.label).tag($0.id) }
                }.disabled(model.busy)
                Button(text("hades.saveEditor.read")) {
                    if model.review.count > 0 { confirmingRead = true } else { model.openSelection() }
                }.disabled(model.busy || !model.sources.contains(where: { $0.id == model.selectedSourceID }))
                Button { model.refreshInventory() } label: { Image(systemName: "arrow.clockwise") }
                    .help(text("host.refresh")).accessibilityLabel(text("host.refresh")).disabled(model.busy)
            }
            if let source = model.source {
                HStack(alignment: .firstTextBaseline) {
                    Text(text(source.kind == "managedBackup" ? "hades.saveEditor.backupSource" : "hades.saveEditor.currentSource"))
                        .font(.caption.weight(.semibold))
                    Text((source.snapshotId.map { $0 + " · " } ?? "") + source.id)
                        .font(.caption).textSelection(.enabled)
                    Spacer()
                }
                Text("SHA-256 · " + model.sourceSHA256).font(.caption2.monospaced()).foregroundStyle(.secondary)
                    .textSelection(.enabled)
                Picker(text("hades.saveEditor.target"), selection: Binding(get: { model.selectedTargetID }, set: model.selectTarget)) {
                    Text(text("hades.saveEditor.selectTarget")).tag("")
                    ForEach(model.targets) { Text($0.label).tag($0.id) }
                }.disabled(model.busy)
            } else if model.sources.isEmpty && !model.busy {
                TrainerEmptyState(text: text("hades.saveEditor.noSources"))
            }
        }.padding(.horizontal, theme.rowHorizontalPadding).padding(.vertical, theme.controlPadding)
    }
    private var toolbar: some View {
        VStack(alignment: .leading, spacing: theme.controlPadding) {
            HStack {
                Picker(text("hades.saveEditor.domain"), selection: Binding(get: { model.domain }, set: model.selectDomain)) {
                    ForEach(model.domains) { Text(text($0.titleKey)).tag($0) }
                }.frame(width: 235)
                TrainerSearchField(text: $model.search, placeholder: text("hades.saveEditor.search"),
                    clearLabel: text("host.search.clear"), onSubmit: { model.query() })
                Button { model.query(offset: model.offset) } label: { Image(systemName: "arrow.clockwise") }
                    .help(text("hades.saveEditor.refreshRows")).accessibilityLabel(text("hades.saveEditor.refreshRows"))
            }.disabled(model.workspaceID == nil)
            if model.parentID != nil {
                HStack(spacing: 6) {
                    Button(text(model.domain.titleKey)) { model.browse(nil) }
                    ForEach(model.breadcrumbs) { crumb in
                        Image(systemName: "chevron.right").font(.caption2).foregroundStyle(.secondary)
                        Button(crumb.name) { model.browse(crumb.id) }
                    }
                }.font(.caption)
            }
            if model.domain == .advanced {
                Text(text("hades.saveEditor.advancedWarning")).font(.caption).foregroundStyle(theme.warning)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }.padding(.horizontal, theme.rowHorizontalPadding).padding(.vertical, theme.controlPadding)
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
        }.padding(theme.controlPadding)
    }
    private var changes: some View {
        VStack(alignment: .leading, spacing: theme.controlPadding) {
            HStack {
                Text(text("hades.saveEditor.changes") + " (\(model.review.count))").font(.headline)
                Spacer()
                Button(text("hades.saveEditor.discard"), action: model.cancel).disabled(model.busy)
                TrainerPrimaryActionButton(title: text("hades.apply"), enabled: model.canApply, action: model.apply)
            }
            ScrollView {
                VStack(alignment: .leading, spacing: theme.controlPadding) {
                    ForEach(model.review.actions) { action in
                        TrainerListCard {
                            VStack(alignment: .leading, spacing: 5) {
                                HStack(alignment: .firstTextBaseline) {
                                    Text(action.name).font(.subheadline.weight(.semibold))
                                    Spacer()
                                    Button(text("hades.saveEditor.revise")) { model.detail(action.id) }.disabled(model.busy)
                                    Button(text("hades.remove")) { model.unstage(action.id) }.disabled(model.busy)
                                }
                                Text(action.before + " → " + action.after).font(.caption).textSelection(.enabled)
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
                    Button(text("hades.saveEditor.editTyped")) { model.detail(row.id, typed: true) }
                        .accessibilityLabel(text("hades.saveEditor.editTyped") + " " + row.name)
                }
                if row.hasChildren { Button { model.browse(row.id) } label: { Image(systemName: "chevron.right") }
                    .help(text("hades.saveEditor.browse")).accessibilityLabel(text("hades.saveEditor.browse") + " " + row.name) }
                if row.operations.contains("unset") {
                    Menu {
                        Button(text("hades.saveEditor.unset"), role: .destructive) {
                            model.stage(row.id, operation: "unset", workspace: workspace)
                        }
                    } label: { Image(systemName: "ellipsis") }.menuStyle(.borderlessButton).fixedSize()
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
        .onChange(of: model.editRevision) { _, _ in if !focused { draft = nil } }
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
                if choices.indices.contains(index) { model.stage(row.id, operation: "set", value: choices[index].value.object, workspace: workspace) }
            })) {
                Text(displayValue).tag(-1)
                ForEach(choices.indices, id: \.self) { Text(choices[$0].name).tag($0) }
            }.labelsHidden().frame(maxWidth: 240)
        } else if case .some(.boolean(let enabled)) = value {
            Toggle(row.name, isOn: Binding(get: { enabled }, set: {
                model.stage(row.id, operation: "set", value: HadesSaveValue.boolean($0).object, workspace: workspace)
            })).labelsHidden().toggleStyle(.switch).controlSize(.small)
        } else if let scalar = value?.scalarText {
            TrainerTextField(title: row.name, text: Binding(get: { draft ?? scalar }, set: { draft = $0 }),
                onEditingChanged: { focused = $0 }, onCommit: { completed in
                    guard completed.changed else { return completed.text }
                    return model.commit(row, text: completed.text, workspace: workspace)
                })
                .frame(width: row.valueType == "number" ? 155 : 280)
        } else {
            Text(displayValue).font(.caption).lineLimit(3).textSelection(.enabled).frame(maxWidth: 220, alignment: .trailing)
            Button(text("hades.saveEditor.editTyped")) { model.detail(row.id) }
        }
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
    @FocusState private var editing: Bool
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
                        append = appending
                        json = appending ? HadesSaveValue.string("").json
                            : ((action?.operation == "set" ? action?.typedValue : nil) ?? row.typedValue ?? .null).json
                        initial = json
                    }))
                }
                if append {
                    TrainerTextField(title: text("hades.saveEditor.key"), text: $appendKey)
                }
                TextEditor(text: $json).font(.system(.body, design: .monospaced)).focused($editing)
                    .frame(minHeight: 280).overlay(RoundedRectangle(cornerRadius: 6).stroke(theme.accent.opacity(0.35)))
                    .onChange(of: editing) { old, current in if old && !current { commit() } }
            }
            if !valid { Text(text("hades.saveEditor.invalidValue")).font(.caption).foregroundStyle(theme.warning) }
            if let failure = model.failures[row.id] { Text(localization.string(failure)).font(.caption).foregroundStyle(theme.warning) }
            HStack {
                if action != nil { Button(text("hades.remove")) { model.unstage(row.id); model.dismissDetail() }.disabled(model.busy) }
                Spacer()
                Button(text("host.done")) {
                    editing = false
                    if native || commit() { model.dismissDetail() }
                }.disabled(model.busy)
            }
        }.padding(20).frame(width: 700)
        .trainerDismissTextEditingOnClickAway()
        .onAppear {
            append = action?.operation == "append"
            appendKey = action?.typedKey?.json ?? appendKey
            json = (action?.typedValue ?? row.typedValue ?? .null).json
            initial = json; initialKey = appendKey; initialAppend = append
        }
    }
    @discardableResult private func commit() -> Bool {
        guard json != initial || appendKey != initialKey || append != initialAppend else { return true }
        valid = model.commitJSON(row, text: json, appendKey: append ? appendKey : nil, workspace: workspace)
        if valid { initial = json; initialKey = appendKey; initialAppend = append }
        return valid
    }
}
