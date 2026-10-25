"""Read-only, installed-source investigation of Hades II dialogue in a static save.

Narrative content is read from the game installation, never bundled with the
Trainer. A matching reset manifest does not certify every installed input as a
supported build. Source ownership is many-to-many; game-state observations are
not predictions of future dialogue eligibility.
"""

from collections import defaultdict, OrderedDict
import hashlib
import json
import math
from pathlib import Path
import re

from .localization import _sjson_unescape, _clean_display_name
from .save_document import AmbiguousLuaKeyError, LuaTable
from .save_native_ids import STORY_RESET_TEXT_IDS

_SUPPORTED_STORY_SHA = "58509042a27542f96d666071da2fa58ca3c3b227002e4ae628501b7d7738ef8e"
_ASSIGN = re.compile(r"(?m)^[ \t]*([A-Za-z_][A-Za-z_0-9]*)[ \t]*=[ \t]*(?:\r?\n[ \t]*)?(\{)")
_TEXT_FIELD = re.compile(r'\b(Id|Event|Speaker|DisplayName)\s*=\s*"((?:\\.|[^"\\])*)"')
_CUE = re.compile(r'\bCue\s*=\s*"/VO/((?:\\.|[^"\\])*)"')
_STRING = re.compile(r'^"((?:\\.|[^"\\])*)"$')
_LUA_TOKENS = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[A-Za-z_][A-Za-z0-9_]*|-?\d+(?:\.\d+)?|[{}=,;\[\].()]|[^\s]', re.S)
_NATIVE_CACHE = OrderedDict()


def _masked(text, *, lua):
    """Keep braces and identifiers, mask comments and literals at fixed offsets."""
    chars = list(text)
    i, end = 0, len(text)
    while i < end:
        start = i
        if text[i] in ('"', "'"):
            quote = text[i]
            i += 1
            while i < end:
                if text[i] == "\\":
                    i += 2
                elif text[i] == quote:
                    i += 1
                    break
                else:
                    i += 1
        elif lua and text.startswith('--', i):
            opening = re.match(r'--\[(=*)\[', text[i: i + 30])
            if opening:
                close = ']' + opening.group(1) + ']'
                found = text.find(close, i + len(opening.group()))
                i = end if found < 0 else found + len(close)
            else:
                found = text.find('\n', i)
                i = end if found < 0 else found
        elif not lua and text.startswith('//', i):
            found = text.find('\n', i)
            i = end if found < 0 else found
        elif not lua and text.startswith('/*', i):
            found = text.find('*/', i + 2)
            i = end if found < 0 else found + 2
        elif lua and text[i] == '[' and (opening := re.match(r'\[(=*)\[', text[i: i + 30])):
            close = ']' + opening.group(1) + ']'
            found = text.find(close, i + len(opening.group()))
            i = end if found < 0 else found + len(close)
        else:
            i += 1
            continue
        for j in range(start, min(i, end)):
            if chars[j] not in '\r\n':
                chars[j] = ' '
    return ''.join(chars)


def _braces(masked, parents=None):
    stack, pairs = [], {}
    for i, character in enumerate(masked):
        if character == '{':
            if parents is not None:
                parents[i] = stack[-1] if stack else None
            stack.append(i)
        elif character == '}' and stack:
            pairs[stack.pop()] = i
    return pairs


def _lua_without_comments(text):
    """Strip Lua comments without losing quoted path/requirement literals."""
    out = list(text)
    i, length = 0, len(text)
    while i < length:
        if text[i] in ('"', "'"):
            quote = text[i]
            i += 1
            while i < length:
                if text[i] == "\\":
                    i += 2
                elif text[i] == quote:
                    i += 1
                    break
                else:
                    i += 1
            continue
        if text.startswith('--', i):
            start = i
            long = re.match(r'--\[(=*)\[', text[i: i + 30])
            if long:
                close = ']' + long.group(1) + ']'
                found = text.find(close, i + len(long.group()))
                i = length if found < 0 else found + len(close)
            else:
                found = text.find('\n', i)
                i = length if found < 0 else found
            for position in range(start, i):
                if out[position] not in '\r\n':
                    out[position] = ' '
        else:
            i += 1
    return ''.join(out)


def _parse_lua_table(source, *, reject_duplicate_fields=()):
    """Conservative literal-only table reader for presenting authored requirements."""
    tokens = _LUA_TOKENS.findall(_lua_without_comments(source))
    pos = 0

    def value():
        nonlocal pos
        if pos < len(tokens) and tokens[pos] == '{':
            pos += 1
            fields, members = {}, []
            while pos < len(tokens) and tokens[pos] != '}':
                if tokens[pos] in (',', ';'):
                    pos += 1
                    continue
                if pos + 1 < len(tokens) and tokens[pos + 1] == '=' and re.fullmatch(r'[A-Za-z_]\w*', tokens[pos]):
                    key = tokens[pos]
                    pos += 2
                    if key in fields and key in reject_duplicate_fields:
                        raise ValueError("Save Editor native source has a duplicate field: " + key)
                    fields[key] = value()
                else:
                    members.append(value())
                if pos < len(tokens) and tokens[pos] in (',', ';'):
                    pos += 1
            if pos < len(tokens):
                pos += 1
            return {'fields': fields, 'members': members}
        start = pos
        while pos < len(tokens) and tokens[pos] not in (',', ';', '}'):
            pos += 1
        if start == pos:
            pos += 1
        return ' '.join(tokens[start:pos]).strip()

    return value()


