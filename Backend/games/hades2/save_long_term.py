"""Source-verified relationship and long-term progression save descriptors.

Gift history combines purchased quantities, ordered gifts, dialogue records,
and game-triggered side effects; it is inspectable but not safely synthesizable.
Arcana loadout and automatic-card semantics belong to save_arcana.
"""

from . import save_advanced, save_arcana
from .localization import official_display_names
from .save_document import AmbiguousLuaKeyError, LuaTable
from .save_native_ids import NPC_INTERACTION_IDS, OBJECTIVE_IDS

_MAX = 9_007_199_254_740_991


def linked_cache_label(raw_id, language, game_path=None):
    return save_arcana.cache_label(raw_id, language, game_path=game_path)


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


def _npc_person(native_id):
    if not native_id.startswith("NPC_"):
        return native_id
    name = native_id[len("NPC_"):]
    for variant in (
        "_Story_01", "_Field_01", "_Home_01", "_Past_01",
        "_DreamRun", "_01", "_02", "_03", "_04",
    ):
        if name.endswith(variant):
            return name[:-len(variant)]
    return name


def _row(entry_id, domain, raw_id, path, label, en, value, value_type,
         *, group, editable=True, maximum=_MAX,
         block_reason_code=None, owner_state=None,
         entity_id=None, entity_name=None):
    result = {
        "id": entry_id, "domain": domain, "rawId": raw_id, "path": path,
        "name": label, "englishName": en, "value": value,
        "valueType": value_type, "editable": editable,
        "mutationKinds": ["set"] if editable else [],
        "group": group,
        "choices": [False, True] if value_type == "boolean" else [],
    }
    if entity_id is not None:
        result["entityId"] = entity_id
        result["entityName"] = entity_name
    if value_type == "integer":
        result["constraints"] = {"min": 0 if not entry_id.startswith("card:") else 1,
                                 "max": maximum, "integer": True}
    if block_reason_code:
        result["blockReasonCode"] = block_reason_code
    if owner_state:
        result["ownerState"] = owner_state
    return result


def rows(root, domain, language="zh-CN", game_path=None, *, include_absent=False):
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
                entity_id="person:" + _npc_person(name),
                entity_name=title if title != name else _npc_person(name),
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
                    entity_id="person:" + _npc_person(name),
                    entity_name=special_native.get(name) or _npc_person(name),
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
                        entity_id="person:" + person,
                        entity_name=gift_native.get(person) or person,
                    ))

    if domain == "progression":
        result.extend(save_arcana.rows(root, language, game_path=game_path, include_absent=include_absent))

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
    for row in rows(root, domain, "en", game_path=game_path, include_absent=entry_id.startswith("card:")):
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
                "rawTyped": row.get("rawTyped", False),
            }
    return None


def validate(descriptor_value, operation, value):
    if operation not in descriptor_value["mutationKinds"] or operation != "set":
        raise ValueError("Save Editor long-term mutation is not authorized.")
    if descriptor_value.get("rawTyped"):
        save_advanced.validate_scalar(value, descriptor_value["valueType"])
        return
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
        return save_arcana.apply_intent(root, intent)
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
    return save_arcana.linked_changes(root, intents)


def finalize_batch(root, intents, source=None):
    save_arcana.finalize_batch(root, intents, source=source)


def validate_batch(root, intents):
    save_arcana.validate_batch(root, intents)
