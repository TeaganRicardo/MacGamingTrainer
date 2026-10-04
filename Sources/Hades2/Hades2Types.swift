import Foundation

struct MaterialResource: Identifiable {
    let id: String
    let name: String
    let englishName: String
    let count: Double
    let locked: Bool
    let sectionTitle: String
    let englishSectionTitle: String
    let sortOrder: Int
}

struct BoonOption: Identifiable {
    let id: String
    let name: String
    let englishName: String
    let category: String
    let englishCategory: String
    let kind: String
    let group: String
    /// Stable language-neutral target identity. For exact trait acquisition this
    /// is the TraitData id; otherwise it falls back to the catalog row id.
    let targetID: String
    /// Whether `name` came from the supported build's official localization.
    let officialName: Bool
    let sectionTitle: String
    let englishSectionTitle: String
    let sourceId: String
    let sourceName: String
    let sourceEnglishName: String
    let nativeChoice: Bool
    let nativeChoiceTitle: String
    let nativeChoiceEnglishTitle: String
    /// Language-neutral resident strategy identity for exact acquisition.
    /// Empty for ordinary reward rows and synthetic native-choice actions.
    let acquisitionMode: String
    let sortSection: Int
    let sortGroup: Int
    let sortOrder: Int
}

enum Hades2FeatureKey: String, CaseIterable, Hashable {
    case invincibility, infiniteHealth, infiniteMana, damageEnabled, instantCastCooldown
    case hexAlwaysReady, infiniteAmmo, autoMiniGames, gardenQoL, boonRarityEnabled
    case moneyMultiplierEnabled, resourceMultiplierEnabled
}

enum ShortcutAction: String, CaseIterable, Identifiable {
    case invincibility, infiniteHealth, infiniteMana, instantCastCooldown, hexAlwaysReady
    case infiniteAmmo, damageEnabled, autoMiniGames, gardenQoL
    case boonRarityEnabled, forceLegendary, forceDuo
    case moneyMultiplierEnabled, resourceMultiplierEnabled
    case applyNextRoomReward, spawnOlympian, spawnPickup, spawnSpecial
    case disableAll

    var id: String { rawValue }
    var featureKey: Hades2FeatureKey? { Hades2FeatureKey(rawValue: rawValue) }

    static let uiOrder: [ShortcutAction] = [
        .invincibility, .infiniteHealth, .infiniteMana, .instantCastCooldown, .hexAlwaysReady,
        .infiniteAmmo, .damageEnabled, .autoMiniGames, .gardenQoL,
        .boonRarityEnabled, .forceLegendary, .forceDuo,
        .moneyMultiplierEnabled, .resourceMultiplierEnabled,
        .spawnOlympian, .spawnPickup, .spawnSpecial, .applyNextRoomReward,
        .disableAll,
    ]

    static let legacyDigitActions: [ShortcutAction] = [
        .invincibility, .infiniteHealth, .infiniteMana, .instantCastCooldown, .hexAlwaysReady,
        .infiniteAmmo, .damageEnabled, .autoMiniGames, .moneyMultiplierEnabled, .disableAll,
    ]

    /// Presentation key for this action's label. Resolved by
    /// `Hades2Presentation` at the presentation boundary so a language switch
    /// re-renders the shortcut sheet and its conflict diagnostics live.
    var presentationKey: String {
        switch self {
        case .invincibility: return "hades2.feature.invincibility"
        case .infiniteHealth: return "hades2.feature.infiniteHealth"
        case .infiniteMana: return "hades2.feature.infiniteMana"
        case .instantCastCooldown: return "hades2.feature.instantCastCooldown"
        case .hexAlwaysReady: return "hades2.feature.hexAlwaysReady"
        case .infiniteAmmo: return "hades2.feature.infiniteAmmo"
        case .damageEnabled: return "hades2.feature.damageMultiplier"
        case .autoMiniGames: return "hades2.feature.autoMiniGames"
        case .gardenQoL: return "hades2.feature.gardenQoL"
        case .boonRarityEnabled: return "hades2.feature.boonRarity"
        case .forceLegendary: return "hades2.feature.forceLegendary"
        case .forceDuo: return "hades2.feature.forceDuo"
        case .moneyMultiplierEnabled: return "hades2.feature.moneyMultiplier"
        case .resourceMultiplierEnabled: return "hades2.feature.resourceMultiplier"
        case .applyNextRoomReward: return "hades2.nextRoom.title"
        case .spawnOlympian: return "hades2.spawn.olympianBoons"
        case .spawnPickup: return "hades2.spawn.pickupRewards"
        case .spawnSpecial: return "hades2.spawn.characterRewards"
        // Disable All is a Host-shell action that happens to live in the Hades
        // module, so it keeps the Host key and the Host resource.
        case .disableAll: return "host.disableAll"
        }
    }
}

struct ElementCount: Identifiable, Equatable {
    let id: String
    let name: String
    let count: Double
    let locked: Bool
}

struct TrainerProfile: Identifiable {
    var id: String { name }
    let name: String
    let updatedAt: String
}

struct DiagnosticCheck: Identifiable {
    var id: String { name }
    let name: String
    let ok: Bool
    let detail: String
}


// MARK: - Current-run trait/buff inventory
//
// A row projected from live runtime state, never from the acquisition catalog
// and never from desired state. generation/run/instance identifiers form one
// ephemeral target snapshot; every mutation is re-resolved by the resident
// runtime before applying any game-owned operation.

enum TraitLevelCapability: String, Codable, Equatable, Sendable {
    case none
    case increaseOne
}

enum TraitRarityCapability: String, Codable, Equatable, Sendable {
    case none
    case setExact
}

enum TraitRemovalCapability: String, Codable, Equatable, Sendable {
    case none
    case nameLevelAllMatching
    case singleInstanceForce
}

struct CurrentRunTrait: Identifiable, Equatable, Sendable {
    /// Ephemeral resident/run identity. None of these values are durable.
    let generationID: String
    let runID: String
    let instanceID: String

    /// Language-neutral runtime identity plus official localized presentation.
    let name: String
    let displayName: String
    let englishName: String
    let family: String
    let sourceID: String
    let sourceName: String
    let sourceEnglishName: String

    let level: Int
    let rarity: String
    let availableRarities: [String]
    let sameNameCount: Int
    let remainingUses: Double?
    let lifecycleState: String
    let linkedTrait: String
    let linkedDisplayName: String
    let linkedEnglishName: String
    let canAdvanceLifecycle: Bool
    let canSetRemainingUses: Bool
    let canExpire: Bool

    let levelCapability: TraitLevelCapability
    let levelReason: String
    let rarityCapability: TraitRarityCapability
    let rarityReason: String
    let removalCapability: TraitRemovalCapability
    let removalReason: String
    let removalScopeAllMatching: Bool
    let deferredIssue: Int?

    var id: String { "\(generationID):\(runID):\(instanceID)" }
    var canIncreaseLevel: Bool { levelCapability == .increaseOne }
    var canSetRarity: Bool { rarityCapability == .setExact }
    var canRemove: Bool { removalCapability != .none }
}

/// The identity scope the runtime reported, carried so the UI cannot imply more
/// than the backend proved.
struct CurrentRunTraitScope: Equatable, Sendable {
    let identityScope: String
    let isPersistent: Bool

    static let currentRun = CurrentRunTraitScope(
        identityScope: "currentRunInstance",
        isPersistent: false
    )
}
