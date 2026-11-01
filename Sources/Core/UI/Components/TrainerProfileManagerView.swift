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
    let save: (String, @escaping (Bool) -> Void) -> Void
    let load: (String) -> Void
    let delete: (String) -> Void
    let dismiss: () -> Void
}

/// Modules provide an inventory and commands; Core owns the complete sheet
/// interaction without interpreting profile contents or application semantics.
struct TrainerProfileManagerView: View {
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var selection = TrainerProfileSelection()
    @State private var lifetime = TrainerSheetLifetime()

    let labels: TrainerProfileManagerLabels
    let entries: [TrainerProfileEntry]
    let busy: Bool
    let enabled: Bool
    var warning = ""
    var error = ""
    let actions: TrainerProfileManagerActions

    private var canAct: Bool { lifetime.isActive && enabled && !busy && !selection.saving }
    private var names: [String] { entries.map(\.name) }
    private var canUseSelection: Bool { canAct && names.contains(selection.selectedName) }

    var body: some View {
        let presentationID = lifetime.id
        TrainerSheetScaffold(title: labels.title, icon: TrainerSemanticIcon.Tool.profiles, width: 620, minimumWidth: 360) {
            ProgressView().controlSize(.small).frame(width: 16, height: 16)
                .opacity(busy || selection.saving ? 1 : 0)
                .accessibilityHidden(!busy && !selection.saving)
                .accessibilityLabel(localization.localized("host.operation.inProgress"))
                .animation(TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion), value: busy || selection.saving)
            Button {
                guard lifetime.accepts(presentationID), canAct else { return }
                actions.refresh()
            } label: {
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
                    widthRole: .sheet,
                    systemImage: TrainerSemanticIcon.Action.save,
                    enabled: canAct && !selection.trimmedName.isEmpty) {
                    guard lifetime.accepts(presentationID), canAct, let request = selection.beginSave() else { return }
                    actions.save(request.name) { succeeded in
                        selection.completeSave(request, succeeded: succeeded)
                    }
                }
            }
            Divider()
            VStack(alignment: .leading, spacing: theme.sheetSpacing) {
                if entries.isEmpty {
                    TrainerEmptyState(text: labels.empty).transition(.opacity)
                } else {
                    Picker(labels.picker, selection: $selection.selectedName) {
                        ForEach(entries) { entry in Text(entry.title).tag(entry.name) }
                    }
                    .trainerPickerWidth(.form)
                    .disabled(!canAct)
                    HStack {
                        TrainerPrimaryActionButton(title: labels.load,
                            widthRole: .sheet,
                            systemImage: TrainerSemanticIcon.Action.load, enabled: canUseSelection) {
                            guard lifetime.accepts(presentationID), canUseSelection else { return }
                            actions.load(selection.selectedName)
                        }
                        Button(role: .destructive) {
                            guard lifetime.accepts(presentationID), canUseSelection else { return }
                            actions.delete(selection.selectedName)
                        } label: {
                            Label(localization.localized("host.delete"), systemImage: TrainerSemanticIcon.Action.remove)
                        }.disabled(!canUseSelection)
                        Spacer()
                    }
                }
            }
            .frame(minHeight: 104, alignment: .topLeading)
            .animation(TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion), value: entries.isEmpty)
            Text(error).foregroundStyle(theme.warning).fixedSize(horizontal: false, vertical: true)
                .textSelection(.enabled)
                .frame(minHeight: 18, alignment: .leading)
                .accessibilityHidden(error.isEmpty)
                .contentTransition(.opacity)
                .animation(TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion), value: error)
        } footer: {
            HStack {
                Spacer()
                Button(localization.localized("host.done")) {
                    guard lifetime.accepts(presentationID) else { return }
                    dismiss()
                }.keyboardShortcut(.cancelAction)
            }
        }
        .onChange(of: entries, initial: true) { _, _ in reconcileSelection() }
        .onChange(of: selection.savedNameToSelect) { _, _ in reconcileSelection() }
        .onAppear { lifetime.appear() }
        .onDisappear { lifetime.invalidate(); selection.invalidateSave() }
    }

    private func reconcileSelection() {
        selection.reconcile(names)
    }

    private func dismiss() {
        lifetime.invalidate()
        selection.invalidateSave()
        actions.dismiss()
    }
}
