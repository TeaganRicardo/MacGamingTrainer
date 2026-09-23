import Foundation
import Combine

public enum TrainerPresentationLanguage: String, CaseIterable {
    case zhCN = "zh-CN"
    case en = "en"
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
}
