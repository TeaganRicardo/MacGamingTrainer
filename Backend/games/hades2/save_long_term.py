"""Source-verified relationship and long-term progression save descriptors.

Gift history combines purchased quantities, ordered gifts, dialogue records,
and game-triggered side effects; it is inspectable but not safely synthesizable.
Arcana changes preserve unlocked/equipped/level invariants.
"""

from .localization import official_display_names
from .save_document import LuaTable

_MAX = 9_007_199_254_740_991
_ARCANA_CARDS = frozenset((
    "ChanneledCast", "HealthRegen", "LowManaDamageBonus", "CastCount",
    "SorceryRegenUpgrade", "CastBuff", "BonusHealth", "BonusDodge",
    "ManaOverTime", "MagicCrit", "SprintShield", "LastStand",
    "MaxHealthPerRoom", "StatusVulnerability", "ChanneledBlock",
    "DoorReroll", "StartingGold", "MetaToRunUpgrade", "RarityBoost",
    "BonusRarity", "TradeOff", "ScreenReroll", "LowHealthBonus",
    "EpicRarityBoost", "CardDraw",
))
# Confirmed against MetaUpgradeCardData.UpgradeResourceCost in target build
# 1.143476 / 25481925. Each card has two upgrade purchases, hence levels 1..3.
_ARCANA_MAX_LEVEL = 3


def _state(root):
    state = root["GameState"]
    if not isinstance(state, LuaTable):
        raise ValueError("Save Editor GameState is malformed.")
    return state


def _table(state, field):
    value = state.get(field)
    if not isinstance(value, LuaTable):
        raise ValueError("Save Editor {} is unavailable or malformed.".format(field))
    return value


def _integer(value):
    return (type(value) in (float, int) and
            0 <= value <= _MAX and
            float(value).is_integer())


def _display(ids, language, game_path):
    native = official_display_names(ids, language, game_path=game_path)
    en = native if language == "en" else official_display_names(ids, "en", game_path=game_path)
    return native, en


def _row(entry_id, domain, raw_id, path, label, en, value, value_type,
         *, group, editable=True, maximum=_MAX):
    result = {
        "id": entry_id, "domain": domain, "rawId": raw_id, "path": path,
        "name": label, "englishName": en, "value": value,
        "valueType": value_type, "editable": editable,
        "mutationKinds": ["set"] if editable else [],
        "group": group,
        "choices": [False, True] if value_type == "boolean" else [],
    }
    if value_type == "integer":
        result["constraints"] = {"min": 0 if not entry_id.startswith("card:") else 1,
                                 "max": maximum, "integer": True}
    return result


