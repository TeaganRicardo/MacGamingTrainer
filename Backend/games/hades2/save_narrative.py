"""Hades-owned narrative Save Editor descriptors and linked-state mutations.

Only explicit, source-verified records receive write authority. The generic
Advanced tree remains the read-only escape hatch for everything else.
"""
from .localization import official_display_names
from .save_native_ids import QUEST_IDS, STORY_RESET_TEXT_IDS
from .save_document import AmbiguousLuaKeyError, LuaTable


# Boolean records written/read directly by current-build Scripts/*Logic.lua.
# These are Trainer descriptions of the state, not claimed native game titles.
_FLAG_DESCRIPTORS = {
    "AcquiredMixerForCirceQuest": ("story", "已为喀耳刻任务取得材料", "Acquired material for Circe's request"),
    "AcquiredMixerForMedeaQuest": ("story", "已为美狄亚任务取得材料", "Acquired material for Medea's request"),
    "HasMultiPlanted": ("progress", "曾同时种植多株植物", "Has planted multiple plants together"),
    "HasPinnedAnyBoon": ("interface", "曾标记祝福", "Has pinned a boon"),
    "HasShuffledMusicPlayer": ("interface", "曾随机播放音乐", "Has shuffled the music player"),
    "HasUpgradedCards": ("progress", "曾升级塔罗牌", "Has upgraded an Arcana card"),
    "HasUsedSaveFirstSystem": ("progress", "曾使用纪念品保留功能", "Has used the Keepsake save-first feature"),
    "HasUsedWeaponShopNavigation": ("interface", "已使用武器商店导航", "Has used weapon-shop navigation"),
    "InspectedMetaUpgrade": ("interface", "曾查看塔罗牌升级", "Has inspected an Arcana upgrade"),
    "MetaUpgradeExpandPsycheHint": ("interface", "已显示塔罗牌扩容提示", "Arcana capacity hint displayed"),
    "SecondUpgradeReminder": ("interface", "已显示第二次升级提醒", "Second card-upgrade reminder shown"),
    "SeenElementalIcons": ("interface", "曾看到元素标识", "Has seen elemental icons"),
    "SeenUnityBoons": ("story", "曾见过联动祝福提示", "Has seen unity boon presentation"),
    "UsedSlowAgainstChronos": ("story", "曾对克洛诺斯使用减速", "Has used slowdown against Chronos"),
}
_GROUP_NAMES = {
    "story": ("剧情条件", "Narrative conditions"),
    "progress": ("成长记录", "Progression records"),
    "interface": ("提示与界面记录", "Tutorial and presentation records"),
    "quest": ("命运清单", "Fated List quests"),
    "dialogue": ("对话历史", "Dialogue history"),
}
_QUEST_STATUSES = ("Unlocked", "Complete", "CashedOut")


class DialogueWriteBlocked(ValueError):
    """A stable rejection reason from the same owner that stages dialogue."""

    def __init__(self, code, diagnostic):
        self.code = code
        super().__init__(diagnostic)


def _game_state(root):
    state = root["GameState"]
    if not isinstance(state, LuaTable):
        raise ValueError("Save Editor GameState is malformed.")
    return state


def _table(state, name):
    value = state.get(name)
    if not isinstance(value, LuaTable):
        raise ValueError("Save Editor {} is malformed.".format(name))
    return value


def _read_bool(table, identifier):
    value = table.get(identifier)
    if value is not None and type(value) is not bool:
        raise ValueError("Save Editor narrative flag is not boolean.")
    return bool(value)


def _dialogue_unique_value(owner, name):
    """Resolve exactly one string key before a first-match LuaTable mutation."""
    found = False
    value = None
    for key, entry in owner.entries():
        if type(key) is str and key == name:
            if found:
                raise DialogueWriteBlocked("ambiguousOwner", "Save Editor dialogue owner has duplicate keys.")
            found = True
            value = entry
    return value


