import Foundation
import TrainerCore

/// Hades-owned bilingual presentation.
///
/// Two rules keep this layer game-local instead of a second Host table:
///
/// 1. Host/Core never gains a Hades terminology API. Host keys stay on
///    `TrainerLocalizationStore`; module text stays here.
/// 2. Native game vocabulary is not retyped. `{term:<registry key>}`
///    placeholders resolve through the authoritative terminology registry that
///    `Backend/games/hades2/terminology.py` also validates, so one native label
///    keeps one identity and one target-build provenance.
///
/// The bundled tables are packaged through module `appResources` under
/// `Contents/Resources/Modules/hades2/`, mirroring the Host `Host.strings` seam.
/// The model stays language-neutral: it produces `Text` values, and the
/// presentation boundary resolves them against the live Host language, so
/// switching language re-renders without a backend restart or a game reconnect.
enum Hades2Presentation {
    enum Key {
        static let prefix = "hades2."

        /// Surfaces an unnamespaced key in debug builds instead of shipping one
        /// that silently bypasses this catalogue.
        static func validate(_ key: String) -> String {
            assert(key.hasPrefix(prefix), "Hades presentation keys must be namespaced: \(key)")
            return key
        }
    }

    /// A module-owned presentation token.
    ///
    /// This is the Core `TrainerTextToken` type rather than a second one: the
    /// Host renders these tokens, so Core owns their shape. The module owns only
    /// the resolver that turns a key into wording.
    typealias Text = TrainerTextToken

    /// Builds a module-owned token, asserting the key namespace.
    static func token(_ key: String, arguments: [String] = []) -> Text {
        Text(key: Key.validate(key), arguments: arguments)
    }

    /// Resolves keys against a Host language. The catalogue holds only immutable
    /// tables; the language is supplied per call because the Host store, not this
    /// Read-only bilingual table + terminology expander. `Localization` inside
    /// `TrainerHost`, not this module, owns the observable language state.
    struct Catalog {
        private let stringTable: TrainerModuleStringTable
        private let terminology: Hades2TerminologyCatalog

        init(
            tables: [TrainerPresentationLanguage: [String: String]],
            terminology: Hades2TerminologyCatalog
        ) {
            self.terminology = terminology
            self.stringTable = TrainerModuleStringTable(
                tables: tables,
                resolveArgumentKeys: true,
                transform: { template, language in
                    terminology.expand(template, fallbackLanguage: language)
                }
            )
        }

        fileprivate init(
            moduleID: String,
            terminology: Hades2TerminologyCatalog
        ) {
            self.terminology = terminology
            self.stringTable = TrainerModuleStringTable(
                moduleID: moduleID,
                resolveArgumentKeys: true,
                transform: { template, language in
                    terminology.expand(template, fallbackLanguage: language)
                }
            )
        }

        func text(_ value: Text, language: TrainerPresentationLanguage) -> String {
            stringTable.string(value.key, language: language, arguments: value.arguments)
        }

        func string(_ key: String, language: TrainerPresentationLanguage, arguments: [String] = []) -> String {
            stringTable.string(key, language: language, arguments: arguments)
        }

        /// True when every shipped language defines this key. A drifting table
        /// pair would otherwise leave one language showing a raw key, which the
        /// parity test and this accessor both surface.
        func hasKey(_ key: String) -> Bool {
            stringTable.hasKey(key)
        }

        var termKeys: [String] { terminology.termKeys }
    }

    static func substitute(
        _ template: String,
        arguments: [String],
        map: (Int, String) -> String
    ) -> String {
        TrainerModuleStringTable.substitute(template, arguments: arguments, map: map)
    }

    static func dropUnfilledPlaceholders(_ text: String) -> String {
        TrainerModuleStringTable.dropUnfilledPlaceholders(text)
    }

    // MARK: - Loading

    private static let catalog: Catalog = loadCatalog()

    /// Process-wide catalogue. Loading happens once; switching language is a
    /// lookup change rather than a reload.
    static var shared: Catalog { catalog }

    /// Test seam: build a catalogue directly from decoded tables.
    static func makeCatalog(
        tables: [TrainerPresentationLanguage: [String: String]],
        terminology: Hades2TerminologyCatalog
    ) -> Catalog {
        Catalog(tables: tables, terminology: terminology)
    }

    static func decodeTable(_ data: Data) -> [String: String]? {
        TrainerModuleStringTable.decodeTable(data)
    }

    private static func loadCatalog() -> Catalog {
        Catalog(moduleID: "hades2", terminology: Hades2TerminologyCatalog())
    }
}

/// Target-build terminology values consumed by the Hades presentation tables.
///
/// The registry packaged as `ui_terminology.json` is the same evidence the
/// Python `TerminologyRegistry` validates, so native and Trainer-owned labels
/// keep one governed identity instead of the Swift layer inventing a second
/// table. Only user-facing groups are readable: internal domain terms and
/// compatibility aliases are forbidden on these surfaces, so they are not
/// resolvable from presentation at all.
struct Hades2TerminologyCatalog {
    private let values: [String: [TrainerPresentationLanguage: String]]

    init(reference: [String: Any]? = nil) {
        let document = reference ?? Hades2TerminologyCatalog.loadReference()
        var values: [String: [TrainerPresentationLanguage: String]] = [:]
        for group in Self.userFacingGroups {
            guard let rows = document[group] as? [String: Any] else { continue }
            for (key, row) in rows {
                guard let fields = row as? [String: Any] else { continue }
                let zh = fields["value"] as? String
                let en = fields["englishValue"] as? String
                values["\(group).\(key)"] = [
                    .zhCN: zh ?? "",
                    .en: en ?? zh ?? "",
                ]
            }
        }
        self.values = values
    }

    /// `internalTerms` and `compatibilityAliases` are intentionally excluded.
    static let userFacingGroups = [
        "officialTerms",
        "nativeChoiceTitles",
        "officialSourceNames",
        "productTerms",
    ]

    private static func loadReference() -> [String: Any] {
        TrainerModuleResources.jsonObject(moduleID: "hades2", relativePath: "ui_terminology.json") ?? [:]
    }

    /// Expands `{term:<registry key>}` placeholders.
    ///
    /// An unresolvable placeholder stays visible rather than being dropped: an
    /// untranslated label is a visible defect, whereas a silently empty one
    /// would hide the missing registry entry.
    func expand(_ template: String, fallbackLanguage: TrainerPresentationLanguage) -> String {
        guard template.contains("{term:") else { return template }
        var result = template
        for (key, languages) in values {
            let preferred = languages[fallbackLanguage] ?? ""
            let value = preferred.isEmpty ? (languages[.zhCN] ?? "") : preferred
            guard !value.isEmpty else { continue }
            result = result.replacingOccurrences(of: "{term:\(key)}", with: value)
        }
        return result
    }

    func value(forTerm key: String, language: TrainerPresentationLanguage) -> String? {
        values[key]?[language]
    }

    var termKeys: [String] { values.keys.sorted() }
}
