import SwiftUI

@MainActor
enum Hades2ManagementCatalog {
    static func make(
        model: Hades2TrainerModel, localization: TrainerLocalizationStore,
        openSaveEditor: (() -> Void)? = nil, openSaveManagement: (() -> Void)? = nil
    ) -> TrainerManagementCatalog {
        @MainActor func text(_ key: String) -> String {
            Hades2GameModule.resolveText(key: key, localization: localization)
        }
        let canUseBackend = { model.backendAvailable && model.protocolCompatible && !model.exiting }
        let canStartBackendAction = { canUseBackend() && !model.busy }
        let canChangeSignature = { canStartBackendAction() && !model.connected && model.pid == nil }
        return TrainerManagementCatalog(
            titles: .init(daily: text("hades2.manage.daily"), settings: text("hades2.manage.settings"),
                          maintenance: text("hades2.manage.maintenance")),
            refresh: .init(.refreshStatus, localization: localization,
                           enabled: canStartBackendAction, action: model.refreshFromHost),
            disableAll: .init(.disableAll, localization: localization,
                              enabled: { model.connected && canUseBackend() && model.canAcceptRuntimeAction },
                              action: model.disableAll),
            profiles: .init(id: "profiles", title: text("hades2.manage.profiles"),
                            icon: TrainerSemanticIcon.Tool.profiles, enabled: canStartBackendAction) {
                model.profilesPresented = true
                model.listProfiles()
            },
            shortcuts: .init(.shortcuts, localization: localization,
                             enabled: { !model.exiting }) { model.shortcutSettingsPresented = true },
            log: .init(.log, localization: localization, action: model.openLog),
            diagnostics: .init(id: "diagnostics", title: text("hades2.manage.diagnostics"),
                               icon: TrainerSemanticIcon.Tool.diagnostics, enabled: canStartBackendAction) {
                model.diagnosticsPresented = true
                model.runDiagnostics()
            },
            logHistory: .init(.logHistory, localization: localization, action: model.openLogHistory),
            clearLogs: .init(.clearLogs, localization: localization, action: model.clearCompletedLogs),
            saveEditor: openSaveEditor.map { open in
                .init(id: "saveEditor", title: text("hades2.saveEditor.title"), icon: TrainerSemanticIcon.Tool.saveEditor,
                      enabled: canUseBackend, action: open)
            },
            saveManagement: openSaveManagement.map { open in
                .init(.saveManagement, localization: localization, enabled: canUseBackend, action: open)
            },
            additionalMaintenance: [
                .init(id: "prepareSigning", title: text("hades2.manage.prepareSigning"),
                      icon: Hades2WorkbenchIcon.prepareSigning, enabled: canChangeSignature, action: model.prepareDebugging),
                .init(id: "restoreSigning", title: text("hades2.manage.restoreSigning"),
                      icon: Hades2WorkbenchIcon.restoreSigning, enabled: canChangeSignature, action: model.restoreOriginalSignature),
            ],
            maintenanceNote: text("hades2.manage.signatureExplanation")
        )
    }
}