def _scalar(value):
    if isinstance(value, str):
        match = _STRING.fullmatch(value)
        if match:
            return _sjson_unescape(match.group(1))
    return value


def _raw(value):
    if isinstance(value, dict):
        return '{' + ', '.join(
            [k + ' = ' + _raw(v) for k, v in value['fields'].items()] +
            [_raw(v) for v in value['members']]
        ) + '}'
    return str(_scalar(value))


def _observed_path(root, path):
    """Report stored evidence, never future scene eligibility.

    Only durable GameState fields can be observed from a cold save.
    CurrentRun and nonliteral authored selectors require live context.
    """
    if not path or path[0] != 'GameState':
        return 'unknown', None
    current = root
    try:
        for part in path:
            if not isinstance(current, LuaTable):
                return 'unknown', None
            current = current.get(part)
    except AmbiguousLuaKeyError:
        return 'ambiguous', None
    if current is None:
        return 'absent', None
    if type(current) is bool:
        return ('recorded' if current else 'absent'), str(current).lower()
    if type(current) in (int, float, str):
        # Bounded diagnostic values, not an instruction to infer a predicate.
        value = str(current)
        return 'recorded', value[:120] + ('...' if len(value) > 120 else '')
    return 'recorded', None


def _requirement_nodes(node, root):
    """Retain AND/OR grouping and surface cold-observable leaves separately."""
    if not isinstance(node, dict):
        return {'kind': 'unknown', 'text': _raw(node), 'evidence': 'unknown', 'children': []}
    fields, members = node['fields'], node['members']
    if not fields:
        return {'kind': 'and', 'text': 'AND', 'evidence': 'unknown',
                'children': [_requirement_nodes(member, root) for member in members]}
    children = []
    path = None
    for key in ('PathTrue', 'PathFalse', 'Path'):
        arg = fields.get(key)
        if isinstance(arg, dict):
            path = [_scalar(p) for p in arg['members']]
            break
    if path:
        # For Path + predicate, observing a value is not evaluating the full
        # comparison. Likewise PathFalse is a cold-state fact, not eligibility.
        evidence, observation = _observed_path(root, path)
        name = next(k for k in ('PathTrue', 'PathFalse', 'Path') if k in fields)
        suffix = ' / ' + ', '.join(k + ': ' + _raw(v) for k, v in fields.items() if k not in ('Path', 'PathTrue', 'PathFalse')) if len(fields) > 1 else ''
        children.append({'kind': 'path', 'text': name + ': ' + '.'.join(str(p) for p in path) + suffix,
                         'evidence': evidence, 'observation': observation, 'children': []})
    for key, item in fields.items():
        if key in ('Path', 'PathTrue', 'PathFalse') or (path and key in ('HasAll', 'HasAny', 'HasNone', 'Comparison', 'Value', 'Min', 'Max')):
            continue
        if key in ('OrRequirements', 'GameStateRequirements') and isinstance(item, dict):
            children.append({'kind': 'or' if key == 'OrRequirements' else 'and', 'text': key,
                             'evidence': 'unknown', 'children': [_requirement_nodes(v, root) for v in item['members']]})
        elif key in ('NamedRequirements', 'NamedRequirementsFalse', 'FunctionName', 'ChanceToPlay'):
            children.append({'kind': 'dynamic', 'text': key + ': ' + _raw(item),
                             'evidence': 'unknown', 'children': []})
        elif isinstance(item, dict):
            children.append({'kind': 'and', 'text': key, 'evidence': 'unknown',
                             'children': [_requirement_nodes(v, root) for v in item['members']]
                             + [_requirement_nodes({'fields': {k: v}, 'members': []}, root) for k, v in item['fields'].items()]})
        else:
            children.append({'kind': 'predicate', 'text': key + ': ' + _raw(item),
                             'evidence': 'unknown', 'children': []})
    children.extend(_requirement_nodes(v, root) for v in members)
    return {'kind': 'and', 'text': 'AND', 'evidence': 'unknown', 'children': children}


