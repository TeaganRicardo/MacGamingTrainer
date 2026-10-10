"""Read-only, installed-source investigation of Hades II dialogue in a cold save.

All narrative content is read from the supported game installation, never bundled
with the Trainer. Source ownership is many-to-many; game-state observations are
not predictions of future dialogue eligibility.
"""

from collections import defaultdict
from functools import lru_cache
import hashlib
from pathlib import Path
import re

from .localization import _sjson_unescape
from .save_document import AmbiguousLuaKeyError, LuaTable
from .save_native_ids import STORY_RESET_TEXT_IDS

_SUPPORTED_STORY_SHA = "58509042a27542f96d666071da2fa58ca3c3b227002e4ae628501b7d7738ef8e"
_ASSIGN = re.compile(r"(?m)^[ \t]*([A-Za-z_][A-Za-z_0-9]*)[ \t]*=[ \t]*(?:\r?\n[ \t]*)?(\{)")
_TEXT_FIELD = re.compile(r'\b(Id|Event|Speaker|DisplayName)\s*=\s*"((?:\\.|[^"\\])*)"')
_CUE = re.compile(r'\bCue\s*=\s*"/VO/((?:\\.|[^"\\])*)"')
_STRING = re.compile(r'^"((?:\\.|[^"\\])*)"$')
_LUA_TOKENS = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[A-Za-z_][A-Za-z0-9_]*|-?\d+(?:\.\d+)?|[{}=,;\[\].()]|[^\s]', re.S)


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


def _braces(masked):
    stack, pairs = [], {}
    for i, character in enumerate(masked):
        if character == '{':
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


def _parse_lua_table(source):
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
    if not path or path[0] != 'GameState':
        return 'unknown'
    current = root
    try:
        for part in path:
            if not isinstance(current, LuaTable):
                return 'unknown'
            current = current.get(part)
    except AmbiguousLuaKeyError:
        return 'ambiguous'
    if current is None or current is False:
        return 'absent'
    return 'recorded'


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
        evidence = _observed_path(root, path)
        name = next(k for k in ('PathTrue', 'PathFalse', 'Path') if k in fields)
        suffix = ' / ' + ', '.join(k + ': ' + _raw(v) for k, v in fields.items() if k not in ('Path', 'PathTrue', 'PathFalse')) if len(fields) > 1 else ''
        children.append({'kind': 'path', 'text': name + ': ' + '.'.join(str(p) for p in path) + suffix,
                         'evidence': evidence, 'children': []})
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


def _load_native(game_path, expected_hash):
    scripts, texts = _original_roots(game_path)
    if scripts is None:
        return {'status': 'missing', 'scenes': {}, 'events': {}, 'text': {'en': {}, 'zh-CN': {}}, 'errors': []}
    sentinel = scripts / 'StoryResetData.lua'
    try:
        observed_hash = hashlib.sha256(sentinel.read_bytes()).hexdigest()
    except OSError:
        return {'status': 'missing', 'scenes': {}, 'events': {}, 'text': {'en': {}, 'zh-CN': {}}, 'errors': []}
    if observed_hash != expected_hash:
        return {'status': 'mismatch', 'scenes': {}, 'events': {}, 'text': {'en': {}, 'zh-CN': {}}, 'errors': []}

    by_language = {'en': defaultdict(list), 'zh-CN': defaultdict(list)}
    events = defaultdict(list)
    for language in ('en', 'zh-CN'):
        folder = texts / language
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob('*.sjson')):
            if path.name.startswith('._'):
                continue
            try:
                raw = path.read_text(encoding='utf-8-sig')
            except (OSError, UnicodeError):
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
                         'event': fields.get('Event', ''), 'source': path.name}
                by_language[language][cue_id].append(entry)
                if language == 'en' and entry['event']:
                    events[entry['event']].append(cue_id)

    candidates = set(STORY_RESET_TEXT_IDS)
    candidates.update(events)
    scenes = defaultdict(list)
    for path in sorted(scripts.glob('*.lua')):
        if path.name.startswith('._'):
            continue
        try:
            raw = path.read_text(encoding='utf-8-sig')
        except (OSError, UnicodeError):
            continue
        masked = _masked(raw, lua=True)
        pairs = _braces(masked)
        for match in _ASSIGN.finditer(masked):
            name = match.group(1)
            if name not in candidates:
                continue
            opening = match.start(2)
            end = pairs.get(opening)
            if end is None:
                continue
            body = raw[opening: end + 1]
            # Guard against unrelated lookalike names (not all reset targets
            # are guaranteed to exist in scripts; preserving unresolved is intentional).
            active_body = _lua_without_comments(body)
            cues = [c.group(1) for c in _CUE.finditer(active_body)]
            if not cues and 'GameStateRequirements' not in body and name not in STORY_RESET_TEXT_IDS:
                continue
            scenes[name].append({'file': path.name, 'line': raw.count('\n', 0, match.start()) + 1,
                                 'script': body, 'search': active_body, 'cues': cues,
                                 'partner': bool(re.search(r'\b(?:Partner|CopyDataFromPartner)\b', body))})
    return {'status': 'available', 'scenes': dict(scenes), 'events': dict(events),
            'text': {lang: dict(index) for lang, index in by_language.items()}, 'errors': []}


@lru_cache(maxsize=2)
def _cached(game_path, expected_hash, signature):
    return _load_native(game_path, expected_hash)


