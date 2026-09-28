import Foundation

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
/// The bundled tables are packaged through module `appResources` and load from
/// `Contents/Resources`, mirroring the Host `Host.strings` seam. The model stays
/// language-neutral: it produces `Text` values, and the presentation boundary
/// resolves them against the live Host language, so switching language
/// re-renders without a backend restart or a game reconnect.
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
    /// module, owns the observable language state.
    struct Catalog {
        private let tables: [TrainerPresentationLanguage: [String: String]]
        private let terminology: Hades2TerminologyCatalog

        init(
            tables: [TrainerPresentationLanguage: [String: String]],
            terminology: Hades2TerminologyCatalog
        ) {
            self.tables = tables
            self.terminology = terminology
        }

        func text(_ value: Text, language: TrainerPresentationLanguage) -> String {
            let template = tables[language]?[value.key] ?? value.key
            let expanded = terminology.expand(template, fallbackLanguage: language)
            let rendered = Hades2Presentation.substitute(
                expanded,
                arguments: value.arguments,
                // An argument is normally runtime text (a display name, a process
                // name). Resolve it as a key only when this catalogue owns it, so a
                // receipt can name another key without a raw value being mistaken
                // for one.
                map: { _, argument in
                    self.hasKey(argument)
                        ? self.string(argument, language: language)
                        : argument
                }
            )
            // A placeholder with no argument is a defect, and a literal "{0}" in
            // player-facing text is worse than a missing value, so drop it.
            return Hades2Presentation.dropUnfilledPlaceholders(rendered)
        }

        func string(_ key: String, language: TrainerPresentationLanguage, arguments: [String] = []) -> String {
            text(token(key, arguments: arguments), language: language)
        }

        /// True when every shipped language defines this key. A drifting table
        /// pair would otherwise leave one language showing a raw key, which the
        /// parity test and this accessor both surface.
        func hasKey(_ key: String) -> Bool {
            TrainerPresentationLanguage.allCases.allSatisfy { tables[$0]?[key] != nil }
        }

        var termKeys: [String] { terminology.termKeys }
    }

    /// Placeholder substitution, matching the `{0}` convention `Host.strings`
    /// already uses.
    ///
    /// Arguments are mapped first, which lets one argument be another key of
    /// this same catalogue: a receipt is a sentence composed from an operation
    /// key and a status key, and the module owns both halves.
    static func substitute(
        _ template: String,
        arguments: [String],
        map: (Int, String) -> String
    ) -> String {
        var result = template
        for index in arguments.indices.reversed() {
            result = result.replacingOccurrences(of: "{\(index)}", with: map(index, arguments[index]))
        }
        return result
    }

    /// Remove `{n}` placeholders that no argument filled.
    static func dropUnfilledPlaceholders(_ text: String) -> String {
        var result = text
        for index in stride(from: 32, through: 0, by: -1) {
            result = result.replacingOccurrences(of: "{\(index)}", with: "")
        }
        return result
    }

    // MARK: - Loading

    /// Resource search order. A packaged module keeps its tables in
    /// `Contents/Resources`; a source-tree build finds them beside this file.
    private static func candidateURLs(language: TrainerPresentationLanguage) -> [URL] {
        let filename = "hades2.\(language.rawValue).json"
        var urls: [URL] = []
        if let resources = Bundle.main.resourceURL {
            urls.append(resources.appendingPathComponent(filename))
        }
        urls.append(
            URL(fileURLWithPath: #filePath)
                .deletingLastPathComponent()
                .appendingPathComponent("Localization/\(filename)")
        )
        return urls
    }

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
        guard let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        return payload["entries"] as? [String: String]
    }

    private static func loadCatalog() -> Catalog {
        var tables: [TrainerPresentationLanguage: [String: String]] = [:]
        for language in TrainerPresentationLanguage.allCases {
            for url in candidateURLs(language: language)
            where FileManager.default.fileExists(atPath: url.path) {
                guard let data = try? Data(contentsOf: url),
                      let entries = decodeTable(data) else { continue }
                tables[language] = entries
                break
            }
        }
        return Catalog(tables: tables, terminology: Hades2TerminologyCatalog())
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
        var candidates: [URL] = []
        if let resources = Bundle.main.resourceURL {
            candidates.append(resources.appendingPathComponent("ui_terminology.json"))
        }
        // Source tree: Sources/Hades2/Presentation/<this file> -> repository root
        let repositoryRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // Sources/Hades2/Presentation
            .deletingLastPathComponent()   // Sources/Hades2
            .deletingLastPathComponent()   // Sources
            .deletingLastPathComponent()   // <repo>
        candidates.append(
            repositoryRoot
                .appendingPathComponent("docs/reference/hades2/1.139672-24556151/ui_terminology.json")
        )
        for url in candidates where FileManager.default.fileExists(atPath: url.path) {
            guard let data = try? Data(contentsOf: url),
                  let document = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { continue }
            return document
        }
        return [:]
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
