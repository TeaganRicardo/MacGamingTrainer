import Foundation
import TrainerCore

/// Hades II-specific presentation icons. Shared visual roles live in Core;
/// these names describe concepts unique to this module.
enum Hades2WorkbenchIcon {
    static let grasp = Hades2CheatIcon.grasp
    static let spellCharge = Hades2CheatIcon.spellCharge
    static let sprintSpeed = Hades2CheatIcon.sprintSpeed
    static let occurrence = Hades2CheatIcon.occurrence
    static let fishing = Hades2CheatIcon.fishing
    static let portal = Hades2CheatIcon.portal
    static let doorway = Hades2CheatIcon.doorway
    static let specialReward = Hades2CheatIcon.specialReward
    static let purge = Hades2CheatIcon.purge
    static let flora = Hades2CheatIcon.flora
    static let garden = Hades2CheatIcon.garden
    static let targetLevel = TrainerSemanticIcon.Concept.level
    static let exactBoons = TrainerSemanticIcon.Concept.precision
    static let chaosAdvance = "arrow.right.circle"
    static let chaosProbability = "percent"
    static let prepareSigning = "signature"
    static let restoreSigning = "arrow.uturn.backward.circle"
    static let refreshStatus = TrainerSemanticIcon.Tool.refreshStatus
    static let miniGames = Hades2CheatIcon.miniGames
    static let hexReady = Hades2CheatIcon.hexReady
    static let legendary = Hades2CheatIcon.legendary
    static let duo = Hades2CheatIcon.duo
    static let mining = Hades2CheatIcon.mining
    static let digging = Hades2CheatIcon.digging
    static let shades = Hades2CheatIcon.shades

    static func icon(for titleKey: String) -> String? {
        if let family = Hades2GatheringFamily.allCases.first(where: { $0.titleKey == titleKey }) {
            return family.icon
        }
        switch titleKey {
        case "hades2.vital.health": return TrainerSemanticIcon.Concept.vitality
        case "hades2.vital.mana", "hades2.stat.manaRegen": return TrainerSemanticIcon.Concept.energy
        case "hades2.vital.runGold": return TrainerSemanticIcon.Concept.currency
        case "hades2.vital.armor", "hades2.stat.dodge": return TrainerSemanticIcon.Concept.defense
        case "hades2.feature.damageMultiplier", "hades2.stat.enemyDamage": return TrainerSemanticIcon.Concept.impact
        case "hades2.stat.grasp": return grasp
        case "hades2.metric.rerolls": return TrainerSemanticIcon.Concept.randomize
        case "hades2.metric.spellCharge": return spellCharge
        case "hades2.stat.crit": return TrainerSemanticIcon.Concept.precision
        case "hades2.stat.enemyHealth": return TrainerSemanticIcon.Concept.vitality
        case "hades2.stat.chargeSpeed": return TrainerSemanticIcon.Concept.timer
        case "hades2.stat.moveSpeed": return TrainerSemanticIcon.Concept.movement
        case "hades2.stat.sprintSpeed": return sprintSpeed
        case "hades2.stat.dashSpeed": return TrainerSemanticIcon.Concept.dash
        case "hades2.stat.attackSpeed": return TrainerSemanticIcon.Concept.actionSpeed
        case "hades2.gameSpeed.title": return TrainerSemanticIcon.Concept.timeScale
        case "hades2.traits.manager": return TrainerSemanticIcon.Concept.controls
        case "hades2.traits.targetLevel": return targetLevel
        case "hades2.traits.targetRarity", "hades2.rarity.minimum": return TrainerSemanticIcon.Concept.quality
        case "hades2.traits.remainingUses", "hades2.traits.expireNow": return TrainerSemanticIcon.Concept.duration
        case "hades2.traits.temporary.cancel", "hades2.traits.remove",
             "hades2.traits.removeAllMatching", "hades2.traits.chaos.cancelPair":
            return TrainerSemanticIcon.Action.remove
        case "hades2.traits.chaos.advance": return chaosAdvance
        case "hades2.section.elements": return TrainerSemanticIcon.Section.effects
        case "hades2.resource.materials": return TrainerSemanticIcon.Concept.item
        case "hades2.gathering.title": return TrainerSemanticIcon.Section.inventory
        case "hades2.gathering.restoreNative": return TrainerSemanticIcon.Action.restore
        case "hades2.facility.title": return TrainerSemanticIcon.Action.generate
        case "hades2.chaosGate.title": return portal
        case "hades2.chaosGate.probability": return chaosProbability
        case "hades2.worldActions.modifyExit": return doorway
        case "hades2.occurrence.title": return occurrence
        case "hades2.spawn.olympianBoons": return TrainerSemanticIcon.Section.effects
        case "hades2.spawn.pickupRewards": return TrainerSemanticIcon.Section.inventory
        case "hades2.spawn.characterRewards": return specialReward
        case "hades2.spawn.exactBoons": return exactBoons
        case "hades2.manage.profiles": return TrainerSemanticIcon.Tool.profiles
        case "hades2.saveEditor.title": return TrainerSemanticIcon.Tool.saveEditor
        case "hades2.manage.diagnostics": return TrainerSemanticIcon.Tool.diagnostics
        case "hades2.manage.prepareSigning": return prepareSigning
        case "hades2.manage.restoreSigning": return restoreSigning
        case "host.saveManagement": return TrainerSemanticIcon.Tool.saveManagement
        case "host.shortcutSettings": return TrainerSemanticIcon.Tool.shortcuts
        case "host.viewLog": return TrainerSemanticIcon.Tool.log
        case "host.viewLogHistory": return TrainerSemanticIcon.Tool.logHistory
        case "host.clearCompletedLogs": return TrainerSemanticIcon.Tool.clearLogs
        case "host.refreshStatus": return refreshStatus
        default: return nil
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
        case .fishing: Hades2WorkbenchIcon.fishing
        }
    }
}

