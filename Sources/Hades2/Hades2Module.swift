import SwiftUI

struct Hades2GameModule: TrainerGameModule {
    // Identity/protocol descriptor is generated from module.json. Presentation
    // belongs to the Swift module, not the backend manifest.
    static let presentation = TrainerGamePresentation(
        sidebarIconSystemName: "moonphase.waning.crescent",
        platformLabel: "Apple Silicon",
        headerTitle: "HADES II"
    )

    /// Hades-owned presentation namespace. The Host registers this so it can
    /// resolve Hades model tokens without Core learning any Hades vocabulary.
    static let presentationKeyPrefix = Hades2Presentation.Key.prefix

    static func presentationText(
        key: String,
        arguments: [String],
        language: TrainerPresentationLanguage
    ) -> String {
        Hades2Presentation.shared.string(key, language: language, arguments: arguments)
    }

    static func makeModel(session: TrainerBackendSession) -> Hades2TrainerModel {
        Hades2TrainerModel(session: session, logSink: TrainerLogSink(gameID: descriptor.id))
    }
    static func makeContent(model: Hades2TrainerModel) -> Hades2TrainerView { Hades2TrainerView(model: model) }
    static func makeSidebarActions(model: Hades2TrainerModel) -> Hades2SidebarActions { Hades2SidebarActions(model: model) }
    static func makeHeaderActions(model: Hades2TrainerModel) -> Hades2HeaderActions { Hades2HeaderActions(model: model) }
    static func makeManagementCommands(
        model: Hades2TrainerModel,
        localization: TrainerLocalizationStore
    ) -> Hades2ManagementCommands {
        Hades2ManagementCommands(model: model, localization: localization)
    }
}
