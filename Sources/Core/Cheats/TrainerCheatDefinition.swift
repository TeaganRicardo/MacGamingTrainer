import Foundation

package enum TrainerCheatKind: String, Codable, CaseIterable, Equatable, Hashable, Sendable {
    case toggle
    case value
    case lock
    case oneShot = "one_shot"
}

package struct TrainerCheatText: Equatable, Hashable, Sendable {
    package let zhCN: String
    package let en: String

    package init(zhCN: String, en: String) {
        self.zhCN = zhCN
        self.en = en
    }

    package func resolve(languageCode: String) -> String {
        languageCode == "en" ? en : zhCN
    }
}

package enum TrainerCheatLabel: Equatable, Hashable, Sendable {
    case key(String)
    case bilingual(TrainerCheatText)

    package var rawKey: String? {
        guard case .key(let value) = self else { return nil }
        return value
    }
}

package struct TrainerCheatActionSpec: Equatable, Hashable, Sendable {
    package let command: String
    package let secondaryCommand: String?
    package let valueParam: String?

    package init(
        command: String,
        secondaryCommand: String? = nil,
        valueParam: String? = nil
    ) {
        self.command = command
        self.secondaryCommand = secondaryCommand
        self.valueParam = valueParam
    }
}

package struct TrainerCheatDefinition: Identifiable, Equatable, Hashable, Sendable {
    package let id: String
    package let kind: TrainerCheatKind
    package let label: TrainerCheatLabel
    package let help: TrainerCheatLabel?
    package let icon: String
    package let action: TrainerCheatActionSpec
    package let shortcutID: String?
    package let aliases: [String]

    package init(
        id: String,
        kind: TrainerCheatKind,
        label: TrainerCheatLabel,
        help: TrainerCheatLabel? = nil,
        icon: String,
        action: TrainerCheatActionSpec,
        shortcutID: String? = nil,
        aliases: [String] = []
    ) {
        self.id = id
        self.kind = kind
        self.label = label
        self.help = help
        self.icon = icon
        self.action = action
        self.shortcutID = shortcutID
        self.aliases = aliases
    }
}

package enum TrainerCheatCatalogError: Error, Equatable, CustomStringConvertible {
    case emptyID
    case duplicateID(String)
    case emptyLabel(String)
    case emptyCommand(String)
    case emptyShortcutID(String)
    case duplicateShortcutID(String)
    case invalidAlias(cheatID: String, alias: String)
    case duplicateAlias(String)
    case aliasCollidesWithCanonicalID(String)
    case retiredIDCollision(String)

    package var description: String {
        switch self {
        case .emptyID:
            return "Cheat definition id cannot be empty"
        case .duplicateID(let id):
            return "Duplicate cheat definition id: \(id)"
        case .emptyLabel(let id):
            return "Empty label for cheat definition: \(id)"
        case .emptyCommand(let id):
            return "Empty backend command for cheat definition: \(id)"
        case .emptyShortcutID(let id):
            return "Empty shortcutID for cheat definition: \(id)"
        case .duplicateShortcutID(let shortcutID):
            return "Duplicate cheat shortcutID: \(shortcutID)"
        case .invalidAlias(let cheatID, let alias):
            return "Invalid alias '\(alias)' for cheat '\(cheatID)'"
        case .duplicateAlias(let alias):
            return "Duplicate cheat alias: \(alias)"
        case .aliasCollidesWithCanonicalID(let alias):
            return "Cheat alias '\(alias)' collides with a canonical cheat id"
        case .retiredIDCollision(let id):
            return "Retired id '\(id)' cannot match an active cheat id or alias"
        }
    }
}