def _dialogue_authority(root):
    """Validate native dialogue companion owners before inferring absence."""
    # The codec preserves duplicate entries for lossless reads. Every owner
    # selector and target key must therefore be unique before any reset.
    _dialogue_unique_value(root, "GameState")
    _dialogue_unique_value(root, "CurrentRun")
    state = _game_state(root)
    lines = _dialogue_unique_value(state, "TextLinesRecord")
    gift_history = _dialogue_unique_value(state, "GiftTextLinesOrderRecord")
    choice_history = _dialogue_unique_value(state, "TextLinesChoiceRecord")
    if not all(isinstance(owner, LuaTable)
               for owner in (lines, gift_history, choice_history)):
        raise DialogueWriteBlocked("companionMissing", "Save Editor dialogue companion history is unavailable.")
    gifted_ids = set()
    seen_people = set()
    for person, history in gift_history.entries():
        if type(person) is not str or not isinstance(history, LuaTable):
            raise DialogueWriteBlocked("giftHistory", "Save Editor gift dialogue history is malformed.")
        if person in seen_people:
            raise DialogueWriteBlocked("giftHistory", "Save Editor gift dialogue owner has duplicate keys.")
        seen_people.add(person)
        seen_indexes = set()
        for index, line in history.entries():
            if (type(index) not in (int, float) or index < 1 or
                    not float(index).is_integer() or type(line) is not str):
                raise DialogueWriteBlocked("giftHistory", "Save Editor gift dialogue history is malformed.")
            # Lua numeric keys share one identity for 1 and 1.0.
            numeric_key = float(index)
            if numeric_key in seen_indexes:
                raise DialogueWriteBlocked("giftHistory", "Save Editor gift dialogue history has duplicate indexes.")
            seen_indexes.add(numeric_key)
            gifted_ids.add(line)

    # PlayTextLine and native narrative choice selection write both the
    # persistent and the current-run owners. A reset must account for both.
    owners = [("GameState.TextLinesChoiceRecord", choice_history, str)]
    run = _dialogue_unique_value(root, "CurrentRun")
    if run is not None:
        if not isinstance(run, LuaTable):
            raise DialogueWriteBlocked("currentRun", "Save Editor current-run dialogue history is malformed.")
        for field, expected_type in (
            ("TextLinesRecord", bool),
            ("HubTextLinesRecord", bool),
            ("TextLinesChoiceRecord", str),
        ):
            value = _dialogue_unique_value(run, field)
            if value is not None:
                if not isinstance(value, LuaTable):
                    raise DialogueWriteBlocked("currentRun", "Save Editor current-run dialogue history is malformed.")
                owners.append(("CurrentRun." + field, value, expected_type))
        room = _dialogue_unique_value(run, "CurrentRoom")
        if room is not None:
            if not isinstance(room, LuaTable):
                raise DialogueWriteBlocked("currentRun", "Save Editor current-room dialogue history is malformed.")
            room_lines = _dialogue_unique_value(room, "TextLinesRecord")
            if room_lines is not None:
                if not isinstance(room_lines, LuaTable):
                    raise DialogueWriteBlocked("currentRun", "Save Editor current-room dialogue history is malformed.")
                owners.append(("CurrentRun.CurrentRoom.TextLinesRecord", room_lines, bool))
    return gifted_ids, owners


def _validated_dialogue_owners(root, name, authority):
    # StoryResetData.TextLines is a native-authored reset boundary. Neither a
    # boolean observation nor missing gift evidence grants write authority.
    if name not in STORY_RESET_TEXT_IDS:
        raise DialogueWriteBlocked("notResettable", "Save Editor dialogue identity is not a native reset target.")
    if _dialogue_unique_value(_table(_game_state(root), "TextLinesRecord"), name) is not True:
        raise DialogueWriteBlocked("notPlayed", "Save Editor dialogue must be a played record.")
    gifted_ids, owners = authority
    if name in gifted_ids:
        raise DialogueWriteBlocked("giftLinked", "Save Editor gift-linked dialogue cannot be reset alone.")
    for _owner_name, record, expected_type in owners:
        before = _dialogue_unique_value(record, name)
        if before is not None and type(before) is not expected_type:
            raise DialogueWriteBlocked("linkedHistory", "Save Editor linked dialogue history is malformed.")
    return owners


def _row(*, entry_id, domain, key, path, label, english, value,
         value_type, editable, operations, group, choices=None,
         block_reason_code=None, owner_state=None):
    row = {
        "id": entry_id, "domain": domain, "rawId": key, "path": path,
        "name": label, "englishName": english, "value": value,
        "valueType": value_type, "editable": editable,
        "mutationKinds": list(operations), "group": group,
        "choices": list(choices or ()),
    }
    if block_reason_code:
        row["blockReasonCode"] = block_reason_code
    if owner_state:
        row["ownerState"] = owner_state
    return row


