import SwiftUI

/// Explicit structure/type editing for Advanced. Ordinary scalar controls stay
/// inline; this editor preserves table key types and non-UTF8 Lua strings.
struct Hades2SaveAdvancedValueView: View {
    @ObservedObject var model: Hades2SaveEditorModel
    let entry: Hades2SaveEditorEntry
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme
    @Environment(\.dismiss) private var dismiss
    @State private var detail: Hades2SaveAdvancedDetail?
    @State private var loading = false
    @State private var loaded = false
    @State private var failure: TrainerTextToken?
    @State private var requestID = UUID()
    @State private var valueDraft = ""

    private var membershipDraft: Hades2SaveAdvancedMembershipDraft {
        model.membershipDrafts[entry.id] ?? Hades2SaveAdvancedMembershipDraft()
    }
    private func membershipBinding(_ path: WritableKeyPath<Hades2SaveAdvancedMembershipDraft, String>) -> Binding<String> {
        Binding(get: { membershipDraft[keyPath: path] }, set: { value in
            var draft = membershipDraft
            draft[keyPath: path] = value
            model.retainMembershipDraft(draft, for: entry.id, baseline: entry.baselineGeneration)
        })
    }

    private func text(_ key: String) -> String {
        Hades2GameModule.resolveText(key: key, localization: localization)
    }
    private var mutations: [String] { detail?.mutationKinds ?? entry.mutationKinds }
    private var editable: Bool { loaded && (detail?.editable ?? entry.editable) && !model.busy && entry.baselineGeneration == model.baselineGeneration }

    var body: some View {
        VStack(alignment: .leading, spacing: theme.sectionSpacing) {
            HStack {
                Text(entry.displayName).font(.headline).textSelection(.enabled)
                Spacer()
                Button(localization.localized("host.done")) { dismiss() }.disabled(model.busy)
            }
            Text(detail?.warning ?? entry.warning ?? text("hades2.saveEditor.advanced.unknownImpact"))
                .font(.caption).foregroundStyle(theme.warning).fixedSize(horizontal: false, vertical: true)
            if loading { ProgressView().controlSize(.small) }
            if let failure {
                Text(localization.string(failure)).foregroundStyle(theme.warning)
                Button(text("hades2.saveEditor.advanced.retry")) { load(preservingDraft: loaded) }
            }
            if loaded {
                Text(text("hades2.saveEditor.advanced.typedHint"))
                    .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                TrainerTextField(
                    title: text("hades2.saveEditor.advanced.typedValue"), text: $valueDraft,
                    accessibilityLabel: entry.displayName + " · " + text("hades2.saveEditor.advanced.typedValue"),
                    onCommit: { edit in
                        model.completeTypedEdit(entry, text: edit.text, changed: edit.changed)
                    }
                )
                .disabled(!editable || !mutations.contains("set"))
                if let reason = detail?.readOnlyReason { Text(reason).font(.caption).foregroundStyle(theme.warning) }
                if let correction = model.editFailures[entry.id] {
                    Text(localization.string(correction)).font(.caption).foregroundStyle(theme.warning)
                }
                if mutations.contains("addMembership") || mutations.contains("removeMembership") {
                    Divider()
                    Text(text("hades2.saveEditor.advanced.membership")).font(.callout.weight(.medium))
                    HStack {
                        Picker(text("hades2.saveEditor.advanced.keyType"), selection: membershipBinding(\.keyType)) {
                            Text(text("hades2.saveEditor.advanced.type.string")).tag("string")
                            Text(text("hades2.saveEditor.advanced.type.number")).tag("number")
                            Text(text("hades2.saveEditor.advanced.type.boolean")).tag("boolean")
                        }.trainerPickerWidth(.standard)
                        TrainerTextField(title: text("hades2.saveEditor.advanced.key"), text: membershipBinding(\.key))
                    }
                    TrainerTextField(title: text("hades2.saveEditor.advanced.memberValue"), text: membershipBinding(\.value))
                    HStack {
                        Button(text("hades2.saveEditor.advanced.addMember")) { membership("addMembership") }
                            .disabled(!editable || !mutations.contains("addMembership"))
                        Button(text("hades2.saveEditor.advanced.removeMember")) { membership("removeMembership") }
                            .disabled(!editable || !mutations.contains("removeMembership"))
                    }
                    if let memberFailure = membershipDraft.failure {
                        Text(localization.string(memberFailure)).font(.caption).foregroundStyle(theme.warning)
                    }
                }
                if mutations.contains("unset") {
                    Button(text("hades2.saveEditor.advanced.removeField")) {
                        model.stage(entryID: entry.id, operation: "unset", value: nil, baseline: entry.baselineGeneration)
                    }.disabled(!editable)
                }
            }
        }
        .padding(theme.pagePadding)
        .frame(width: 780)
        .trainerSurface(.canvas)
        .trainerDismissTextEditingOnClickAway()
        .interactiveDismissDisabled(model.busy)
        .onAppear { load(preservingDraft: false) }
        .onDisappear { requestID = UUID() }
        .onChange(of: localization.language) { _, _ in load(preservingDraft: loaded) }
        .onChange(of: model.editRevision) { _, _ in
            guard model.reconciledEntryIDs == nil || model.reconciledEntryIDs?.contains(entry.id) == true else { return }
            load(preservingDraft: false)
        }
    }

    private func load(preservingDraft: Bool) {
        if !preservingDraft, let retained = model.typedDrafts[entry.id] {
            valueDraft = retained
        }
        if let current = model.pendingActions.first(where: { $0.entryID == entry.id })?.typedAfter ?? entry.typedValue {
            if !preservingDraft && model.typedDrafts[entry.id] == nil { valueDraft = current.json }
            loaded = true
            return
        }
        let request = UUID()
        requestID = request
        loading = true
        failure = nil
        model.loadAdvancedValue(entry, language: localization.language) { value, error in
            guard requestID == request else { return }
            loading = false
            failure = error
            guard let value else { return }
            detail = value
            if !preservingDraft { valueDraft = model.typedDrafts[entry.id] ?? value.value.json }
            loaded = true
        }
    }

    private func membership(_ operation: String) {
        var draft = membershipDraft
        let rawKey: Any
        switch draft.keyType {
        case "number":
            guard let number = TrainerJSONNumericInput.number(draft.key, allowsInfinity: true), !number.isNaN else { invalidMembership(); return }
            rawKey = number
        case "boolean":
            guard ["true", "false"].contains(draft.key) else { invalidMembership(); return }
            rawKey = draft.key == "true"
        default: rawKey = draft.key
        }
        let key: [String: Any]
        if draft.keyType == "number", let number = rawKey as? Double, number.isInfinite {
            key = ["luaType": "number", "encoding": "nonfinite", "value": number.sign == .minus ? "-inf" : "inf"]
        } else {
            key = ["luaType": draft.keyType, "value": rawKey]
        }
        var payload: [String: Any] = ["key": Hades2SaveTypedValue(key)!.object]
        if operation == "addMembership" {
            guard let value = Hades2SaveTypedValue(text: draft.value) else { invalidMembership(); return }
            payload["value"] = value.object
        }
        draft.failure = nil
        model.retainMembershipDraft(draft, for: entry.id, baseline: entry.baselineGeneration)
        model.stage(entryID: entry.id, operation: operation, value: payload, baseline: entry.baselineGeneration)
    }

    private func invalidMembership() {
        var draft = membershipDraft
        draft.failure = TrainerTextToken(key: "hades2.saveEditor.invalidDraft")
        model.retainMembershipDraft(draft, for: entry.id, baseline: entry.baselineGeneration)
    }
}
