import Foundation

/// Hades II-specific presentation icons. Shared visual roles live in Core;
/// these names describe concepts unique to this module.
enum Hades2WorkbenchIcon {
    static let grasp = "brain.head.profile"
    static let spellCharge = "moonphase.waxing.crescent"
    static let sprintSpeed = "hare.fill"
    static let occurrence = "figure.walk.motion"
    static let specialReward = "moon.stars.fill"
    static let purge = "arrow.left.arrow.right.circle"
    static let flora = "leaf.fill"
    static let garden = flora
    static let targetLevel = TrainerSemanticIcon.Concept.level
    static let chaosAdvance = "arrow.right.circle"
    static let chaosProbability = "percent"
    static let prepareSigning = "signature"
    static let restoreSigning = "arrow.uturn.backward.circle"
    static let refreshStatus = TrainerSemanticIcon.Tool.refreshStatus
    static let miniGames = "gamecontroller.fill"
    static let hexReady = specialReward
    static let legendary = "star.fill"
    static let duo = "person.2.fill"
    static let mining = "hammer.fill"
    static let digging = "mountain.2.fill"
    static let shades = "person.crop.circle"

    static func icon(for titleKey: String) -> String? {
        if let family = Hades2GatheringFamily.allCases.first(where: { $0.titleKey == titleKey }) {
            return family.icon
        }
        switch titleKey {
        case "hades2.vital.health": TrainerSemanticIcon.Concept.vitality
        case "hades2.vital.mana", "hades2.stat.manaRegen": TrainerSemanticIcon.Concept.energy
        case "hades2.vital.runGold": TrainerSemanticIcon.Concept.currency
        case "hades2.vital.armor", "hades2.stat.dodge": TrainerSemanticIcon.Concept.defense
        case "hades2.feature.damageMultiplier", "hades2.stat.enemyDamage": TrainerSemanticIcon.Concept.impact
        case "hades2.stat.grasp": grasp
        case "hades2.metric.rerolls": TrainerSemanticIcon.Concept.randomize
        case "hades2.metric.spellCharge": spellCharge
        case "hades2.stat.crit": TrainerSemanticIcon.Concept.precision
        case "hades2.stat.enemyHealth": TrainerSemanticIcon.Concept.vitality
        case "hades2.stat.chargeSpeed": TrainerSemanticIcon.Concept.timer
        case "hades2.stat.moveSpeed": TrainerSemanticIcon.Concept.movement
        case "hades2.stat.sprintSpeed": sprintSpeed
        case "hades2.stat.dashSpeed": TrainerSemanticIcon.Concept.dash
        case "hades2.stat.attackSpeed": TrainerSemanticIcon.Concept.actionSpeed
        case "hades2.gameSpeed.title": TrainerSemanticIcon.Concept.timeScale
        case "hades2.traits.manager": TrainerSemanticIcon.Concept.controls
        case "hades2.traits.targetLevel": targetLevel
        case "hades2.traits.targetRarity", "hades2.rarity.minimum": TrainerSemanticIcon.Concept.quality
        case "hades2.traits.remainingUses", "hades2.traits.expireNow": TrainerSemanticIcon.Concept.duration
        case "hades2.traits.temporary.cancel", "hades2.traits.remove",
             "hades2.traits.removeAllMatching", "hades2.traits.chaos.cancelPair":
            TrainerSemanticIcon.Action.remove
        case "hades2.traits.chaos.advance": chaosAdvance
        case "hades2.section.elements": TrainerSemanticIcon.Section.effects
        case "hades2.resource.materials": TrainerSemanticIcon.Concept.item
        case "hades2.gathering.title": TrainerSemanticIcon.Section.inventory
        case "hades2.gathering.restoreNative": TrainerSemanticIcon.Action.restore
        case "hades2.chaosGate.title": TrainerSemanticIcon.Context.portal
        case "hades2.chaosGate.probability": chaosProbability
        case "hades2.nextRoom.title": TrainerSemanticIcon.Context.doorway
        case "hades2.occurrence.title": occurrence
        case "hades2.spawn.olympianBoons": TrainerSemanticIcon.Section.effects
        case "hades2.spawn.pickupRewards": TrainerSemanticIcon.Section.inventory
        case "hades2.spawn.characterRewards": specialReward
        case "hades2.manage.profiles": TrainerSemanticIcon.Tool.profiles
        case "hades2.saveEditor.title": TrainerSemanticIcon.Tool.saveEditor
        case "hades2.manage.diagnostics": TrainerSemanticIcon.Tool.diagnostics
        case "hades2.manage.prepareSigning": prepareSigning
        case "hades2.manage.restoreSigning": restoreSigning
        case "host.saveManagement": TrainerSemanticIcon.Tool.saveManagement
        case "host.shortcutSettings": TrainerSemanticIcon.Tool.shortcuts
        case "host.viewLog": TrainerSemanticIcon.Tool.log
        case "host.viewLogHistory": TrainerSemanticIcon.Tool.logHistory
        case "host.clearCompletedLogs": TrainerSemanticIcon.Tool.clearLogs
        case "host.refreshStatus": refreshStatus
        default: nil
        }
    }
}