def rows(root, domain, language="zh-CN", game_path=None):
    state = _game_state(root)
    result = []
    if domain == "flags":
        try:
            flags = _table(state, "Flags")
            flags_owner_state = None
        except AmbiguousLuaKeyError:
            flags = None
            flags_owner_state = "ambiguous"
        except ValueError:
            flags = None
            flags_owner_state = "unsupported"
        for name, (group, zh, en) in _FLAG_DESCRIPTORS.items():
            value = None
            owner_state = flags_owner_state
            if flags is not None:
                try:
                    value = _read_bool(flags, name)
                except AmbiguousLuaKeyError:
                    owner_state = "ambiguous"
                except ValueError:
                    owner_state = "unsupported"
            editable = owner_state is None
            result.append(_row(
                entry_id="flag:" + name, domain="flags", key=name,
                path=["GameState", "Flags", name],
                label=zh if language == "zh-CN" else en, english=en, value=value,
                value_type="boolean", editable=editable,
                operations=("set",) if editable else (),
                group=_GROUP_NAMES[group][0 if language == "zh-CN" else 1],
                choices=(False, True),
                block_reason_code=(
                    "ambiguousOwner" if owner_state == "ambiguous"
                    else "unsupportedOwner" if owner_state == "unsupported"
                    else None
                ),
                owner_state=owner_state,
            ))
    if domain == "dialogue":
        lines = _table(state, "TextLinesRecord")
        try:
            authority = _dialogue_authority(root)
            authority_error = None
        except ValueError as error:
            authority = None  # Keep the recorded rows inspectable, but read-only.
            authority_error = error
        seen_lines = set()
        for name, value in lines.entries():
            if not isinstance(name, str) or type(value) is not bool:
                continue
            # Duplicate physical keys retain one read-only semantic row; the
            # full underlying entries remain inspectable in Advanced.
            if name in seen_lines:
                continue
            seen_lines.add(name)
            # A gift event also changes GiftRecord/order/choice history. It
            # cannot safely be reset by treating one text flag as independent.
            writable = False
            block = authority_error if value is True else DialogueWriteBlocked(
                "notPlayed", "Save Editor dialogue must be a played record."
            )
            if authority is not None and value is True:
                try:
                    _validated_dialogue_owners(root, name, authority)
                except ValueError as error:
                    block = error
                else:
                    writable = True
                    block = None
            row = _row(
                entry_id="dialogue:" + name, domain="dialogue", key=name,
                path=["GameState", "TextLinesRecord", name],
                label=("对话记录 · " if language == "zh-CN" else "Dialogue record · ") + name,
                english="Dialogue record · " + name, value=value,
                value_type="boolean", editable=writable,
                operations=("set",) if writable else (),
                group=_GROUP_NAMES["dialogue"][0 if language == "zh-CN" else 1],
                choices=(False, True),
            )
            # Share the exact native companion-owner verdict with the
            # investigation. Never infer editability from the scene index.
            row["blockReasonCode"] = (
                getattr(block, "code", "invalidOwner") if block else None
            )
            row["blockReasonDiagnostic"] = str(block) if block else None
            result.append(row)
    if domain == "progression":
        try:
            statuses = _table(state, "QuestStatus")
            statuses_owner_state = None
            names = {
                key for key, _ in statuses.entries()
                if isinstance(key, str) and key in QUEST_IDS
            }
        except AmbiguousLuaKeyError:
            statuses = None
            statuses_owner_state = "ambiguous"
            names = set(QUEST_IDS)
        except ValueError:
            statuses = None
            statuses_owner_state = "unsupported"
            names = set(QUEST_IDS)
        official = official_display_names(names, language, game_path=game_path)
        english = (
            official if language == "en"
            else official_display_names(names, "en", game_path=game_path)
        )
        for name in sorted(names):
            owner_state = statuses_owner_state
            status = None
            if statuses is not None:
                try:
                    status = statuses.get(name)
                except AmbiguousLuaKeyError:
                    owner_state = "ambiguous"
                else:
                    if status not in _QUEST_STATUSES:
                        owner_state = "unsupported"
            label = official.get(name) or (("任务 · " if language == "zh-CN" else "Quest · ") + name)
            en = english.get(name) or ("Quest · " + name)
            editable = owner_state is None and status != "CashedOut"
            block_reason = (
                "ambiguousOwner" if owner_state == "ambiguous"
                else "unsupportedOwner" if owner_state == "unsupported"
                else None if editable
                else "rewardClaimed"
            )
            result.append(_row(
                entry_id="quest:" + name, domain="progression", key=name,
                path=["GameState", "QuestStatus", name],
                label=label, english=en, value=status, value_type="enum",
                editable=editable, operations=("setEnum",) if editable else (),
                group=_GROUP_NAMES["quest"][0 if language == "zh-CN" else 1],
                choices=("Unlocked", "Complete") if editable else (),
                block_reason_code=block_reason,
                owner_state=owner_state,
            ))
    return result