def rows(root, domain, language="zh-CN", game_path=None):
    state = _state(root)
    result = []
    zh = language == "zh-CN"
    if domain == "relationships":
        interaction = state.get("NPCInteractions")
        if isinstance(interaction, LuaTable):
            names = [key for key, _ in interaction.entries() if isinstance(key, str)]
            native, en = _display(names, language, game_path)
            for name in names:
                value = interaction[name]
                if not _integer(value):
                    continue
                title = native.get(name) or name
                english = en.get(name) or name
                result.append(_row(
                    "interaction:" + name, domain, name,
                    ["GameState", "NPCInteractions", name],
                    ("互动次数 · " if zh else "Interactions · ") + title,
                    "Interactions · " + english, int(value), "integer",
                    group="角色互动" if zh else "Character interactions",
                ))

        special = state.get("SpecialInteractRecord")
        if isinstance(special, LuaTable):
            names = [name for name, _ in special.entries() if isinstance(name, str)]
            native, en = _display(names, language, game_path)
            for name in names:
                value = special[name]
                if not _integer(value):
                    continue
                result.append(_row(
                    "specialInteraction:" + name, domain, name,
                    ["GameState", "SpecialInteractRecord", name],
                    ("特殊互动次数 · " if zh else "Special interactions · ") +
                        (native.get(name) or name),
                    "Special interactions · " + (en.get(name) or name),
                    int(value), "integer",
                    group="角色互动" if zh else "Character interactions",
                ))

        gift_record = state.get("GiftRecord")
        gift_totals = state.get("GiftResourceRecord")
        if isinstance(gift_record, LuaTable) and isinstance(gift_totals, LuaTable):
            names = [key for key, value in gift_record.entries()
                     if isinstance(key, str) and isinstance(value, LuaTable)]
            resources = {key for _, record in gift_record.entries()
                         if isinstance(record, LuaTable)
                         for key, _ in record.entries() if isinstance(key, str)}
            native, en = _display(set(names) | resources, language, game_path)
            for person in names:
                record = gift_record[person]
                # Gift counts include quantities, while array entries record
                # gift events. Changing either without the actual conversation
                # and gift outcome would fabricate relationship history.
                writable = False
                for resource, value in record.entries():
                    if not isinstance(resource, str) or not _integer(value):
                        continue
                    title = (native.get(person) or person) + " · " + (native.get(resource) or resource)
                    english = (en.get(person) or person) + " · " + (en.get(resource) or resource)
                    result.append(_row(
                        "gift:{}:{}".format(person, resource), domain,
                        "{} / {}".format(person, resource),
                        ["GameState", "GiftRecord", person, resource],
                        title, english, int(value), "integer",
                        group="赠礼记录" if zh else "Gift history",
                        editable=writable, maximum=999999,
                    ))
    if domain == "progression":
        states = state.get("MetaUpgradeState")
        if isinstance(states, LuaTable):
            names = {name for name, value in states.entries()
                     if isinstance(name, str) and name in _ARCANA_CARDS and isinstance(value, LuaTable)}
            native, en = _display(names, language, game_path)
            for name in sorted(names):
                card = states[name]
                unlocked = card.get("Unlocked")
                level = card.get("Level", 1)
                equipped = card.get("Equipped")
                if (unlocked is not None and type(unlocked) is not bool) or not _integer(level) or (equipped is not None and type(equipped) is not bool):
                    continue
                if int(level) < 1 or int(level) > _ARCANA_MAX_LEVEL:
                    continue
                title = native.get(name) or (("塔罗牌 · " if zh else "Arcana · ") + name)
                english = en.get(name) or ("Arcana · " + name)
                result.append(_row(
                    "card:{}:Unlocked".format(name), domain, name,
                    ["GameState", "MetaUpgradeState", name, "Unlocked"],
                    title + (" · 已解锁" if zh else " · Unlocked"),
                    english + " · Unlocked", bool(unlocked), "boolean",
                    group="塔罗牌" if zh else "Arcana",
                ))
                result.append(_row(
                    "card:{}:Level".format(name), domain, name,
                    ["GameState", "MetaUpgradeState", name, "Level"],
                    title + (" · 等级" if zh else " · Level"),
                    english + " · Level", int(level), "integer",
                    group="塔罗牌" if zh else "Arcana", maximum=_ARCANA_MAX_LEVEL,
                ))

        objectives = state.get("ObjectivesCompleted")
        if isinstance(objectives, LuaTable):
            names = [name for name, _ in objectives.entries() if isinstance(name, str)]
            native, en = _display(names, language, game_path)
            for name in names:
                amount = objectives[name]
                if not _integer(amount):
                    continue
                result.append(_row(
                    "objective:" + name, domain, name,
                    ["GameState", "ObjectivesCompleted", name],
                    ("目标完成次数 · " if zh else "Objective completions · ") + (native.get(name) or name),
                    "Objective completions · " + (en.get(name) or name),
                    int(amount), "integer",
                    group="目标统计" if zh else "Objective counters",
                ))
    return result


def descriptor(root, entry_id, game_path=None):
    if not isinstance(entry_id, str):
        return None
    domain = ("relationships" if entry_id.startswith(("interaction:", "specialInteraction:"))
              else "progression" if entry_id.startswith(("card:", "objective:")) else None)
    if domain is None:
        return None
    for row in rows(root, domain, "en", game_path=game_path):
        if row["id"] == entry_id:
            return {
                "id": row["id"], "domain": domain, "rawId": row["rawId"],
                "path": row["path"], "before": row["value"],
                "valueType": row["valueType"],
                "mutationKinds": tuple(row["mutationKinds"]),
                "constraints": row.get("constraints", {}),
            }
    return None


