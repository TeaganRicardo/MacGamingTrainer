"""Source-verified relationship and long-term progression save descriptors.

Gift history combines purchased quantities, ordered gifts, dialogue records,
and game-triggered side effects; it is inspectable but not safely synthesizable.
Arcana changes preserve unlocked/equipped/level invariants.
"""

from .localization import official_display_names
from .save_document import AmbiguousLuaKeyError, LuaTable
from .save_native_ids import NPC_INTERACTION_IDS, OBJECTIVE_IDS

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
         *, group, editable=True, maximum=_MAX,
         block_reason_code=None, owner_state=None):
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
    if block_reason_code:
        result["blockReasonCode"] = block_reason_code
    if owner_state:
        result["ownerState"] = owner_state
    return result


def rows(root, domain, language="zh-CN", game_path=None):
    state = _state(root)
    result = []
    zh = language == "zh-CN"
    if domain == "relationships":
        names = sorted(NPC_INTERACTION_IDS)
        native, en = _display(names, language, game_path)
        try:
            interaction = state.get("NPCInteractions")
        except AmbiguousLuaKeyError:
            interaction = None
            interaction_owner_state = "ambiguous"
        else:
            interaction_owner_state = (
                None if interaction is None or isinstance(interaction, LuaTable)
                else "unsupported"
            )
        for name in names:
            owner_state = interaction_owner_state
            value = 0 if interaction is None else None
            if isinstance(interaction, LuaTable):
                try:
                    raw_value = interaction.get(name, 0)
                except AmbiguousLuaKeyError:
                    owner_state = "ambiguous"
                else:
                    if _integer(raw_value):
                        value = int(raw_value)
                    else:
                        owner_state = "unsupported"
            title = native.get(name) or name
            english = en.get(name) or name
            editable = owner_state is None and isinstance(interaction, LuaTable)
            result.append(_row(
                "interaction:" + name, domain, name,
                ["GameState", "NPCInteractions", name],
                ("互动次数 · " if zh else "Interactions · ") + title,
                "Interactions · " + english, value, "integer",
                group="角色互动" if zh else "Character interactions",
                editable=editable,
                block_reason_code=(
                    "ambiguousOwner" if owner_state == "ambiguous"
                    else "unsupportedOwner" if owner_state == "unsupported"
                    else None
                ),
                owner_state=owner_state,
            ))

        try:
            special = state.get("SpecialInteractRecord")
        except AmbiguousLuaKeyError:
            special = None
        if isinstance(special, LuaTable):
            special_names = {
                name for name, _ in special.entries()
                if isinstance(name, str) and name in NPC_INTERACTION_IDS
            }
            special_native, special_en = _display(
                special_names, language, game_path
            )
            for name in sorted(special_names):
                owner_state = None
                value = None
                try:
                    raw_value = special[name]
                except AmbiguousLuaKeyError:
                    owner_state = "ambiguous"
                else:
                    if _integer(raw_value):
                        value = int(raw_value)
                    else:
                        owner_state = "unsupported"
                editable = owner_state is None
                result.append(_row(
                    "specialInteraction:" + name, domain, name,
                    ["GameState", "SpecialInteractRecord", name],
                    ("特殊互动次数 · " if zh else "Special interactions · ") +
                        (special_native.get(name) or name),
                    "Special interactions · " + (special_en.get(name) or name),
                    value, "integer",
                    group="角色互动" if zh else "Character interactions",
                    editable=editable,
                    block_reason_code=(
                        "ambiguousOwner" if owner_state == "ambiguous"
                        else "unsupportedOwner" if owner_state == "unsupported"
                        else None
                    ),
                    owner_state=owner_state,
                ))

        try:
            gift_record = state.get("GiftRecord")
            gift_totals = state.get("GiftResourceRecord")
        except AmbiguousLuaKeyError:
            gift_record = None
            gift_totals = None
        if isinstance(gift_record, LuaTable) and isinstance(gift_totals, LuaTable):
            person_records = {}
            resources = set()
            for _index, person, record, ambiguous in gift_record.physical_entries():
                if not isinstance(person, str) or not isinstance(record, LuaTable):
                    continue
                person_records.setdefault(person, []).append((record, ambiguous))
                resources.update(
                    resource
                    for _child_index, resource, _value, _child_ambiguous
                    in record.physical_entries()
                    if isinstance(resource, str)
                )
            gift_native, gift_en = _display(
                set(person_records) | resources, language, game_path
            )
            for person in sorted(person_records):
                records = person_records[person]
                person_ambiguous = (
                    len(records) > 1 or any(ambiguous for _record, ambiguous in records)
                )
                by_resource = {}
                for record, _person_ambiguous in records:
                    for _index, resource, value, ambiguous in record.physical_entries():
                        if not isinstance(resource, str):
                            continue
                        by_resource.setdefault(resource, []).append((value, ambiguous))
                for resource in sorted(by_resource):
                    occurrences = by_resource[resource]
                    owner_state = None
                    presented_value = None
                    if (
                        person_ambiguous
                        or len(occurrences) > 1
                        or any(ambiguous for _value, ambiguous in occurrences)
                    ):
                        owner_state = "ambiguous"
                    else:
                        value = occurrences[0][0]
                        if _integer(value):
                            presented_value = int(value)
                        else:
                            owner_state = "unsupported"
                    title = (
                        (gift_native.get(person) or person) + " · " +
                        (gift_native.get(resource) or resource)
                    )
                    english = (
                        (gift_en.get(person) or person) + " · " +
                        (gift_en.get(resource) or resource)
                    )
                    result.append(_row(
                        "gift:{}:{}".format(person, resource), domain,
                        "{} / {}".format(person, resource),
                        ["GameState", "GiftRecord", person, resource],
                        title, english, presented_value, "integer",
                        group="赠礼记录" if zh else "Gift history",
                        editable=False, maximum=999999,
                        block_reason_code=(
                            "ambiguousOwner" if owner_state == "ambiguous"
                            else "unsupportedOwner" if owner_state == "unsupported"
                            else "giftHistoryLinked"
                        ),
                        owner_state=owner_state,
                    ))

    if domain == "progression":
        try:
            states = state.get("MetaUpgradeState")
        except AmbiguousLuaKeyError:
            states = None
            states_owner_state = "ambiguous"
            card_names = set(_ARCANA_CARDS)
        else:
            if states is None:
                states_owner_state = None
                card_names = set()
            elif isinstance(states, LuaTable):
                states_owner_state = None
                card_names = {
                    name for name, _ in states.entries()
                    if isinstance(name, str) and name in _ARCANA_CARDS
                }
            else:
                states_owner_state = "unsupported"
                card_names = set(_ARCANA_CARDS)

        card_native, card_en = _display(card_names, language, game_path)
        for name in sorted(card_names):
            owner_state = states_owner_state
            unlocked = None
            level = None
            if isinstance(states, LuaTable):
                try:
                    card = states[name]
                except AmbiguousLuaKeyError:
                    owner_state = "ambiguous"
                    card = None
                if owner_state is None and not isinstance(card, LuaTable):
                    owner_state = "unsupported"
                if owner_state is None:
                    try:
                        raw_unlocked = card.get("Unlocked")
                        raw_level = card.get("Level", 1)
                        raw_equipped = card.get("Equipped")
                    except AmbiguousLuaKeyError:
                        owner_state = "ambiguous"
                    else:
                        if (
                            (raw_unlocked is not None and type(raw_unlocked) is not bool)
                            or not _integer(raw_level)
                            or (raw_equipped is not None and type(raw_equipped) is not bool)
                            or not 1 <= int(raw_level) <= _ARCANA_MAX_LEVEL
                        ):
                            owner_state = "unsupported"
                        else:
                            unlocked = bool(raw_unlocked)
                            level = int(raw_level)
            title = card_native.get(name) or (
                ("塔罗牌 · " if zh else "Arcana · ") + name
            )
            english = card_en.get(name) or ("Arcana · " + name)
            editable = owner_state is None
            block_reason = (
                "ambiguousOwner" if owner_state == "ambiguous"
                else "unsupportedOwner" if owner_state == "unsupported"
                else None
            )
            result.append(_row(
                "card:{}:Unlocked".format(name), domain, name,
                ["GameState", "MetaUpgradeState", name, "Unlocked"],
                title + (" · 已解锁" if zh else " · Unlocked"),
                english + " · Unlocked", unlocked, "boolean",
                group="塔罗牌" if zh else "Arcana",
                editable=editable, block_reason_code=block_reason,
                owner_state=owner_state,
            ))
            result.append(_row(
                "card:{}:Level".format(name), domain, name,
                ["GameState", "MetaUpgradeState", name, "Level"],
                title + (" · 等级" if zh else " · Level"),
                english + " · Level", level, "integer",
                group="塔罗牌" if zh else "Arcana", maximum=_ARCANA_MAX_LEVEL,
                editable=editable, block_reason_code=block_reason,
                owner_state=owner_state,
            ))

        try:
            objectives = state.get("ObjectivesCompleted")
        except AmbiguousLuaKeyError:
            objectives = None
            objectives_owner_state = "ambiguous"
            objective_names = sorted(OBJECTIVE_IDS)
        else:
            if objectives is None:
                objectives_owner_state = None
                objective_names = []
            elif isinstance(objectives, LuaTable):
                objectives_owner_state = None
                objective_names = sorted(OBJECTIVE_IDS)
            else:
                objectives_owner_state = "unsupported"
                objective_names = sorted(OBJECTIVE_IDS)

        objective_native, objective_en = _display(
            objective_names, language, game_path
        )
        for name in objective_names:
            owner_state = objectives_owner_state
            amount = None
            if isinstance(objectives, LuaTable):
                try:
                    raw_amount = objectives.get(name, 0)
                except AmbiguousLuaKeyError:
                    owner_state = "ambiguous"
                else:
                    if _integer(raw_amount):
                        amount = int(raw_amount)
                    else:
                        owner_state = "unsupported"
            editable = owner_state is None
            result.append(_row(
                "objective:" + name, domain, name,
                ["GameState", "ObjectivesCompleted", name],
                ("目标完成次数 · " if zh else "Objective completions · ") +
                    (objective_native.get(name) or name),
                "Objective completions · " + (objective_en.get(name) or name),
                amount, "integer",
                group="目标统计" if zh else "Objective counters",
                editable=editable,
                block_reason_code=(
                    "ambiguousOwner" if owner_state == "ambiguous"
                    else "unsupportedOwner" if owner_state == "unsupported"
                    else None
                ),
                owner_state=owner_state,
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
            if row.get("ownerState") == "ambiguous":
                raise AmbiguousLuaKeyError(
                    "Save Editor semantic owner is ambiguous."
                )
            if row.get("ownerState") == "unsupported":
                raise ValueError("Save Editor semantic owner is unsupported.")
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
        if name not in NPC_INTERACTION_IDS:
            raise ValueError("Save Editor NPC identity is not supported.")
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
        if name not in OBJECTIVE_IDS:
            raise ValueError("Save Editor objective identity is not supported.")
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
