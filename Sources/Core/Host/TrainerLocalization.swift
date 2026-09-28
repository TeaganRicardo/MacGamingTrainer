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
    private var moduleResolvers: [String: (String, [String], TrainerPresentationLanguage) -> String] = [:]

    public init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        self.language = TrainerPresentationLanguage(rawValue: defaults.string(forKey: Self.userDefaultsKey) ?? "") ?? Self.defaultLanguage
    }

    public func localized(_ key: String, arguments: [String] = []) -> String {
        let tableURL = Bundle.standard.url(forResource: language.rawValue, withExtension: "lproj")
        let bundle = tableURL.flatMap(Bundle.init(url:)) ?? Bundle.standard
        var value = bundle.localizedString(forKey: key, value: key, table: "Host")
        for (index, argument) in arguments.enumerated().reversed() {
            value = value.replacingOccurrences(of: "{\(index)}", with: argument)
        }
        return value
    }

    /// Resolve only Host-owned presentation keys. Module/game copy stays
    /// opaque here and remains owned by the module presentation layer.
    public func presentation(_ value: String, arguments: [String] = []) -> String {
        if isModuleOwned(value) { return string(value, arguments: arguments) }
        guard value.hasPrefix("host.") else { return value }
        return localized(value, arguments: arguments)
    }

    /// Register the selected module's presentation resolver.
    ///
    /// This is a game-agnostic seam: the module supplies a closure that maps its
    /// own key namespace to text, and the Host simply re-resolves tokens when the
    /// language changes. Core stores no module vocabulary, and removing a
    /// module cannot leave stale copy behind.
    public func registerModulePresentation(
        prefix: String,
        resolver: @escaping (String, [String], TrainerPresentationLanguage) -> String
    ) {
        // A module that declares no namespace gets the protocol default of "",
        // and every key has that prefix. Registering it would send Host-owned
        // chrome through the module's resolver and replace the whole shell with
        // its own copy. An empty namespace owns nothing, so it registers
        // nothing rather than claiming everything.
        guard !prefix.isEmpty else { return }
        moduleResolvers[prefix] = resolver
    }

    public func removeModulePresentation(prefix: String) {
        moduleResolvers.removeValue(forKey: prefix)
    }

    /// Resolve one token from whichever layer owns it.
    ///
    /// Order is deliberate: an explicitly registered module resolver wins, then
    /// the shared Host table, then the key itself. An unknown key renders as
    /// its own identity so a missing entry is visible instead of blank.
    public func string(_ token: TrainerTextToken) -> String {
        string(token.key, arguments: token.arguments)
    }

    public func string(_ key: String, arguments: [String] = []) -> String {
        if let resolved = resolveModule(key, arguments: arguments) { return resolved }
        if key.hasPrefix("host.") { return localized(key, arguments: arguments) }
        // A key with no owning table and no arguments is not copy, it is a
        // defect. Showing the raw key makes that visible; a missing `{0}`
        // argument is dropped rather than rendered, because a literal "{0}" in
        // player-facing text is worse than a missing value.
        return substitute(key, arguments: arguments, dropUnfilled: true)
    }

    private func isModuleOwned(_ key: String) -> Bool {
        moduleResolvers.keys.contains { key.hasPrefix($0) }
    }

    private func resolveModule(_ key: String, arguments: [String]) -> String? {
        for (prefix, resolver) in moduleResolvers where key.hasPrefix(prefix) {
            return resolver(key, arguments, language)
        }
        return nil
    }

    private func substitute(_ template: String, arguments: [String]) -> String {
        substitute(template, arguments: arguments, dropUnfilled: false)
    }

    /// Replace `{n}` placeholders.
    ///
    /// `dropUnfilled` removes placeholders that have no argument instead of
    /// leaving them visible, which is what an unresolved key needs.
    private func substitute(_ template: String, arguments: [String], dropUnfilled: Bool) -> String {
        var result = template
        for (index, argument) in arguments.enumerated().reversed() {
            result = result.replacingOccurrences(of: "{\(index)}", with: argument)
        }
        if dropUnfilled {
            for index in stride(from: 32, through: 0, by: -1) {
                result = result.replacingOccurrences(of: "{\(index)}", with: "")
            }
        }
        return result
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
