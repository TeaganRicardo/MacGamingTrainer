import Foundation
import TrainerCore

package enum HadesCheatIcon {
    package static let godGauge = "bolt.heart.fill"
    package static let fishing = "fish.fill"
    package static let portal = "circle.hexagongrid.fill"
}

package enum HadesCheatCatalog {
    package static let catalog = TrainerCheatCatalog(
        definitions: [
            TrainerCheatDefinition(
                id: "invincibility",
                kind: .toggle,
                label: .key("hades.invincibility"),
                help: .key("hades.invincibilityHelp"),
                icon: TrainerSemanticIcon.Concept.protection,
                action: TrainerCheatActionSpec(command: "set_feature", valueParam: "value"),
                shortcutID: "invincibility"
            ),
            TrainerCheatDefinition(
                id: "infiniteHealth",
                kind: .toggle,
                label: .key("hades.infiniteHealth"),
                help: .key("hades.infiniteHealthHelp"),
                icon: TrainerSemanticIcon.Concept.vitality,
                action: TrainerCheatActionSpec(command: "set_feature", valueParam: "value"),
                shortcutID: "infiniteHealth",
                aliases: ["fullHealth"]
            ),
            TrainerCheatDefinition(
                id: "infiniteMoney",
                kind: .toggle,
                label: .key("hades.infiniteMoney"),
                help: .key("hades.noConsumptionHelp"),
                icon: TrainerSemanticIcon.Concept.currency,
                action: TrainerCheatActionSpec(command: "set_feature", valueParam: "value"),
                shortcutID: "infiniteMoney",
                aliases: ["moneyNoDecrease"]
            ),
            TrainerCheatDefinition(
                id: "infiniteRerolls",
                kind: .toggle,
                label: .key("hades.infiniteRerolls"),
                help: .key("hades.noConsumptionHelp"),
                icon: TrainerSemanticIcon.Concept.randomize,
                action: TrainerCheatActionSpec(command: "set_feature", valueParam: "value"),
                shortcutID: "infiniteRerolls",
                aliases: ["rerollsNoDecrease"]
            ),
            TrainerCheatDefinition(
                id: "fullGodGauge",
                kind: .toggle,
                label: .key("hades.fullGodGauge"),
                help: .key("hades.fullGodGaugeHelp"),
                icon: HadesCheatIcon.godGauge,
                action: TrainerCheatActionSpec(command: "set_feature", valueParam: "value"),
                shortcutID: "fullGodGauge"
            ),
            TrainerCheatDefinition(
                id: "infiniteAmmo",
                kind: .toggle,
                label: .key("hades.infiniteAmmo"),
                help: .key("hades.infiniteAmmoHelp"),
                icon: TrainerSemanticIcon.Concept.capacity,
                action: TrainerCheatActionSpec(command: "set_feature", valueParam: "value"),
                shortcutID: "infiniteAmmo"
            ),
            TrainerCheatDefinition(
                id: "forceEnableRerolls",
                kind: .toggle,
                label: .key("hades.forceEnableRerolls"),
                help: .key("hades.forceEnableRerollsHelp"),
                icon: TrainerSemanticIcon.Concept.refresh,
                action: TrainerCheatActionSpec(command: "set_feature", valueParam: "value"),
                shortcutID: "forceEnableRerolls",
                aliases: ["forceRerolls"]
            ),
            TrainerCheatDefinition(
                id: "boonRarityEnabled",
                kind: .toggle,
                label: .key("hades.boonRarityEnabled"),
                help: .key("hades.boonRarityHelp"),
                icon: TrainerSemanticIcon.Concept.quality,
                action: TrainerCheatActionSpec(command: "set_feature", valueParam: "value"),
                shortcutID: "boonRarityEnabled"
            ),
            TrainerCheatDefinition(
                id: "gameSpeed",
                kind: .value,
                label: .key("hades.gameSpeed"),
                icon: TrainerSemanticIcon.Concept.timeScale,
                action: TrainerCheatActionSpec(command: "set_feature", valueParam: "value")
            ),
            TrainerCheatDefinition(
                id: "damageMultiplier",
                kind: .value,
                label: .key("hades.damageMultiplier"),
                icon: TrainerSemanticIcon.Concept.impact,
                action: TrainerCheatActionSpec(command: "set_feature", valueParam: "value")
            ),
            TrainerCheatDefinition(
                id: "incomingDamageMultiplier",
                kind: .value,
                label: .key("hades.incomingDamageMultiplier"),
                icon: TrainerSemanticIcon.Concept.defense,
                action: TrainerCheatActionSpec(command: "set_feature", valueParam: "value")
            ),
            TrainerCheatDefinition(
                id: "moveSpeedMultiplier",
                kind: .value,
                label: .key("hades.moveSpeedMultiplier"),
                icon: TrainerSemanticIcon.Concept.movement,
                action: TrainerCheatActionSpec(command: "set_feature", valueParam: "value")
            ),
            TrainerCheatDefinition(
                id: "attackSpeedMultiplier",
                kind: .value,
                label: .key("hades.attackSpeedMultiplier"),
                icon: TrainerSemanticIcon.Concept.actionSpeed,
                action: TrainerCheatActionSpec(command: "set_feature", valueParam: "value")
            ),
            TrainerCheatDefinition(
                id: "dashBonus",
                kind: .value,
                label: .key("hades.dashBonus"),
                icon: TrainerSemanticIcon.Concept.dash,
                action: TrainerCheatActionSpec(command: "set_feature", valueParam: "value")
            ),
            TrainerCheatDefinition(
                id: "health",
                kind: .value,
                label: .key("hades.health"),
                icon: TrainerSemanticIcon.Concept.vitality,
                action: TrainerCheatActionSpec(command: "set_value", valueParam: "value")
            ),
            TrainerCheatDefinition(
                id: "maxHealth",
                kind: .value,
                label: .key("hades.maxHealth"),
                icon: TrainerSemanticIcon.Concept.vitality,
                action: TrainerCheatActionSpec(command: "set_value", valueParam: "value")
            ),
            TrainerCheatDefinition(
                id: "money",
                kind: .value,
                label: .key("hades.money"),
                icon: TrainerSemanticIcon.Concept.currency,
                action: TrainerCheatActionSpec(command: "set_value", valueParam: "value")
            ),
            TrainerCheatDefinition(
                id: "rerolls",
                kind: .value,
                label: .key("hades.rerolls"),
                icon: TrainerSemanticIcon.Concept.randomize,
                action: TrainerCheatActionSpec(command: "set_value", valueParam: "value")
            ),
            TrainerCheatDefinition(
                id: "godGauge",
                kind: .value,
                label: .key("hades.godGauge"),
                icon: HadesCheatIcon.godGauge,
                action: TrainerCheatActionSpec(command: "set_value", valueParam: "value")
            ),
            TrainerCheatDefinition(
                id: "healthLock",
                kind: .lock,
                label: .bilingual(TrainerCheatText(zhCN: "锁定生命值", en: "Lock Life")),
                icon: TrainerSemanticIcon.Concept.vitality,
                action: TrainerCheatActionSpec(command: "lock_vital", valueParam: "locked")
            ),
            TrainerCheatDefinition(
                id: "moneyLock",
                kind: .lock,
                label: .bilingual(TrainerCheatText(zhCN: "锁定金币", en: "Lock Gold")),
                icon: TrainerSemanticIcon.Concept.currency,
                action: TrainerCheatActionSpec(command: "lock_resource", valueParam: "locked")
            ),
            TrainerCheatDefinition(
                id: "rerollsLock",
                kind: .lock,
                label: .bilingual(TrainerCheatText(zhCN: "锁定重掷次数", en: "Lock Rerolls")),
                icon: TrainerSemanticIcon.Concept.randomize,
                action: TrainerCheatActionSpec(command: "lock_rerolls", valueParam: "locked")
            ),
            TrainerCheatDefinition(
                id: "generateFishing",
                kind: .oneShot,
                label: .key("hades.generateFishing"),
                help: .key("hades.fishingHelp"),
                icon: HadesCheatIcon.fishing,
                action: TrainerCheatActionSpec(command: "generate_fishing"),
                shortcutID: "generateFishing"
            ),
            TrainerCheatDefinition(
                id: "generateChaosGate",
                kind: .oneShot,
                label: .key("hades.generateChaosGate"),
                help: .key("hades.chaosGateHelp"),
                icon: HadesCheatIcon.portal,
                action: TrainerCheatActionSpec(command: "generate_chaos_gate"),
                shortcutID: "generateChaosGate"
            ),
            TrainerCheatDefinition(
                id: "spawnReward",
                kind: .oneShot,
                label: .key("hades.spawnReward"),
                icon: TrainerSemanticIcon.Section.effects,
                action: TrainerCheatActionSpec(command: "spawn_reward")
            ),
            TrainerCheatDefinition(
                id: "gainResource",
                kind: .oneShot,
                label: .key("hades.gainResource"),
                icon: TrainerSemanticIcon.Action.acquire,
                action: TrainerCheatActionSpec(command: "gain_resource")
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
    )

    package static func definition(id: String) -> TrainerCheatDefinition? {
        catalog.definition(id: id)
    }

    package static let legacyAliases: [String: String] = catalog.legacyAliasMap()
}