extension Hades2GatheringFamily {
    var icon: String {
        switch self {
        case .flora: Hades2WorkbenchIcon.flora
        case .mining: Hades2WorkbenchIcon.mining
        case .digging: Hades2WorkbenchIcon.digging
        case .shades: Hades2WorkbenchIcon.shades
        case .fishing: TrainerSemanticIcon.Context.fishing
        }
    }
}

extension ShortcutAction {
    var icon: String {
        switch self {
        case .invincibility: TrainerSemanticIcon.Concept.protection
        case .infiniteHealth: TrainerSemanticIcon.Concept.vitality
        case .infiniteMana: TrainerSemanticIcon.Concept.energy
        case .infiniteMoney: TrainerSemanticIcon.Concept.currency
        case .infiniteRerolls: TrainerSemanticIcon.Concept.randomize
        case .forceEnableRerolls: TrainerSemanticIcon.Concept.refresh
        case .instantCastCooldown: TrainerSemanticIcon.Concept.timer
        case .hexAlwaysReady: Hades2WorkbenchIcon.hexReady
        case .infiniteAmmo: TrainerSemanticIcon.Concept.capacity
        case .autoMiniGames: Hades2WorkbenchIcon.miniGames
        case .decreaseGameSpeed: "gauge.with.dots.needle.33percent"
        case .increaseGameSpeed: TrainerSemanticIcon.Concept.timeScale
        case .boonRarityEnabled: TrainerSemanticIcon.Concept.quality
        case .forceLegendary: Hades2WorkbenchIcon.legendary
        case .forceDuo: Hades2WorkbenchIcon.duo
        case .acquireChaosPair: TrainerSemanticIcon.Context.portal
        case .acquireExactBoon: TrainerSemanticIcon.Concept.precision
        case .openSellTraits: Hades2WorkbenchIcon.purge
        case .moneyMultiplierEnabled: TrainerSemanticIcon.Concept.currency
        case .resourceMultiplierEnabled: TrainerSemanticIcon.Section.inventory
        case .generateFlora: Hades2WorkbenchIcon.flora
        case .generateMining: Hades2WorkbenchIcon.mining
        case .generateDigging: Hades2WorkbenchIcon.digging
        case .generateShades: Hades2WorkbenchIcon.shades
        case .generateFishing: TrainerSemanticIcon.Context.fishing
        case .matureGarden: Hades2WorkbenchIcon.garden
        case .applyNextRoomReward: TrainerSemanticIcon.Context.doorway
        case .applyNextOccurrence: Hades2WorkbenchIcon.occurrence
        case .spawnOlympian: TrainerSemanticIcon.Section.effects
        case .spawnPickup: TrainerSemanticIcon.Section.inventory
        case .spawnSpecial: Hades2WorkbenchIcon.specialReward
        case .disableAll: TrainerSemanticIcon.Tool.disableAll
        }
    }

    var commonFeatureIcon: String? {
        switch self {
        case .invincibility, .infiniteHealth, .infiniteMana, .infiniteMoney, .infiniteRerolls,
             .forceEnableRerolls, .instantCastCooldown, .hexAlwaysReady, .infiniteAmmo, .autoMiniGames:
            icon
        default: nil
        }
    }
}

enum Hades2WorkbenchSection: String, CaseIterable, Identifiable {
    case values, common, boons, resources, rooms, management

    var id: String { "hades2-workbench-\(rawValue)" }
    var titleKey: String {
        switch self {
        case .values: "hades2.section.runData"
        case .common: "hades2.section.common"
        case .boons: "hades2.section.boonsAndEffects"
        case .resources: "hades2.section.resourcesAndGathering"
        case .rooms: "hades2.section.roomsAndRewards"
        case .management: "hades2.section.management"
        }
    }
    var icon: String {
        switch self {
        case .values: TrainerSemanticIcon.Section.metrics
        case .common: TrainerSemanticIcon.Section.general
        case .boons: TrainerSemanticIcon.Section.effects
        case .resources: TrainerSemanticIcon.Section.inventory
        case .rooms: TrainerSemanticIcon.Section.navigation
        case .management: TrainerSemanticIcon.Section.settings
        }
    }
}

struct Hades2WorkbenchEntry: Identifiable {
    let id: String
    let titleKey: String
    let section: Hades2WorkbenchSection
    let shortcut: ShortcutAction?
    var icon: String { shortcut?.icon ?? Hades2WorkbenchIcon.icon(for: titleKey) ?? section.icon }
}

