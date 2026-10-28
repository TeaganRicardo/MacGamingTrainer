import Foundation

enum HadesFeature: String, CaseIterable, Identifiable {
    case invincibility, fullHealth, moneyNoDecrease, rerollsNoDecrease, fullGodGauge, infiniteAmmo, forceRerolls, boonRarityEnabled, gameSpeed
    case damageMultiplier, incomingDamageMultiplier, moveSpeedMultiplier, attackSpeedMultiplier, dashBonus

    var id: String { rawValue }
    var key: String { self == .gameSpeed ? "host.timeWarp.title" : "hades.\(rawValue)" }
    var isToggle: Bool {
        switch self {
        case .invincibility, .fullHealth, .moneyNoDecrease, .rerollsNoDecrease,
             .fullGodGauge, .infiniteAmmo, .forceRerolls, .boonRarityEnabled: true
        default: false
        }
    }
    var helpKey: String {
        switch self {
        case .fullGodGauge: "hades.fullGodGaugeHelp"
        case .invincibility: "hades.invincibilityHelp"
        case .boonRarityEnabled: "hades.boonRarityHelp"
        case .forceRerolls: "hades.forceRerollsHelp"
        case .infiniteAmmo: "hades.infiniteAmmoHelp"
        case .fullHealth: "hades.fullHealthHelp"
        default: "hades.noConsumptionHelp"
        }
    }
    var neutralValue: Double { self == .dashBonus ? 0 : 1 }
    var icon: String {
        switch self {
        case .invincibility: return "shield.fill"
        case .fullHealth: return "heart.fill"
        case .infiniteAmmo: return "infinity"
        case .forceRerolls: return "dice.fill"
        case .incomingDamageMultiplier: return "shield.lefthalf.filled"
        case .moneyNoDecrease: return "circle.fill"
        case .rerollsNoDecrease: return "arrow.triangle.2.circlepath"
        case .fullGodGauge: return "bolt.heart.fill"
        case .boonRarityEnabled: return "sparkles"
        case .gameSpeed: return "speedometer"
        case .damageMultiplier: return "burst.fill"
        case .moveSpeedMultiplier: return "figure.run"
        case .attackSpeedMultiplier: return "bolt.fill"
        case .dashBonus: return "wind"
        }
    }
}

enum HadesFeatureValue: Decodable, Equatable {
    case boolean(Bool), number(Double)
    case gameSpeed(desired: Double, actual: Double?, active: Bool?,
                   errorPresentation: String?, errorArguments: [String])

    private enum Keys: String, CodingKey {
        case desired, actual, active, errorPresentation, errorArguments
    }

    init(from decoder: Decoder) throws {
        if let container = try? decoder.container(keyedBy: Keys.self),
           let desired = try? container.decode(Double.self, forKey: .desired) {
            let actual = try container.decodeIfPresent(Double.self, forKey: .actual)
            let active = try container.decodeIfPresent(Bool.self, forKey: .active)
            let error = try container.decodeIfPresent(String.self, forKey: .errorPresentation)
            let arguments = try container.decodeIfPresent([String].self, forKey: .errorArguments) ?? []
            self = .gameSpeed(desired: desired, actual: actual, active: active,
                              errorPresentation: error, errorArguments: arguments)
            return
        }
        let value = try decoder.singleValueContainer()
        if let boolean = try? value.decode(Bool.self) { self = .boolean(boolean) }
        else { self = .number(try value.decode(Double.self)) }
    }

    var bool: Bool {
        switch self {
        case let .boolean(value): return value
        case let .gameSpeed(_, _, active, _, _): return active ?? false
        case .number(_): return false
        }
    }

    var number: Double? {
        switch self {
        case let .number(value): return value
        case let .gameSpeed(desired, _, _, _, _): return desired
        case .boolean(_): return nil
        }
    }

    var actualNumber: Double? {
        if case let .gameSpeed(_, actual, _, _, _) = self { return actual }
        return nil
    }

    var errorPresentation: String? {
        if case let .gameSpeed(_, _, _, error, _) = self { return error }
        return nil
    }

    var errorArguments: [String] {
        if case let .gameSpeed(_, _, _, _, arguments) = self { return arguments }
        return []
    }
}

struct HadesHeroTarget: Decodable, Equatable {
    let heroId: String
    var payload: [String: Any] { ["heroId": heroId] }
}

struct HadesCurrentTrait: Decodable, Identifiable, Equatable {
    let instanceId: String
    let name: String
    let rarity: String
    let level: Int
    let canEdit: Bool
    let canRemove: Bool
    let limitation: String
    var remainingUses: Int? = nil
    var canSetUses: Bool? = nil
    var canExpire: Bool? = nil
    var canRefresh: Bool? = nil
    var cooldown: Double? = nil
    var cooldownLimit: Double? = nil
    var blessing: String? = nil
    var curse: String? = nil
    var id: String { instanceId }
}

