"""Hades-owned narrative Save Editor descriptors and linked-state mutations.

Direct saved records are editable by their reliable type and physical owner.
Native event resets retain their distinct verified companion-owner operation.
"""
from . import save_advanced
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


_MAX_INTEGER = 9_007_199_254_740_991
_QUEST_COMPANIONS = {
    'QuestsCompleted': ('完成记录', 'Completion record'),
    'QuestsViewed': ('已查看', 'Viewed'),
    'QuestsUpdated': ('更新提示', 'Update marker'),
    'PlayedQuestInterstitials': ('已播放任务过场', 'Quest interstitial played'),
}


def _owner(root, path, *, create=False):
    current = root
    for key in path:
        if not isinstance(current, LuaTable):
            raise save_advanced.AdvancedMutationError('Save Editor narrative path crosses a non-table owner.')
        child = current.get(key)
        if child is None and create:
            child = LuaTable()
            current[key] = child
        if child is not None and not isinstance(child, LuaTable):
            raise save_advanced.AdvancedMutationError('Save Editor narrative path crosses a non-table owner.')
        if child is None:
            return None
        current = child
    return current


def _read(root, path):
    owner = _owner(root, path[:-1])
    return owner.get(path[-1]) if owner is not None else None


def _direct_descriptor(root, entry_id):
    prefix, _, name = entry_id.partition(':')
    if not name:
        return None
    kind, choices, minimum = 'boolean', (), None
    if prefix == 'flag':
        path, domain = ['GameState', 'Flags', name], 'flags'
    elif prefix == 'dialogue':
        path, domain = ['GameState', 'TextLinesRecord', name], 'dialogue'
    elif prefix == 'dialogueChoice':
        path, domain, kind = ['GameState', 'TextLinesChoiceRecord', name], 'dialogue', 'string'
    elif prefix == 'quest':
        if name not in QUEST_IDS:
            return None
        path, domain, kind = ['GameState', 'QuestStatus', name], 'progression', 'enum'
        choices = ('Unrecorded', 'Unlocked', 'Complete', 'CashedOut')
    elif prefix == 'questObservation':
        owner, separator, name = name.partition(':')
        if not separator or owner not in _QUEST_COMPANIONS or name not in QUEST_IDS:
            return None
        path, domain = ['GameState', owner, name], 'questObservation'
    elif prefix == 'speech':
        path, domain, kind, minimum = ['GameState', 'SpeechRecord', name], 'speechHistory', 'integer', 0
    else:
        return None
    before = _read(root, path)
    if prefix == 'speech' and type(before) is bool:
        kind, minimum = 'boolean', None
    if before is not None:
        if kind == 'enum':
            # A nonstandard saved string can still be replaced with a supported
            # status. Arbitrary raw strings remain editable in Advanced.
            if type(before) is not str:
                raise save_advanced.AdvancedMutationError('Save Editor quest status owner is not a string.')
        else:
            save_advanced.validate_scalar(before, kind)
            if minimum is not None and not 0 <= before <= _MAX_INTEGER:
                raise save_advanced.AdvancedMutationError('Save Editor narrative counter is outside its integer range.')
    if prefix == 'quest':
        completed = _read(root, ['GameState', 'QuestsCompleted', name])
        if completed is not None:
            save_advanced.validate_scalar(completed, 'boolean')
    return {'id': entry_id, 'domain': domain, 'rawId': name, 'path': path,
            'before': before, 'mutationKinds': ('setEnum',) if kind == 'enum' else ('set',),
            'valueType': kind, 'choices': choices,
            'constraints': {'min': 0, 'max': _MAX_INTEGER, 'integer': True} if kind == 'integer' else {}}


def reset_descriptor(root, name):
    """Native reset is distinct from directly editing a playback record."""
    before = _read(root, ['GameState', 'TextLinesRecord', name])
    _validated_dialogue_owners(root, name, _dialogue_authority(root))
    return {'id': 'dialogueReset:' + name, 'domain': 'dialogue', 'rawId': name,
            'path': ['GameState', 'TextLinesRecord', name], 'before': before,
            'mutationKinds': ('set',), 'valueType': 'boolean', 'choices': (False,)}


def descriptor(root, entry_id, game_path=None):
    if not isinstance(entry_id, str):
        return None
    if entry_id.startswith('dialogueReset:'):
        return reset_descriptor(root, entry_id[len('dialogueReset:'):])
    return _direct_descriptor(root, entry_id)