def descriptor(root, entry_id, game_path=None):
    if not isinstance(entry_id, str) or ":" not in entry_id:
        return None
    prefix = entry_id.partition(":")[0]
    domain = {"flag": "flags", "dialogue": "dialogue", "quest": "progression"}.get(prefix)
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
                "id": entry_id, "domain": domain, "rawId": row["rawId"],
                "path": row["path"], "before": row["value"],
                "mutationKinds": tuple(row["mutationKinds"]),
                "valueType": row["valueType"], "choices": row["choices"],
            }
    return None


def validate(descriptor_value, operation, value):
    if operation not in descriptor_value["mutationKinds"]:
        raise ValueError("Save Editor narrative mutation is not authorized.")
    if descriptor_value["valueType"] == "boolean":
        if type(value) is not bool or operation != "set":
            raise ValueError("Save Editor narrative flag must be boolean.")
    elif descriptor_value["valueType"] == "enum":
        if type(value) is not str or value not in descriptor_value["choices"] or operation != "setEnum":
            raise ValueError("Save Editor quest status is not an authorized transition.")
    else:
        raise ValueError("Save Editor narrative value type is unsupported.")


def apply_intent(root, intent):
    state = _game_state(root)
    prefix = intent["id"].partition(":")[0]
    name = intent["rawId"]
    after = intent["after"]
    if prefix == "flag":
        owner = _table(state, "Flags")
        if after:
            owner[name] = True
        else:
            owner.pop(name, None)
    elif prefix == "dialogue":
        if after is not False:
            raise ValueError("Save Editor dialogue reset requires an explicit false value.")
        # Validate every linked owner before modifying this candidate document.
        owners = _validated_dialogue_owners(root, name, _dialogue_authority(root))
        _table(state, "TextLinesRecord").pop(name, None)
        for _owner_name, record, _type in owners:
            record.pop(name, None)
    elif prefix == "quest":
        if name not in QUEST_IDS:
            raise ValueError("Save Editor quest identity is unknown.")
        status = _table(state, "QuestStatus")
        if status.get(name) == "CashedOut":
            raise ValueError("Save Editor cannot rewrite a claimed quest reward.")
        completed = state.get("QuestsCompleted")
        if completed is not None and not isinstance(completed, LuaTable):
            raise ValueError("Save Editor quest completion history is malformed.")
        if completed is None and after == "Complete":
            completed = LuaTable()
            state["QuestsCompleted"] = completed
        if completed is not None:
            previous = completed.get(name)
            if previous is not None and type(previous) is not bool:
                raise ValueError("Save Editor quest completion record is malformed.")
            if after == "Complete":
                completed[name] = True
            else:
                completed.pop(name, None)
        status[name] = after
    else:
        raise ValueError("Save Editor narrative mutation is unknown.")


def linked_changes(root, intents):
    state = _game_state(root)
    changes = []
    intents = tuple(intents)
    completed = state.get("QuestsCompleted") if any(
        intent["id"].startswith("quest:") for intent in intents
    ) else None
    if completed is not None and not isinstance(completed, LuaTable):
        raise ValueError("Save Editor quest completion history is malformed.")
    for intent in intents:
        if intent["id"].startswith("quest:"):
            name = intent["rawId"]
            record = completed.get(name) if completed is not None else None
            if record is not None and type(record) is not bool:
                raise ValueError("Save Editor quest completion record is malformed.")
            before = record is True
            after = intent["after"] == "Complete"
            if before != after:
                changes.append({
                    "id": "linked:quest:" + name,
                    "domain": "progression",
                    "rawId": name,
                    "name": "Quest completion history · " + name,
                    "operation": "set",
                    "before": before,
                    "after": after,
                })
        if intent["id"].startswith("dialogue:") and intent["after"] is False:
            name = intent["rawId"]
            owners = _validated_dialogue_owners(root, name, _dialogue_authority(root))
            for owner_name, record, _expected_type in owners:
                before = record.get(name)
                if before is None:
                    continue
                identity = ("linked:dialogue:" + name
                            if owner_name == "GameState.TextLinesChoiceRecord"
                            else "linked:dialogue:" + owner_name + ":" + name)
                changes.append({
                    "id": identity, "domain": "dialogue", "rawId": name,
                    "name": owner_name + " · " + name,
                    "operation": "unset", "before": before, "after": None,
                })
    return changes