def _original_roots(game_path):
    if game_path is None:
        from .config import GAME_SPEC
        game_path = GAME_SPEC.app_path
    base = Path(game_path)
    candidates = (
        (base / 'Contents/Resources/Content/Scripts', base / 'Contents/Resources/Content/Game/Text'),
        (base / 'Contents/Resources/Scripts', base / 'Contents/Resources/Game/Text'),
        (base / 'Content/Scripts', base / 'Content/Game/Text'),
        (base / 'sources/Scripts', base / 'sources/Text'),
    )
    for scripts, text in candidates:
        if scripts.is_dir() and text.is_dir():
            return scripts, text
    return None, None


def _source_signature(game_path):
    """Cheap freshness signature for the installed source set.

    This deliberately avoids reading file contents on the typeahead path. File
    identity, size, mode, mtime and ctime detect normal replacement and in-place
    rewrites, including replacement that preserves mtime. Deliberate detail
    retrieval still forces a byte capture/hash before presenting evidence.
    """
    scripts, texts = _original_roots(game_path)
    roots = tuple(str(path.resolve()) for path in (scripts, texts)) if scripts else ()
    entries = []
    if scripts:
        groups = [('Scripts', scripts, sorted(scripts.glob('*.lua')))]
        groups.extend((language, texts / language, sorted((texts / language).rglob('*.sjson')))
                      for language in ('en', 'zh-CN'))
        for owner, folder, paths in groups:
            for path in paths:
                if path.name.startswith('._'):
                    continue
                name = path.relative_to(folder).as_posix()
                try:
                    stat = path.stat()
                except OSError:
                    identity = None
                else:
                    identity = (
                        stat.st_dev, stat.st_ino, stat.st_mode, stat.st_size,
                        stat.st_mtime_ns, stat.st_ctime_ns,
                    )
                entries.append((owner, name, identity))
    return roots, tuple(entries)


