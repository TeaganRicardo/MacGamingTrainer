import SwiftUI
import AppKit

struct Hades2ProfileManagerView: View {
    @ObservedObject var model: Hades2TrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Binding var isPresented: Bool

    private func text(_ key: String) -> String {
        Hades2GameModule.resolveText(key: key, localization: localization)
    }

    var body: some View {
        TrainerProfileManagerView(
            labels: .init(title: text("hades2.manage.profiles"), explanation: text("hades2.profile.explanation"),
                name: text("hades2.profile.namePlaceholder"), picker: text("hades2.profile.picker"),
                save: text("hades2.profile.saveCurrent"), load: text("hades2.profile.load"), empty: text("hades2.profile.empty")),
            entries: model.profiles.map { .init(name: $0.name, updatedAt: $0.updatedAt) },
            busy: model.busy,
            enabled: model.backendAvailable && model.protocolCompatible && !model.exiting && model.canAcceptRuntimeAction,
            warning: model.profileShortcutWarning.map { localization.string($0) } ?? "",
            error: hades2ManagementError(model, localization: localization),
            actions: .init(refresh: model.listProfiles,
                save: { name, completion in model.saveProfile(name, completion: completion) }, load: model.loadProfile,
                delete: model.deleteProfile, dismiss: { isPresented = false })
        )
        .onDisappear { model.clearProfileShortcutWarning() }
    }
}

struct Hades2DiagnosticsView: View {
    @ObservedObject var model: Hades2TrainerModel
    @Binding var isPresented: Bool
    @EnvironmentObject private var localization: TrainerLocalizationStore

    private func text(_ key: String) -> String {
        Hades2GameModule.resolveText(key: key, localization: localization)
    }

    private var enabled: Bool {
        model.backendAvailable && model.protocolCompatible && !model.exiting && model.canAcceptRuntimeAction
    }

    var body: some View {
        TrainerDiagnosticsView(
            labels: .init(title: text("hades2.diagnostics.title"), explanation: text("hades2.diagnostics.explanation"),
                refresh: text("hades2.diagnostics.rerun"), export: text("hades2.diagnostics.export")),
            checks: model.diagnostics.map {
                .init(id: $0.id, name: $0.name, detail: $0.detail, status: $0.ok ? .passed : .failed)
            },
            busy: model.busy, canRefresh: enabled, canExport: enabled,
            error: hades2ManagementError(model, localization: localization),
            actions: .init(refresh: model.runDiagnostics, export: model.exportDiagnostics,
                dismiss: { isPresented = false })
        )
    }
}

struct Hades2ShortcutSettingsView: View {
    @ObservedObject var model: Hades2TrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore

    var body: some View {
        TrainerShortcutSettingsView(
            isPresented: $model.shortcutSettingsPresented,
            entries: Hades2WorkbenchCatalog.orderedShortcutActions.map { action in
                TrainerShortcutSettingsEntry(
                    id: action.rawValue,
                    title: Hades2GameModule.resolveText(key: action.presentationKey, localization: localization),
                    icon: action.icon,
                    chordText: model.shortcutText(action),
                    isEditable: action != .disableAll
                )
            },
            registrationFailure: model.shortcutRegistrationFailure,
            onAssign: { actionID, chord in
                guard let action = ShortcutAction(rawValue: actionID) else {
                    return .rejected(messageKey: "host.hotkeys.unrecognized")
                }
                return model.setShortcut(action: action, chord: chord)
            }
        )
    }
}

struct Hades2ManagementUtilities: View {
    @ObservedObject var model: Hades2TrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerManagementActions) private var managementActions
    let openSaveEditor: () -> Void

    var body: some View {
        let catalog = Hades2ManagementCatalog.make(model: model, localization: localization,
            openSaveEditor: openSaveEditor, openSaveManagement: managementActions.openSaveManagement)
        TrainerManagementGroups(groups: catalog.groups)
            .trainerPanel()
    }
}

@MainActor
private func hades2ManagementError(_ model: Hades2TrainerModel, localization: TrainerLocalizationStore) -> String {
    let token = model.errorText.key.isEmpty ? model.backendErrorText : model.errorText
    return token.key.isEmpty ? "" : localization.string(token)
}
