#!/usr/bin/env python3
"""Freeze supported Hades room rewards and native bilingual world terms."""
import argparse
import hashlib
import json
from pathlib import Path

from generate_hades_catalog import render_text, text_records


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'Backend/games/hades/world_catalog.json'
OLYMPIANS = ('ZeusUpgrade', 'PoseidonUpgrade', 'AthenaUpgrade', 'AphroditeUpgrade',
             'AresUpgrade', 'ArtemisUpgrade', 'DionysusUpgrade', 'DemeterUpgrade')
LOOT = (*OLYMPIANS, 'HermesUpgrade', 'WeaponUpgrade', 'StackUpgrade', 'TrialUpgrade')
CONSUMABLES = ('RoomRewardMetaPointDrop', 'GemDrop', 'LockKeyDrop', 'GiftDrop',
               'SuperGemDrop', 'SuperLockKeyDrop', 'SuperGiftDrop',
               'RoomRewardMaxHealthDrop', 'RoomRewardMoneyDrop')
TERMS = {'trove': 'ChallengeSwitch', 'well': 'Store_Title', 'purge': 'SellTrait_Title',
         'fishing': 'FishingPoint', 'chaos': 'HealthGate'}
SCRIPTS = ('RoomManager.lua', 'RunManager.lua', 'RoomEvents.lua', 'RoomPresentation.lua',
           'FishingScripts.lua', 'Interactables.lua', 'LootData.lua', 'ConsumableData.lua',
           'RoomData.lua', 'RoomDataTartarus.lua', 'RoomDataAsphodel.lua',
           'RoomDataElysium.lua', 'RoomDataStyx.lua', 'RoomDataSecrets.lua',
           'EncounterSets.lua', 'EncounterData.lua', 'ObstacleData.lua', 'SellTraitScripts.lua')


def generate(content):
    paths, localized = [], {}
    for language in ('zh-CN', 'en'):
        records = {}
        for name in ('HelpText', 'MiscText'):
            path = content / 'Game/Text' / language / f'{name}.{language}.sjson'
            paths.append(path)
            records.update(text_records(path))
        localized[language] = records

    def names(identifier):
        result = {language: render_text(records, identifier, 'DisplayName')
                  for language, records in localized.items()}
        if not all(result.values()):
            raise ValueError(f'Missing native bilingual name: {identifier}')
        return result

    rewards = {identifier: {
        'id': identifier, 'kind': 'loot' if identifier in LOOT else 'consumable',
        'names': names(identifier),
        'rewardType': 'Boon' if identifier in OLYMPIANS else identifier,
        'doorAllowed': identifier != 'TrialUpgrade',
    } for identifier in (*LOOT, *CONSUMABLES)}
    paths.extend(content / 'Scripts' / name for name in SCRIPTS)
    return {
        'schemaVersion': 1, 'rewards': rewards,
        'terms': {key: names(identifier) for key, identifier in TERMS.items()},
        'sourceEvidence': {
            'method': 'Supported-build native room/door, loot, consumable and fishing owners; '
                      'same-ID official bilingual HelpText/MiscText. Native entrypoints and '
                      'limitations are mapped in docs/reference/hades/rooms_resources.md.',
            'files': {str(path.relative_to(content)): hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in paths},
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--content', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    args.output.write_text(json.dumps(generate(args.content), ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
