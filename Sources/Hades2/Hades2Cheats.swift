import Foundation
import TrainerCore

package enum Hades2CheatIcon {
    package static let grasp = "brain.head.profile"
    package static let spellCharge = "moonphase.waxing.crescent"
    package static let sprintSpeed = "hare.fill"
    package static let occurrence = "figure.walk.motion"
    package static let fishing = "fish.fill"
    package static let portal = "circle.hexagongrid.fill"
    package static let doorway = TrainerSemanticIcon.Section.navigation
    package static let specialReward = "moon.stars.fill"
    package static let purge = "arrow.left.arrow.right.circle"
    package static let flora = "leaf.fill"
    package static let garden = "tree.fill"
    package static let miniGames = "gamecontroller.fill"
    package static let hexReady = "moon.fill"
    package static let legendary = "star.fill"
    package static let duo = "person.2.fill"
    package static let mining = "hammer.fill"
    package static let digging = "mountain.2.fill"
    package static let shades = "person.3.fill"
}

package enum Hades2CheatCatalog {
    package static let commonToggleDefinitions: [TrainerCheatDefinition] = [
        TrainerCheatDefinition(
            id: "invincibility",
            kind: .toggle,
            label: .key("hades2.feature.invincibility"),
            icon: TrainerSemanticIcon.Concept.protection,
            action: TrainerCheatActionSpec(command: "set_desired", valueParam: "value"),
            shortcutID: "invincibility",
            aliases: ["godMode"]
        ),
        TrainerCheatDefinition(
            id: "infiniteHealth",
            kind: .toggle,
            label: .key("hades2.feature.infiniteHealth"),
            icon: TrainerSemanticIcon.Concept.vitality,
            action: TrainerCheatActionSpec(command: "set_desired", valueParam: "value"),
            shortcutID: "infiniteHealth"
        ),
        TrainerCheatDefinition(
            id: "infiniteMana",
            kind: .toggle,
            label: .key("hades2.feature.infiniteMana"),
            icon: TrainerSemanticIcon.Concept.energy,
            action: TrainerCheatActionSpec(command: "set_desired", valueParam: "value"),
            shortcutID: "infiniteMana"
        ),
        TrainerCheatDefinition(
            id: "infiniteMoney",
            kind: .toggle,
            label: .key("hades2.feature.infiniteMoney"),
            help: .key("hades2.feature.infiniteMoney.help"),
            icon: TrainerSemanticIcon.Concept.currency,
            action: TrainerCheatActionSpec(command: "set_desired", valueParam: "value"),
            shortcutID: "infiniteMoney"
        ),
        TrainerCheatDefinition(
            id: "infiniteRerolls",
            kind: .toggle,
            label: .key("hades2.feature.infiniteRerolls"),
            help: .key("hades2.feature.infiniteRerolls.help"),
            icon: TrainerSemanticIcon.Concept.randomize,
            action: TrainerCheatActionSpec(command: "set_desired", valueParam: "value"),
            shortcutID: "infiniteRerolls"
        ),
        TrainerCheatDefinition(
            id: "forceEnableRerolls",
            kind: .toggle,
            label: .key("hades2.feature.forceEnableRerolls"),
            icon: TrainerSemanticIcon.Concept.refresh,
            action: TrainerCheatActionSpec(command: "set_desired", valueParam: "value"),
            shortcutID: "forceEnableRerolls"
        ),
        TrainerCheatDefinition(
            id: "instantCastCooldown",
            kind: .toggle,
            label: .key("hades2.feature.instantCastCooldown"),
            icon: TrainerSemanticIcon.Concept.timer,
            action: TrainerCheatActionSpec(command: "set_desired", valueParam: "value"),
            shortcutID: "instantCastCooldown"
        ),
        TrainerCheatDefinition(
            id: "hexAlwaysReady",
            kind: .toggle,
            label: .key("hades2.feature.hexAlwaysReady"),
            icon: Hades2CheatIcon.hexReady,
            action: TrainerCheatActionSpec(command: "set_desired", valueParam: "value"),
            shortcutID: "hexAlwaysReady"
        ),
        TrainerCheatDefinition(
            id: "infiniteAmmo",
            kind: .toggle,
            label: .key("hades2.feature.infiniteAmmo"),
            icon: TrainerSemanticIcon.Concept.capacity,
            action: TrainerCheatActionSpec(command: "set_desired", valueParam: "value"),
            shortcutID: "infiniteAmmo"
        ),
        TrainerCheatDefinition(
            id: "autoMiniGames",
            kind: .toggle,
            label: .key("hades2.feature.autoMiniGames"),
            icon: Hades2CheatIcon.miniGames,
            action: TrainerCheatActionSpec(command: "set_desired", valueParam: "value"),
            shortcutID: "autoMiniGames"
        ),
    ]

    package static let multiplierToggleDefinitions: [TrainerCheatDefinition] = [
        TrainerCheatDefinition(
            id: "moneyMultiplierEnabled",
            kind: .toggle,
            label: .key("hades2.feature.moneyMultiplier"),
            icon: TrainerSemanticIcon.Concept.currency,
            action: TrainerCheatActionSpec(command: "set_desired", valueParam: "value"),
            shortcutID: "moneyMultiplierEnabled"
        ),
        TrainerCheatDefinition(
            id: "resourceMultiplierEnabled",
            kind: .toggle,
            label: .key("hades2.feature.resourceMultiplier"),
            icon: TrainerSemanticIcon.Section.inventory,
            action: TrainerCheatActionSpec(command: "set_desired", valueParam: "value"),
            shortcutID: "resourceMultiplierEnabled"
        ),
    ]

    private static let boonToggleDefinitions: [TrainerCheatDefinition] = [
        TrainerCheatDefinition(
            id: "boonRarityEnabled",
            kind: .toggle,
            label: .key("hades2.feature.boonRarity"),
            icon: TrainerSemanticIcon.Concept.quality,
            action: TrainerCheatActionSpec(command: "set_desired", valueParam: "value"),
            shortcutID: "boonRarityEnabled"
        ),
        TrainerCheatDefinition(
            id: "forceLegendary",
            kind: .toggle,
            label: .key("hades2.feature.forceLegendary"),
            icon: Hades2CheatIcon.legendary,
            action: TrainerCheatActionSpec(command: "set_boon_rarity_desired", valueParam: "forceLegendary"),
            shortcutID: nil
        ),
        TrainerCheatDefinition(
            id: "forceDuo",
            kind: .toggle,
            label: .key("hades2.feature.forceDuo"),
            icon: Hades2CheatIcon.duo,
            action: TrainerCheatActionSpec(command: "set_boon_rarity_desired", valueParam: "forceDuo"),
            shortcutID: nil
        ),
    ]

    package static let statDefinitions: [TrainerCheatDefinition] = [
        TrainerCheatDefinition(
            id: "grasp",
            kind: .value,
            label: .key("hades2.stat.grasp"),
            icon: Hades2CheatIcon.grasp,
            action: TrainerCheatActionSpec(command: "set_stat", valueParam: "value")
        ),
        TrainerCheatDefinition(
            id: "dodge",
            kind: .value,
            label: .key("hades2.stat.dodge"),
            icon: TrainerSemanticIcon.Concept.defense,
            action: TrainerCheatActionSpec(command: "set_stat", valueParam: "value")
        ),
        TrainerCheatDefinition(
            id: "crit",
            kind: .value,
            label: .key("hades2.stat.crit"),
            icon: TrainerSemanticIcon.Concept.precision,
            action: TrainerCheatActionSpec(command: "set_stat", valueParam: "value")
        ),
        TrainerCheatDefinition(
            id: "enemyDamage",
            kind: .value,
            label: .key("hades2.stat.enemyDamage"),
            icon: TrainerSemanticIcon.Concept.impact,
            action: TrainerCheatActionSpec(command: "set_stat", valueParam: "value")
        ),
        TrainerCheatDefinition(
            id: "enemyHealth",
            kind: .value,
            label: .key("hades2.stat.enemyHealth"),
            icon: TrainerSemanticIcon.Concept.vitality,
            action: TrainerCheatActionSpec(command: "set_stat", valueParam: "value")
        ),
        TrainerCheatDefinition(
            id: "chargeSpeed",
            kind: .value,
            label: .key("hades2.stat.chargeSpeed"),
            icon: TrainerSemanticIcon.Concept.timer,
            action: TrainerCheatActionSpec(command: "set_stat", valueParam: "value")
        ),
        TrainerCheatDefinition(
            id: "moveSpeed",
            kind: .value,
            label: .key("hades2.stat.moveSpeed"),
            icon: TrainerSemanticIcon.Concept.movement,
            action: TrainerCheatActionSpec(command: "set_stat", valueParam: "value")
        ),
        TrainerCheatDefinition(
            id: "sprintSpeed",
            kind: .value,
            label: .key("hades2.stat.sprintSpeed"),
            icon: Hades2CheatIcon.sprintSpeed,
            action: TrainerCheatActionSpec(command: "set_stat", valueParam: "value")
        ),
        TrainerCheatDefinition(
            id: "dashSpeed",
            kind: .value,
            label: .key("hades2.stat.dashSpeed"),
            icon: TrainerSemanticIcon.Concept.dash,
            action: TrainerCheatActionSpec(command: "set_stat", valueParam: "value")
        ),
        TrainerCheatDefinition(
            id: "attackSpeed",
            kind: .value,
            label: .key("hades2.stat.attackSpeed"),
            icon: TrainerSemanticIcon.Concept.actionSpeed,
            action: TrainerCheatActionSpec(command: "set_stat", valueParam: "value")
        ),
        TrainerCheatDefinition(
            id: "manaRegen",
            kind: .value,
            label: .key("hades2.stat.manaRegen"),
            icon: TrainerSemanticIcon.Concept.energy,
            action: TrainerCheatActionSpec(command: "set_stat", valueParam: "value")
        ),
    ]

    private static let valueDefinitions: [TrainerCheatDefinition] = [
        TrainerCheatDefinition(
            id: "gameSpeed",
            kind: .value,
            label: .key("hades2.gameSpeed.title"),
            help: .key("hades2.gameSpeed.hint"),
            icon: TrainerSemanticIcon.Concept.timeScale,
            action: TrainerCheatActionSpec(command: "set_desired", valueParam: "value")
        ),
        TrainerCheatDefinition(
            id: "damageMultiplier",
            kind: .value,
            label: .key("hades2.feature.damageMultiplier"),
            icon: TrainerSemanticIcon.Concept.impact,
            action: TrainerCheatActionSpec(command: "set_desired", valueParam: "value")
        ),
        TrainerCheatDefinition(
            id: "moneyMultiplier",
            kind: .value,
            label: .key("hades2.feature.moneyMultiplier"),
            icon: TrainerSemanticIcon.Concept.currency,
            action: TrainerCheatActionSpec(command: "set_desired", valueParam: "value")
        ),
        TrainerCheatDefinition(
            id: "resourceMultiplier",
            kind: .value,
            label: .key("hades2.feature.resourceMultiplier"),
            icon: TrainerSemanticIcon.Section.inventory,
            action: TrainerCheatActionSpec(command: "set_desired", valueParam: "value")
        ),
        TrainerCheatDefinition(
            id: "health",
            kind: .value,
            label: .key("hades2.vital.health"),
            icon: TrainerSemanticIcon.Concept.vitality,
            action: TrainerCheatActionSpec(command: "set_vital", valueParam: "value")
        ),
        TrainerCheatDefinition(
            id: "mana",
            kind: .value,
            label: .key("hades2.vital.mana"),
            icon: TrainerSemanticIcon.Concept.energy,
            action: TrainerCheatActionSpec(command: "set_vital", valueParam: "value")
        ),
        TrainerCheatDefinition(
            id: "armor",
            kind: .value,
            label: .key("hades2.vital.armor"),
            icon: TrainerSemanticIcon.Concept.defense,
            action: TrainerCheatActionSpec(command: "set_vital", valueParam: "value")
        ),
        TrainerCheatDefinition(
            id: "runGold",
            kind: .value,
            label: .key("hades2.vital.runGold"),
            icon: TrainerSemanticIcon.Concept.currency,
            action: TrainerCheatActionSpec(command: "set_resource", valueParam: "amount")
        ),
        TrainerCheatDefinition(
            id: "rerolls",
            kind: .value,
            label: .key("hades2.metric.rerolls"),
            icon: TrainerSemanticIcon.Concept.randomize,
            action: TrainerCheatActionSpec(command: "set_rerolls", valueParam: "amount")
        ),
        TrainerCheatDefinition(
            id: "spellCharge",
            kind: .value,
            label: .key("hades2.metric.spellCharge"),
            icon: Hades2CheatIcon.spellCharge,
            action: TrainerCheatActionSpec(command: "set_counter", valueParam: "value")
        ),
        TrainerCheatDefinition(
            id: "biomeTime",
            kind: .value,
            label: .key("hades2.metric.biomeTime"),
            icon: TrainerSemanticIcon.Concept.timer,
            action: TrainerCheatActionSpec(command: "set_counter", valueParam: "value")
        ),
    ] + statDefinitions

    private static let lockDefinitions: [TrainerCheatDefinition] = [
        TrainerCheatDefinition(
            id: "healthLock",
            kind: .lock,
            label: .key("hades2.lock.health"),
            icon: TrainerSemanticIcon.Concept.vitality,
            action: TrainerCheatActionSpec(command: "lock_vital", valueParam: "locked")
        ),
        TrainerCheatDefinition(
            id: "manaLock",
            kind: .lock,
            label: .key("hades2.lock.mana"),
            icon: TrainerSemanticIcon.Concept.energy,
            action: TrainerCheatActionSpec(command: "lock_vital", valueParam: "locked")
        ),
        TrainerCheatDefinition(
            id: "armorLock",
            kind: .lock,
            label: .key("hades2.lock.armor"),
            icon: TrainerSemanticIcon.Concept.defense,
            action: TrainerCheatActionSpec(command: "lock_vital", valueParam: "locked")
        ),
        TrainerCheatDefinition(
            id: "moneyLock",
            kind: .lock,
            label: .key("hades2.lock.money"),
            icon: TrainerSemanticIcon.Concept.currency,
            action: TrainerCheatActionSpec(command: "lock_resource", valueParam: "locked")
        ),
        TrainerCheatDefinition(
            id: "rerollsLock",
            kind: .lock,
            label: .key("hades2.lock.rerolls"),
            icon: TrainerSemanticIcon.Concept.randomize,
            action: TrainerCheatActionSpec(command: "lock_rerolls", valueParam: "locked")
        ),
        TrainerCheatDefinition(
            id: "biomeTimeLock",
            kind: .lock,
            label: .key("hades2.lock.biomeTime"),
            icon: TrainerSemanticIcon.Concept.timer,
            action: TrainerCheatActionSpec(command: "lock_biome_time", valueParam: "locked")
        ),
    ]

    private static let oneShotDefinitions: [TrainerCheatDefinition] = [
        TrainerCheatDefinition(
            id: "matureGarden",
            kind: .oneShot,
            label: .key("hades2.garden.title"),
            help: .key("hades2.garden.help"),
            icon: Hades2CheatIcon.garden,
            action: TrainerCheatActionSpec(command: "mature_garden"),
            shortcutID: "matureGarden"
        ),
        TrainerCheatDefinition(
            id: "generateFlora",
            kind: .oneShot,
            label: .key("hades2.shortcut.generateFlora"),
            icon: Hades2CheatIcon.flora,
            action: TrainerCheatActionSpec(command: "generate_gathering"),
            shortcutID: "generateFlora"
        ),
        TrainerCheatDefinition(
            id: "generateMining",
            kind: .oneShot,
            label: .key("hades2.shortcut.generateMining"),
            icon: Hades2CheatIcon.mining,
            action: TrainerCheatActionSpec(command: "generate_gathering"),
            shortcutID: "generateMining"
        ),
        TrainerCheatDefinition(
            id: "generateDigging",
            kind: .oneShot,
            label: .key("hades2.shortcut.generateDigging"),
            icon: Hades2CheatIcon.digging,
            action: TrainerCheatActionSpec(command: "generate_gathering"),
            shortcutID: "generateDigging"
        ),
        TrainerCheatDefinition(
            id: "generateShades",
            kind: .oneShot,
            label: .key("hades2.shortcut.generateShades"),
            icon: Hades2CheatIcon.shades,
            action: TrainerCheatActionSpec(command: "generate_gathering"),
            shortcutID: "generateShades"
        ),
        TrainerCheatDefinition(
            id: "generateFishing",
            kind: .oneShot,
            label: .key("hades2.shortcut.generateFishing"),
            icon: Hades2CheatIcon.fishing,
            action: TrainerCheatActionSpec(command: "generate_gathering"),
            shortcutID: "generateFishing"
        ),
        TrainerCheatDefinition(
            id: "applyWorldExit",
            kind: .oneShot,
            label: .key("hades2.shortcut.applyWorldExit"),
            icon: Hades2CheatIcon.doorway,
            action: TrainerCheatActionSpec(command: "apply_world_exit"),
            shortcutID: "applyWorldExit",
            aliases: ["applyNextRoomReward"]
        ),
        TrainerCheatDefinition(
            id: "applyNextOccurrence",
            kind: .oneShot,
            label: .key("hades2.shortcut.applyNextOccurrence"),
            icon: Hades2CheatIcon.occurrence,
            action: TrainerCheatActionSpec(command: "apply_world_occurrence"),
            shortcutID: "applyNextOccurrence"
        ),
        TrainerCheatDefinition(
            id: "generateChamberFacility",
            kind: .oneShot,
            label: .key("hades2.facility.title"),
            icon: TrainerSemanticIcon.Action.generate,
            action: TrainerCheatActionSpec(command: "generate_chamber_facility"),
            shortcutID: "generateChamberFacility"
        ),
        TrainerCheatDefinition(
            id: "generateChaosGate",
            kind: .oneShot,
            label: .key("hades2.chaosGate.generate"),
            help: .key("hades2.chaosGate.generateHelp"),
            icon: Hades2CheatIcon.portal,
            action: TrainerCheatActionSpec(command: "generate_chaos_gate"),
            shortcutID: "generateChaosGate"
        ),
        TrainerCheatDefinition(
            id: "spawnReward",
            kind: .oneShot,
            label: .key("hades2.spawn.olympianBoons"),
            icon: TrainerSemanticIcon.Section.effects,
            action: TrainerCheatActionSpec(command: "spawn_reward")
        ),
        TrainerCheatDefinition(
            id: "acquireChaosPair",
            kind: .oneShot,
            label: .key("hades2.shortcut.acquireChaosPair"),
            icon: Hades2CheatIcon.portal,
            action: TrainerCheatActionSpec(command: "acquire_chaos_pair"),
            shortcutID: "acquireChaosPair"
        ),
        TrainerCheatDefinition(
            id: "openSellTraits",
            kind: .oneShot,
            label: .key("hades2.shortcut.openPurgingPool"),
            icon: Hades2CheatIcon.purge,
            action: TrainerCheatActionSpec(command: "open_sell_traits"),
            shortcutID: "openSellTraits"
        ),
        TrainerCheatDefinition(
            id: "disableAll",
            kind: .oneShot,
            label: .key("host.disableAll"),
            icon: TrainerSemanticIcon.Tool.disableAll,
            action: TrainerCheatActionSpec(command: "disable_all"),
            shortcutID: "disableAll"
        ),
    ]

    package static let catalog = TrainerCheatCatalog(
        definitions: commonToggleDefinitions
            + [boonToggleDefinitions[0], boonToggleDefinitions[1], boonToggleDefinitions[2]]
            + multiplierToggleDefinitions
            + valueDefinitions
            + lockDefinitions
            + oneShotDefinitions,
        retiredIDs: ["gardenQoL", "damageEnabled"]
    )

    package static func definition(id: String) -> TrainerCheatDefinition? {
        catalog.definition(id: id)
    }

    package static let legacyAliases: [String: String] = catalog.legacyAliasMap()
}
