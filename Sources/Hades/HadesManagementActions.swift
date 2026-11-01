import SwiftUI

@MainActor
enum HadesManagementCatalog {
    static func make(
        model: HadesTrainerModel, localization: TrainerLocalizationStore,
        openSaveEditor: (() -> Void)? = nil, openSaveManagement: (() -> Void)? = nil
    ) -> TrainerManagementCatalog {
        @MainActor func text(_ key: String) -> String {
            HadesGameModule.resolveText(key: key, localization: localization)
        }
        let canUseBackend = { model.hostActionsEnabled }
        return TrainerManagementCatalog(
            titles: .init(daily: text("hades.manage.daily"), settings: text("hades.manage.settings"),
                          maintenance: text("hades.manage.maintenance")),
            refresh: .init(.refreshStatus, localization: localization,
                           enabled: canUseBackend, action: model.refreshFromHost),
            // Detached Hades can still reset its durable desired settings.
            disableAll: .init(.disableAll, localization: localization,
                              enabled: canUseBackend, action: model.disableAll),
            profiles: .init(id: "profiles", title: text("hades.manage.profiles"),
                            icon: TrainerSemanticIcon.Tool.profiles, enabled: canUseBackend) {
                model.profilesPresented = true
                model.listProfiles()
            },
            shortcuts: .init(.shortcuts, localization: localization) { model.shortcutSettingsPresented = true },
            log: .init(.log, localization: localization, action: model.openLog),
            diagnostics: .init(id: "diagnostics", title: text("hades.manage.diagnostics"),
                               icon: TrainerSemanticIcon.Tool.diagnostics, enabled: canUseBackend) {
                model.diagnosticsPresented = true
                model.runDiagnostics()
            },
            logHistory: .init(.logHistory, localization: localization, action: model.openLogHistory),
            clearLogs: .init(.clearLogs, localization: localization, action: model.clearCompletedLogs),
            saveEditor: openSaveEditor.map { open in
                .init(id: "saveEditor", title: text("hades.saveEditor.title"), icon: TrainerSemanticIcon.Tool.saveEditor,
                      enabled: canUseBackend, action: open)
            },
            saveManagement: openSaveManagement.map { open in
                .init(.saveManagement, localization: localization, enabled: canUseBackend, action: open)
            }
        )
    }
}