def entry_row(root, entry_id, language='zh-CN', game_path=None):
    zh = language == 'zh-CN'
    prefix, _, name = entry_id.partition(':')
    block = None
    try:
        item = descriptor(root, entry_id, game_path)
    except (ValueError, KeyError) as error:
        block = error
        item = None
    if item is None:
        # Keep malformed saved fields visible with the actual technical reason.
        if prefix == 'questObservation':
            owner, _, name = name.partition(':')
            path, kind, domain = ['GameState', owner, name], 'boolean', 'questObservation'
        else:
            fields = {'flag': ('Flags', 'boolean', 'flags'),
                      'dialogue': ('TextLinesRecord', 'boolean', 'dialogue'),
                      'dialogueReset': ('TextLinesRecord', 'boolean', 'dialogue'),
                      'dialogueChoice': ('TextLinesChoiceRecord', 'string', 'dialogue'),
                      'speech': ('SpeechRecord', 'integer', 'speechHistory'),
                      'quest': ('QuestStatus', 'enum', 'progression')}
            if prefix not in fields:
                return None
            owner, kind, domain = fields[prefix]
            path = ['GameState', owner, name]
        item = {'id': entry_id, 'domain': domain, 'rawId': name, 'path': path,
                'before': None, 'valueType': kind, 'mutationKinds': (), 'choices': ()}
    name = item['rawId']
    label = name
    en = name
    entity = None
    entity_name = None
    group = _GROUP_NAMES['dialogue'][0 if zh else 1]
    if prefix == 'flag':
        category, chinese, en = _FLAG_DESCRIPTORS.get(name, ('story', '布尔记录 · ' + name, 'Boolean record · ' + name))
        label = chinese if zh else en
        group = _GROUP_NAMES[category][0 if zh else 1]
    elif prefix in ('quest', 'questObservation'):
        native = official_display_names((name,), language, game_path=game_path)
        english = native if not zh else official_display_names((name,), 'en', game_path=game_path)
        entity_name = native.get(name) or ('任务 · ' if zh else 'Quest · ') + name
        entity = 'quest:' + name
        label, en = entity_name, english.get(name) or 'Quest · ' + name
        group = _GROUP_NAMES['quest'][0 if zh else 1]
        if prefix == 'questObservation':
            labels = _QUEST_COMPANIONS[item['path'][1]]
            label, en = labels[0 if zh else 1], labels[1]
    else:
        labels = {'dialogue': ('已播放记录', 'Playback record'),
                  'dialogueReset': ('重置剧情事件', 'Reset narrative event'),
                  'dialogueChoice': ('选择记录', 'Choice record'),
                  'speech': ('语音计数', 'Speech count')}
        chinese, english = labels[prefix]
        label, en = (chinese if zh else english) + ' · ' + name, english + ' · ' + name
    result = {**item, 'name': label, 'englishName': en, 'value': item['before'],
              'editable': block is None and bool(item['mutationKinds']),
              'mutationKinds': list(item['mutationKinds']), 'choices': list(item['choices']),
              'group': group, 'reasonCode': 'editable'}
    result.pop('before', None)
    if entity:
        result.update(entityId=entity, entityName=entity_name)
    if item['valueType'] == 'boolean':
        result['choices'] = [False, True] if prefix != 'dialogueReset' else [False]
    if prefix == 'quest':
        result['choiceNames'] = dict(zip(('Unrecorded', 'Unlocked', 'Complete', 'CashedOut'),
            ('状态未记录', '已解锁', '已完成', '已领取奖励') if zh else
            ('Status unrecorded', 'Unlocked', 'Complete', 'Reward claimed')))
        result['reason'] = ('直接修改任务状态和完成记录；不发放或收回奖励资源。' if zh else
                            'Edits the status and completion record; does not grant or reclaim reward resources.')
    if block:
        result.update(reasonCode='ambiguousOwner' if isinstance(block, AmbiguousLuaKeyError) else 'unsupportedOwner',
                      blockReasonCode='ambiguousOwner' if isinstance(block, AmbiguousLuaKeyError) else 'unsupportedOwner',
                      ownerState='ambiguous' if isinstance(block, AmbiguousLuaKeyError) else 'unsupported',
                      reason=('目标路径重复，无法确定唯一记录。' if zh else 'The target path has duplicate physical records.')
                      if isinstance(block, AmbiguousLuaKeyError) else
                      ('此路径的实际类型与字段类型不符；可在高级编辑中按实际类型修改。' if zh else
                       'The saved type differs from this field type; edit its actual type in Advanced.'),
                      blockReasonDiagnostic=str(block))
    return result


def rows(root, domain, language='zh-CN', game_path=None):
    state = _game_state(root)
    identities = []
    if domain == 'flags':
        names = set(_FLAG_DESCRIPTORS)
        try:
            owner = state.get('Flags')
            if isinstance(owner, LuaTable):
                names.update(key for key, _ in owner.entries() if type(key) is str)
        except AmbiguousLuaKeyError:
            pass
        identities.extend('flag:' + name for name in sorted(names))
    elif domain == 'dialogue':
        for field, prefix in (('TextLinesRecord', 'dialogue:'), ('TextLinesChoiceRecord', 'dialogueChoice:')):
            try:
                owner = state.get(field)
            except AmbiguousLuaKeyError:
                continue
            if isinstance(owner, LuaTable):
                identities.extend(prefix + name for name in sorted({key for key, _ in owner.entries() if type(key) is str}))
    elif domain == 'progression':
        try:
            statuses = state.get('QuestStatus')
            names = {key for key, _ in statuses.entries() if type(key) is str and key in QUEST_IDS} if isinstance(statuses, LuaTable) else set()
        except AmbiguousLuaKeyError:
            names = set(QUEST_IDS)
        identities.extend('quest:' + name for name in sorted(names))
    return [entry_row(root, identity, language, game_path) for identity in identities]


