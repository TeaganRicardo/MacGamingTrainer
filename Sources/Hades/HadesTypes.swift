import Foundation
import TrainerCore

enum HadesFeature: String, CaseIterable, Identifiable {
    case invincibility, infiniteHealth, infiniteMoney, infiniteRerolls, fullGodGauge, infiniteAmmo, forceEnableRerolls, boonRarityEnabled, moneyMultiplierEnabled, resourceMultiplierEnabled, gameSpeed
    case damageMultiplier, incomingDamageMultiplier, moveSpeedMultiplier, attackSpeedMultiplier, dashBonus, moneyMultiplier, resourceMultiplier

    var id: String { rawValue }
    var cheatDefinition: TrainerCheatDefinition { HadesCheatCatalog.definition(id: rawValue)! }
    var key: String { cheatDefinition.label.rawKey ?? "hades.\(rawValue)" }
    var isToggle: Bool { cheatDefinition.kind == .toggle }
    var helpKey: String { cheatDefinition.help?.rawKey ?? "hades.noConsumptionHelp" }
    var neutralValue: Double {
        switch self {
        case .dashBonus: return 0
        case .moneyMultiplier, .resourceMultiplier: return 2
        default: return 1
        }
    }
}

/// Only the exact-acquisition workbench may set this session state.
enum HadesAcquisitionTarget: String, Equatable {
    case exact
    case chaos
}

/// A live hero value the runtime observes and edits through `set_value`.
enum HadesHeroValue: String {
    case health, maxHealth, money, rerolls, godGauge
}

/// One completed text edit and the owner it applies to.
enum HadesTextEdit {
    case value(HadesHeroValue)
    case resource(String)
    case feature(HadesFeature)
    case fishingChance
    case chaosGateChance
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

    func gameSpeedIntent(preservingRuntimeFrom current: Self? = nil) -> Self? {
        guard case let .gameSpeed(desired, _, _, _, _) = self else { return nil }
        if case let .gameSpeed(_, actual, active, error, arguments) = current {
            return .gameSpeed(desired: desired, actual: actual, active: active,
                              errorPresentation: error, errorArguments: arguments)
        }
        return .gameSpeed(desired: desired, actual: nil, active: nil, errorPresentation: nil, errorArguments: [])
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
    var hasContextualControls: Bool {
        remainingUses != nil || canRefresh == true || canExpire == true
    }
}

/// The Generate row a reward belongs to. The world catalog classifies each
/// reward as Hades II's resident catalog does.
enum HadesRewardGroup: String, Decodable, CaseIterable {
    case olympian, pickup, special

    /// The shortcut that generates this row's shown selection.
    var shortcut: HadesShortcutAction {
        switch self {
        case .olympian: .spawnOlympian
        case .pickup: .spawnPickup
        case .special: .spawnSpecial
        }
    }
}

struct HadesWorldReward: Decodable, Identifiable {
    let id: String
    let kind: String
    let names: [String: String]
    let doorAllowed: Bool
    let group: HadesRewardGroup
    /// Section identity inside its Generate row, in catalog order.
    let section: String
    /// The section's native title where the game names it.
    let sectionNames: [String: String]?
    func name(language: TrainerPresentationLanguage) -> String {
        names[language.rawValue] ?? names["en"] ?? id
    }
    /// Language-first label matching Hades II's exactItemLabel: English UI
    /// shows English only, while Chinese UI pairs "中文 · English".
    func label(for language: TrainerPresentationLanguage) -> String {
        if language == .en {
            return names["en"] ?? names["zh-CN"] ?? id
        }
        guard let primary = names["zh-CN"], !primary.isEmpty else {
            return names["en"] ?? id
        }
        if let english = names["en"], !english.isEmpty, english != primary {
            return "\(primary) · \(english)"
        }
        return primary
    }
}

struct HadesWorldActionTarget: Decodable, Equatable {
    let kind: String
    let id: String
    let enabled: Bool
    let reason: String?
    let warning: String?
    let acceptsReward: Bool

    private enum CodingKeys: String, CodingKey {
        case kind, id, enabled, reason, warning, acceptsReward
    }

