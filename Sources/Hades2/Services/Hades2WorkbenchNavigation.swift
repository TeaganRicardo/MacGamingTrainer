import Foundation

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
        case .values: "gauge.with.dots.needle.67percent"
        case .common: "bolt.fill"
        case .boons: "sparkles"
        case .resources: "shippingbox.fill"
        case .rooms: "door.left.hand.open"
        case .management: "gearshape.2.fill"
        }
    }
}

struct Hades2WorkbenchEntry: Identifiable {
    let id: String
    let titleKey: String
    let section: Hades2WorkbenchSection
    let shortcut: ShortcutAction?
}

/// Function discovery owns only stable destinations and existing label keys.
/// Choosing a result locates a section; it never performs a game action.
enum Hades2WorkbenchCatalog {
    static let entries: [Hades2WorkbenchEntry] = {
        var result = ShortcutAction.allCases.map { action in
            Hades2WorkbenchEntry(id: "shortcut.\(action.rawValue)", titleKey: action.presentationKey,
                                 section: section(for: action), shortcut: action)
        }
        let numeric = [
            "hades2.vital.health", "hades2.vital.mana", "hades2.vital.runGold", "hades2.vital.armor",
            "hades2.metric.rerolls", "hades2.metric.spellCharge", "hades2.stat.grasp",
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
                      "hades2.rarity.minimum", "hades2.rarity.multiplier", "hades2.section.elements"]),
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
        case .damageEnabled: .values
        case .boonRarityEnabled, .forceLegendary, .forceDuo, .acquireChaosPair, .acquireExactBoon, .openSellTraits: .boons
        case .moneyMultiplierEnabled, .resourceMultiplierEnabled, .generateFlora, .generateMining,
             .generateDigging, .generateShades, .generateFishing, .matureGarden: .resources
        case .spawnOlympian, .spawnPickup, .spawnSpecial, .applyNextRoomReward, .applyNextOccurrence: .rooms
        case .disableAll: .management
        }
    }
}
