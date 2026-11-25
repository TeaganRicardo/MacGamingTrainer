"""Declarative cheat catalog and bilingual label resolver for Hades II."""

from __future__ import annotations

import json
import re
from pathlib import Path

from core.cheats import (
    CheatBackendAction,
    CheatCatalog,
    CheatDefinition,
    CheatLabel,
)

from .terminology import TerminologyRegistry, load_hades2_terminology

_TERM_PATTERN = re.compile(r"\{term:([^}]+)\}")


def _localization_path(language: str, module_file: Path = Path(__file__)) -> Path:
    resource_root = module_file.resolve().parents[3]
    if resource_root.name == "Resources" and resource_root.parent.name == "Contents":
        return resource_root / "Modules" / "hades2" / f"hades2.{language}.json"
    return (
        resource_root
        / "Sources"
        / "Hades2"
        / "Presentation"
        / "Localization"
        / f"hades2.{language}.json"
    )


def _load_entries(language: str) -> dict[str, str]:
    payload = json.loads(_localization_path(language).read_text(encoding="utf-8"))
    return dict(payload["entries"])


def _resolve_terms(template: str, language: str, terminology: TerminologyRegistry) -> str:
    def replace(match: re.Match[str]) -> str:
        term = terminology.get(match.group(1))
        return term.english if language == "en" else term.zh_cn

    return _TERM_PATTERN.sub(replace, template)


