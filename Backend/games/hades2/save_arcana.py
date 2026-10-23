"""Native Arcana loadout ownership for permanent Save operations.

The supported-build manifest below owns card identities, costs and automatic
requirements. Native menus spend resources and mount runtime traits separately;
these edits change the durable loadout and its derived Save projections.
"""
import itertools
import json
import math

from . import save_advanced
from .localization import official_display_names
from .save_document import clone_lua_value, AmbiguousLuaKeyError, LuaTable


LAYOUT = (
    ("ChanneledCast", "HealthRegen", "LowManaDamageBonus", "CastCount", "SorceryRegenUpgrade"),
    ("CastBuff", "BonusHealth", "BonusDodge", "ManaOverTime", "MagicCrit"),
    ("SprintShield", "LastStand", "MaxHealthPerRoom", "StatusVulnerability", "ChanneledBlock"),
    ("DoorReroll", "StartingGold", "MetaToRunUpgrade", "RarityBoost", "BonusRarity"),
    ("TradeOff", "ScreenReroll", "LowHealthBonus", "EpicRarityBoost", "CardDraw"),
)
# MetaUpgradeData.lua, after native inheritance. BonusDodge's old automatic
# requirements are commented out in this build, so it remains a manual card.
CARDS = {
    "ChanneledCast": (1, None), "HealthRegen": (1, None),
    "LowManaDamageBonus": (2, None), "CastCount": (3, None),
    "SorceryRegenUpgrade": (0, "neighbor"), "CastBuff": (2, None),
    "BonusHealth": (2, None), "BonusDodge": (1, None), "ManaOverTime": (5, None),
    "MagicCrit": (2, None), "SprintShield": (1, None), "LastStand": (4, None),
    "MaxHealthPerRoom": (0, "costs1to5"), "StatusVulnerability": (5, None),
    "ChanneledBlock": (3, None), "DoorReroll": (3, None), "StartingGold": (5, None),
    "MetaToRunUpgrade": (3, None), "RarityBoost": (5, None),
    "BonusRarity": (0, "duplicates2"), "TradeOff": (0, "allNeighbors"),
    "ScreenReroll": (4, None), "LowHealthBonus": (4, None),
    "EpicRarityBoost": (0, "otherRowOrColumn"), "CardDraw": (0, "oneToThree"),
}
_MAX = 9_007_199_254_740_991
_CACHE_LABELS = {
    "MetaUpgradeUnlockedCountCache": ("Arcana unlocked count", "阿卡那牌已解锁数量"),
    "MetaUpgradeMaxLevelCountCache": ("Arcana maximum-level count", "阿卡那牌满级数量"),
    "MetaUpgradeCostCache": ("Arcana equipped cost", "阿卡那牌已装备消耗"),
    "MetaUpgradeLimitLevel": ("Grasp purchased level", "悟性已购等级"),
    "MaxMetaUpgradeCostCache": ("Grasp capacity", "悟性容量"),
    "MetaUpgradeCardLayout": ("Arcana card layout", "阿卡那牌布局"),
}


def cache_label(raw_id, language, game_path=None):
    if raw_id.startswith("AdjacencyBonuses:"):
        name = raw_id.split(":", 1)[1]
        title = official_display_names([name], language, game_path=game_path).get(name) or name
        return title + (" · 相邻效果倍率" if language == "zh-CN" else " · Adjacency multiplier")
    labels = _CACHE_LABELS.get(raw_id)
    return labels[1 if language == "zh-CN" else 0] if labels else None


def _table(owner, key, *, create=False):
    value = owner.get(key)
    if value is None:
        value = LuaTable()
        if create:
            owner[key] = value
    if not isinstance(value, LuaTable):
        raise ValueError("Save Editor semantic owner is unsupported.")
    return value


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _truth(value):
    return value is not None and value is not False


def _level(card):
    value = card.get("Level", 1)
    return int(value) if _number(value) and value >= 1 and int(value) == value else 1