extension ShortcutAction {
    var icon: String {
        if let definition = Hades2CheatCatalog.definition(id: rawValue) {
            return definition.icon
        }
        return switch self {
        case .decreaseGameSpeed, .increaseGameSpeed: TrainerSemanticIcon.Concept.timeScale
        case .acquireExactBoon: TrainerSemanticIcon.Concept.precision
        case .spawnOlympian: TrainerSemanticIcon.Section.effects
        case .spawnPickup: TrainerSemanticIcon.Section.inventory
        case .spawnSpecial: Hades2WorkbenchIcon.specialReward
        default: TrainerSemanticIcon.Concept.controls
        }
    }

    var commonFeatureIcon: String? {
        Hades2CheatCatalog.commonToggleDefinitions.first { $0.id == rawValue }?.icon
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
        .applyWorldExit,
        .applyNextOccurrence,
        .generateChamberFacility,
        .generateChaosGate,
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
                      "hades2.feature.forceLegendary", "hades2.feature.forceDuo",
                      "hades2.rarity.minimum", "hades2.section.elements", "hades2.spawn.exactBoons"]),
            (.resources, Hades2GatheringFamily.allCases.map(\.titleKey)
                + ["hades2.resource.materials", "hades2.gathering.title", "hades2.gathering.restoreNative"]),
            (.rooms, ["hades2.chaosGate.title", "hades2.chaosGate.probability", "hades2.worldActions.modifyExit",
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
        TrainerWorkbenchSearch.matches(query, entries: entries) { entry in
            labels(entry.titleKey) + labels(entry.section.titleKey)
        }
    }

    private static func section(for action: ShortcutAction) -> Hades2WorkbenchSection {
        switch action {
        case .invincibility, .infiniteHealth, .infiniteMana, .infiniteMoney, .infiniteRerolls,
             .forceEnableRerolls, .instantCastCooldown, .hexAlwaysReady, .infiniteAmmo, .autoMiniGames,
             .decreaseGameSpeed, .increaseGameSpeed: .common
        case .boonRarityEnabled, .acquireChaosPair, .acquireExactBoon, .openSellTraits: .boons
        case .moneyMultiplierEnabled, .resourceMultiplierEnabled, .generateFlora, .generateMining,
             .generateDigging, .generateShades, .generateFishing, .matureGarden: .resources
        case .spawnOlympian, .spawnPickup, .spawnSpecial, .applyWorldExit, .applyNextOccurrence,
             .generateChamberFacility, .generateChaosGate: .rooms
        case .disableAll: .management
        }
    }
}
