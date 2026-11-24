"""Declarative cheat catalog and runtime name mappings for Hades."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any

from core.cheats import (
    CheatBackendAction,
    CheatCatalog,
    CheatDefinition,
    CheatLabel,
)

HADES_CHEAT_CATALOG = CheatCatalog(
    (
        CheatDefinition(
            id="invincibility",
            kind="toggle",
            label=CheatLabel(zh_cn="无敌模式", en="Invincibility"),
            help_label=CheatLabel(
                zh_cn="跨房间保持无敌，保留游戏原有保护。",
                en="Keeps protection across rooms and preserves native protection.",
            ),
            action=CheatBackendAction("set_feature", {"feature": "invincibility"}, "value"),
            shortcut_id="invincibility",
            default_value=False,
        ),
        CheatDefinition(
            id="infiniteHealth",
            kind="toggle",
            label=CheatLabel(zh_cn="无限生命", en="Infinite Life"),
            help_label=CheatLabel(
                zh_cn="伤害结算时维持当前角色的生命上限；保留原生伤害记录。",
                en="Keeps the current hero at maximum life during damage resolution while preserving native damage records.",
            ),
            action=CheatBackendAction("set_feature", {"feature": "infiniteHealth"}, "value"),
            shortcut_id="infiniteHealth",
            aliases=("fullHealth",),
            default_value=False,
        ),
        CheatDefinition(
            id="infiniteMoney",
            kind="toggle",
            label=CheatLabel(zh_cn="无限金币", en="Infinite Gold"),
            help_label=CheatLabel(
                zh_cn="保留获得的增量，购买和使用仍按原生流程执行。",
                en="Keeps gains while purchases and use follow their native flow.",
            ),
            action=CheatBackendAction("set_feature", {"feature": "infiniteMoney"}, "value"),
            shortcut_id="infiniteMoney",
            aliases=("moneyNoDecrease",),
            default_value=False,
        ),
        CheatDefinition(
            id="infiniteRerolls",
            kind="toggle",
            label=CheatLabel(zh_cn="无限重骰", en="Infinite Rerolls"),
            help_label=CheatLabel(
                zh_cn="保留获得的增量，购买和使用仍按原生流程执行。",
                en="Keeps gains while purchases and use follow their native flow.",
            ),
            action=CheatBackendAction("set_feature", {"feature": "infiniteRerolls"}, "value"),
            shortcut_id="infiniteRerolls",
            aliases=("rerollsNoDecrease",),
            default_value=False,
        ),
        CheatDefinition(
            id="fullGodGauge",
            kind="toggle",
            label=CheatLabel(zh_cn="神力槽常满", en="Full God Gauge"),
            help_label=CheatLabel(
                zh_cn="援助可用时维持满槽，保留援助原有持续时间。",
                en="Keeps the gauge full when an Aid is available and preserves its native duration.",
            ),
            action=CheatBackendAction("set_feature", {"feature": "fullGodGauge"}, "value"),
            shortcut_id="fullGodGauge",
            default_value=False,
        ),
        CheatDefinition(
            id="infiniteAmmo",
            kind="toggle",
            label=CheatLabel(zh_cn="无限弹药", en="Infinite Ammo"),
            help_label=CheatLabel(
                zh_cn="使用后补满原生弹药，保留嵌入、装填、掉落和拾取的原生流程。",
                en="Refills native ammo after use while preserving stored Casts, loading, drops and pickups.",
            ),
            action=CheatBackendAction("set_feature", {"feature": "infiniteAmmo"}, "value"),
            shortcut_id="infiniteAmmo",
            default_value=False,
        ),
        CheatDefinition(
            id="forceEnableRerolls",
            kind="toggle",
            label=CheatLabel(zh_cn="强制重骰", en="Force Enable Rerolls"),
            help_label=CheatLabel(
                zh_cn="新建祝福、商店、出售面板与出口可使用对应重掷；保留禁止重掷、费用和出口资格，不改变黑夜之镜选择。",
                en="Enables rerolls on newly built boon, shop, purge menus and exits. Preserves blocked offers, costs and door eligibility without changing Mirror selections.",
            ),
            action=CheatBackendAction("set_feature", {"feature": "forceEnableRerolls"}, "value"),
            shortcut_id="forceEnableRerolls",
            aliases=("forceRerolls",),
            default_value=False,
        ),
        CheatDefinition(
            id="boonRarityEnabled",
            kind="toggle",
            label=CheatLabel(zh_cn="祝福稀有度控制", en="Boon Rarity Control"),
            help_label=CheatLabel(
                zh_cn="启用后，新生成或重掷的奥林匹斯和赫尔墨斯祝福至少达到所选稀有度；保留更高稀有度的原生概率、合法传奇、原生资格及强制普通规则。不改变混沌、锤子或已经生成的选项。",
                en="New or rerolled Olympian and Hermes offers meet the selected minimum rarity while preserving native higher-tier odds, eligible Legendary rolls, native availability and Force Common. Chaos, Hammers and existing offers are unchanged.",
            ),
            action=CheatBackendAction("set_feature", {"feature": "boonRarityEnabled"}, "value"),
            shortcut_id="boonRarityEnabled",
            default_value=False,
        ),
        CheatDefinition(
            id="gameSpeed",
            kind="value",
            label=CheatLabel(zh_cn="游戏速度", en="Game Speed"),
            action=CheatBackendAction("set_feature", {"feature": "gameSpeed"}, "value"),
            default_value=1.0,
        ),
        CheatDefinition(
            id="damageMultiplier",
            kind="value",
            label=CheatLabel(zh_cn="伤害倍率", en="Damage Multiplier"),
            action=CheatBackendAction("set_feature", {"feature": "damageMultiplier"}, "value"),
            default_value=1,
        ),
        CheatDefinition(
            id="incomingDamageMultiplier",
            kind="value",
            label=CheatLabel(zh_cn="受到伤害倍率", en="Incoming Damage Multiplier"),
            action=CheatBackendAction("set_feature", {"feature": "incomingDamageMultiplier"}, "value"),
            default_value=1,
        ),
        CheatDefinition(
            id="moveSpeedMultiplier",
            kind="value",
            label=CheatLabel(zh_cn="移动速度倍率", en="Move Speed Multiplier"),
            action=CheatBackendAction("set_feature", {"feature": "moveSpeedMultiplier"}, "value"),
            default_value=1,
        ),
        CheatDefinition(
            id="attackSpeedMultiplier",
            kind="value",
            label=CheatLabel(zh_cn="攻击速度倍率", en="Attack Speed Multiplier"),
            action=CheatBackendAction("set_feature", {"feature": "attackSpeedMultiplier"}, "value"),
            default_value=1,
        ),
        CheatDefinition(
            id="dashBonus",
            kind="value",
            label=CheatLabel(zh_cn="额外冲刺次数", en="Additional Dashes"),
            action=CheatBackendAction("set_feature", {"feature": "dashBonus"}, "value"),
            default_value=0,
        ),
        CheatDefinition(
            id="health",
            kind="value",
            label=CheatLabel(zh_cn="生命值", en="Life"),
            action=CheatBackendAction("set_value", {"field": "health"}, "value"),
        ),
        CheatDefinition(
            id="maxHealth",
            kind="value",
            label=CheatLabel(zh_cn="生命上限", en="Max Life"),
            action=CheatBackendAction("set_value", {"field": "maxHealth"}, "value"),
        ),
        CheatDefinition(
            id="money",
            kind="value",
            label=CheatLabel(zh_cn="卡戎金币", en="Charon’s Obol"),
            action=CheatBackendAction("set_value", {"field": "money"}, "value"),
        ),
        CheatDefinition(
            id="rerolls",
            kind="value",
            label=CheatLabel(zh_cn="重掷次数", en="Rerolls"),
            action=CheatBackendAction("set_value", {"field": "rerolls"}, "value"),
        ),
        CheatDefinition(
            id="godGauge",
            kind="value",
            label=CheatLabel(zh_cn="神力槽", en="God Gauge"),
            action=CheatBackendAction("set_value", {"field": "godGauge"}, "value"),
        ),
        CheatDefinition(
            id="healthLock",
            kind="lock",
            label=CheatLabel(zh_cn="锁定生命值", en="Lock Life"),
            action=CheatBackendAction("lock_vital", {"vital": "health"}, "locked"),
        ),
        CheatDefinition(
            id="moneyLock",
            kind="lock",
            label=CheatLabel(zh_cn="锁定金币", en="Lock Gold"),
            action=CheatBackendAction("lock_resource", {"resource": "Money"}, "locked"),
        ),
        CheatDefinition(
            id="rerollsLock",
            kind="lock",
            label=CheatLabel(zh_cn="锁定重掷次数", en="Lock Rerolls"),
            action=CheatBackendAction("lock_rerolls", value_param="locked"),
        ),
        CheatDefinition(
            id="generateFishing",
            kind="one_shot",
            label=CheatLabel(zh_cn="生成钓鱼点", en="Generate Fishing Point"),
            help_label=CheatLabel(
                zh_cn="在具备钓鱼资格及原生钓鱼点的房间内生成一次。保留原生钓鱼、渔获记录和兑换流程。",
                en="Generates once in an eligible room with a native fishing point. Fishing, catch records and turn-in follow the native flow.",
            ),
            action=CheatBackendAction("generate_fishing"),
            shortcut_id="generateFishing",
        ),
        CheatDefinition(
            id="generateChaosGate",
            kind="one_shot",
            label=CheatLabel(zh_cn="生成混沌之门", en="Generate Chaos Gate"),
            help_label=CheatLabel(
                zh_cn="在符合原生条件且有入口位置的房间内生成一次。进入时保留原生生命消耗和房间流程。",
                en="Generates once where native eligibility and entrance points permit it. Entry retains the native health cost and room flow.",
            ),
            action=CheatBackendAction("generate_chaos_gate"),
            shortcut_id="generateChaosGate",
        ),
        CheatDefinition(
            id="spawnReward",
            kind="one_shot",
            label=CheatLabel(zh_cn="生成奖励", en="Generate Reward"),
            action=CheatBackendAction("spawn_reward"),
        ),
        CheatDefinition(
            id="gainResource",
            kind="one_shot",
            label=CheatLabel(zh_cn="资源获取", en="Gain Resources"),
            action=CheatBackendAction("gain_resource"),
        ),
        CheatDefinition(
            id="disableAll",
            kind="one_shot",
            label=CheatLabel(zh_cn="禁用全部", en="Disable All"),
            action=CheatBackendAction("disable_all"),
            shortcut_id="disableAll",
        ),
    )
)

LEGACY_FEATURE_ALIASES: dict[str, str] = HADES_CHEAT_CATALOG.alias_map()
_CANONICAL_TO_RUNTIME_FEATURE: dict[str, str] = {
    canonical: legacy for legacy, canonical in LEGACY_FEATURE_ALIASES.items()
}


def to_runtime_feature(name: str) -> str:
    """Translate a canonical cheat id into the resident Hades Lua feature key."""

    return _CANONICAL_TO_RUNTIME_FEATURE.get(name, name)


def to_runtime_features(values: Mapping[str, Any], allowed_keys: Collection[str]) -> dict[str, Any]:
    """Build a resident-Lua feature dict from canonical feature preferences."""

    allowed = set(allowed_keys)
    return {
        to_runtime_feature(name): value
        for name, value in values.items()
        if name in allowed
    }


def from_runtime_feature_map(values: Mapping[str, Any], allowed_keys: Collection[str]) -> dict[str, Any]:
    """Translate resident-Lua feature state maps into canonical cheat keys."""

    allowed = set(allowed_keys)
    translated: dict[str, Any] = {}
    for runtime_key, value in values.items():
        canonical = HADES_CHEAT_CATALOG.resolve_id(runtime_key) or runtime_key
        if canonical in allowed:
            translated[canonical] = value
    return translated