def rows(root, language="zh-CN", game_path=None, *, include_absent=False):
    state = root["GameState"]
    container_state = None
    try:
        cards = _table(state, "MetaUpgradeState")
    except AmbiguousLuaKeyError:
        cards, container_state = LuaTable(), "ambiguous"
    except ValueError:
        cards, container_state = LuaTable(), "unsupported"
    try:
        for key in _CACHE_LABELS:
            state.get(key)
    except AmbiguousLuaKeyError:
        container_state = "ambiguous"
    names = {name for name, _ in cards.entries() if isinstance(name, str)}
    if include_absent:
        names.update(CARDS)
    native = official_display_names(names, language, game_path=game_path)
    english = native if language == "en" else official_display_names(names, "en", game_path=game_path)
    zh = language == "zh-CN"
    result = []
    for name in sorted(names):
        owner_state = container_state if name in CARDS else None
        try:
            card = _table(cards, name)
        except AmbiguousLuaKeyError:
            card, owner_state = LuaTable(), "ambiguous"
        except ValueError:
            card, owner_state = LuaTable(), "unsupported"
        title = native.get(name) or ("阿卡那牌 · " if zh else "Arcana · ") + name
        en = english.get(name) or "Arcana · " + name
        for field, labels, kind in (
            ("Unlocked", ("已解锁", "Unlocked"), "boolean"),
            ("Level", ("等级", "Level"), "integer"),
            ("Equipped", ("已装备", "Equipped"), "boolean"),
        ):
            field_state = owner_state
            if name not in CARDS and field not in card:
                continue
            try:
                raw = card.get(field, 1 if field == "Level" else False)
                if name not in CARDS:
                    kind = save_advanced.value_type(raw)
                    if kind in ("table", "unsupported", "nil") or (kind == "number" and not _number(raw)):
                        # Structured/encoded data remains addressable through
                        # Advanced; scalar rows must always serialize as JSON.
                        continue
                    if kind == "number" and int(raw) == raw and -_MAX <= raw <= _MAX:
                        kind = "integer"
                    value = raw
                elif isinstance(raw, LuaTable):
                    # The native child field itself is uniquely addressable;
                    # an explicit scalar intent can replace an invalid value.
                    value = None if field == "Level" else _truth(raw)
                else:
                    value = _level(card) if field == "Level" else _truth(raw)
            except AmbiguousLuaKeyError:
                value, field_state = None, "ambiguous"
            row = {
                "id": "card:{}:{}".format(name, field), "domain": "progression",
                "rawId": name, "path": ["GameState", "MetaUpgradeState", name, field],
                "name": title + " · " + labels[0 if zh else 1],
                "englishName": en + " · " + labels[1], "value": value,
                "valueType": kind, "editable": field_state is None,
                "mutationKinds": ["set"] if field_state is None else [],
                "choices": [False, True] if kind == "boolean" else [],
                "group": "阿卡那牌" if zh else "Arcana", "entityId": "arcana:" + name,
                "entityName": title,
            }
            if field_state:
                row.update(ownerState=field_state, blockReasonCode=(
                    "ambiguousOwner" if field_state == "ambiguous" else "unsupportedOwner"))
            if name not in CARDS:
                row["warning"] = save_advanced.warning(language)
                row["rawTyped"] = True
                if kind == "integer":
                    row["constraints"] = {"min": -_MAX, "max": _MAX, "integer": True}
            elif field == "Level":
                row["constraints"] = {"min": 1, "max": 3, "integer": True}
            result.append(row)
    return result


def apply_intent(root, intent):
    _, name, field = intent["id"].split(":", 2)
    cards = _table(root["GameState"], "MetaUpgradeState", create=True)
    if name not in CARDS and name not in cards:
        raise ValueError("Save Editor Arcana card identity is invalid.")
    card = _table(cards, name, create=True)
    after = intent["after"]
    if name not in CARDS:
        # The physical fields are writable, but unknown native metadata cannot
        # authorize invented unlocks, costs or runtime effects.
        card[field] = after
        return
    if field == "Unlocked" and not after:
        card.pop("Unlocked", None)
        card.pop("Equipped", None)
        card["Level"] = 1
    elif field in ("Unlocked", "Equipped"):
        if after:
            card[field] = card["Unlocked"] = True
        else:
            card.pop(field, None)
    elif field == "Level":
        card[field] = after
        if after > 1:
            card["Unlocked"] = True
    else:
        raise ValueError("Save Editor Arcana field is not editable.")
    if card.get("Level") is None:
        card["Level"] = 1