    init(kind: String, id: String, enabled: Bool = true, reason: String? = nil,
         warning: String? = nil, acceptsReward: Bool = false) {
        self.kind = kind
        self.id = id
        self.enabled = enabled
        self.reason = reason
        self.warning = warning
        self.acceptsReward = acceptsReward
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        kind = try container.decode(String.self, forKey: .kind)
        id = try container.decode(String.self, forKey: .id)
        enabled = try container.decodeIfPresent(Bool.self, forKey: .enabled) ?? true
        reason = try container.decodeIfPresent(String.self, forKey: .reason)
        warning = try container.decodeIfPresent(String.self, forKey: .warning)
        acceptsReward = try container.decodeIfPresent(Bool.self, forKey: .acceptsReward) ?? false
    }

    var stableID: String { kind + ":" + id }
    var isRoom: Bool { kind == "roomCategory" }
}

struct HadesWorldExitChoice: Equatable {
    let room: String
    let reward: String?

    init(room: String, reward: String? = nil) {
        self.room = room
        self.reward = reward
    }

    init?(id: String) {
        let parts = id.split(separator: ">", maxSplits: 1, omittingEmptySubsequences: false)
        guard let room = parts.first, !room.isEmpty else { return nil }
        if parts.count == 2 {
            guard !parts[1].isEmpty else { return nil }
            self.init(room: String(room), reward: String(parts[1]))
        } else {
            self.init(room: String(room))
        }
    }

    var id: String { reward.map { room + ">" + $0 } ?? room }
}

struct HadesWorldActionLease: Decodable, Equatable {
    let room: String
    let reward: String?
    let leaseToken: String

    var choice: HadesWorldExitChoice { HadesWorldExitChoice(room: room, reward: reward) }
}

struct HadesWorldOccurrenceTarget: Decodable, Identifiable, Equatable {
    let id: String
    let kind: String
    let sourceId: String
}

struct HadesWorldOccurrenceLease: Decodable, Equatable {
    let target: String
    let leaseToken: String
}

struct HadesWorldDoor: Decodable, Identifiable, Equatable {
    let id: String
    let doorToken: String?
    let number: Int
    let roomName: String?
    let roomKind: String?
    let reward: String
    let rewardWarning: String?
    let targets: [HadesWorldActionTarget]?
    let activeLease: HadesWorldActionLease?

    var effectiveDoorToken: String { doorToken ?? id }
    var effectiveRoomKind: String { roomKind ?? "" }
    var worldActionTargets: [HadesWorldActionTarget] { targets ?? [] }
    var roomTargets: [HadesWorldActionTarget] { worldActionTargets.filter(\.isRoom) }
    var rewardTargets: [HadesWorldActionTarget] { worldActionTargets.filter { $0.kind == "reward" } }

    func isCurrentRoom(_ room: String) -> Bool {
        room == "current" || room == roomName || (!effectiveRoomKind.isEmpty && room == effectiveRoomKind)
    }

    func offersAnyReward(_ room: HadesWorldActionTarget) -> Bool {
        room.acceptsReward && room.id != "current"
    }

    func isEnabled(_ choice: HadesWorldExitChoice) -> Bool {
        guard let room = roomTargets.first(where: { $0.id == choice.room }), room.enabled else { return false }
        guard let reward = choice.reward else { return !room.acceptsReward || offersAnyReward(room) }
        return room.acceptsReward && rewardTargets.contains { $0.id == reward && $0.enabled }
    }

    var defaultChoice: HadesWorldExitChoice? {
        let rooms = roomTargets.filter(\.enabled)
        if let current = rooms.first(where: { $0.acceptsReward && isCurrentRoom($0.id) }),
           let reward = rewardTargets.first(where: { $0.enabled && $0.id != self.reward }) {
            return HadesWorldExitChoice(room: current.id, reward: reward.id)
        }
        for room in rooms {
            if !room.acceptsReward { return HadesWorldExitChoice(room: room.id) }
            if let reward = rewardTargets.first(where: \.enabled) {
                return HadesWorldExitChoice(room: room.id, reward: reward.id)
            }
            if offersAnyReward(room) { return HadesWorldExitChoice(room: room.id) }
        }
        return nil
    }
}

struct HadesWorldObservation: Decodable, Equatable {
    let roomId: String
    let doors: [HadesWorldDoor]
    let canFish: Bool
    let fishingReason: String?
    let canChaos: Bool
    let chaosReason: String?
    let objects: [String]
    let occurrenceTargets: [HadesWorldOccurrenceTarget]?
    let occurrence: HadesWorldOccurrenceLease?

