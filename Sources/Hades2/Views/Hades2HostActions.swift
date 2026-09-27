import SwiftUI

struct Hades2SidebarActions: View {
    @ObservedObject var model: Hades2TrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Button { model.shortcutSettingsPresented = true } label: {
                Label(localization.localized("host.shortcutSettings"), systemImage: "keyboard")
            }
            Button { model.openLog() } label: {
                Label(localization.localized("host.viewRuntimeLog"), systemImage: "doc.text")
            }
        }
    }
}

struct Hades2HeaderActions: View {
    @ObservedObject var model: Hades2TrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore

    var body: some View {
        Button { model.launchGame() } label: {
            Label(localization.localized("host.launchGame"), systemImage: "play.fill").padding(.horizontal, 7).padding(.vertical, 5)
        }
        .buttonStyle(.bordered)
        .disabled(model.busy || model.exiting)
    }
}


struct Hades2ManagementCommands: Commands {
    @ObservedObject var model: Hades2TrainerModel
    @ObservedObject private var localization: TrainerLocalizationStore

    init(model: Hades2TrainerModel, localization: TrainerLocalizationStore) {
        self.model = model
        _localization = ObservedObject(wrappedValue: localization)
    }

    var body: some Commands {
        CommandMenu(localization.localized("host.trainerMenu")) {
            Button(localization.localized("host.refreshStatus")) { model.refreshFromHost() }
                .disabled(model.busy)
            Button(localization.localized("host.disableAll")) { model.disableAll() }
                .disabled(model.busy || !model.connected)
            Divider()
            Button(localization.localized("host.shortcutSettings")) { model.shortcutSettingsPresented = true }
            Button(localization.localized("host.viewLog")) { model.openLog() }
        }
    }
}