def _layout(state):
    value = state.get("MetaUpgradeCardLayout")
    if value is None:
        value = LuaTable(5, 0, [(index, LuaTable(5, 0, list(enumerate(row, 1))))
                               for index, row in enumerate(LAYOUT, 1)])
        state["MetaUpgradeCardLayout"] = value
    if not isinstance(value, LuaTable):
        raise ValueError("Save Editor semantic owner is unsupported.")
    result, seen = [], set()
    for row in range(1, 6):
        line = value.get(row)
        if not isinstance(line, LuaTable):
            raise ValueError("Save Editor semantic owner is unsupported.")
        result.append([])
        for column in range(1, 6):
            name = line.get(column)
            if not isinstance(name, str) or name in seen:
                raise ValueError("Save Editor semantic owner is ambiguous.")
            seen.add(name)
            result[-1].append(name)
    return result


def _automatic(cards, layout, manual):
    unlocked = manual | {name for name in CARDS if isinstance(cards.get(name), LuaTable)
                         and _truth(cards[name].get("Unlocked"))}
    equipped = manual | {name for name in CARDS if CARDS[name][1]
                         and name in cards and _truth(cards[name].get("Equipped"))}
    coords = {name: (r, c) for r, row in enumerate(layout) for c, name in enumerate(row)}
    unlocked.update(name for name in coords if name not in CARDS
                    and isinstance(cards.get(name), LuaTable) and _truth(cards[name].get("Unlocked")))
    zoom = max([3] + [min(5, max(r, c) + 2) for name, (r, c) in coords.items() if name in unlocked])
    counts = {}
    for name in manual:
        if name in CARDS and not CARDS[name][1]:
            cost = CARDS[name][0]
            counts[cost] = counts.get(cost, 0) + 1

    def eligible(name, equipped):
        rule = CARDS[name][1]
        if rule == "costs1to5":
            return all(counts.get(cost) for cost in range(1, 6))
        if rule == "duplicates2":
            return bool(counts) and max(counts.values()) <= 2
        if rule == "oneToThree":
            return 1 <= sum(counts.values()) <= 3
        if name not in coords:
            return False
        r, c = coords[name]
        neighbors = [layout[i][j] for i in range(max(0, r - 1), min(5, r + 2))
                     for j in range(max(0, c - 1), min(5, c + 2)) if (i, j) != (r, c)]
        if rule == "neighbor":
            return any(other in equipped for other in neighbors)
        if rule == "allNeighbors":
            return all(other in equipped for other in neighbors)
        return any(all(layout[i][j] in equipped for j in range(zoom))
                   for i in range(zoom) if i != r) or any(
            all(layout[i][j] in equipped for i in range(zoom))
            for j in range(zoom) if j != c)

    # Native CheckAutoEquipCards collects a snapshot before assigning results;
    # UpdateMetaUpgradeCardState explicitly invokes that snapshot pass twice.
    for _ in range(2):
        changes = {name: eligible(name, equipped) for name in CARDS
                   if CARDS[name][1] and name in unlocked}
        equipped = (equipped - set(changes)) | {name for name, value in changes.items() if value}
    return equipped


