#!/usr/bin/env python3
"""Extract Save Editor identities from supported native text; never run Lua."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from generate_hades_catalog import text_records, render_text

ROOT = Path(__file__).resolve().parents[1]

_LUA_TOKEN = re.compile(r'--\[\[.*?\]\]|--[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[A-Za-z_]\w*|-?\d+(?:\.\d+)?|[{}\[\]=,;.]', re.DOTALL)


def lua_string(token):
    return re.sub(r'\\([nrt"\'\\])', lambda match: {
        'n': '\n', 'r': '\r', 't': '\t', '"': '"', "'": "'", '\\': '\\',
    }[match[1]], token[1:-1])


def native_tables(source):
    """Read literal table structure and string attributes without running Lua."""
    tokens = [token for token in _LUA_TOKEN.findall(source) if not token.startswith('--')]
    roots, stack = [], []
    for index, token in enumerate(tokens):
        if token == '{':
            key = None
            if index > 1 and tokens[index - 1] == '=':
                key = tokens[index - 2]
                if key == ']' and index > 3: key = tokens[index - 3]
                if key.startswith(('"', "'")): key = lua_string(key)
            node = {'key': key, 'fields': {}, 'children': []}
            (stack[-1]['children'] if stack else roots).append(node)
            stack.append(node)
        elif token == '}':
            if not stack: raise ValueError('Unmatched native table close')
            stack.pop()
        elif (stack and index + 2 < len(tokens) and tokens[index + 1] == '='
              and tokens[index + 2].startswith(('"', "'"))):
            stack[-1]['fields'][token] = lua_string(tokens[index + 2])
    if stack: raise ValueError('Unclosed native literal table')
    return roots


def scene_lines(node):
    # Only displayed line/choice nodes contribute content. Requirement tables,
    # event arguments and voice-line callback metadata are never search prose.
    if node['fields'].get('Text'): yield node['fields']
    for child in node['children']:
        if child['key'] is None or child['key'].isdigit() or child['key'] == 'Choices':
            yield from scene_lines(child)


def extract_scenes(paths, localized):
    scenes = {}

    def visit(node, ancestors):
        key = node['key'] or ''
        if key.endswith('TextLineSets'):
            source = next((parent for parent in reversed(ancestors)
                           if parent['fields'].get('Speaker') or (parent['key'] or '').startswith('NPC_')), None)
            owner = (source['fields'].get('Speaker') or source['key']) if source else ''
            for scene in node['children']:
                if not scene['key']: continue
                lines = list(scene_lines(scene))
                if not lines: continue
                result = scenes.setdefault(scene['key'], {'owner': owner, 'content': {'en': [], 'zh-CN': []}})
                for line in lines:
                    cue = line.get('Cue', '').removeprefix('/VO/')
                    speaker = line.get('Speaker') or owner or cue.split('_')[0]
                    # Narrative.lua:470..476 identifies CharProtag as the hero,
                    # whose official label is PlayerUnit / PlayerUnit_Intro.
                    if speaker == 'CharProtag': speaker = 'PlayerUnit'
                    for language in ('en', 'zh-CN'):
                        text = (render_text(localized[language], cue, 'DisplayName')
                                if language != 'en' else '') or render_text({'line': {'DisplayName': line['Text']}}, 'line', 'DisplayName')
                        item = {'speaker': render_text(localized[language], speaker, 'DisplayName') or speaker,
                                'text': text}
                        if item not in result['content'][language]: result['content'][language].append(item)
        for child in node['children']: visit(child, [*ancestors, node])

    for path in paths:
        for root in native_tables(path.read_text(encoding='utf-8-sig')): visit(root, [])
    return scenes


def block(source, start):
    start = source.index('{', start)
    depth, quote, escaped, position = 0, None, False, start
    while position < len(source):
        character = source[position]
        if quote:
            if escaped: escaped = False
            elif character == '\\': escaped = True
            elif character == quote: quote = None
        elif source.startswith('--', position):
            position = source.find('\n', position)
            if position == -1: raise ValueError('Unclosed native data table')
            continue
        elif character in ('"', "'"): quote = character
        elif character == '{': depth += 1
        elif character == '}':
            depth -= 1
            if depth == 0: return source[start:position + 1], position + 1
        position += 1
    raise ValueError('Unclosed native data table')


def generate(content):
    content = Path(content)
    files = [content / 'Scripts' / name for name in
             ('Main.lua', 'RunManager.lua', 'RoomManager.lua', 'MetaUpgradeData.lua',
              'MetaUpgrades.lua', 'WeaponUpgradeData.lua', 'WeaponUpgradeScripts.lua',
              'GiftData.lua', 'GiftScripts.lua', 'Narrative.lua', 'CodexScripts.lua',
              'QuestLogScreen.lua', 'GhostAdminScreen.lua', 'AwardMenuScripts.lua', 'TextLineSets.lua')]
    scene_paths = [path for path in sorted((content / 'Scripts').glob('*.lua'))
                   if re.search(r'\b\w*TextLineSets\s*=', path.read_text(encoding='utf-8-sig'))]
    files.extend(path for path in scene_paths if path not in files)
    meta = (content / 'Scripts/MetaUpgradeData.lua').read_text(encoding='utf-8-sig')
    order, _ = block(meta, meta.index('MetaUpgradeOrder ='))
    mirror = [list(pair) for pair in re.findall(r'\{\s*"(\w+)"\s*,\s*"(\w+)"\s*\}', order)]
    if len(mirror) != 12: raise ValueError('Supported native Mirror row inventory changed')
    weapon_source = (content / 'Scripts/WeaponUpgradeData.lua').read_text(encoding='utf-8-sig')
    weapons = {}
    for match in re.finditer(r'\b(\w+Weapon)\s*=\s*\{', weapon_source):
        body, _ = block(weapon_source, match.end() - 1)
        items, position = [], 1
        while position < len(body) - 1:
            next_table = body.find('{', position)
            if next_table == -1: break
            item, position = block(body, next_table)
            maximum = re.search(r'\bMaxUpgradeLevel\s*=\s*(\d+)', item)
            if maximum is None: raise ValueError('Native aspect has no maximum rank')
            trait = re.search(r'\b(?:TraitName|RequiredInvestmentTraitName)\s*=\s*"(\w+)"',
                              re.sub(r'--[^\n]*', '', item))
            items.append({'index': len(items) + 1, 'maxRank': int(maximum[1]),
                          'startsUnlocked': bool(re.search(r'\bStartsUnlocked\s*=\s*true', item)),
                          'trait': trait[1] if trait else ''})
        weapons[match[1]] = items
    if len(weapons) != 6 or any(len(rows) != 4 for rows in weapons.values()):
        raise ValueError('Supported native weapon/aspect inventory changed')
    identifiers = set(re.findall(r'\b[A-Za-z_][A-Za-z0-9_]*\b', '\n'.join(
        path.read_text(encoding='utf-8-sig') for path in files)))
    names = {}
    aliases = {}
    for name in ('HelpText', 'MiscText'):
        path = content / 'Game/Text/en' / f'{name}.en.sjson'
        source = re.sub(r'/\*.*?\*/', '', path.read_text(encoding='utf-8-sig'), flags=re.DOTALL)
        starts = list(re.finditer(r'\bId\s*=\s*"([^"\\]+)"', source))
        records = text_records(path)
        for index, match in enumerate(starts):
            body = source[match.end():starts[index + 1].start() if index + 1 < len(starts) else len(source)]
            if re.search(r'\bOverwriteLocalization\s*=\s*true', body):
                aliases[match[1]] = records[match[1]]
    localized = {}
    for language in ('zh-CN', 'en'):
        # Native language-independent alias definitions refer to translated
        # Keywords; the Chinese file deliberately omits these aliases.
        records = dict(aliases)
        for name in ('HelpText', 'MiscText'):
            path = content / 'Game/Text' / language / f'{name}.{language}.sjson'
            files.append(path)
            records.update(text_records(path))
        for identifier in sorted(identifiers):
            label = render_text(records, identifier, 'DisplayName')
            if label: names.setdefault(identifier, {})[language] = label
        for path in sorted((content / 'Game/Text' / language).glob('_*.' + language + '.sjson')):
            files.append(path)
            records.update(text_records(path))
        localized[language] = records
    names = {key: value for key, value in names.items() if len(value) == 2}
    scenes = extract_scenes(scene_paths, localized)
    return {'schemaVersion': 1, 'mirrorRows': mirror, 'weapons': weapons, 'names': names, 'scenes': scenes,
            'sourceEvidence': {'method': 'Static native tables, displayed scene lines/choices and same-ID official bilingual text.',
                'files': {str(path.relative_to(content)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in files}}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--content', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'Backend/games/hades/save_catalog.json')
    args = parser.parse_args()
    args.output.write_text(json.dumps(generate(args.content), ensure_ascii=False, indent=2) + '\n')