def validate(descriptor_value, operation, value):
    if operation not in descriptor_value["mutationKinds"] or operation != "set":
        raise ValueError("Save Editor long-term mutation is not authorized.")
    if descriptor_value["valueType"] == "boolean":
        if type(value) is not bool:
            raise ValueError("Save Editor long-term flag must be boolean.")
    elif descriptor_value["valueType"] == "integer":
        limits = descriptor_value["constraints"]
        if type(value) is not int or not limits["min"] <= value <= limits["max"]:
            raise ValueError("Save Editor long-term counter is out of range.")
    else:
        raise ValueError("Save Editor long-term mutation type is unsupported.")


def apply_intent(root, intent):
    state = _state(root)
    entry_id = intent["id"]
    after = intent["after"]
    if entry_id.startswith(("interaction:", "specialInteraction:")):
        special = entry_id.startswith("specialInteraction:")
        name = entry_id[len("specialInteraction:"):] if special else entry_id[len("interaction:"):]
        owner = _table(state, "SpecialInteractRecord" if special else "NPCInteractions")
        if after == 0:
            owner.pop(name, None)
        else:
            owner[name] = after
        return
    if entry_id.startswith("card:"):
        _, name, field = entry_id.split(":", 2)
        cards = _table(state, "MetaUpgradeState")
        card = cards.get(name)
        if name not in _ARCANA_CARDS or not isinstance(card, LuaTable):
            raise ValueError("Save Editor Arcana card identity is invalid.")
        if field == "Unlocked":
            if after:
                card[field] = True
            else:
                card.pop(field, None)
                card.pop("Equipped", None)
                card["Level"] = 1
        elif field == "Level":
            card[field] = after
        else:
            raise ValueError("Save Editor Arcana field is not editable.")
        return
    if entry_id.startswith("objective:"):
        name = entry_id[len("objective:"):]
        owner = _table(state, "ObjectivesCompleted")
        if after:
            owner[name] = after
        else:
            owner.pop(name, None)
        return
    raise ValueError("Save Editor long-term mutation is unknown.")


def linked_changes(root, intents):
    state = _state(root)
    changes = []
    cards = state.get("MetaUpgradeState")
    for intent in intents:
        entry = intent["id"]
        if entry.startswith("card:") and entry.endswith(":Unlocked") and intent["after"] is False:
            _, name, _ = entry.split(":", 2)
            card = cards.get(name) if isinstance(cards, LuaTable) else None
            if isinstance(card, LuaTable):
                if card.get("Equipped") is True:
                    changes.append({
                        "id": "linked:card:{}:Equipped".format(name),
                        "domain": "progression", "rawId": name,
                        "name": "Arcana equipped · " + name,
                        "operation": "set", "before": True, "after": False,
                    })
                if int(card.get("Level", 1)) != 1:
                    changes.append({
                        "id": "linked:card:{}:Level".format(name),
                        "domain": "progression", "rawId": name,
                        "name": "Arcana level · " + name,
                        "operation": "set", "before": int(card.get("Level")), "after": 1,
                    })
    return changes


def validate_batch(root, intents):
    state = _state(root)
    for intent in intents:
        entry_id = intent["id"]
        if entry_id.startswith("card:"):
            _, name, field = entry_id.split(":", 2)
            card = _table(state, "MetaUpgradeState")[name]
            unlocked = card.get("Unlocked") is True
            equipped = card.get("Equipped") is True
            level = card.get("Level", 1)
            if not _integer(level) or not 1 <= level <= _ARCANA_MAX_LEVEL:
                raise ValueError("Save Editor Arcana level is invalid.")
            if equipped and not unlocked:
                raise ValueError("Save Editor equipped Arcana must be unlocked.")
            if level > 1 and not unlocked:
                raise ValueError("Save Editor upgraded Arcana must be unlocked.")
            actual = (bool(card.get(field)) if field == "Unlocked" else int(level))
            if actual != intent["after"]:
                raise ValueError("Save Editor Arcana changes conflict.")
