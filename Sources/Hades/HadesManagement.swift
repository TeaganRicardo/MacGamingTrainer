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
        let catalog = HadesManagementCatalog.make(model: model, localization: localization,
            openSaveEditor: {
                toolWindows.open("hades-save-editor", text("hades.saveEditor.title")) {
                    HadesGameModule.makeSaveEditorWindow(model: model)
                }
            }, openSaveManagement: managementActions.openSaveManagement)
        VStack(alignment: .leading, spacing: theme.sheetSpacing) {
            TrainerManagementGroups(groups: catalog.groups)
            if !model.shortcutError.isEmpty {
                TrainerMessageBanner(text: text(model.shortcutError), icon: "keyboard", color: theme.warning)
            }
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
            actions: .init(refresh: model.listProfiles,
                save: { name, completion in model.saveProfile(name, completion: completion) }, load: model.loadProfile,
                delete: model.deleteProfile, dismiss: { model.profilesPresented = false })
        )
    }
}

struct HadesDiagnosticsView: View {
    @ObservedObject var model: HadesTrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore

    private func text(_ key: String) -> String {
        HadesGameModule.resolveText(key: key, localization: localization)
    }

    var body: some View {
        TrainerDiagnosticsView(
            labels: .init(title: text("hades.manage.diagnostics"), explanation: text("hades.diagnostics.explanation"),
                refresh: text("host.refresh"), export: text("hades.diagnostics.export")),
            checks: model.diagnostics.map {
                .init(id: $0.id, name: text($0.name), detail: $0.detail, status: $0.ok ? .passed : .warning)
            },
            busy: model.busy, canRefresh: model.hostActionsEnabled, canExport: model.hostActionsEnabled,
            error: hadesManagementError(model, localization: localization),
            actions: .init(refresh: model.runDiagnostics, export: model.exportDiagnostics,
                dismiss: { model.diagnosticsPresented = false })
        )
    }
}

@MainActor
private func hadesManagementError(_ model: HadesTrainerModel, localization: TrainerLocalizationStore) -> String {
    let key = model.localError.isEmpty ? model.backendStatus.error : model.localError
    return key.isEmpty ? "" : localization.presentation(key, arguments: model.backendStatus.errorArguments)
}
