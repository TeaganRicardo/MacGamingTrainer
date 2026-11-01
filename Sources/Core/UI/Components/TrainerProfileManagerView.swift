import SwiftUI

struct TrainerProfileManagerLabels {
    let title: String
    let explanation: String
    let name: String
    let picker: String
    let save: String
    let load: String
    let empty: String
}

struct TrainerProfileManagerActions {
    let refresh: () -> Void
    let save: (String) -> Void
    let load: (String) -> Void
    let delete: (String) -> Void
    let dismiss: () -> Void
}

/// Modules provide an inventory and commands; Core owns the complete sheet
/// interaction without interpreting profile contents or application semantics.
struct TrainerProfileManagerView: View {
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme
    @State private var selection = TrainerProfileSelection()

    let labels: TrainerProfileManagerLabels
    let entries: [TrainerProfileEntry]
    let busy: Bool
    let enabled: Bool
    var warning = ""
    var error = ""
    let actions: TrainerProfileManagerActions

    private var canAct: Bool { enabled && !busy }
    private var names: [String] { entries.map(\.name) }
    private var canUseSelection: Bool { canAct && names.contains(selection.selectedName) }

    var body: some View {
        TrainerSheetScaffold(title: labels.title, icon: TrainerSemanticIcon.Tool.profiles, width: 620) {
            if busy {
                ProgressView().controlSize(.small)
                    .accessibilityLabel(localization.localized("host.operation.inProgress"))
            }
            Button(action: actions.refresh) {
                Label(localization.localized("host.refresh"), systemImage: TrainerSemanticIcon.Concept.refresh)
            }.disabled(!canAct)
        } content: {
            Text(labels.explanation).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            if !warning.isEmpty {
                Text(warning).font(.caption).foregroundStyle(theme.warning)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack(spacing: 10) {
                TrainerTextField(title: labels.name, text: $selection.draftName)
                    .frame(maxWidth: .infinity)
                TrainerPrimaryActionButton(title: labels.save,
                    systemImage: TrainerSemanticIcon.Action.save,
                    enabled: canAct && !selection.trimmedName.isEmpty) {
                    guard canAct, let name = selection.beginSave() else { return }
                    actions.save(name)
                }
            }
            Divider()
            if entries.isEmpty {
                TrainerEmptyState(text: labels.empty)
            } else {
                Picker(labels.picker, selection: $selection.selectedName) {
                    ForEach(entries) { entry in Text(entry.title).tag(entry.name) }
                }
                .trainerPickerWidth(.wide)
                .disabled(!canAct)
                HStack {
                    TrainerPrimaryActionButton(title: labels.load,
                        systemImage: TrainerSemanticIcon.Action.load, enabled: canUseSelection) {
                        guard canUseSelection else { return }
                        actions.load(selection.selectedName)
                    }
                    Button(role: .destructive) {
                        guard canUseSelection else { return }
                        actions.delete(selection.selectedName)
                    } label: {
                        Label(localization.localized("host.delete"), systemImage: TrainerSemanticIcon.Action.remove)
                    }.disabled(!canUseSelection)
                    Spacer()
                }
            }
            if !error.isEmpty {
                Text(error).foregroundStyle(theme.warning).fixedSize(horizontal: false, vertical: true)
                    .textSelection(.enabled)
            }
        } footer: {
            HStack {
                Spacer()
                Button(localization.localized("host.done"), action: actions.dismiss).keyboardShortcut(.cancelAction)
            }
        }
        .onChange(of: entries, initial: true) { _, _ in reconcileSelection() }
        .onChange(of: busy) { _, _ in reconcileSelection() }
        .onChange(of: error) { _, _ in reconcileSelection() }
    }

    private func reconcileSelection() {
        selection.reconcile(names, busy: busy)
    }
}
