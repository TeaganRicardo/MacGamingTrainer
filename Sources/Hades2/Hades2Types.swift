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

struct Hades2OccurrenceTarget: Identifiable, Equatable {
    let id: String
    let kind: String
    let sourceID: String

    var titleKey: String { "hades2.occurrence.target.\(sourceID)" }
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

enum ShortcutAction: String, CaseIterable, Identifiable {
    // Declaration order mirrors the workbench for diagnostics. The canonical
    // allocation and presentation order is Hades2WorkbenchCatalog.orderedShortcutActions.
    case invincibility, infiniteHealth, infiniteMana, infiniteMoney, infiniteRerolls
    case forceEnableRerolls, instantCastCooldown, hexAlwaysReady, infiniteAmmo, autoMiniGames
    case decreaseGameSpeed, increaseGameSpeed
    case boonRarityEnabled, forceLegendary, forceDuo, acquireChaosPair, acquireExactBoon, openSellTraits
    case moneyMultiplierEnabled, resourceMultiplierEnabled
    case generateFlora, generateMining, generateDigging, generateShades, generateFishing, matureGarden
    case applyNextRoomReward, applyNextOccurrence
    case spawnOlympian, spawnPickup, spawnSpecial
    case disableAll

    /// Stable legacy subset used only to interpret the v3 numeric layout.
    /// The retired damage toggle remains recognized as legacy data by the
    /// migration store, but is no longer a current shortcut action.
    static let legacyDigitActions: [ShortcutAction] = [
        .invincibility, .infiniteHealth, .infiniteMana, .instantCastCooldown, .hexAlwaysReady,
        .infiniteAmmo, .autoMiniGames, .moneyMultiplierEnabled, .disableAll,
    ]

    var id: String { rawValue }
    var featureKey: Hades2FeatureKey? { Hades2FeatureKey(rawValue: rawValue) }

    var isSpeedAdjustment: Bool { self == .decreaseGameSpeed || self == .increaseGameSpeed }

    var commonFeatureIcon: String? {
        switch self {
        case .invincibility: TrainerSemanticIcon.Feature.invincibility
        case .infiniteHealth: TrainerSemanticIcon.Feature.infiniteLife
        case .infiniteMana: TrainerSemanticIcon.Feature.infiniteMagick
        case .infiniteMoney: TrainerSemanticIcon.Feature.infiniteCurrency
        case .infiniteRerolls: TrainerSemanticIcon.Feature.infiniteRerolls
        case .forceEnableRerolls: TrainerSemanticIcon.Feature.forceRerolls
        case .instantCastCooldown: "timer"
        case .hexAlwaysReady: "moon.stars.fill"
        case .infiniteAmmo: TrainerSemanticIcon.Feature.infiniteAmmo
        case .autoMiniGames: "gamecontroller.fill"
        default: nil
        }
    }

    var commonFeatureHelpKey: String? {
        switch self {
        case .infiniteMoney: "hades2.feature.infiniteMoney.help"
        case .infiniteRerolls: "hades2.feature.infiniteRerolls.help"
        default: nil
        }
    }

    var gatheringFamily: Hades2GatheringFamily? {
        switch self {
        case .generateFlora: .flora
        case .generateMining: .mining
        case .generateDigging: .digging
        case .generateShades: .shades
        case .generateFishing: .fishing
        default: nil
        }
    }

    /// Presentation key for this action's label. Resolved by the presentation
    /// boundary so a language switch updates the shortcut sheet live.
    var presentationKey: String {
        switch self {
        case .invincibility: return "hades2.feature.invincibility"
        case .infiniteHealth: return "hades2.feature.infiniteHealth"
        case .infiniteMana: return "hades2.feature.infiniteMana"
        case .infiniteMoney: return "hades2.feature.infiniteMoney"
        case .infiniteRerolls: return "hades2.feature.infiniteRerolls"
        case .instantCastCooldown: return "hades2.feature.instantCastCooldown"
        case .hexAlwaysReady: return "hades2.feature.hexAlwaysReady"
        case .infiniteAmmo: return "hades2.feature.infiniteAmmo"
        case .autoMiniGames: return "hades2.feature.autoMiniGames"
        case .decreaseGameSpeed: return "hades2.shortcut.decreaseGameSpeed"
        case .increaseGameSpeed: return "hades2.shortcut.increaseGameSpeed"
        case .matureGarden: return "hades2.garden.title"
        case .forceEnableRerolls: return "hades2.feature.forceEnableRerolls"
        case .boonRarityEnabled: return "hades2.feature.boonRarity"
        case .forceLegendary: return "hades2.feature.forceLegendary"
        case .forceDuo: return "hades2.feature.forceDuo"
        case .moneyMultiplierEnabled: return "hades2.feature.moneyMultiplier"
        case .resourceMultiplierEnabled: return "hades2.feature.resourceMultiplier"
        case .generateFlora: return "hades2.shortcut.generateFlora"
        case .generateMining: return "hades2.shortcut.generateMining"
        case .generateDigging: return "hades2.shortcut.generateDigging"
        case .generateShades: return "hades2.shortcut.generateShades"
        case .generateFishing: return "hades2.shortcut.generateFishing"
        case .spawnOlympian: return "hades2.shortcut.spawnOlympian"
        case .spawnPickup: return "hades2.shortcut.spawnPickup"
        case .spawnSpecial: return "hades2.shortcut.spawnSpecial"
        case .acquireChaosPair: return "hades2.shortcut.acquireChaosPair"
        case .acquireExactBoon: return "hades2.shortcut.acquireExactBoon"
        case .openSellTraits: return "hades2.shortcut.openPurgingPool"
        case .applyNextRoomReward: return "hades2.shortcut.applyNextRoomReward"
        case .applyNextOccurrence: return "hades2.shortcut.applyNextOccurrence"
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
    var hasTemporaryContextualControls: Bool {
        family == "temporary"
            && (remainingUses != nil || canSetRemainingUses || canExpire)
    }
    var hasContextualControls: Bool {
        hasTemporaryContextualControls || canAdvanceLifecycle
    }
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

/// Hades wire families. Native generation and collection strategy stays in Lua.
enum Hades2GatheringFamily: String, CaseIterable, Identifiable {
    case flora, mining, digging, shades, fishing
    var id: String { rawValue }
    var titleKey: String { "hades2.gathering.family.\(rawValue)" }
    var collectionKey: String { "hades2.gathering.collection.\(rawValue)" }

    var shortcutAction: ShortcutAction {
        switch self {
        case .flora: .generateFlora
        case .mining: .generateMining
        case .digging: .generateDigging
        case .shades: .generateShades
        case .fishing: .generateFishing
        }
    }
}

struct Hades2GatheringTarget {
    let available: Bool
    let scopeToken: String?
    let reason: String?
}
