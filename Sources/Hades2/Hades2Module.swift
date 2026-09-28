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

    /// Resolve a key that may belong to either owner.
    ///
    /// A module-hosted shell action (Disable All) deliberately keeps its Host key
    /// and Host resource, so `hades2.`-prefixed copy comes from the module
    /// catalogue and every other key comes from the Host table. Without this
    /// split a Host key is looked up in the Hades catalogue, misses, and renders
    /// as its own raw name.
    @MainActor
    static func resolveText(
        key: String,
        arguments: [String] = [],
        localization: TrainerLocalizationStore
    ) -> String {
        guard key.hasPrefix(Hades2Presentation.Key.prefix) else {
            return localization.string(key, arguments: arguments)
        }
        return Hades2Presentation.shared.string(
            key,
            language: localization.language,
            arguments: arguments
        )
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
