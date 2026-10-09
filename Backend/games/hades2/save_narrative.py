"""Hades-owned narrative Save Editor descriptors and linked-state mutations.

Only explicit, source-verified records receive write authority. The generic
Advanced tree remains the read-only escape hatch for everything else.
"""
from .localization import official_display_names
from .save_native_ids import QUEST_IDS, STORY_RESET_TEXT_IDS
from .save_document import LuaTable


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


def _game_state(root):
    state = root["GameState"]
    if not isinstance(state, LuaTable):
        raise ValueError("Save Editor GameState is malformed.")
    return state


def _table(state, name):
    value = state[name]
    if not isinstance(value, LuaTable):
        raise ValueError("Save Editor {} is malformed.".format(name))
    return value


def _read_bool(table, identifier):
    value = table.get(identifier)
    if value is not None and type(value) is not bool:
        raise ValueError("Save Editor narrative flag is not boolean.")
    return bool(value)


def _dialogue_authority(root):
    """Validate native dialogue companion owners before inferring absence."""
    state = _game_state(root)
    gift_history = state.get("GiftTextLinesOrderRecord")
    choice_history = state.get("TextLinesChoiceRecord")
    if not isinstance(gift_history, LuaTable) or not isinstance(choice_history, LuaTable):
        raise ValueError("Save Editor dialogue companion history is unavailable.")
    gifted_ids = set()
    for person, history in gift_history.entries():
        if type(person) is not str or not isinstance(history, LuaTable):
            raise ValueError("Save Editor gift dialogue history is malformed.")
        for index, line in history.entries():
            if (type(index) not in (int, float) or index < 1 or
                    not float(index).is_integer() or type(line) is not str):
                raise ValueError("Save Editor gift dialogue history is malformed.")
            gifted_ids.add(line)

    # PlayTextLine and native narrative choice selection write both the
    # persistent and the current-run owners. A reset must account for both.
    owners = [("GameState.TextLinesChoiceRecord", choice_history, str)]
    run = root.get("CurrentRun")
    if run is not None:
        if not isinstance(run, LuaTable):
            raise ValueError("Save Editor current-run dialogue history is malformed.")
        for field, expected_type in (
            ("TextLinesRecord", bool),
            ("HubTextLinesRecord", bool),
            ("TextLinesChoiceRecord", str),
        ):
            value = run.get(field)
            if value is not None:
                if not isinstance(value, LuaTable):
                    raise ValueError("Save Editor current-run dialogue history is malformed.")
                owners.append(("CurrentRun." + field, value, expected_type))
        room = run.get("CurrentRoom")
        if room is not None:
            if not isinstance(room, LuaTable):
                raise ValueError("Save Editor current-room dialogue history is malformed.")
            room_lines = room.get("TextLinesRecord")
            if room_lines is not None:
                if not isinstance(room_lines, LuaTable):
                    raise ValueError("Save Editor current-room dialogue history is malformed.")
                owners.append(("CurrentRun.CurrentRoom.TextLinesRecord", room_lines, bool))
    return gifted_ids, owners


def _validated_dialogue_owners(root, name, authority):
    # StoryResetData.TextLines is a native-authored reset boundary. Neither a
    # boolean observation nor missing gift evidence grants write authority.
    if name not in STORY_RESET_TEXT_IDS:
        raise ValueError("Save Editor dialogue identity is not a native reset target.")
    if _table(_game_state(root), "TextLinesRecord").get(name) is not True:
        raise ValueError("Save Editor dialogue must be a played record.")
    gifted_ids, owners = authority
    if name in gifted_ids:
        raise ValueError("Save Editor gift-linked dialogue cannot be reset alone.")
    for _owner_name, record, expected_type in owners:
        before = record.get(name)
        if before is not None and type(before) is not expected_type:
            raise ValueError("Save Editor linked dialogue history is malformed.")
    return owners


def _row(*, entry_id, domain, key, path, label, english, value,
         value_type, editable, operations, group, choices=None):
    return {
        "id": entry_id, "domain": domain, "rawId": key, "path": path,
        "name": label, "englishName": english, "value": value,
        "valueType": value_type, "editable": editable,
        "mutationKinds": list(operations), "group": group,
        "choices": list(choices or ()),
    }


def rows(root, domain, language="zh-CN", game_path=None):
    state = _game_state(root)
    result = []
    if domain == "flags":
        flags = _table(state, "Flags")
        for name, (group, zh, en) in _FLAG_DESCRIPTORS.items():
            try:
                value = _read_bool(flags, name)
            except ValueError:
                continue  # Malformed flags remain accessible in Advanced.
            result.append(_row(
                entry_id="flag:" + name, domain="flags", key=name,
                path=["GameState", "Flags", name],
                label=zh if language == "zh-CN" else en, english=en, value=value,
                value_type="boolean", editable=True, operations=("set",),
                group=_GROUP_NAMES[group][0 if language == "zh-CN" else 1],
                choices=(False, True),
            ))
    if domain == "dialogue":
        lines = _table(state, "TextLinesRecord")
        try:
            authority = _dialogue_authority(root)
        except ValueError:
            authority = None  # Keep the recorded rows inspectable, but read-only.
        for name, value in lines.entries():
            if not isinstance(name, str) or type(value) is not bool:
                continue
            # A gift event also changes GiftRecord/order/choice history. It
            # cannot safely be reset by treating one text flag as independent.
            writable = False
            if authority is not None and value is True:
                try:
                    _validated_dialogue_owners(root, name, authority)
                except ValueError:
                    pass
                else:
                    writable = True
            result.append(_row(
                entry_id="dialogue:" + name, domain="dialogue", key=name,
                path=["GameState", "TextLinesRecord", name],
                label=("对话记录 · " if language == "zh-CN" else "Dialogue record · ") + name,
                english="Dialogue record · " + name, value=value,
                value_type="boolean", editable=writable,
                operations=("set",) if writable else (),
                group=_GROUP_NAMES["dialogue"][0 if language == "zh-CN" else 1],
                choices=(False, True),
            ))
    if domain == "progression":
        statuses = _table(state, "QuestStatus")
        names = set(k for k, _ in statuses.entries() if isinstance(k, str))
        official = official_display_names(names, language, game_path=game_path)
        english = official if language == "en" else official_display_names(names, "en", game_path=game_path)
        for name in sorted(names & QUEST_IDS):
            status = statuses.get(name)
            if status not in _QUEST_STATUSES:
                continue
            label = official.get(name) or (("任务 · " if language == "zh-CN" else "Quest · ") + name)
            en = english.get(name) or ("Quest · " + name)
            editable = status != "CashedOut"
            result.append(_row(
                entry_id="quest:" + name, domain="progression", key=name,
                path=["GameState", "QuestStatus", name],
                label=label, english=en, value=status, value_type="enum",
                editable=editable, operations=("setEnum",) if editable else (),
                group=_GROUP_NAMES["quest"][0 if language == "zh-CN" else 1],
                choices=("Unlocked", "Complete") if editable else (),
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
    choices = state.get("TextLinesChoiceRecord")
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
        if (intent["id"].startswith("dialogue:") and intent["after"] is False
                and isinstance(choices, LuaTable)):
            name = intent["rawId"]
            before = choices.get(name)
            if isinstance(before, LuaTable):
                before = "Table ({} entries)".format(len(before))
            if before is not None:
                changes.append({
                    "id": "linked:dialogue:" + name, "domain": "dialogue", "rawId": name,
                    "name": "TextLinesChoiceRecord · " + name,
                    "operation": "unset", "before": before, "after": None,
                })
    return changes