/// Function discovery owns only stable destinations and existing label keys.
/// Choosing a result locates a section; it never performs a game action.
enum Hades2WorkbenchCatalog {
    /// One ordered registry drives default shortcut allocation, shortcut
    /// settings and function discovery. Keep this in the visible workbench order.
    static let orderedShortcutActions: [ShortcutAction] = [
        .invincibility,
        .infiniteHealth,
        .infiniteMana,
        .infiniteMoney,
        .infiniteRerolls,
        .forceEnableRerolls,
        .instantCastCooldown,
        .hexAlwaysReady,
        .infiniteAmmo,
        .autoMiniGames,
        .decreaseGameSpeed,
        .increaseGameSpeed,
        .boonRarityEnabled,
        .forceLegendary,
        .forceDuo,
        .openSellTraits,
        .acquireChaosPair,
        .acquireExactBoon,
        .moneyMultiplierEnabled,
        .resourceMultiplierEnabled,
        .generateFlora,
        .generateMining,
        .generateDigging,
        .generateShades,
        .generateFishing,
        .matureGarden,
        .applyNextRoomReward,
        .applyNextOccurrence,
        .spawnOlympian,
        .spawnPickup,
        .spawnSpecial,
        .disableAll,
    ]

    static func shortcutActions(in workbenchSection: Hades2WorkbenchSection) -> [ShortcutAction] {
        orderedShortcutActions.filter { section(for: $0) == workbenchSection }
    }

    static let entries: [Hades2WorkbenchEntry] = {
        var result = orderedShortcutActions.map { action in
            Hades2WorkbenchEntry(id: "shortcut.\(action.rawValue)", titleKey: action.presentationKey,
                                 section: section(for: action), shortcut: action)
        }
        let numeric = [
            "hades2.vital.health", "hades2.vital.mana", "hades2.vital.runGold", "hades2.vital.armor",
            "hades2.feature.damageMultiplier", "hades2.stat.grasp", "hades2.metric.rerolls", "hades2.metric.spellCharge",
            "hades2.stat.dodge", "hades2.stat.crit", "hades2.stat.enemyDamage", "hades2.stat.enemyHealth",
            "hades2.stat.chargeSpeed", "hades2.stat.moveSpeed", "hades2.stat.sprintSpeed",
            "hades2.stat.dashSpeed", "hades2.stat.attackSpeed", "hades2.stat.manaRegen",
        ]
        let other: [(Hades2WorkbenchSection, [String])] = [
            (.values, numeric),
            (.common, ["hades2.gameSpeed.title"]),
            (.boons, ["hades2.traits.manager", "hades2.traits.targetLevel", "hades2.traits.targetRarity",
                      "hades2.traits.remainingUses", "hades2.traits.expireNow", "hades2.traits.temporary.cancel",
                      "hades2.traits.remove", "hades2.traits.removeAllMatching",
                      "hades2.traits.chaos.advance", "hades2.traits.chaos.cancelPair",
                      "hades2.rarity.minimum", "hades2.section.elements"]),
            (.resources, Hades2GatheringFamily.allCases.map(\.titleKey)
                + ["hades2.resource.materials", "hades2.gathering.title", "hades2.gathering.restoreNative"]),
            (.rooms, ["hades2.chaosGate.title", "hades2.chaosGate.probability", "hades2.nextRoom.title",
                      "hades2.occurrence.title", "hades2.spawn.olympianBoons", "hades2.spawn.pickupRewards",
                      "hades2.spawn.characterRewards"]),
            (.management, ["hades2.manage.profiles", "hades2.saveEditor.title", "hades2.manage.diagnostics",
                           "hades2.manage.prepareSigning", "hades2.manage.restoreSigning", "host.saveManagement",
                           "host.shortcutSettings", "host.viewLog", "host.viewLogHistory", "host.clearCompletedLogs",
                           "host.refreshStatus"]),
        ]
        for (section, keys) in other {
            result += keys.map { Hades2WorkbenchEntry(id: $0, titleKey: $0, section: section, shortcut: nil) }
        }
        return result
    }()

    static func matches(_ query: String, resolving labels: (String) -> [String]) -> [Hades2WorkbenchEntry] {
        let words = query.split(whereSeparator: \.isWhitespace).map { normalized(String($0)) }
        guard !words.isEmpty else { return [] }
        return entries.filter { entry in
            let searchable = normalized((labels(entry.titleKey) + labels(entry.section.titleKey)).joined(separator: " "))
            return words.allSatisfy { searchable.contains($0) }
        }
    }

    private static func normalized(_ value: String) -> String {
        value.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: Locale(identifier: "en_US_POSIX"))
    }

    private static func section(for action: ShortcutAction) -> Hades2WorkbenchSection {
        switch action {
        case .invincibility, .infiniteHealth, .infiniteMana, .infiniteMoney, .infiniteRerolls,
             .forceEnableRerolls, .instantCastCooldown, .hexAlwaysReady, .infiniteAmmo, .autoMiniGames,
             .decreaseGameSpeed, .increaseGameSpeed: .common
        case .boonRarityEnabled, .forceLegendary, .forceDuo, .acquireChaosPair, .acquireExactBoon, .openSellTraits: .boons
        case .moneyMultiplierEnabled, .resourceMultiplierEnabled, .generateFlora, .generateMining,
             .generateDigging, .generateShades, .generateFishing, .matureGarden: .resources
        case .spawnOlympian, .spawnPickup, .spawnSpecial, .applyNextRoomReward, .applyNextOccurrence: .rooms
        case .disableAll: .management
        }
    }
}
