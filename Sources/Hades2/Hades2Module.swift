import SwiftUI
import TrainerCore

struct Hades2GameModule: TrainerGameModule {
    // Identity/protocol descriptor is generated from module.json. Presentation
    // belongs to the Swift module, not the backend manifest.
    static let presentation = TrainerGamePresentation(
        sidebarIconSystemName: "moonphase.waning.crescent"
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

    static func makeModel(services: TrainerModuleServices) -> Hades2TrainerModel {
        Hades2TrainerModel(services: services)
    }
    static func makeContent(model: Hades2TrainerModel) -> Hades2TrainerView { Hades2TrainerView(model: model) }
    static func workbenchSections(model: Hades2TrainerModel) -> [TrainerWorkbenchSectionItem] {
        Hades2WorkbenchSection.allCases.map { section in
            TrainerWorkbenchSectionItem(
                id: section.id,
                titleKey: section.titleKey,
                icon: section.icon,
                separatedFromPrevious: section == .management
            ) {
                model.showWorkbenchSection(section)
            }
        }
    }
    static func workbenchSearch(model: Hades2TrainerModel) -> TrainerWorkbenchSearchCatalog? {
        TrainerWorkbenchSearchCatalog(
            query: Binding(
                get: { model.workbenchSearch },
                set: { model.workbenchSearch = $0 }
            ),
            placeholderKey: "hades2.workbench.search",
            emptyLabelKey: "hades2.workbench.searchEmpty",
            search: { query, localization in
                Hades2WorkbenchCatalog.matches(query) { key in
                    TrainerPresentationLanguage.allCases.map {
                        localization.string(key, language: $0)
                    }
                }.map { entry in
                    TrainerWorkbenchSearchCatalog.Result(
                        id: entry.id,
                        title: localization.string(entry.titleKey),
                        detail: localization.string(entry.section.titleKey),
                        icon: entry.icon,
                        sectionID: entry.section.id,
                        onNavigate: {
                            model.showWorkbenchSection(entry.section)
                        }
                    )
                }
            }
        )
    }
    static func makeManagementCatalog(
        model: Hades2TrainerModel,
        localization: TrainerLocalizationStore,
        toolWindows: TrainerToolWindowActions
    ) -> TrainerManagementCatalog? {
        Hades2ManagementCatalog.make(
            model: model,
            localization: localization,
            openSaveEditor: {
                toolWindows.open("hades2-save-editor", localization.string("hades2.saveEditor.title")) {
                    makeSaveEditorWindow(model: model)
                }
            }
        )
    }
    static var managedBackupEditor: (@MainActor (Hades2TrainerModel, TrainerSaveSnapshot) -> TrainerToolWindowContent)? {
        { model, snapshot in
            makeSaveEditorWindow(model: model, snapshotID: snapshot.id)
        }
    }

    @MainActor
    static func makeSaveEditorWindow(model: Hades2TrainerModel, snapshotID: String? = nil) -> TrainerToolWindowContent {
        let editor = model.makeSaveEditorModel(snapshotID: snapshotID)
        return TrainerToolWindowContent(canClose: { !editor.busy }, onClose: editor.close) {
            Hades2SaveEditorView(model: editor)
        }
    }
}
