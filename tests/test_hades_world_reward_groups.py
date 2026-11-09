"""Hades I Generate-reward rows group rewards as Hades II's resident catalog does (#706)."""
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
sys.path.insert(0, str(ROOT / 'Tools'))

from games.hades.world import reward_catalog
import generate_hades_world_catalog as generator

rows = reward_catalog()

# Every reward names its Generate row and a section that belongs to that row only.
section_groups = {}
for row in rows:
    assert row['group'] in ('olympian', 'pickup', 'special'), row
    assert section_groups.setdefault(row['section'], row['group']) == row['group'], row
assert {row['group'] for row in rows} == {'olympian', 'pickup', 'special'}

# Hades II's classification decides each identity the two games share: its
# Olympian loot table (gods and Hermes) versus its reward table's pickup and
# character-reward groups.
resident = (ROOT / 'Backend/games/hades2/runtime/hades.lua').read_text()
olympian_table = resident.split('catalogs.boonDefinitions = {', 1)[1].split('\n  }', 1)[0]
reward_table = resident.split('catalogs.rewardDefinitions = {', 1)[1].split('\n  }', 1)[0]
hades2_groups = {identifier: 'olympian' for identifier in re.findall(r'\bid = "(\w+)"', olympian_table)}
for identifier, group in re.findall(r'\{ id = "(\w+)",[^\n]*?\bgroup = "(\w+)"', reward_table):
    hades2_groups.setdefault(identifier, group)
shared = {row['id']: row['group'] for row in rows if row['id'] in hades2_groups}
assert {'ZeusUpgrade', 'HermesUpgrade', 'WeaponUpgrade', 'StackUpgrade', 'TrialUpgrade', 'GiftDrop'} <= set(shared), shared
for identifier, group in shared.items():
    assert group == hades2_groups[identifier], (identifier, group, hades2_groups[identifier])
# Hades I's other gods are the same native Olympian loot as Zeus.
assert ({row['id'] for row in rows if row['group'] == 'olympian'}
        == {row['id'] for row in rows if row['rewardType'] == 'Boon'} | {'HermesUpgrade'})

# A native section title is the same-ID official pair (Chaos's NPC); every
# other section has a Trainer-owned bilingual label in the frontend.
chaos = next(row for row in rows if row['id'] == 'TrialUpgrade')
assert chaos['section'] == 'chaos' and chaos['sectionNames'] == {'zh-CN': '卡俄斯', 'en': 'Chaos'}
presentation = (ROOT / 'Sources/Hades/HadesPresentation.swift').read_text()
for section in {row['section'] for row in rows if 'sectionNames' not in row}:
    assert f'"hades.rewardSection.{section}"' in presentation, section

# The generator owns the committed grouping and reads native section titles
# from the official text of the section's identity.
with tempfile.TemporaryDirectory(prefix='mgt-hades-world-groups-') as directory:
    content = Path(directory)
    (content / 'Scripts').mkdir()
    for name in generator.SCRIPTS:
        (content / 'Scripts' / name).write_text('-- provenance-only native source\n')
    identifiers = [*generator.LOOT, *generator.CONSUMABLES, *generator.TERMS.values(),
                   *generator.SECTION_TEXT_IDS.values()]
    for language in ('zh-CN', 'en'):
        text = content / 'Game/Text' / language
        text.mkdir(parents=True)
        (text / f'HelpText.{language}.sjson').write_text('\n'.join(
            '{ Id = ' + json.dumps(name) + ' DisplayName = ' + json.dumps(f'{language}:{name}') + ' }'
            for name in identifiers))
        (text / f'MiscText.{language}.sjson').write_text('{ Texts = [] }')
    generated = generator.generate(content)


def grouping(rewards):
    return [(row['id'], row['group'], row['section'], 'sectionNames' in row) for row in rewards]


committed = json.loads((ROOT / 'Backend/games/hades/world_catalog.json').read_text())
assert grouping(generated['rewards'].values()) == grouping(committed['rewards'].values())
assert generated['rewards']['TrialUpgrade']['sectionNames'] == {
    'zh-CN': 'zh-CN:NPC_Chaos_01', 'en': 'en:NPC_Chaos_01'}

print('hades_world_reward_groups_ok')