def _choose_manual(cards, layout, own, manual):
    """Resolve an activation intent without overriding explicit card choices.

    There are nineteen native manual cards. Search by changed selection count,
    then added unlock count, total cost, and native manifest order. The bounded
    candidate space makes the tie-break independent of Lua/Python table order.
    """
    explicit = {tuple(intent["id"].split(":")[1:]): intent["after"] for intent in own}
    wanted = {name: value for (name, field), value in explicit.items()
              if field == "Equipped" and name in CARDS and CARDS[name][1]}
    if any(value and explicit.get((name, "Unlocked")) is False for name, value in wanted.items()):
        raise ValueError("Save Editor Arcana changes conflict.")
    fixed = {name: value for (name, field), value in explicit.items()
             if field == "Equipped" and name in CARDS and not CARDS[name][1]}
    for (name, field), value in explicit.items():
        if field == "Unlocked" and value is False and name in CARDS and not CARDS[name][1]:
            if fixed.get(name) is True:
                raise ValueError("Save Editor Arcana changes conflict.")
            fixed[name] = False
    coordinates = {name for line in layout for name in line}
    if any(value and CARDS[name][1] in ("neighbor", "allNeighbors", "otherRowOrColumn")
           and name not in coordinates for name, value in wanted.items()):
        raise ValueError("Save Editor Arcana changes conflict.")
    if wanted.get("MaxHealthPerRoom") and wanted.get("CardDraw"):
        raise ValueError("Save Editor Arcana changes conflict.")
    known_manual = [name for row in LAYOUT for name in row if not CARDS[name][1]]
    if wanted.get("MaxHealthPerRoom") and any(not any(
        CARDS[name][0] == cost and fixed.get(name) is not False for name in known_manual
    ) for cost in range(1, 6)):
        raise ValueError("Save Editor Arcana changes conflict.")
    if sum(CARDS[name][0] for name, value in fixed.items() if value) > 30:
        raise ValueError("Save Editor Arcana changes conflict.")
    free = [name for name in known_manual if name not in fixed]
    initial = (manual - set(fixed)) | {name for name, value in fixed.items() if value}
    for distance in range(len(free) + 1):
        best = None
        for flips in itertools.combinations(range(len(free)), distance):
            selected = initial.symmetric_difference(free[index] for index in flips)
            cost = sum(CARDS[name][0] for name in selected if name in CARDS)
            if cost > 30:
                continue
            counts = {}
            for name in selected:
                if name in CARDS:
                    counts[CARDS[name][0]] = counts.get(CARDS[name][0], 0) + 1
            if wanted.get("MaxHealthPerRoom") and not all(counts.get(cost) for cost in range(1, 6)):
                continue
            if wanted.get("CardDraw") and not 1 <= sum(counts.values()) <= 3:
                continue
            if wanted.get("BonusRarity") and (not counts or max(counts.values()) > 2):
                continue
            equipped = _automatic(cards, layout, selected)
            if any((name in equipped) != value for name, value in wanted.items()):
                continue
            unlocks = sum(not isinstance(cards.get(name), LuaTable)
                          or not _truth(cards[name].get("Unlocked")) for name in selected if name in CARDS)
            rank = (unlocks, cost, flips)
            if best is None or rank < best[0]:
                best = rank, selected, equipped
        if best is not None:
            return best[1:]
    raise ValueError("Save Editor Arcana changes conflict.")


def finalize_batch(root, intents, source=None):
    own = [intent for intent in intents if intent["id"].startswith("card:")
           and intent["id"].split(":")[1] in CARDS]
    if not own:
        return
    state = root["GameState"]
    cards = _table(state, "MetaUpgradeState", create=True)
    manual = {name for name, card in cards.entries() if isinstance(card, LuaTable)
              and _truth(card.get("Equipped")) and (name not in CARDS or not CARDS[name][1])}
    loadout_change = source is None or any(not intent["id"].endswith(":Level") for intent in own)
    if not loadout_change:
        original = _table(source["GameState"], "MetaUpgradeState")
        loadout_change = any(intent["after"] > 1 and not _truth(
            _table(original, intent["id"].split(":")[1]).get("Unlocked")) for intent in own)
    if loadout_change:
        layout = _layout(state)
        manual, equipped = _choose_manual(cards, layout, own, manual)
        for name in manual:
            if name in CARDS:
                card = _table(cards, name, create=True)
                card["Unlocked"] = True
                if card.get("Level") is None:
                    card["Level"] = 1
        for name, card in cards.entries():
            if name not in CARDS or not isinstance(card, LuaTable):
                continue
            if name in equipped:
                card["Equipped"] = True
            else:
                card.pop("Equipped", None)
            bonuses = card.get("AdjacencyBonuses")
            if isinstance(bonuses, LuaTable):
                bonuses.pop("CustomMultiplier", None)
    else:
        equipped = manual | {name for name in CARDS if CARDS[name][1]
                             and isinstance(cards.get(name), LuaTable) and _truth(cards[name].get("Equipped"))}
    cost = sum(CARDS[name][0] for name in equipped if name in CARDS)
    level = state.get("MetaUpgradeLimitLevel", 0)
    level = int(level) if _number(level) and level >= 0 and int(level) == level else 0
    capacity = lambda tier: 10 + min(tier, 5) * 2 + max(0, min(tier, 15) - 5)
    while loadout_change and capacity(level) < cost and level < 15:
        level += 1
    if loadout_change and capacity(level) < cost:
        raise ValueError("Save Editor Arcana changes conflict.")
    if level or "MetaUpgradeLimitLevel" in state:
        state["MetaUpgradeLimitLevel"] = level
    state["MaxMetaUpgradeCostCache"] = capacity(level)
    state["MetaUpgradeCostCache"] = cost
    state["MetaUpgradeUnlockedCountCache"] = sum(
        isinstance(cards.get(name), LuaTable) and _truth(cards[name].get("Unlocked")) for name in CARDS)
    state["MetaUpgradeMaxLevelCountCache"] = sum(
        isinstance(cards.get(name), LuaTable) and _level(cards[name]) >= 3 for name in CARDS)


