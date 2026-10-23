"""Source-verified relationship and long-term progression save descriptors.

Gift quantities delegate to their own stored-count/aggregate transaction owner;
ordered gift events and dialogue history remain separate.
Arcana loadout and automatic-card semantics belong to save_arcana.
"""

from . import save_advanced, save_arcana, save_relationships
from .save_mutation_utils import owner as lua_owner
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


def _counter_rows(state, field, prefix, known, domain, language, game_path, chinese, english, *, person=False):
    owner_state = None
    try:
        collection = state.get(field)
    except AmbiguousLuaKeyError:
        collection, owner_state = None, "ambiguous"
    else:
        if collection is not None and not isinstance(collection, LuaTable):
            owner_state = "unsupported"
    names = set(known)
    if isinstance(collection, LuaTable):
        names.update(name for name, _ in collection.entries() if type(name) is str)
    native, en = _display(names, language, game_path)
    result = []
    for name in sorted(names):
        issue, value, kind = owner_state, 0, "integer"
        if isinstance(collection, LuaTable):
            try:
                raw_value = collection.get(name, 0)
            except AmbiguousLuaKeyError:
                issue, value = "ambiguous", None
            else:
                if name not in known and save_advanced.value_type(raw_value) in ("boolean", "number", "string"):
                    kind = save_advanced.value_type(raw_value)
                    try:
                        value = save_advanced.validate_scalar(raw_value, kind)
                    except ValueError:
                        issue, value = "unsupported", None
                elif _integer(raw_value):
                    value = int(raw_value)
                else:
                    issue, value = "unsupported", None
        title = native.get(name) or name
        row = _row(prefix + ":" + name, domain, name, ["GameState", field, name],
            (chinese if language == "zh-CN" else english) + " · " + title,
            english + " · " + (en.get(name) or name), value, kind,
            group=("角色互动" if language == "zh-CN" else "Character interactions") if person else
                  ("目标统计" if language == "zh-CN" else "Objective counters"),
            editable=issue is None, owner_state=issue,
            block_reason_code="ambiguousOwner" if issue == "ambiguous" else "unsupportedOwner" if issue else None,
            entity_id="person:" + _npc_person(name) if person else None,
            entity_name=title if title != name else _npc_person(name) if person else None)
        if name not in known:
            row["rawTyped"] = True
            row["reason"] = ("此已保存字段用途未编目；按实际类型修改，不重放互动事件。" if language == "zh-CN" else
                             "This saved field is not catalogued; edit its actual type without replaying interaction events.")
            if issue is None:
                row["warning"] = row["reason"]
        result.append(row)
    return result


def rows(root, domain, language="zh-CN", game_path=None, *, include_absent=False):
    state = _state(root)
    result = []
    zh = language == "zh-CN"
    if domain == "relationships":
        result.extend(_counter_rows(state, "NPCInteractions", "interaction", NPC_INTERACTION_IDS,
            domain, language, game_path, "互动次数", "Interactions", person=True))
        result.extend(_counter_rows(state, "SpecialInteractRecord", "specialInteraction", NPC_INTERACTION_IDS,
            domain, language, game_path, "特殊互动次数", "Special interactions", person=True))

        result.extend(save_relationships.rows(root, language, game_path))

    if domain == "progression":
        result.extend(save_arcana.rows(root, language, game_path=game_path, include_absent=include_absent))

        result.extend(_counter_rows(state, "ObjectivesCompleted", "objective", OBJECTIVE_IDS,
            domain, language, game_path, "目标完成次数", "Objective completions"))
    return result


def descriptor(root, entry_id, game_path=None):
    if not isinstance(entry_id, str):
        return None
    if entry_id.startswith("gift:"):
        return save_relationships.descriptor(root, entry_id)
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
    if descriptor_value["id"].startswith("gift:"):
        return save_relationships.validate(descriptor_value, operation, value)
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
    if intent["id"].startswith("gift:"):
        return save_relationships.apply_intent(root, intent)
    state = _state(root)
    entry_id = intent["id"]
    after = intent["after"]
    if entry_id.startswith(("interaction:", "specialInteraction:")):
        special = entry_id.startswith("specialInteraction:")
        name = entry_id[len("specialInteraction:"):] if special else entry_id[len("interaction:"):]
        owner = lua_owner(root, ["GameState", "SpecialInteractRecord" if special else "NPCInteractions"], create=True)
        if name not in NPC_INTERACTION_IDS:
            owner[name] = after
            return
        if after == 0:
            owner.pop(name, None)
        else:
            owner[name] = after
        return
    if entry_id.startswith("card:"):
        return save_arcana.apply_intent(root, intent)
    if entry_id.startswith("objective:"):
        name = entry_id[len("objective:"):]
        owner = lua_owner(root, ["GameState", "ObjectivesCompleted"], create=True)
        if name not in OBJECTIVE_IDS:
            owner[name] = after
            return
        if after:
            owner[name] = after
        else:
            owner.pop(name, None)
        return
    raise ValueError("Save Editor long-term mutation is unknown.")


def linked_changes(root, intents):
    return save_arcana.linked_changes(root, intents) + save_relationships.linked_changes(root, intents)


def finalize_batch(root, intents, source=None):
    save_arcana.finalize_batch(root, intents, source=source)


def validate_batch(root, intents):
    save_arcana.validate_batch(root, intents)