def _capture_native(game_path):
    """Capture and hash the exact native bytes used for parsed evidence.

    Queries reuse the parsed capture while the cheap source signature is
    unchanged. Any signature change, and every deliberate detail read, returns
    through this byte-level integrity boundary before evidence is presented.
    """
    scripts, texts = _original_roots(game_path)
    roots = [str(path.resolve()) for path in (scripts, texts)] if scripts else []
    inputs, errors = [], []
    if scripts:
        groups = [('Scripts', scripts, sorted(scripts.glob('*.lua')))]
        groups.extend((language, texts / language, sorted((texts / language).rglob('*.sjson')))
                      for language in ('en', 'zh-CN'))
        for owner, folder, paths in groups:
            for path in paths:
                if path.name.startswith('._'):
                    continue
                name = path.relative_to(folder).as_posix()
                try:
                    content = path.read_bytes()
                    raw = content.decode('utf-8-sig')
                except OSError:
                    content, raw = None, None
                    errors.append({'input': owner + '/' + name, 'reason': 'unreadable'})
                except UnicodeError:
                    raw = None
                    errors.append({'input': owner + '/' + name, 'reason': 'invalidEncoding'})
                digest = hashlib.sha256(content).hexdigest() if content is not None else None
                inputs.append((owner, name, digest, raw))
    manifest = {'roots': roots, 'inputs': [item[:3] for item in inputs]}
    identity = hashlib.sha256(json.dumps(manifest, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()
    return {
        'identity': identity, 'roots': roots, 'inputs': inputs, 'errors': errors,
        'signature': _source_signature(game_path),
    }


def _load_native(source, expected_hash):
    observed_hash = next((digest for owner, name, digest, raw in source['inputs']
                          if owner == 'Scripts' and name == 'StoryResetData.lua'), None)
    provenance = {
        'roots': source['roots'], 'storyResetSHA256': observed_hash,
        'expectedStoryResetSHA256': expected_hash,
        'storyResetVerification': 'matched' if observed_hash == expected_hash else 'missing' if observed_hash is None else 'mismatch',
        # This index certifies only the StoryReset boundary. Other consumers
        # verify their specific mutation owners in the shared native registry;
        # installed NPC text and translations remain observational evidence.
        'buildVerification': 'unverified',
        'limitation': 'The complete installed script/localization set has no supported-build digest manifest.',
    }
    result = {'status': 'available', 'scenes': {}, 'quests': {}, 'resources': {}, 'events': {}, 'text': {'en': {}, 'zh-CN': {}},
              'scriptHashes': {name: digest for owner, name, digest, raw in source['inputs'] if owner == 'Scripts'},
              'errors': source['errors'], 'sourceIdentity': source['identity'], 'sourceProvenance': provenance}
    if observed_hash is None or observed_hash != expected_hash:
        result['status'] = 'missing' if observed_hash is None else 'mismatch'
        return result

    by_language = {'en': defaultdict(list), 'zh-CN': defaultdict(list)}
    events = defaultdict(list)
    for language in ('en', 'zh-CN'):
        for owner, filename, digest, raw in source['inputs']:
            if owner != language or raw is None:
                continue
            # Per-record Id positions, bounded by the enclosing Texts item.
            masked = _masked(raw, lua=False)
            table_ends = _braces(masked)
            for opening, closing in table_ends.items():
                if closing - opening > 50000:
                    continue
                record = raw[opening + 1:closing]
                # A syntactically valid field must occur outside comments and
                # quoted literals. Unmasked record regexes can otherwise turn
                # commented-out Id/DisplayName assignments into official text
                # (or discard the real entry when a second Id is seen).
                record_mask = masked[opening + 1:closing]
                fields = {}
                for field in _TEXT_FIELD.finditer(record):
                    name = field.group(1)
                    if record_mask[field.start():field.start() + len(name)] == name:
                        fields[name] = _sjson_unescape(field.group(2))
                cue_id = fields.get('Id')
                if not cue_id or not fields.get('DisplayName'):
                    continue
                # A Texts entry owns its Id directly. Its outer Texts wrapper
                # and any nested content must not yield duplicate translations.
                identifiers = list(re.finditer(r'\bId\s*=', record_mask))
                if len(identifiers) != 1 or '{' in record_mask[:identifiers[0].start()]:
                    continue
                entry = {'id': cue_id, 'text': fields['DisplayName'], 'speaker': fields.get('Speaker', ''),
                         'event': fields.get('Event', ''), 'source': filename}
                by_language[language][cue_id].append(entry)
                # Both installed languages can own Event annotations; never
                # require an English counterpart to discover a zh-only cue.
                if entry['event']:
                    events[entry['event']].append(cue_id)

    candidates = set(STORY_RESET_TEXT_IDS)
    candidates.update(events)
    scenes = defaultdict(list)
    quests = defaultdict(list)
    resources = defaultdict(list)
    for owner, filename, digest, raw in source['inputs']:
        if owner != 'Scripts' or raw is None:
            continue
        masked = _masked(raw, lua=True)
        parents = {}
        pairs = _braces(masked, parents)
        assignments = list(_ASSIGN.finditer(masked))
        # Quest definitions are immediate members of the named native owner.
        # Nested progress/voice tables with a matching key are not definitions.
        quest_owners = {match.start(1) for match in re.finditer(
            r'\bOverwriteTableKeys\s*\(\s*QuestData\s*,\s*(\{)', masked)}
        quest_owners.update(match.start(2) for match in assignments if match.group(1) == 'QuestData')
        resource_owners = {match.start(1) for match in re.finditer(
            r'\bOverwriteTableKeys\s*\(\s*ResourceData\s*,\s*(\{)', masked)}
        resource_owners.update(match.start(2) for match in assignments if match.group(1) == 'ResourceData')
        for match in assignments:
            opening = match.start(2)
            if parents.get(opening) in resource_owners and opening in pairs:
                resources[match.group(1)].append({'file': filename,
                    'line': raw.count('\n', 0, match.start()) + 1,
                    'script': raw[opening:pairs[opening] + 1]})
            if parents.get(opening) not in quest_owners or opening not in pairs:
                continue
            quests[match.group(1)].append({
                'file': filename, 'line': raw.count('\n', 0, match.start()) + 1,
                'script': raw[opening:pairs[opening] + 1],
            })
        # Authored scene identity belongs to an immediate TextLineSets entry.
        # StoryReset and localized Event IDs are supplementary evidence, not
        # admission gates: many real native scenes have neither association.
        # The direct-parent test avoids classifying arbitrary voice-line lists
        # or nested Cue tables as standalone scenes.
        text_line_owners = {
            assignment.start(2) for assignment in assignments
            if assignment.group(1).endswith('TextLineSets')
        }
        for match in assignments:
            name = match.group(1)
            opening = match.start(2)
            authored_scene = parents.get(opening) in text_line_owners
            if not authored_scene and name not in candidates:
                continue
            if not authored_scene and name.endswith(('VoiceLines', 'TextLineSets')):
                continue
            end = pairs.get(opening)
            if end is None:
                continue
            body = raw[opening: end + 1]
            active_body = _lua_without_comments(body)
            cues = [c.group(1) for c in _CUE.finditer(active_body)]
            partner = bool(re.search(r'\b(?:Partner|CopyDataFromPartner)\b', active_body))
            # A line set may forward its dialogue through a partner without a
            # local Cue. Mere key/requirement resemblance outside these owners
            # is insufficient to turn a generic speech table into a scene.
            if not cues and not partner and (
                'GameStateRequirements' not in active_body or
                name not in candidates
            ):
                continue
            scenes[name].append({'file': filename, 'line': raw.count('\n', 0, match.start()) + 1,
                                 'script': body, 'search': active_body, 'cues': cues,
                                 'partner': partner})
    result.update(scenes=dict(scenes), quests=dict(quests), resources=dict(resources), events=dict(events),
                  text={lang: dict(index) for lang, index in by_language.items()})
    return result


def _cached(source, expected_hash):
    # Retain parsed source evidence only, not the large input snapshot or any
    # mutable save document. Freshness and supported-reset validity are distinct.
    key = (source['identity'], expected_hash)
    if key not in _NATIVE_CACHE:
        _NATIVE_CACHE[key] = _load_native(source, expected_hash)
    _NATIVE_CACHE.move_to_end(key)
    while len(_NATIVE_CACHE) > 2:
        _NATIVE_CACHE.popitem(last=False)
    return _NATIVE_CACHE[key]


class NativeDialogueInvestigation:
    """Search current installed evidence with the caller's static save state."""

    def __init__(self, game_path=None, *, expected_hash=_SUPPORTED_STORY_SHA):
        # Cache only source evidence, never a LuaTable from a mutable Save
        # document. Query/detail receive the workspace's current document.
        self.game_path = str(game_path) if game_path is not None else None
        self.expected_hash = expected_hash
        self.native = None
        self._native_signature = None
        self._query_index = {}
        self._refresh(force=True)

    def _refresh(self, *, force=False):
        if not force and self.native is not None:
            current = _source_signature(self.game_path)
            if current == self._native_signature:
                return False
        source = _capture_native(self.game_path)
        native = _cached(source, self.expected_hash)
        if self.native is not native:
            self._query_index = {}
        self.native = native
        self._native_signature = source['signature']
        return True

    def _records(self, save_root):
        try:
            state = save_root['GameState']
            lines = state['TextLinesRecord']
        except (KeyError, TypeError, AmbiguousLuaKeyError):
            return {}, {'__owner__'}
        if not isinstance(lines, LuaTable):
            return {}, {'__owner__'}
        values, ambiguous = {}, set()
        for key, value in lines.entries():
            if type(key) is str:
                if key in values:
                    ambiguous.add(key)
                else:
                    values[key] = value
        return values, ambiguous

    def quest_rows(self, save_root, language, *, include_absent=False):
        """Read lifecycle companions beside the existing physical quest action."""
        self._refresh()
        from .localization import official_display_names
        from .save_native_ids import QUEST_IDS
        zh = language == 'zh-CN'
        try:
            state = save_root['GameState']
        except (KeyError, TypeError, AmbiguousLuaKeyError):
            state = None
        try:
            statuses = state.get('QuestStatus')
            status_owner_error = None if isinstance(statuses, LuaTable) else 'unknown'
        except AmbiguousLuaKeyError:
            statuses, status_owner_error = None, 'ambiguous'
        except (AttributeError, TypeError):
            statuses, status_owner_error = None, 'unknown'
        observed = {key for key, _ in statuses.entries() if isinstance(key, str)} if isinstance(statuses, LuaTable) else set()
        names = (observed | (set(self.native['quests']) & QUEST_IDS if include_absent else set())) & QUEST_IDS
        localized = official_display_names(names, language, game_path=self.game_path)
        english = official_display_names(names, 'en', game_path=self.game_path)

        def observation(owner, name):
            try:
                value = state.get(owner) if isinstance(state, LuaTable) else None
                if not isinstance(value, LuaTable):
                    return None, 'unsupportedOwner'
                value = value.get(name)
            except AmbiguousLuaKeyError:
                return None, 'ambiguousOwner'
            return (value, None) if value is None or type(value) is bool else (None, 'unsupportedOwner')

        rows = []
        for name in sorted(names):
            title = localized.get(name) or ('任务 · ' if zh else 'Quest · ') + name
            en = english.get(name) or 'Quest · ' + name
            try:
                status = statuses.get(name) if isinstance(statuses, LuaTable) else None
                status = status_owner_error or (status if status in ('Unlocked', 'Complete', 'CashedOut') else 'absent' if status is None else 'unknown')
            except AmbiguousLuaKeyError:
                status = 'ambiguous'
            common = {'entityId': 'quest:' + name, 'entityName': title,
                      'editable': False, 'mutationKinds': [], 'choices': [],
                      'group': '命运清单' if zh else 'Fated List quests', '_browseReadOnly': True,
                      '_search': (name, title, en, *(source['script'] for source in self.native['quests'].get(name, ()))),
                      'reasonCode': 'questContextReadOnly',
                      'reason': ('此项展示原生条件和调查结果；保存字段在同一任务下单独编辑。' if zh else
                                 'Shows authored conditions and investigation results; edit saved fields on this quest.')}
            rows.append({**common, 'id': 'investigate:quest:' + name, 'domain': 'investigate',
                         'rawId': 'quest:' + name, 'path': ['GameState', 'QuestStatus', name],
                         'name': '任务状态与原生条件' if zh else 'Quest state and authored conditions',
                         'englishName': 'Quest state and authored conditions', 'valueType': 'string', 'value': status,
                         'snippet': {
                             'absent': ('状态未记录', 'Status unrecorded'),
                             'Unlocked': ('已解锁', 'Unlocked'), 'Complete': ('已完成', 'Complete'),
                             'CashedOut': ('已领取奖励', 'Reward claimed'),
                             'ambiguous': ('记录存在歧义', 'Ambiguous record'),
                             'unknown': ('未识别状态', 'Unidentified state'),
                         }[status][0 if zh else 1]})
            for owner, labels in (
                ('QuestsCompleted', ('完成记录', 'Completion record')),
                ('QuestsViewed', ('已查看', 'Viewed')),
                ('QuestsUpdated', ('更新提示', 'Update marker')),
                ('PlayedQuestInterstitials', ('已播放任务过场', 'Quest interstitial played')),
            ):
                value, reason = observation(owner, name)
                from . import save_narrative
                record = save_narrative.entry_row(save_root, 'questObservation:' + owner + ':' + name, language, self.game_path)
                rows.append({**common, **record})
        return rows

    def spoken_rows(self, save_root, scenes, language):
        """Join native cue-count observations to the source-proven NPC entity."""
        zh = language == 'zh-CN'
        rows, seen = [], set()
        for scene in scenes:
            if not scene.get('entityId'):
                continue
            for line in self._text_records(scene['rawId']):
                cue = '/VO/' + line['cueId']
                identity = scene['entityId'] + ':' + cue
                if identity in seen:
                    continue
                seen.add(identity)
                try:
                    state = save_root['GameState']
                    speech = state.get('SpeechRecord')
                    if not isinstance(speech, LuaTable):
                        continue
                    count = speech.get(cue)
                    if count is None:
                        continue
                    reason = None if type(count) is bool or (type(count) in (int, float) and math.isfinite(count) and count >= 0 and count == int(count)) else 'unsupportedOwner'
                except (KeyError, TypeError, AmbiguousLuaKeyError):
                    count, reason = None, 'ambiguousOwner'
                phrases = line['zhCN' if zh else 'en']
                english = line['en']
                title = next(iter(phrases), '未翻译台词' if zh else 'Untranslated line')
                en = next(iter(english), 'Untranslated line')
                from . import save_narrative
                authority = save_narrative.entry_row(save_root, 'speech:' + cue, language, self.game_path)
                row = {**authority,
                    'entityId': scene['entityId'], 'entityName': scene['entityName'],
                    'name': ('语音记录 · ' if zh else 'Speech history · ') + title[:100],
                    'englishName': 'Speech history · ' + en[:100],
                    '_browseReadOnly': True, 'group': '语音历史' if zh else 'Speech history',
                    '_search': (cue, title, en),
                }
                rows.append(row)

        return rows

    def quest_detail(self, save_root, name, language):
        self._refresh(force=True)
        rows = self.quest_rows(save_root, language, include_absent=True)
        overview = next((row for row in rows if row['id'] == 'investigate:quest:' + name), None)
        if overview is None:
            raise ValueError('Save Editor native quest identity is unknown.')
        definitions, visited, active, unresolved = [], set(), set(), []

        def collect(identity):
            if identity in active:
                unresolved.append(identity)
                return
            if identity in visited:
                return
            visited.add(identity)
            active.add(identity)
            sources = self.native['quests'].get(identity, ())
            if len(sources) != 1:
                unresolved.append(identity)
                active.remove(identity)
                return
            source = sources[0]
            fields = _parse_lua_table(source['script'])
            if not isinstance(fields, dict):
                unresolved.append(identity)
                active.remove(identity)
                return
            authored = []
            for field in ('UnlockGameStateRequirements', 'CompleteGameStateRequirements', 'SetupEvents'):
                if field in fields['fields']:
                    title = ('解锁条件' if language == 'zh-CN' else 'Unlock conditions') if field.startswith('Unlock') else (
                        '完成条件' if language == 'zh-CN' else 'Completion conditions')
                    if field == 'SetupEvents':
                        title = '阶段条件（由原生运行时选择）' if language == 'zh-CN' else 'Stage conditions (selected by native runtime)'
                    if identity != name:
                        title += ('（继承定义）' if language == 'zh-CN' else ' (inherited definition)')
                    authored.append({'line': source['line'], 'scope': identity + ' · ' + field,
                                     'tree': {'kind': 'and', 'text': title, 'evidence': 'unknown',
                                              'children': [_requirement_nodes(fields['fields'][field], save_root)]}})
            inheritance = fields['fields'].get('InheritFrom')
            definitions.append({'file': source['file'], 'line': source['line'], 'partner': False,
                                'requirements': authored, 'cueIDs': []})
            if isinstance(inheritance, dict):
                for parent in inheritance['members']:
                    parent_id = _scalar(parent)
                    if isinstance(parent_id, str):
                        collect(parent_id)
                    else:
                        unresolved.append('dynamic inheritance')
            active.remove(identity)

        collect(name)
        block_code = 'questContextReadOnly'
        if unresolved:
            block_code = 'questSourceUnresolved'
        return {'scene': 'quest:' + name, 'status': overview['value'],
                'sourceStatus': self.native['status'], 'sourceIdentity': self.native['sourceIdentity'],
                'sourceProvenance': self.native['sourceProvenance'], 'sourceErrors': self.native['errors'],
                'reason': overview['reason'], 'blockReasonCode': block_code,
                'canStage': False, 'stageID': '', 'character': overview['entityName'],
                'definitions': definitions, 'sourceResolution': 'unresolved' if unresolved or not definitions else 'resolved',
                'unresolvedOwners': unresolved, 'lines': [], 'futureEligibility': 'unknown', 'language': language}

    def _names(self, scene):
        native = self.native
        first = (native['scenes'].get(scene) or [{}])[0]
        file = first.get('file', '')
        person = file.partition('NPCData_')[2].partition('.')[0] if 'NPCData_' in file else ''
        if not person:
            person = scene.split('About', 1)[0].split('Post', 1)[0].split('With', 1)[0]
        npc = 'NPC_' + person + '_01' if person else ''
        localized = {}
        for language in ('en', 'zh-CN'):
            names = native['text'][language].get(npc, ())
            localized[language] = next((item['text'] for item in names if item['text']), person)
        return person, npc, localized

    def _data(self, scene, records, ambiguous):
        native = self.native
        state = 'ambiguous' if scene in ambiguous or '__owner__' in ambiguous else (
            'recorded' if records.get(scene) is True else
            'notRecorded' if scene in native['scenes'] or scene in STORY_RESET_TEXT_IDS else 'unknown')
        return state

    def _text_records(self, scene):
        native = self.native
        # Lua orders the actual spoken lines. SJSON Event tags may reference
        # alternate or shared cues, but filename order is not dialogue order.
        ids = []
        for definition in native['scenes'].get(scene, ()):
            for cue in definition['cues']:
                if cue not in ids:
                    ids.append(cue)
        for cue in native['events'].get(scene, ()):
            if cue not in ids:
                ids.append(cue)
        en = native['text']['en']
        zh = native['text']['zh-CN']
        return [{'cueId': cue, 'en': [x['text'] for x in en.get(cue, ())],
                 'zhCN': [x['text'] for x in zh.get(cue, ())],
                 'speaker': next((x['speaker'] for lang in (en, zh)
                                  for x in lang.get(cue, ()) if x['speaker']), ''),
                 'events': sorted(set(x['event'] for lang in (en, zh)
                                      for x in lang.get(cue, ()) if x['event']))}
                for cue in ids]

    def _summary_row(self, scene, language, records, ambiguous, permissions):
        person, npc, localized = self._names(scene)
        name = (localized[language] + ' · ' + scene) if person else scene
        lines = self._text_records(scene)
        translated_key = 'zhCN' if language == 'zh-CN' else 'en'
        subtitle = next((phrase for row in lines for phrase in row[translated_key]), '')
        state = self._data(scene, records, ambiguous)
        decision = permissions.get(scene, {})
        can_stage = bool(decision.get('allowed') and state == 'recorded')
        block_code = None
        if state == 'recorded' and can_stage:
            reason = 'Native dialogue reset and companion owners validated.'
        elif state == 'recorded':
            block_code = decision.get('code') or 'invalidOwner'
            reason = decision.get('diagnostic') or 'The native dialogue owner was not validated for a standalone reset.'
        elif state == 'notRecorded':
            block_code = 'notPlayed'
            reason = 'No cold-save record: absence is not proof an event never occurred.'
        elif state == 'ambiguous':
            block_code = 'ambiguousOwner'
            reason = 'Duplicate or inaccessible native record owner; write blocked.'
        else:
            block_code = 'unverified'
            reason = 'No verified script scene identity: localization Event tags alone can name voice-line entrypoints.'
        if self.native['status'] != 'available':
            can_stage = False
            block_code = 'sourceUnavailable'
            reason = 'Game source missing or reset-manifest mismatch; native context unavailable.'
        sources = self.native['scenes'].get(scene) or ()
        native_person = bool(person) and (
            any('NPCData_' + person in source.get('file', '') for source in sources)
            or any(self.native['text'][locale].get(npc) for locale in ('en', 'zh-CN'))
        )
        return {
            'id': 'investigate:' + scene, 'domain': 'investigate', 'rawId': scene,
            'path': ['GameState', 'TextLinesRecord', scene],
            'name': name, 'englishName': (localized['en'] + ' · ' if person else '') + scene,
            'value': state == 'recorded', 'valueType': 'boolean',
            'editable': False, 'mutationKinds': [],
            'group': person or ('Other dialogue' if language == 'en' else '其他对话'),
            'entityId': 'person:' + person if native_person else None,
            'entityName': localized[language] if native_person else None,
            'status': state, 'snippet': subtitle, 'sourceStatus': self.native['status'],
            'content': [_clean_display_name(phrase) for row in lines for phrase in row[translated_key]],
            'playbackKnown': bool(sources) or scene in STORY_RESET_TEXT_IDS,
            'sourceIdentity': self.native['sourceIdentity'],
            'reason': reason, 'blockReasonCode': block_code,
            'canStage': can_stage, 'stageID': 'dialogueReset:' + scene if can_stage else '',
        }

    def scene_row(self, save_root, scene, language, permissions):
        self._refresh()
        records, ambiguous = self._records(save_root)
        return self._summary_row(scene, language, records, ambiguous, permissions)

    def query(self, save_root, *, search, offset, limit, language, permissions, state_filter="all", include_unobserved=False):
        self._refresh()
        records, ambiguous = self._records(save_root)
        # An empty search never floods the user with thousands of unobserved
        # native scenes; deliberate queries expand the discoverable index.
        if search.strip() or state_filter != 'all' or include_unobserved:
            candidates = set(records) | set(self.native['events']) | set(self.native['scenes']) | set(STORY_RESET_TEXT_IDS)
        else:
            candidates = {name for name, value in records.items() if value is True}
        # Retain only source-derived names/text for current candidates. Save
        # state, permissions and presentation rows are rebuilt for every query.
        self._query_index = {scene: metadata for scene, metadata in self._query_index.items()
                             if scene in candidates}
        words = search.casefold().split()
        matches = []
        for scene in candidates:
            state = self._data(scene, records, ambiguous)
            if state_filter != "all" and state != state_filter:
                continue
            metadata = self._query_index.get(scene)
            if metadata is None and words:
                person, npc, localized = self._names(scene)
                lines = self._text_records(scene)
                corpus = ' '.join((scene, person, npc, *localized.values(),
                    *(line['cueId'] + ' ' + ' '.join(line['en']) + ' ' + ' '.join(line['zhCN'])
                      + ' ' + ' '.join(line['events']) for line in lines))).casefold()
                metadata = self._query_index[scene] = person, corpus
            if metadata is None:
                person, _, _ = self._names(scene)
            else:
                person, corpus = metadata
                if words and not all(word in corpus for word in words):
                    continue
            group = person or ('Other dialogue' if language == 'en' else '其他对话')
            matches.append((state != 'recorded', group.casefold(), scene))
        matches.sort()
        rows = [self._summary_row(scene, language, records, ambiguous, permissions)
                for _, _, scene in matches[offset:offset + limit]]
        return {'total': len(matches), 'items': rows, 'sourceStatus': self.native['status'],
                'sourceIdentity': self.native['sourceIdentity'], 'sourceProvenance': self.native['sourceProvenance'],
                'sourceErrors': self.native['errors']}

    def detail(self, save_root, scene, language, permissions):
        if scene.startswith('quest:'):
            return self.quest_detail(save_root, scene[len('quest:'):], language)
        # Detail is deliberate evidence retrieval rather than typeahead. Force
        # byte capture/hash here so presented native context is integrity-bound
        # even if filesystem metadata was preserved unusually.
        self._refresh(force=True)
        records, ambiguous = self._records(save_root)
        if scene not in records and scene not in STORY_RESET_TEXT_IDS and scene not in self.native['scenes'] and scene not in self.native['events']:
            raise ValueError('Save Editor native scene identity is unknown.')
        overview = self._summary_row(scene, language, records, ambiguous, permissions)
        definitions = []
        for definition in self.native['scenes'].get(scene, ()):
            body = definition['script']
            mask = _masked(body, lua=True)
            pairs = _braces(mask)
            authored = []
            for hit in re.finditer(r'\b(?:GameStateRequirements|LineRequirements|Requirements)\s*=\s*(\{)', mask):
                end = pairs.get(hit.start(1))
                if end is None:
                    continue
                # Nested line requirements are distinguished from scene-wide
                # requirements by their offset in the source definition.
                snippet = body[hit.start(1):end + 1]
                first_cue = re.search(r'\bCue\s*=', mask)
                scope = 'scene' if first_cue is None or hit.start() < first_cue.start() else 'line'
                authored.append({'line': definition['line'] + body.count('\n', 0, hit.start()),
                                 'scope': scope,
                                 'tree': _requirement_nodes(_parse_lua_table(snippet), save_root)})
            definitions.append({'file': definition['file'], 'line': definition['line'],
                                'partner': definition['partner'], 'requirements': authored,
                                'cueIDs': definition['cues']})
        return {'scene': scene, 'status': overview['status'], 'sourceStatus': self.native['status'],
                'sourceIdentity': self.native['sourceIdentity'], 'sourceProvenance': self.native['sourceProvenance'],
                'sourceErrors': self.native['errors'],
                'reason': overview['reason'], 'blockReasonCode': overview['blockReasonCode'],
                'canStage': overview['canStage'],
                'stageID': overview['stageID'], 'character': overview['group'],
                'definitions': definitions, 'sourceResolution': 'resolved' if definitions else 'unresolved',
                'lines': self._text_records(scene),
                'futureEligibility': 'unknown', 'language': language}