def _build_catalog() -> CheatCatalog:
    zh_entries = _load_entries("zh-CN")
    en_entries = _load_entries("en")
    terminology = load_hades2_terminology()

    def label(key: str) -> CheatLabel:
        return CheatLabel(
            zh_cn=_resolve_terms(zh_entries[key], "zh-CN", terminology),
            en=_resolve_terms(en_entries[key], "en", terminology),
        )

    common_toggles = (
        CheatDefinition(
            id="invincibility",
            kind="toggle",
            label=label("hades2.feature.invincibility"),
            action=CheatBackendAction("set_desired", {"feature": "invincibility"}, "value"),
            shortcut_id="invincibility",
            aliases=("godMode",),
            default_value=False,
        ),
        CheatDefinition(
            id="infiniteHealth",
            kind="toggle",
            label=label("hades2.feature.infiniteHealth"),
            action=CheatBackendAction("set_desired", {"feature": "infiniteHealth"}, "value"),
            shortcut_id="infiniteHealth",
            default_value=False,
        ),
        CheatDefinition(
            id="infiniteMana",
            kind="toggle",
            label=label("hades2.feature.infiniteMana"),
            action=CheatBackendAction("set_desired", {"feature": "infiniteMana"}, "value"),
            shortcut_id="infiniteMana",
            default_value=False,
        ),
        CheatDefinition(
            id="infiniteMoney",
            kind="toggle",
            label=label("hades2.feature.infiniteMoney"),
            help_label=label("hades2.feature.infiniteMoney.help"),
            action=CheatBackendAction("set_desired", {"feature": "infiniteMoney"}, "value"),
            shortcut_id="infiniteMoney",
            default_value=False,
        ),
        CheatDefinition(
            id="infiniteRerolls",
            kind="toggle",
            label=label("hades2.feature.infiniteRerolls"),
            help_label=label("hades2.feature.infiniteRerolls.help"),
            action=CheatBackendAction("set_desired", {"feature": "infiniteRerolls"}, "value"),
            shortcut_id="infiniteRerolls",
            default_value=False,
        ),
        CheatDefinition(
            id="forceEnableRerolls",
            kind="toggle",
            label=label("hades2.feature.forceEnableRerolls"),
            action=CheatBackendAction("set_desired", {"feature": "forceEnableRerolls"}, "value"),
            shortcut_id="forceEnableRerolls",
            default_value=False,
        ),
        CheatDefinition(
            id="instantCastCooldown",
            kind="toggle",
            label=label("hades2.feature.instantCastCooldown"),
            action=CheatBackendAction("set_desired", {"feature": "instantCastCooldown"}, "value"),
            shortcut_id="instantCastCooldown",
            default_value=False,
        ),
        CheatDefinition(
            id="hexAlwaysReady",
            kind="toggle",
            label=label("hades2.feature.hexAlwaysReady"),
            action=CheatBackendAction("set_desired", {"feature": "hexAlwaysReady"}, "value"),
            shortcut_id="hexAlwaysReady",
            default_value=False,
        ),
        CheatDefinition(
            id="infiniteAmmo",
            kind="toggle",
            label=label("hades2.feature.infiniteAmmo"),
            action=CheatBackendAction("set_desired", {"feature": "infiniteAmmo"}, "value"),
            shortcut_id="infiniteAmmo",
            default_value=False,
        ),
        CheatDefinition(
            id="autoMiniGames",
            kind="toggle",
            label=label("hades2.feature.autoMiniGames"),
            action=CheatBackendAction("set_desired", {"feature": "autoMiniGames"}, "value"),
            shortcut_id="autoMiniGames",
            default_value=False,
        ),
    )

    boon_and_resource_toggles = (
        CheatDefinition(
            id="boonRarityEnabled",
            kind="toggle",
            label=label("hades2.feature.boonRarity"),
            action=CheatBackendAction("set_desired", {"feature": "boonRarityEnabled"}, "value"),
            shortcut_id="boonRarityEnabled",
            default_value=False,
        ),
        CheatDefinition(
            id="forceLegendary",
            kind="toggle",
            label=label("hades2.feature.forceLegendary"),
            action=CheatBackendAction("set_boon_rarity_desired", value_param="forceLegendary"),
            shortcut_id="forceLegendary",
            default_value=False,
        ),
        CheatDefinition(
            id="forceDuo",
            kind="toggle",
            label=label("hades2.feature.forceDuo"),
            action=CheatBackendAction("set_boon_rarity_desired", value_param="forceDuo"),
            shortcut_id="forceDuo",
            default_value=False,
        ),
        CheatDefinition(
            id="moneyMultiplierEnabled",
            kind="toggle",
            label=label("hades2.feature.moneyMultiplier"),
            action=CheatBackendAction("set_desired", {"feature": "moneyMultiplierEnabled"}, "value"),
            shortcut_id="moneyMultiplierEnabled",
            default_value=False,
        ),
        CheatDefinition(
            id="resourceMultiplierEnabled",
            kind="toggle",
            label=label("hades2.feature.resourceMultiplier"),
            action=CheatBackendAction("set_desired", {"feature": "resourceMultiplierEnabled"}, "value"),
            shortcut_id="resourceMultiplierEnabled",
            default_value=False,
        ),
    )

    values = (
        CheatDefinition(
            id="gameSpeed",
            kind="value",
            label=label("hades2.gameSpeed.title"),
            help_label=label("hades2.gameSpeed.hint"),
            action=CheatBackendAction("set_desired", {"feature": "gameSpeed"}, "value"),
            default_value=1.0,
        ),
        CheatDefinition(
            id="damageMultiplier",
            kind="value",
            label=label("hades2.feature.damageMultiplier"),
            action=CheatBackendAction("set_desired", {"feature": "damageMultiplier"}, "value"),
            default_value=1.0,
        ),
        CheatDefinition(
            id="moneyMultiplier",
            kind="value",
            label=label("hades2.feature.moneyMultiplier"),
            action=CheatBackendAction("set_desired", {"feature": "moneyMultiplier"}, "value"),
            default_value=2.0,
        ),
        CheatDefinition(
            id="resourceMultiplier",
            kind="value",
            label=label("hades2.feature.resourceMultiplier"),
            action=CheatBackendAction("set_desired", {"feature": "resourceMultiplier"}, "value"),
            default_value=2.0,
        ),
        CheatDefinition(
            id="health",
            kind="value",
            label=label("hades2.vital.health"),
            action=CheatBackendAction("set_vital", {"vital": "health"}, "value"),
        ),
        CheatDefinition(
            id="mana",
            kind="value",
            label=label("hades2.vital.mana"),
            action=CheatBackendAction("set_vital", {"vital": "mana"}, "value"),
        ),
        CheatDefinition(
            id="armor",
            kind="value",
            label=label("hades2.vital.armor"),
            action=CheatBackendAction("set_vital", {"vital": "armor"}, "value"),
        ),
        CheatDefinition(
            id="runGold",
            kind="value",
            label=label("hades2.vital.runGold"),
            action=CheatBackendAction("set_resource", {"resource": "Money"}, "amount"),
        ),
        CheatDefinition(
            id="rerolls",
            kind="value",
            label=label("hades2.metric.rerolls"),
            action=CheatBackendAction("set_rerolls", value_param="amount"),
        ),
        CheatDefinition(
            id="spellCharge",
            kind="value",
            label=label("hades2.metric.spellCharge"),
            action=CheatBackendAction("set_counter", {"counter": "spellCharge"}, "value"),
        ),
        CheatDefinition(
            id="biomeTime",
            kind="value",
            label=label("hades2.metric.biomeTime"),
            action=CheatBackendAction("set_counter", {"counter": "biomeTime"}, "value"),
        ),
        *(
            CheatDefinition(
                id=stat,
                kind="value",
                label=label(f"hades2.stat.{stat}"),
                action=CheatBackendAction("set_stat", {"stat": stat}, "value"),
            )
            for stat in (
                "grasp",
                "dodge",
                "crit",
                "enemyDamage",
                "enemyHealth",
                "chargeSpeed",
                "moveSpeed",
                "sprintSpeed",
                "dashSpeed",
                "attackSpeed",
                "manaRegen",
            )
        ),
    )

    locks = (
        CheatDefinition(
            id="healthLock",
            kind="lock",
            label=label("hades2.lock.health"),
            action=CheatBackendAction("lock_vital", {"vital": "health"}, "locked"),
        ),
        CheatDefinition(
            id="manaLock",
            kind="lock",
            label=label("hades2.lock.mana"),
            action=CheatBackendAction("lock_vital", {"vital": "mana"}, "locked"),
        ),
        CheatDefinition(
            id="armorLock",
            kind="lock",
            label=label("hades2.lock.armor"),
            action=CheatBackendAction("lock_vital", {"vital": "armor"}, "locked"),
        ),
        CheatDefinition(
            id="moneyLock",
            kind="lock",
            label=label("hades2.lock.money"),
            action=CheatBackendAction("lock_resource", {"resource": "Money"}, "locked"),
        ),
        CheatDefinition(
            id="rerollsLock",
            kind="lock",
            label=label("hades2.lock.rerolls"),
            action=CheatBackendAction("lock_rerolls", value_param="locked"),
        ),
        CheatDefinition(
            id="biomeTimeLock",
            kind="lock",
            label=label("hades2.lock.biomeTime"),
            action=CheatBackendAction("lock_biome_time", value_param="locked"),
        ),
    )

    one_shots = (
        CheatDefinition(
            id="matureGarden",
            kind="one_shot",
            label=label("hades2.garden.title"),
            help_label=label("hades2.garden.help"),
            action=CheatBackendAction("mature_garden"),
            shortcut_id="matureGarden",
        ),
        CheatDefinition(
            id="generateFlora",
            kind="one_shot",
            label=label("hades2.shortcut.generateFlora"),
            action=CheatBackendAction("generate_gathering", {"family": "flora"}),
            shortcut_id="generateFlora",
        ),
        CheatDefinition(
            id="generateMining",
            kind="one_shot",
            label=label("hades2.shortcut.generateMining"),
            action=CheatBackendAction("generate_gathering", {"family": "mining"}),
            shortcut_id="generateMining",
        ),
        CheatDefinition(
            id="generateDigging",
            kind="one_shot",
            label=label("hades2.shortcut.generateDigging"),
            action=CheatBackendAction("generate_gathering", {"family": "digging"}),
            shortcut_id="generateDigging",
        ),
        CheatDefinition(
            id="generateShades",
            kind="one_shot",
            label=label("hades2.shortcut.generateShades"),
            action=CheatBackendAction("generate_gathering", {"family": "shades"}),
            shortcut_id="generateShades",
        ),
        CheatDefinition(
            id="generateFishing",
            kind="one_shot",
            label=label("hades2.shortcut.generateFishing"),
            action=CheatBackendAction("generate_gathering", {"family": "fishing"}),
            shortcut_id="generateFishing",
        ),
        CheatDefinition(
            id="applyWorldExit",
            kind="one_shot",
            label=label("hades2.shortcut.applyWorldExit"),
            action=CheatBackendAction("apply_world_exit"),
            shortcut_id="applyWorldExit",
            aliases=("applyNextRoomReward",),
        ),
        CheatDefinition(
            id="applyNextOccurrence",
            kind="one_shot",
            label=label("hades2.shortcut.applyNextOccurrence"),
            action=CheatBackendAction("apply_world_occurrence"),
            shortcut_id="applyNextOccurrence",
        ),
        CheatDefinition(
            id="generateChamberFacility",
            kind="one_shot",
            label=label("hades2.facility.title"),
            action=CheatBackendAction("generate_chamber_facility"),
            shortcut_id="generateChamberFacility",
        ),
        CheatDefinition(
            id="generateChaosGate",
            kind="one_shot",
            label=label("hades2.chaosGate.generate"),
            help_label=label("hades2.chaosGate.generateHelp"),
            action=CheatBackendAction("generate_chaos_gate"),
            shortcut_id="generateChaosGate",
        ),
        CheatDefinition(
            id="spawnReward",
            kind="one_shot",
            label=label("hades2.spawn.olympianBoons"),
            action=CheatBackendAction("spawn_reward"),
        ),
        CheatDefinition(
            id="acquireChaosPair",
            kind="one_shot",
            label=label("hades2.shortcut.acquireChaosPair"),
            action=CheatBackendAction("acquire_chaos_pair"),
            shortcut_id="acquireChaosPair",
        ),
        CheatDefinition(
            id="openSellTraits",
            kind="one_shot",
            label=label("hades2.shortcut.openPurgingPool"),
            action=CheatBackendAction("open_sell_traits"),
            shortcut_id="openSellTraits",
        ),
        CheatDefinition(
            id="disableAll",
            kind="one_shot",
            label=CheatLabel(zh_cn="全部关闭", en="Disable All"),
            action=CheatBackendAction("disable_all"),
            shortcut_id="disableAll",
        ),
    )

    return CheatCatalog(
        common_toggles + boon_and_resource_toggles + values + locks + one_shots,
        retired_ids=("gardenQoL", "damageEnabled"),
    )


HADES2_CHEAT_CATALOG = _build_catalog()