class NativeDialogueInvestigation:
    """Search installed version-pinned native evidence with cold save state."""

    def __init__(self, save_root, game_path=None, *, expected_hash=_SUPPORTED_STORY_SHA):
        self.root = save_root
        path = str(game_path) if game_path is not None else None
        scripts, _ = _original_roots(path)
        try:
            signature = (scripts / 'StoryResetData.lua').stat().st_mtime_ns if scripts else None
        except OSError:
            signature = None
        self.native = _cached(path, expected_hash, signature)
        self.expected_hash = expected_hash

    def _records(self):
        try:
            state = self.root['GameState']
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

    def _names(self, scene):
        native = self.native
        first = (native['scenes'].get(scene) or [{}])[0]
        file = first.get('file', '')
        person = file.partition('NPCData_')[2].partition('.')[0] if 'NPCData_' in file else ''
        if not person:
            person = scene.split('About', 1)[0].split('Post', 1)[0].split('With', 1)[0]
        npc = 'NPC_' + person + '_01' if person else ''
        return person, npc

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
                 'speaker': next((x['speaker'] for x in en.get(cue, ()) if x['speaker']), ''),
                 'events': sorted(set(x['event'] for x in en.get(cue, ()) if x['event']))}
                for cue in ids]

    def _summary_row(self, scene, language, records, ambiguous, writable):
        person, npc = self._names(scene)
        name = scene
        if person:
            names = self.native['text'][language].get(npc, ())
            native_name = next((entry['text'] for entry in names if entry['text']), person)
            name = native_name + ' · ' + scene
        lines = self._text_records(scene)
        translated_key = 'zhCN' if language == 'zh-CN' else 'en'
        subtitle = next((phrase for row in lines for phrase in row[translated_key]), '')
        state = self._data(scene, records, ambiguous)
        can_stage = bool(scene in writable and state == 'recorded')
        if state == 'recorded':
            reason = 'Recorded; clearing is authorized only when native companion owners validate.'
        elif state == 'notRecorded':
            reason = 'No cold-save record: absence is not proof an event never occurred.'
        elif state == 'ambiguous':
            reason = 'Duplicate or inaccessible native record owner; write blocked.'
        else:
            reason = 'No verified script scene identity: localization Event tags alone can name voice-line entrypoints.'
        if self.native['status'] != 'available':
            can_stage = False
            reason = 'Supported game source missing or version mismatch; native context unavailable.'
        return {
            'id': 'investigate:' + scene, 'domain': 'investigate', 'rawId': scene,
            'path': ['GameState', 'TextLinesRecord', scene],
            'name': name, 'englishName': (person + ' · ' if person else '') + scene,
            'value': state == 'recorded', 'valueType': 'boolean',
            'editable': False, 'mutationKinds': [],
            'group': person or ('Other dialogue' if language == 'en' else '其他对话'),
            'status': state, 'snippet': subtitle, 'sourceStatus': self.native['status'],
            'reason': reason, 'canStage': can_stage, 'stageID': 'dialogue:' + scene if can_stage else '',
        }

    def query(self, *, search, offset, limit, language, writable, state_filter="all"):
        records, ambiguous = self._records()
        # An empty search never floods the user with thousands of unobserved
        # native scenes; deliberate queries expand the discoverable index.
        if search.strip():
            candidates = set(records) | set(self.native['events']) | set(self.native['scenes']) | set(STORY_RESET_TEXT_IDS)
        else:
            candidates = {name for name, value in records.items() if value is True}
        needle = search.casefold().strip()
        rows = []
        for scene in candidates:
            if needle:
                person, _ = self._names(scene)
                corpus = (scene, person)
                if not any(needle in token.casefold() for token in corpus):
                    definitions = self.native['scenes'].get(scene, ())
                    # Authored requirement paths, named predicates and scene
                    # associations remain searchable without rewriting them.
                    if not any(needle in definition['search'].casefold() for definition in definitions):
                        lines = self._text_records(scene)
                        if not any(needle in (line['cueId'] + ' ' + ' '.join(line['en']) + ' ' + ' '.join(line['zhCN'])
                                              + ' ' + ' '.join(line['events'])).casefold() for line in lines):
                            continue
            row = self._summary_row(scene, language, records, ambiguous, writable)
            if state_filter == "all" or row["status"] == state_filter:
                rows.append(row)
        rows.sort(key=lambda row: (row['status'] != 'recorded', row['group'].casefold(), row['rawId']))
        return {'total': len(rows), 'items': rows[offset:offset + limit], 'sourceStatus': self.native['status']}

    def detail(self, scene, language, writable):
        records, ambiguous = self._records()
        if scene not in records and scene not in STORY_RESET_TEXT_IDS and scene not in self.native['scenes'] and scene not in self.native['events']:
            raise ValueError('Save Editor native scene identity is unknown.')
        overview = self._summary_row(scene, language, records, ambiguous, writable)
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
                                 'tree': _requirement_nodes(_parse_lua_table(snippet), self.root)})
            definitions.append({'file': definition['file'], 'line': definition['line'],
                                'partner': definition['partner'], 'requirements': authored,
                                'cueIDs': definition['cues']})
        return {'scene': scene, 'status': overview['status'], 'sourceStatus': self.native['status'],
                'reason': overview['reason'], 'canStage': overview['canStage'],
                'stageID': overview['stageID'], 'character': overview['group'],
                'definitions': definitions, 'sourceResolution': 'resolved' if definitions else 'unresolved',
                'lines': self._text_records(scene),
                'futureEligibility': 'unknown', 'language': language}
