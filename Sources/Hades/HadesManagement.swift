import SwiftUI

struct HadesSettingsProfile: Decodable, Identifiable {
    let name: String
    let updatedAt: String
    var id: String { name }
}

struct HadesDiagnosticCheck: Decodable, Identifiable {
    let name: String
    let ok: Bool
    let detail: String
    var id: String { name }
}

struct HadesManagementUtilities: View {
    @ObservedObject var model: HadesTrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerManagementActions) private var managementActions
    @Environment(\.trainerTheme) private var theme
    @Environment(\.trainerToolWindows) private var toolWindows

    private func text(_ key: String) -> String {
        HadesGameModule.resolveText(key: key, localization: localization)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: theme.sheetSpacing) {
            group("hades.manage.daily") {
                actions {
                    TrainerSecondaryActionButton(title: text("host.refreshStatus"), systemImage: HadesWorkbenchIcon.refreshStatus,
                        enabled: model.hostActionsEnabled, action: model.refreshFromHost)
                    TrainerSecondaryActionButton(title: text("hades.saveEditor.title"), systemImage: TrainerSemanticIcon.Tool.saveEditor,
                        enabled: model.hostActionsEnabled) {
                        toolWindows.open("hades-save-editor", text("hades.saveEditor.title")) {
                            HadesGameModule.makeSaveEditorWindow(model: model)
                        }
                    }
                    if let open = managementActions.openSaveManagement {
                        TrainerSecondaryActionButton(title: text("host.saveManagement"), systemImage: TrainerSemanticIcon.Tool.saveManagement,
                            enabled: model.hostActionsEnabled, action: open)
                    }
                    TrainerSecondaryActionButton(title: text("host.disableAll"), systemImage: TrainerSemanticIcon.Tool.disableAll,
                        enabled: model.hostActionsEnabled, action: model.disableAll)
                }
            }
            Divider()
            group("hades.manage.settings") {
                actions {
                    TrainerSecondaryActionButton(title: text("hades.manage.profiles"), systemImage: TrainerSemanticIcon.Tool.profiles,
                        enabled: model.hostActionsEnabled) {
                        model.profilesPresented = true
                        model.listProfiles()
                    }
                    TrainerSecondaryActionButton(title: text("host.shortcutSettings"), systemImage: TrainerSemanticIcon.Tool.shortcuts) {
                        model.shortcutSettingsPresented = true
                    }
                }
            }
            Divider()
            group("hades.manage.maintenance") {
                actions {
                    TrainerSecondaryActionButton(title: text("host.viewLog"), systemImage: TrainerSemanticIcon.Tool.log,
                        action: model.openLog)
                    TrainerSecondaryActionButton(title: text("hades.manage.diagnostics"), systemImage: TrainerSemanticIcon.Tool.diagnostics,
                        enabled: model.hostActionsEnabled) {
                        model.diagnosticsPresented = true
                        model.runDiagnostics()
                    }
                }
                actions {
                    TrainerSecondaryActionButton(title: text("host.viewLogHistory"), systemImage: TrainerSemanticIcon.Tool.logHistory,
                        action: model.openLogHistory)
                    TrainerSecondaryActionButton(title: text("host.clearCompletedLogs"), systemImage: TrainerSemanticIcon.Tool.clearLogs,
                        action: model.clearCompletedLogs)
                }
            }
            if !model.shortcutError.isEmpty {
                TrainerMessageBanner(text: text(model.shortcutError), icon: "keyboard", color: theme.warning)
            }
        }
    }

    private func group<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: theme.controlPadding) {
            Text(text(title)).font(.subheadline.weight(.semibold)).accessibilityAddTraits(.isHeader)
            content()
        }
    }

    private func actions<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: theme.controlPadding) { content() }
            VStack(alignment: .leading, spacing: theme.controlPadding) { content() }
        }
    }
}

struct HadesProfileManagerView: View {
    @ObservedObject var model: HadesTrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore

    private func text(_ key: String) -> String {
        HadesGameModule.resolveText(key: key, localization: localization)
    }

    var body: some View {
        TrainerProfileManagerView(
            labels: .init(title: text("hades.manage.profiles"), explanation: text("hades.profile.explanation"),
                name: text("hades.profile.name"), picker: text("hades.manage.profiles"),
                save: text("hades.profile.save"), load: text("hades.profile.load"), empty: text("hades.profile.empty")),
            entries: model.profiles.map { .init(name: $0.name, updatedAt: $0.updatedAt) },
            busy: model.busy, enabled: model.hostActionsEnabled,
            error: hadesManagementError(model, localization: localization),
            actions: .init(refresh: model.listProfiles, save: model.saveProfile, load: model.loadProfile,
                delete: model.deleteProfile, dismiss: { model.profilesPresented = false })
        )
    }
}

struct HadesDiagnosticsView: View {
    @ObservedObject var model: HadesTrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme

    private func text(_ key: String) -> String {
        HadesGameModule.resolveText(key: key, localization: localization)
    }

    var body: some View {
        TrainerSheetScaffold(title: text("hades.manage.diagnostics"), icon: TrainerSemanticIcon.Tool.diagnostics, width: 700) {
            Text("\(model.diagnostics.filter(\.ok).count)/\(model.diagnostics.count)").monospacedDigit()
            Button { model.exportDiagnostics() } label: {
                Label(text("hades.diagnostics.export"), systemImage: TrainerSemanticIcon.Tool.exportDiagnostics)
            }.disabled(!model.hostActionsEnabled)
            Button { model.runDiagnostics() } label: {
                Label(text("host.refresh"), systemImage: TrainerSemanticIcon.Concept.refresh)
            }.disabled(!model.hostActionsEnabled)
        } content: {
            Text(text("hades.diagnostics.explanation")).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            ScrollView {
                VStack(spacing: 8) {
                    ForEach(model.diagnostics) { check in
                        TrainerListCard {
                            HStack(alignment: .top, spacing: 12) {
                                Image(systemName: check.ok ? "checkmark.circle.fill" : "exclamationmark.circle.fill")
                                    .foregroundStyle(check.ok ? theme.success : theme.warning)
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(text(check.name)).font(.subheadline.weight(.semibold))
                                    if !check.detail.isEmpty {
                                        Text(check.detail).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                                    }
                                }
                                Spacer()
                            }
                        }
                    }
                }
            }.frame(minHeight: 260, maxHeight: 430)
            HadesManagementError(model: model)
        } footer: {
            HStack { Spacer(); Button(text("host.done")) { model.diagnosticsPresented = false } }
        }
    }
}

private struct HadesManagementError: View {
    @ObservedObject var model: HadesTrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme
    var body: some View {
        let key = model.localError.isEmpty ? model.backendStatus.error : model.localError
        if !key.isEmpty {
            Text(localization.presentation(key, arguments: model.backendStatus.errorArguments))
                .foregroundStyle(theme.warning).fixedSize(horizontal: false, vertical: true)
        }
    }
}

@MainActor
private func hadesManagementError(_ model: HadesTrainerModel, localization: TrainerLocalizationStore) -> String {
    let key = model.localError.isEmpty ? model.backendStatus.error : model.localError
    return key.isEmpty ? "" : localization.presentation(key, arguments: model.backendStatus.errorArguments)
}
