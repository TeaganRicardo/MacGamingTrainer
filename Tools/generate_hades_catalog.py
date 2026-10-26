#!/usr/bin/env python3
"""Freeze Hades I's native reward pools and bilingual presentation."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'Backend/games/hades/catalog.json'
SCRIPTS = ('WeaponSets.lua', 'TraitData.lua', 'LootData.lua', 'GiftData.lua')
RESOURCE_TEXT_IDS = {
    'MetaPoints': 'MetaPoint', 'Gems': 'Gem', 'LockKeys': 'LockKey',
    'GiftPoints': 'GiftPoint', 'SuperGems': 'SuperGem',
    'SuperGiftPoints': 'SuperGiftPoint', 'SuperLockKeys': 'SuperLockKey',
}
EVIDENCE_SCRIPTS = ('RunManager.lua', 'RoomManager.lua', 'TraitScripts.lua', 'UIScripts.lua',
                    'KeepsakeScripts.lua', 'AwardMenuScripts.lua', 'ShoutScripts.lua',
                    'Main.lua', 'Combat.lua')

EXTRACT = r'''
GlobalVoiceLines = {}; HeroVoiceLines = {}; Color = {}; GameData = {}; ConstantsData = {}
for index = 1, #arg do assert(loadfile(arg[index]))() end
local function quote(value)
  return '"' .. value:gsub('[%z\1-\31\\"]', function(character)
    return string.format('\\u%04x', string.byte(character))
  end) .. '"'
end
local function encode(value)
  if type(value) == 'string' then return quote(value) end
  if type(value) ~= 'table' then return tostring(value) end
  local keys = {}; for key in pairs(value) do keys[#keys+1] = key end
  table.sort(keys)
  local rows = {}
  for _, key in ipairs(keys) do rows[#rows+1] = quote(key) .. ':' .. encode(value[key]) end
  return '{' .. table.concat(rows, ',') .. '}'
end
local function inherited(name, property, seen)
  local data = TraitData[name]
  if not data then return nil end
  if data[property] ~= nil then return data[property] end
  seen = seen or {}; if seen[name] then return nil end; seen[name] = true
  for _, parent in ipairs(data.InheritFrom or {}) do
    local value = inherited(parent, property, seen)
    if value ~= nil then return value end
  end
end
local entries = {}
local function add(name, kind, source)
  if type(name) ~= 'string' or not TraitData[name] then return end
  if not entries[name] then
    local rarities = {}; for rarity in pairs(inherited(name, 'RarityLevels') or {}) do rarities[rarity] = true end
    entries[name] = {id=name, kind=kind, sources={}, rarities=rarities,
      textId=inherited(name, 'CustomTitle') or name,
      isDuo=inherited(name, 'IsDuoBoon') == true,
      slot=inherited(name, 'Slot') or '',
      supportsLevel=kind == 'boon'}
  end
  entries[name].sources[source] = true
end
local gods = {'ZeusUpgrade','PoseidonUpgrade','AthenaUpgrade','AphroditeUpgrade',
  'AresUpgrade','ArtemisUpgrade','DionysusUpgrade','DemeterUpgrade','HermesUpgrade','WeaponUpgrade'}
for _, source in ipairs(gods) do
  local data = assert(LootData[source], source)
  local kind = source == 'WeaponUpgrade' and 'hammer' or 'boon'
  for _, property in ipairs({'PriorityUpgrades','WeaponUpgrades','Traits'}) do
    for _, name in ipairs(data[property] or {}) do add(name, kind, source) end
  end
  for name in pairs(data.LinkedUpgrades or {}) do add(name, kind, source) end
end
for _, name in ipairs(LootData.TrialUpgrade.PermanentTraits or {}) do add(name, 'chaos', 'TrialUpgrade') end
for _, name in ipairs(GiftOrdering) do
  add(name, inherited(name, 'Slot') == 'Assist' and 'companion' or 'keepsake', 'GiftOrdering')
end
local traitTextIds = {}
for name, trait in pairs(TraitData) do
  if type(trait) == 'table' then traitTextIds[name] = inherited(name, 'CustomTitle') or name end
end
print(encode({entries=entries, traitTextIds=traitTextIds}))
'''


def text_records(path):
    source = path.read_text(encoding='utf-8-sig')
    source = re.sub(r'/\*.*?\*/', '', source, flags=re.DOTALL)
    ids = list(re.finditer(r'\bId\s*=\s*"((?:\\.|[^"\\])*)"', source))
    result = {}
    for index, match in enumerate(ids):
        end = ids[index + 1].start() if index + 1 < len(ids) else len(source)
        body = source[match.end():end]
        fields = {}
        for field in ('DisplayName', 'Description', 'InheritFrom'):
            value = re.search(r'\b' + field + r'\s*=\s*"((?:\\.|[^"\\])*)"', body)
            if value:
                fields[field] = re.sub(r'\\([nrt"\\])', lambda m: {
                    'n': '\n', 'r': '\r', 't': '\t', '"': '"', '\\': '\\',
                }[m[1]], value[1])
        result[match[1]] = fields
    return result


def render_text(records, identifier, field, seen=()):
    if identifier in seen:
        return ''
    row = records.get(identifier, {})
    value = row.get(field)
    if value is None:
        return render_text(records, row.get('InheritFrom', ''), field, (*seen, identifier))
    value = re.sub(r'\{\$Keywords\.([^}:]+)(?::[^}]*)?\}',
                   lambda match: render_text(records, match[1], 'DisplayName', (*seen, identifier)), value)
    value = re.sub(r'\{\$[^}]*\}', '…', value)
    value = re.sub(r'\{[^}]*\}', '', value)
    value = re.sub(r'\\Column\s+\d+', '', value)
    return re.sub(r'[ \t]+', ' ', value).strip()


def generate(content, lua):
    content = Path(content)
    paths = [content / 'Scripts' / name for name in SCRIPTS]
    extracted = subprocess.run(
        [str(lua), '-', *map(str, paths)], input=EXTRACT,
        capture_output=True, text=True, check=True,
    )
    extracted_data = json.loads(extracted.stdout)
    traits = extracted_data['entries']
    paths.extend(content / 'Scripts' / name for name in EVIDENCE_SCRIPTS)
    localized = {}
    for language in ('zh-CN', 'en'):
        records = {}
        for name in ('HelpText', 'MiscText'):
            path = content / 'Game/Text' / language / f'{name}.{language}.sjson'
            paths.append(path)
            records.update(text_records(path))
        localized[language] = records
    entries = []
    for identifier in sorted(traits):
        trait = traits[identifier]
        names = {language: render_text(records, trait['textId'], 'DisplayName')
                 for language, records in localized.items()}
        if not all(names.values()):
            raise ValueError(f'Missing native bilingual name: {identifier} / {trait["textId"]}')
        sources = sorted(trait['sources'])
        rarities = [value for value in ('Common', 'Rare', 'Epic', 'Heroic', 'Legendary')
                    if value in trait['rarities']] or ['Common']
        entries.append({
            'id': identifier, 'kind': trait['kind'], 'textId': trait['textId'],
            'names': names,
            'descriptions': {language: render_text(records, trait['textId'], 'Description')
                             for language, records in localized.items()},
            'source': sources[0], 'sources': sources,
            'sourceNames': {language: ' / '.join(render_text(records, source, 'DisplayName')
                or {'GiftOrdering': {'zh-CN': '信物', 'en': 'Keepsakes'}[language]}
                    .get(source, source) for source in sources)
                for language, records in localized.items()},
            'rarities': rarities, 'supportsLevel': trait['supportsLevel'],
            'isDuo': trait['isDuo'], 'slot': trait['slot'],
        })
    resources = []
    for identifier, text_id in RESOURCE_TEXT_IDS.items():
        names = {language: render_text(records, text_id, 'DisplayName')
                 for language, records in localized.items()}
        if not all(names.values()):
            raise ValueError(f'Missing native bilingual resource name: {identifier} / {text_id}')
        resources.append({'id': identifier, 'textId': text_id,
            'names': names,
            'descriptions': {language: render_text(records, text_id, 'Description')
                             for language, records in localized.items()}})
    trait_names = {}
    for identifier, text_id in sorted(extracted_data['traitTextIds'].items()):
        names = {language: render_text(records, text_id, 'DisplayName')
                 for language, records in localized.items()}
        if all(names.values()):
            trait_names[identifier] = names
    return {'schemaVersion': 1, 'game': 'hades', 'steamBuildID': json.loads((ROOT / 'Backend/games/hades/module.json').read_text(encoding='utf-8'))['supportedBuild']['steamBuildID'],
        'sourceEvidence': {
            'files': {path.relative_to(content).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in sorted(paths)},
            'method': 'Native LootData reward pools, TrialUpgrade.PermanentTraits and GiftOrdering; TraitData inheritance; same-ID official bilingual HelpText/MiscText.',
            'dataLoadContext': 'Data chunks only; unrelated Color, voice-line, GameData and ConstantsData tables are empty during extraction.',
            'descriptionValues': 'Native text templates; runtime numeric substitutions are shown as ellipses.',
        }, 'entries': entries, 'resources': resources, 'traitNames': trait_names}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--content', type=Path, required=True)
    parser.add_argument('--lua', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = generate(args.content, args.lua)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(f'hades_catalog_generated: {len(result["entries"])} traits, {len(result["resources"])} resources')


if __name__ == '__main__':
    main()