    var worldOccurrenceTargets: [HadesWorldOccurrenceTarget] { occurrenceTargets ?? [] }
}

struct HadesObservation: Decodable {
    let connected: Bool
    let pid: Int32?
    let status: String?
    let scene: String?
    let version: String?
    let roomName: String?
    let runtimeRevision: String?
    let heroReady: Bool
    let invincible: Bool?
    let health: Double?
    let maxHealth: Double?
    let money: Double?
    let rerolls: Double?
    let healthLocked: Bool?
    let moneyLocked: Bool?
    let rerollsLocked: Bool?
    let godGauge: Double?
    let maxGodGauge: Double?
    let target: HadesHeroTarget?
    let features: [String: HadesFeatureValue]?
    let activeFeatures: [String: Bool]?
    let dormantFeatures: [String: Bool]?
    let boonRarityTarget: String?
    let boonForceLegendary: Bool?
    let boonForceDuo: Bool?
    let fishingChance: Double?
    let chaosGateChance: Double?
    let canOpenSellTraits: Bool?
    let resources: [String: Double]?
    let resourceLocks: [String: Int]?
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
    case invincibility, infiniteHealth, infiniteMoney, infiniteRerolls, fullGodGauge, infiniteAmmo, forceEnableRerolls
    case decreaseGameSpeed, increaseGameSpeed
    case boonRarityEnabled, openSellTraits
    case acquireChaosPair, acquireExactBoon
    case moneyMultiplierEnabled, resourceMultiplierEnabled, generateFishing
    case applyWorldExit, applyWorldOccurrence, generateChamberObject, generateChaosGate
    case spawnOlympian, spawnPickup, spawnSpecial
    case disableAll
    var id: String { rawValue }
    var key: String {
        switch self {
        case .disableAll: "host.disableAll"
        case .decreaseGameSpeed: "hades.shortcut.decreaseGameSpeed"
        case .increaseGameSpeed: "hades.shortcut.increaseGameSpeed"
        case .openSellTraits: "hades.shortcut.openPurgingPool"
        case .applyWorldExit: "hades.worldActions.modifyExit"
        case .applyWorldOccurrence: "hades.occurrence.title"
        case .generateChamberObject: "hades.chamberObject"
        case .spawnOlympian: "hades.shortcut.spawnOlympian"
        case .spawnPickup: "hades.shortcut.spawnPickup"
        case .spawnSpecial: "hades.shortcut.spawnSpecial"
        case .acquireChaosPair: "hades.shortcut.acquireChaosPair"
        case .acquireExactBoon: "hades.shortcut.acquireExactBoon"
        default: HadesCheatCatalog.definition(id: rawValue)?.label.rawKey ?? "hades.\(rawValue)"
        }
    }
    /// The Generate row whose shown selection this shortcut generates.
    var rewardGroup: HadesRewardGroup? { HadesRewardGroup.allCases.first { $0.shortcut == self } }
    var defaultChord: HotkeyChord { HadesShortcutStore.defaultLayout()[self]! }
}

struct HadesShortcutStore {
    static let currentLayoutVersion = 5
    private static let moduleNamespace = "hades"
    static var layoutVersionKey: String { "\(moduleNamespace).shortcut.layoutVersion" }

    static let legacyActionAliases: [String: HadesShortcutAction] = {
        var aliases: [String: HadesShortcutAction] = [:]
        for (legacyKey, canonicalID) in HadesCheatCatalog.legacyAliases {
            if let action = HadesShortcutAction(rawValue: canonicalID) {
                aliases[legacyKey] = action
            }
        }
        return aliases
    }()

    private var core: TrainerShortcutStore<HadesShortcutAction>

    static func defaultLayout() -> [HadesShortcutAction: HotkeyChord] {
        let modifiers = HotkeyChord.controlModifier | HotkeyChord.optionModifier
        return TrainerHotkeyLayout.defaultLayout(
            orderedActions: HadesWorkbenchCatalog.orderedShortcutActions,
            dedicated: [
                .decreaseGameSpeed: HotkeyChord(keyCode: 27, modifiers: modifiers, keyLabel: "−"),
                .increaseGameSpeed: HotkeyChord(keyCode: 24, modifiers: modifiers, keyLabel: "+"),
                .disableAll: TrainerHotkeyLayout.disableAllChord,
            ]
        )
    }

