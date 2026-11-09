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
        TrainerManagementGroups(groups: catalog.groups)
            .trainerPanel()
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
            busy: model.busy, enabled: model.canUseBackend && model.canAcceptRuntimeAction,
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

    private var enabled: Bool { model.canUseBackend && model.canAcceptRuntimeAction }

    var body: some View {
        TrainerDiagnosticsView(
            labels: .init(title: text("hades.manage.diagnostics"), explanation: text("hades.diagnostics.explanation"),
                refresh: text("hades.diagnostics.rerun"), export: text("hades.diagnostics.export")),
            checks: model.diagnostics.map {
                .init(id: $0.id, name: text($0.name), detail: $0.detail, status: $0.ok ? .passed : .failed)
            },
            busy: model.busy, canRefresh: enabled, canExport: enabled,
            error: hadesManagementError(model, localization: localization),
            actions: .init(refresh: model.runDiagnostics, export: model.exportDiagnostics,
                dismiss: { model.diagnosticsPresented = false })
        )
    }
}

@MainActor
private func hadesManagementError(_ model: HadesTrainerModel, localization: TrainerLocalizationStore) -> String {
    let token = model.observationIssue
        ?? TrainerTextToken(key: model.backendStatus.error, arguments: model.backendStatus.errorArguments)
    return token.key.isEmpty ? "" : localization.string(token)
}
