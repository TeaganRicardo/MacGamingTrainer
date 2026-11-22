import Foundation
import TrainerCore

enum HadesPresentation {
    private static let table = TrainerModuleStringTable(moduleID: "hades", resolveArgumentKeys: true)

    static func text(
        _ key: String,
        language: TrainerPresentationLanguage,
        arguments: [String] = []
    ) -> String {
        table.string(key, language: language, arguments: arguments)
    }
}