    private static func shortcutDefaultsKey(for actionID: String) -> String {
        "hades.shortcut.\(actionID)"
    }

    private static func migrateHistoricalOverrides(_ defaults: UserDefaults) -> [HadesShortcutAction: HotkeyChord]? {
        let storedVersion = defaults.integer(forKey: layoutVersionKey)
        if storedVersion >= currentLayoutVersion {
            return nil
        }
        let sortedAliases = legacyActionAliases.keys.sorted()
        let hasLegacyAliases = sortedAliases.contains { defaults.object(forKey: shortcutDefaultsKey(for: $0)) != nil }
        guard storedVersion > 0 || hasLegacyAliases else {
            return nil
        }

        var aliasesByAction: [HadesShortcutAction: [String]] = [:]
        for alias in sortedAliases {
            if let action = legacyActionAliases[alias] {
                aliasesByAction[action, default: []].append(alias)
            }
        }

        var migrated: [HadesShortcutAction: HotkeyChord] = [:]
        var used = Set<String>()
        for action in HadesWorkbenchCatalog.orderedShortcutActions where action != .disableAll {
            var candidate: Any?
            if let canonicalValue = defaults.object(forKey: shortcutDefaultsKey(for: action.rawValue)) {
                candidate = canonicalValue
            } else if let aliases = aliasesByAction[action] {
                for alias in aliases {
                    if let legacyValue = defaults.object(forKey: shortcutDefaultsKey(for: alias)) {
                        candidate = legacyValue
                        break
                    }
                }
            }
            guard let rawValue = candidate,
                  let parsed = HotkeyChord(payload: rawValue),
                  !TrainerHotkeyLayout.sameKeys(parsed, TrainerHotkeyLayout.disableAllChord) else { continue }
            let identity = TrainerHotkeyLayout.identity(parsed)
            guard used.insert(identity).inserted else { continue }
            migrated[action] = parsed
        }
        return migrated
    }

    private static func finalizePersistence(_ defaults: UserDefaults) {
        let storedVersion = defaults.integer(forKey: layoutVersionKey)
        guard storedVersion <= currentLayoutVersion else { return }
        if storedVersion < currentLayoutVersion {
            defaults.set(currentLayoutVersion, forKey: layoutVersionKey)
        }
        defaults.removeObject(forKey: shortcutDefaultsKey(for: "heal"))
        for legacyKey in legacyActionAliases.keys.sorted() {
            defaults.removeObject(forKey: shortcutDefaultsKey(for: legacyKey))
        }
    }

    init(defaults: UserDefaults = .standard) {
        self.core = TrainerShortcutStore(
            orderedActions: HadesWorkbenchCatalog.orderedShortcutActions,
            defaultLayout: Self.defaultLayout(),
            lockedActions: [.disableAll: TrainerHotkeyLayout.disableAllChord],
            storage: TrainerShortcutStorage(
                moduleID: "hades",
                defaults: defaults,
                canWrite: { defaults.integer(forKey: Self.layoutVersionKey) <= Self.currentLayoutVersion },
                finalizePersistence: {
                    Self.finalizePersistence(defaults)
                }
            ),
            cleanupLegacy: {
                Self.finalizePersistence(defaults)
            },
            migrateOverrides: {
                Self.migrateHistoricalOverrides(defaults)
            }
        )
    }

    func chord(_ action: HadesShortcutAction) -> HotkeyChord {
        core.chord(action)
    }

    mutating func set(_ action: HadesShortcutAction, chord proposed: HotkeyChord) -> HadesShortcutAction? {
        core.set(action, chord: proposed)
    }

    mutating func reset() {
        core.reset()
    }

    func payload() -> [String: Any] {
        core.payload()
    }

    @discardableResult
    mutating func applyProfile(_ values: [String: Any]) -> TrainerShortcutProfileApplyResult {
        core.applyProfile(values, legacyActionAliases: Self.legacyActionAliases)
    }
}