def validate_batch(root, intents):
    if not any(intent["id"].startswith("card:") for intent in intents):
        return
    cards = _table(root["GameState"], "MetaUpgradeState")
    for intent in intents:
        if not intent["id"].startswith("card:"):
            continue
        _, name, field = intent["id"].split(":", 2)
        card = cards[name]
        actual = (card.get(field) if name not in CARDS else
                  _level(card) if field == "Level" else _truth(card.get(field)))
        if actual != intent["after"]:
            raise ValueError("Save Editor Arcana changes conflict.")


def linked_changes(root, intents):
    own = [intent for intent in intents if intent["id"].startswith("card:")]
    if not own:
        return []
    candidate = clone_lua_value(root)
    for intent in sorted(own, key=lambda item: item["id"]):
        apply_intent(candidate, intent)
    finalize_batch(candidate, own, source=root)
    before = _table(root["GameState"], "MetaUpgradeState")
    after = _table(candidate["GameState"], "MetaUpgradeState")
    direct = {intent["id"] for intent in own}
    result = []
    for name, card in after.entries():
        if name not in CARDS or not isinstance(card, LuaTable):
            continue
        previous = _table(before, name)
        for field in ("Unlocked", "Equipped", "Level"):
            identity = "card:{}:{}".format(name, field)
            old = _level(previous) if field == "Level" else _truth(previous.get(field))
            new = _level(card) if field == "Level" else _truth(card.get(field))
            if old != new and identity not in direct:
                result.append({"id": "linked:" + identity, "domain": "progression",
                    "rawId": name, "name": "Arcana " + field + " · " + name,
                    "operation": "set", "before": old, "after": new})
        old_bonus, new_bonus = previous.get("AdjacencyBonuses"), card.get("AdjacencyBonuses")
        old = old_bonus.get("CustomMultiplier") if isinstance(old_bonus, LuaTable) else None
        new = new_bonus.get("CustomMultiplier") if isinstance(new_bonus, LuaTable) else None
        if old is not None and new is None:
            key = "AdjacencyBonuses:" + name
            effect = {"id": "linked:arcanaCache:" + key, "domain": "progression", "rawId": key,
                "name": cache_label(key, "en"), "operation": "set", "before": old, "after": None}
            if isinstance(old, LuaTable):
                effect["before"] = save_advanced.typed_value(old)
                effect["beforeDisplay"] = json.dumps(effect["before"], ensure_ascii=False)
            result.append(effect)
    for key in _CACHE_LABELS:
        old, new = root["GameState"].get(key), candidate["GameState"].get(key)
        if (
            (type(old) is type(new) or (_number(old) and _number(new))) and old == new
        ):
            continue
        effect = {"id": "linked:arcanaCache:" + key, "domain": "progression", "rawId": key,
            "name": cache_label(key, "en"), "operation": "set",
            "before": save_advanced.json_value(old), "after": save_advanced.json_value(new)}
        if isinstance(old, LuaTable) or (_number(old) is False and type(old) is float):
            effect["beforeDisplay"] = json.dumps(save_advanced.typed_value(old), ensure_ascii=False)
        if isinstance(new, LuaTable):
            effect["afterDisplay"] = json.dumps(save_advanced.typed_value(new), ensure_ascii=False)
        result.append(effect)
    return result
