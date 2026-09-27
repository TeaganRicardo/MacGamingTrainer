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
    let sectionTitle: String
    let englishSectionTitle: String
    let sourceId: String
    let sourceName: String
    let sourceEnglishName: String
    let nativeChoice: Bool
    let nativeChoiceTitle: String
    let nativeChoiceEnglishTitle: String
    let sortSection: Int
    let sortGroup: Int
    let sortOrder: Int
}

enum Hades2FeatureKey: String, CaseIterable, Hashable {
    case godMode, infiniteHealth, infiniteMana, damageEnabled, instantCastCooldown
    case hexAlwaysReady, infiniteAmmo, autoMiniGames, gardenQoL, boonRarityEnabled
    case moneyMultiplierEnabled, resourceMultiplierEnabled
}

enum ShortcutAction: String, CaseIterable, Identifiable {
    case godMode, infiniteHealth, infiniteMana, instantCastCooldown, hexAlwaysReady
    case infiniteAmmo, damageEnabled, autoMiniGames, gardenQoL
    case boonRarityEnabled, forceLegendary, forceDuo
    case moneyMultiplierEnabled, resourceMultiplierEnabled
    case applyNextRoomReward, spawnOlympian, spawnPickup, spawnSpecial
    case disableAll

    var id: String { rawValue }
    var featureKey: Hades2FeatureKey? { Hades2FeatureKey(rawValue: rawValue) }

    static let uiOrder: [ShortcutAction] = [
        .godMode, .infiniteHealth, .infiniteMana, .instantCastCooldown, .hexAlwaysReady,
        .infiniteAmmo, .damageEnabled, .autoMiniGames, .gardenQoL,
        .boonRarityEnabled, .forceLegendary, .forceDuo,
        .moneyMultiplierEnabled, .resourceMultiplierEnabled,
        .spawnOlympian, .spawnPickup, .spawnSpecial, .applyNextRoomReward,
        .disableAll,
    ]

    static let legacyDigitActions: [ShortcutAction] = [
        .godMode, .infiniteHealth, .infiniteMana, .instantCastCooldown, .hexAlwaysReady,
        .infiniteAmmo, .damageEnabled, .autoMiniGames, .moneyMultiplierEnabled, .disableAll,
    ]

    /// Presentation key for this action's label. Resolved by
    /// `Hades2Presentation` at the presentation boundary so a language switch
    /// re-renders the shortcut sheet and its conflict diagnostics live.
    var presentationKey: String {
        switch self {
        case .godMode: return "hades2.feature.godMode"
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