def reset_decisions(root):
    decisions = {}
    try:
        lines = _table(_game_state(root), 'TextLinesRecord')
    except (ValueError, KeyError):
        return decisions
    for name, _ in lines.entries():
        if type(name) is not str or name in decisions:
            continue
        try:
            reset_descriptor(root, name)
        except (ValueError, KeyError) as error:
            decisions[name] = {'allowed': False, 'code': getattr(error, 'code', 'invalidOwner'), 'diagnostic': str(error)}
        else:
            decisions[name] = {'allowed': True, 'code': None, 'diagnostic': None}
    return decisions


def validate(descriptor_value, operation, value):
    if operation not in descriptor_value['mutationKinds']:
        raise save_advanced.AdvancedMutationError('Save Editor narrative mutation is not authorized.')
    if descriptor_value['id'].startswith('dialogueReset:'):
        if value is not False:
            raise save_advanced.AdvancedMutationError('Save Editor dialogue reset requires an explicit false value.')
        return
    kind = descriptor_value['valueType']
    if kind == 'enum':
        if type(value) is not str or value not in descriptor_value['choices']:
            raise save_advanced.AdvancedMutationError('Save Editor quest status is not an authorized transition.')
    else:
        save_advanced.validate_scalar(value, kind)
        if kind == 'integer' and not 0 <= value <= _MAX_INTEGER:
            raise save_advanced.AdvancedMutationError('Save Editor narrative counter is outside its integer range.')


def apply_intent(root, intent):
    name = intent['rawId']
    if intent['id'].startswith('dialogueReset:'):
        owners = _validated_dialogue_owners(root, name, _dialogue_authority(root))
        _table(_game_state(root), 'TextLinesRecord').pop(name, None)
        for _owner_name, record, _expected_type in owners:
            record.pop(name, None)
        return
    owner = _owner(root, intent['path'][:-1], create=True)
    after = intent['after']
    if intent['id'].startswith('quest:'):
        completion = _owner(root, ['GameState', 'QuestsCompleted'], create=True)
        if after in ('Complete', 'CashedOut'):
            completion[name] = True
        else:
            completion.pop(name, None)
        if after == 'Unrecorded':
            owner.pop(name, None)
            return
    owner[intent['path'][-1]] = after


def linked_changes(root, intents):
    changes = []
    intents = tuple(intents)
    explicit = {intent['id'] for intent in intents}
    for intent in intents:
        name = intent['rawId']
        if intent['id'].startswith('quest:'):
            before = _read(root, ['GameState', 'QuestsCompleted', name])
            after = True if intent['after'] in ('Complete', 'CashedOut') else None
            if before != after and 'questObservation:QuestsCompleted:' + name not in explicit:
                changes.append({'id': 'linked:quest:' + name, 'domain': 'progression', 'rawId': name,
                    'name': 'Quest completion history · ' + name, 'operation': 'set' if after else 'unset',
                    'before': before, 'after': after})
        if intent['id'].startswith('dialogueReset:'):
            owners = _validated_dialogue_owners(root, name, _dialogue_authority(root))
            for owner_name, record, _expected_type in owners:
                before = record.get(name)
                if before is None:
                    continue
                identity = 'linked:dialogue:' + ('' if owner_name == 'GameState.TextLinesChoiceRecord' else owner_name + ':') + name
                changes.append({'id': identity, 'domain': 'dialogue', 'rawId': name,
                    'name': owner_name + ' · ' + name, 'operation': 'unset', 'before': before, 'after': None})
    return changes


def validate_batch(root, intents):
    for intent in intents:
        if intent['domain'] not in ('flags', 'dialogue', 'progression', 'questObservation', 'speechHistory'):
            continue
        if not intent['id'].startswith(('flag:', 'dialogue:', 'dialogueReset:', 'dialogueChoice:', 'quest:', 'questObservation:', 'speech:')):
            continue
        expected = None if (intent['id'].startswith('dialogueReset:') or
                            intent['id'].startswith('quest:') and intent['after'] == 'Unrecorded') else intent['after']
        if intent['id'].startswith('quest:'):
            completion = _read(root, ['GameState', 'QuestsCompleted', intent['rawId']])
            expected_completion = True if intent['after'] in ('Complete', 'CashedOut') else None
            if completion != expected_completion:
                raise save_advanced.AdvancedMutationError('Save Editor quest status conflicts with its explicit completion record.', conflict=True)
        if _read(root, intent['path']) != expected:
            raise save_advanced.AdvancedMutationError('Save Editor staged narrative records conflict at ' + repr(intent['path']), conflict=True)