struct HadesWorldReward: Decodable, Identifiable {
    let id: String
    let kind: String
    let names: [String: String]
    let doorAllowed: Bool
    func name(language: TrainerPresentationLanguage) -> String {
        names[language.rawValue] ?? names["en"] ?? id
    }
}

struct HadesWorldDoor: Decodable, Identifiable, Equatable {
    let id: String
    let number: Int
    let reward: String
    let canReward: Bool
    let routes: [String]
    let canRestore: Bool
    let pendingEncounter: Bool
}

struct HadesWorldObservation: Decodable, Equatable {
    let roomId: String
    let doors: [HadesWorldDoor]
    let canFish: Bool
    let canChaos: Bool
    let objects: [String]
}

struct HadesObservation: Decodable {
    let connected: Bool
    let pid: Int32?
    let heroReady: Bool
    let invincible: Bool?
    let health: Double?
    let maxHealth: Double?
    let money: Double?
    let rerolls: Double?
    let godGauge: Double?
    let maxGodGauge: Double?
    let target: HadesHeroTarget?
    let features: [String: HadesFeatureValue]?
    let activeFeatures: [String: Bool]?
    let resources: [String: Double]?
    let traits: [HadesCurrentTrait]?
    let world: HadesWorldObservation?
}

struct HadesCatalogEntry: Decodable, Identifiable, Equatable {
    let id: String
    let kind: String
    let names: [String: String]
    let descriptions: [String: String]
    let sourceNames: [String: String]?
    let rarities: [String]
    let supportsLevel: Bool
    let acquirable: Bool?

    func name(language: String) -> String { names[language] ?? names["en"] ?? id }
    func description(language: String) -> String { descriptions[language] ?? descriptions["en"] ?? "" }
    func source(language: String) -> String { sourceNames?[language] ?? sourceNames?["en"] ?? "" }
    func matches(_ query: String) -> Bool {
        let values = [id] + Array(names.values) + Array(descriptions.values) + Array((sourceNames ?? [:]).values)
        let text = values.joined(separator: " ").lowercased()
        return query.lowercased().split(whereSeparator: \.isWhitespace).allSatisfy { text.contains($0) }
    }
}

struct HadesResourceDefinition: Decodable, Identifiable, Equatable {
    let id: String
    let names: [String: String]
    func name(language: String) -> String { names[language] ?? names["en"] ?? id }
}

struct HadesCatalogPayload: Decodable {
    let catalog: [HadesCatalogEntry]
    let resourceCatalog: [HadesResourceDefinition]
    let traitNames: [String: [String: String]]?
    let worldRewards: [HadesWorldReward]?
    let worldTerms: [String: [String: String]]?
}

struct HadesNumberDraft {
    private(set) var text: String
    private(set) var editing = false
    private(set) var target: HadesHeroTarget?

    init(value: Double) { text = Self.format(value) }
    mutating func begin(target: HadesHeroTarget?) { editing = true; self.target = target }
    mutating func observe(_ value: Double) { if !editing { text = Self.format(value) } }
    mutating func update(_ text: String) { self.text = text }
    mutating func end() { editing = false }
    static func format(_ value: Double) -> String {
        value.rounded() == value ? String(format: "%.0f", value) : String(format: "%.3g", value)
    }
}

enum HadesShortcutAction: String, CaseIterable, Identifiable {
    case invincibility, heal, fullHealth, moneyNoDecrease, rerollsNoDecrease, fullGodGauge, infiniteAmmo, forceRerolls, boonRarityEnabled, generateFishing, generateChaosGate, disableAll
    var id: String { rawValue }
    var key: String { self == .disableAll ? "host.disableAll" : "hades.\(rawValue)" }
    var defaultChord: HotkeyChord {
        HotkeyChord.defaultShortcut(index: HadesWorkbenchCatalog.orderedShortcutActions.firstIndex(of: self)!)!
    }
}

struct HadesShortcutStore {
    private let defaults: UserDefaults
    private(set) var overrides: [HadesShortcutAction: HotkeyChord] = [:]
    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        for action in HadesShortcutAction.allCases {
            if let payload = defaults.object(forKey: "hades.shortcut.\(action.rawValue)"),
               let chord = HotkeyChord(payload: payload) {
                overrides[action] = chord
            }
        }
    }
    func chord(_ action: HadesShortcutAction) -> HotkeyChord { overrides[action] ?? action.defaultChord }
    mutating func set(_ action: HadesShortcutAction, chord proposed: HotkeyChord) -> HadesShortcutAction? {
        if let conflict = HadesShortcutAction.allCases.first(where: { $0 != action && chord($0).keyCode == proposed.keyCode && chord($0).modifiers == proposed.modifiers }) { return conflict }
        overrides[action] = proposed
        defaults.set(proposed.payload, forKey: "hades.shortcut.\(action.rawValue)")
        return nil
    }
    mutating func reset() {
        for action in HadesShortcutAction.allCases { defaults.removeObject(forKey: "hades.shortcut.\(action.rawValue)") }
        overrides = [:]
    }
}
