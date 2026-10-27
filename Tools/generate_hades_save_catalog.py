#!/usr/bin/env python3
"""Extract Save Editor identities from supported native text; never run Lua."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from generate_hades_catalog import text_records, render_text

ROOT = Path(__file__).resolve().parents[1]


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
              'GiftData.lua', 'GiftScripts.lua')]
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
    names = {key: value for key, value in names.items() if len(value) == 2}
    return {'schemaVersion': 1, 'mirrorRows': mirror, 'weapons': weapons, 'names': names,
            'sourceEvidence': {'method': 'Static native data-table extraction and same-ID official bilingual text.',
                'files': {str(path.relative_to(content)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in files}}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--content', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'Backend/games/hades/save_catalog.json')
    args = parser.parse_args()
    args.output.write_text(json.dumps(generate(args.content), ensure_ascii=False, indent=2) + '\n')
