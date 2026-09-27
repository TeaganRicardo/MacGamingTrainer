import Foundation
import Combine
import SwiftUI

public enum TrainerPresentationLanguage: String, CaseIterable, Identifiable {
    case zhCN = "zh-CN"
    case en = "en"

    public var id: String { rawValue }
}

public struct TrainerLocalizedText: Hashable {
    public let zhCN: String
    public let en: String

    public init(zhCN: String, en: String) {
        self.zhCN = zhCN
        self.en = en
    }

    public func resolve(for language: TrainerPresentationLanguage) -> String {
        language == .en ? en : zhCN
    }
}

@MainActor
public final class TrainerLocalizationStore: ObservableObject {
    public static let userDefaultsKey = "presentationLanguage"
    public static let defaultLanguage: TrainerPresentationLanguage = .zhCN

    @Published public var language: TrainerPresentationLanguage {
        didSet {
            defaults.set(language.rawValue, forKey: Self.userDefaultsKey)
        }
    }

    private let defaults: UserDefaults

    public init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        self.language = TrainerPresentationLanguage(rawValue: defaults.string(forKey: Self.userDefaultsKey) ?? "") ?? Self.defaultLanguage
    }

    public func localized(_ key: String, arguments: [String] = []) -> String {
        let tableURL = Bundle.standard.url(forResource: language.rawValue, withExtension: "lproj")
        let bundle = tableURL.flatMap(Bundle.init(url:)) ?? Bundle.standard
        var value = bundle.localizedString(forKey: key, value: key, table: "Host")
        for (index, argument) in arguments.enumerated() {
            value = value.replacingOccurrences(of: "{\(index)}", with: argument)
        }
        return value
    }

    /// Resolve only Host-owned presentation keys. Module/game copy stays
    /// opaque here and remains owned by the module presentation layer.
    public func presentation(_ value: String, arguments: [String] = []) -> String {
        guard value.hasPrefix("host.") else { return value }
        return localized(value, arguments: arguments)
    }
}

private extension Bundle {
    static let standard = Bundle.main
}

struct TrainerLanguageCommands: Commands {
    @ObservedObject private var localization: TrainerLocalizationStore

    init(localization: TrainerLocalizationStore) {
        _localization = ObservedObject(wrappedValue: localization)
    }

    var body: some Commands {
        CommandMenu(localization.localized("host.language")) {
            Picker(localization.localized("host.language"), selection: $localization.language) {
                Text(localization.localized("host.language.zhCN")).tag(TrainerPresentationLanguage.zhCN)
                Text(localization.localized("host.language.en")).tag(TrainerPresentationLanguage.en)
            }
        }
    }
}
