"""Source-verified relationship and long-term progression save descriptors.

Gift history is represented as a count AND a chronological Lua array. Both
it and the global gift-resource count must be updated as one mutation. Arcana
cards follow MetaUpgradeLogic's locked/equipped/level ownership constraints.
"""
from collections import Counter

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


def _gift_sequence(record):
    pairs = []
    for key, value in record.entries():
        if type(key) in (float, int) and float(key).is_integer() and key >= 1:
            if not isinstance(value, str):
                return None
            pairs.append((int(key), value))
        elif not isinstance(key, str):
            return None
    pairs.sort()
    if [key for key, _ in pairs] != list(range(1, len(pairs) + 1)):
        return None
    return [value for _, value in pairs]


def _gift_consistent(record, global_counts):
    sequence = _gift_sequence(record)
    if sequence is None:
        return False
    counts = Counter(sequence)
    named = set()
    for key, value in record.entries():
        if isinstance(key, str):
            named.add(key)
            if not _integer(value) or counts[key] != int(value):
                return False
            if not _integer(global_counts.get(key, 0)) or int(global_counts.get(key, 0)) < int(value):
                return False
    return named == set(counts)


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
                writable = _gift_consistent(record, gift_totals)
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
        completed_sets = state.get("CompletedObjectiveSets")
        if isinstance(objectives, LuaTable):
            names = [name for name, _ in objectives.entries() if isinstance(name, str)]
            native, en = _display(names, language, game_path)
            for name in names:
                amount = objectives[name]
                if not _integer(amount):
                    continue
                done = isinstance(completed_sets, LuaTable) and completed_sets.get(name) is True
                result.append(_row(
                    "objective:" + name, domain, name,
                    ["GameState", "ObjectivesCompleted", name],
                    ("目标完成次数 · " if zh else "Objective completions · ") + (native.get(name) or name),
                    "Objective completions · " + (en.get(name) or name),
                    int(amount), "integer",
                    group="目标统计" if zh else "Objective counters",
                    editable=not done,
                ))
    return result


def descriptor(root, entry_id, game_path=None):
    if not isinstance(entry_id, str):
        return None
    domain = ("relationships" if entry_id.startswith(("gift:", "interaction:"))
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


def _replace_gift(record, resource, new_value):
    sequence = _gift_sequence(record)
    if sequence is None:
        raise ValueError("Save Editor gift history has invalid order.")
    previous = int(record.get(resource, 0))
    difference = new_value - previous
    if difference > 0:
        sequence.extend([resource] * difference)
    elif difference < 0:
        for _ in range(-difference):
            reverse = len(sequence) - 1 - sequence[::-1].index(resource)
            sequence.pop(reverse)
    named = [(key, value) for key, value in record.entries() if isinstance(key, str) and key != resource]
    if new_value > 0:
        named.append((resource, new_value))
    return LuaTable(
        len(sequence), len(named),
        [(float(index), value) for index, value in enumerate(sequence, 1)] + named,
    )


def apply_intent(root, intent):
    state = _state(root)
    entry_id = intent["id"]
    after = intent["after"]
    if entry_id.startswith("interaction:"):
        name = entry_id[len("interaction:"):]
        owner = _table(state, "NPCInteractions")
        if after == 0:
            owner.pop(name, None)
        else:
            owner[name] = after
        return
    if entry_id.startswith("gift:"):
        _, person, resource = entry_id.split(":", 2)
        all_gifts = _table(state, "GiftRecord")
        totals = _table(state, "GiftResourceRecord")
        record = all_gifts.get(person)
        if not isinstance(record, LuaTable) or not _gift_consistent(record, totals):
            raise ValueError("Save Editor gift history is not internally consistent.")
        old = int(record.get(resource, 0))
        delta = after - old
        global_total = int(totals.get(resource, 0))
        if global_total + delta < 0 or global_total + delta > _MAX:
            raise ValueError("Save Editor gift totals would be invalid.")
        updated = _replace_gift(record, resource, after)
        if len(updated):
            all_gifts[person] = updated
        else:
            all_gifts.pop(person, None)
        if global_total + delta:
            totals[resource] = global_total + delta
        else:
            totals.pop(resource, None)
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
    gift_deltas = Counter()
    order_deltas = Counter()
    cards = state.get("MetaUpgradeState")
    for intent in intents:
        entry = intent["id"]
        if entry.startswith("gift:"):
            _, person, resource = entry.split(":", 2)
            delta = int(intent["after"]) - int(intent["before"])
            gift_deltas[resource] += delta
            order_deltas[person] += delta
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
    totals = state.get("GiftResourceRecord")
    for resource, delta in gift_deltas.items():
        if delta and isinstance(totals, LuaTable):
            before = int(totals.get(resource, 0))
            changes.append({
                "id": "linked:giftTotal:" + resource, "domain": "relationships",
                "rawId": resource, "name": "GiftResourceRecord · " + resource,
                "operation": "set", "before": before, "after": before + delta,
            })
    for person, delta in order_deltas.items():
        if delta:
            gifts = state.get("GiftRecord")
            old = gifts.get(person) if isinstance(gifts, LuaTable) else None
            sequence = _gift_sequence(old) if isinstance(old, LuaTable) else None
            if sequence is not None:
                changes.append({
                    "id": "linked:giftOrder:" + person, "domain": "relationships",
                    "rawId": person, "name": "Gift chronology length · " + person,
                    "operation": "set", "before": len(sequence),
                    "after": len(sequence) + delta,
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
        if entry_id.startswith("gift:"):
            _, person, resource = entry_id.split(":", 2)
            gifts = _table(state, "GiftRecord")
            total = _table(state, "GiftResourceRecord")
            record = gifts.get(person)
            if record is not None and (
                not isinstance(record, LuaTable) or not _gift_consistent(record, total)
            ):
                raise ValueError("Save Editor gift record was not updated coherently.")
            actual = int(record.get(resource, 0)) if isinstance(record, LuaTable) else 0
            if actual != intent["after"]:
                raise ValueError("Save Editor gift changes conflict.")