package struct TrainerCheatCatalog: Equatable, Sendable {
    package let definitions: [TrainerCheatDefinition]
    package let retiredIDs: Set<String>

    private let byID: [String: TrainerCheatDefinition]
    private let aliasToCanonicalID: [String: String]
    private let shortcutLookup: [String: TrainerCheatDefinition]

    package init(
        definitions: [TrainerCheatDefinition],
        retiredIDs: Set<String> = []
    ) {
        self.definitions = definitions
        self.retiredIDs = retiredIDs

        var mappedIDs: [String: TrainerCheatDefinition] = [:]
        var mappedAliases: [String: String] = [:]
        var mappedShortcuts: [String: TrainerCheatDefinition] = [:]

        for definition in definitions {
            if mappedIDs[definition.id] == nil {
                mappedIDs[definition.id] = definition
            }
            if let shortcutID = definition.shortcutID, mappedShortcuts[shortcutID] == nil {
                mappedShortcuts[shortcutID] = definition
            }
        }
        for definition in definitions {
            for alias in definition.aliases where mappedIDs[alias] == nil && mappedAliases[alias] == nil {
                mappedAliases[alias] = definition.id
            }
        }

        self.byID = mappedIDs
        self.aliasToCanonicalID = mappedAliases
        self.shortcutLookup = mappedShortcuts
    }

    package static func validated(
        definitions: [TrainerCheatDefinition],
        retiredIDs: Set<String> = []
    ) throws -> TrainerCheatCatalog {
        let issues = validationErrors(definitions: definitions, retiredIDs: retiredIDs)
        if let first = issues.first {
            throw first
        }
        return TrainerCheatCatalog(definitions: definitions, retiredIDs: retiredIDs)
    }

    package func validationErrors() -> [TrainerCheatCatalogError] {
        Self.validationErrors(definitions: definitions, retiredIDs: retiredIDs)
    }

    package static func validationErrors(
        definitions: [TrainerCheatDefinition],
        retiredIDs: Set<String> = []
    ) -> [TrainerCheatCatalogError] {
        var errors: [TrainerCheatCatalogError] = []
        var canonicalIDs = Set<String>()
        var shortcutIDs = Set<String>()
        var seenAliases = Set<String>()

        for definition in definitions {
            let trimmedID = definition.id.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmedID.isEmpty {
                errors.append(.emptyID)
            } else if !canonicalIDs.insert(definition.id).inserted {
                errors.append(.duplicateID(definition.id))
            }

            if retiredIDs.contains(definition.id) {
                errors.append(.retiredIDCollision(definition.id))
            }

            switch definition.label {
            case .key(let key):
                if key.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    errors.append(.emptyLabel(definition.id))
                }
            case .bilingual(let text):
                if text.zhCN.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    || text.en.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    errors.append(.emptyLabel(definition.id))
                }
            }

            if definition.action.command.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                errors.append(.emptyCommand(definition.id))
            }

            if let shortcutID = definition.shortcutID {
                if shortcutID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    errors.append(.emptyShortcutID(definition.id))
                } else if !shortcutIDs.insert(shortcutID).inserted {
                    errors.append(.duplicateShortcutID(shortcutID))
                }
            }
        }

        for definition in definitions {
            var localAliases = Set<String>()
            for alias in definition.aliases {
                let trimmed = alias.trimmingCharacters(in: .whitespacesAndNewlines)
                if trimmed.isEmpty || alias == definition.id || !localAliases.insert(alias).inserted {
                    errors.append(.invalidAlias(cheatID: definition.id, alias: alias))
                    continue
                }
                if canonicalIDs.contains(alias) {
                    errors.append(.aliasCollidesWithCanonicalID(alias))
                } else if retiredIDs.contains(alias) {
                    errors.append(.retiredIDCollision(alias))
                } else if !seenAliases.insert(alias).inserted {
                    errors.append(.duplicateAlias(alias))
                }
            }
        }

        return errors
    }

    package func definition(id: String) -> TrainerCheatDefinition? {
        guard let canonical = resolveID(id) else { return nil }
        return byID[canonical]
    }

    package func definitions(ofKind kind: TrainerCheatKind) -> [TrainerCheatDefinition] {
        definitions.filter { $0.kind == kind }
    }

    package func resolveID(_ id: String) -> String? {
        if byID[id] != nil { return id }
        return aliasToCanonicalID[id]
    }

    package func resolveShortcutID(_ actionID: String) -> String? {
        if shortcutLookup[actionID] != nil { return actionID }
        guard let canonicalCheat = aliasToCanonicalID[actionID] else { return nil }
        return byID[canonicalCheat]?.shortcutID
    }

    package func legacyAliasMap() -> [String: String] {
        aliasToCanonicalID
    }
}
