"""Hades native reward identity, bilingual search and generated pool boundaries."""
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
sys.path.insert(0, str(ROOT / 'Tools'))

from games.hades.catalog import catalog, get_entry, resource_catalog, data, trait_names
from generate_hades_catalog import generate, RESOURCE_TEXT_IDS, EVIDENCE_SCRIPTS
from lua_runtime_support import require_lua52

zeus = get_entry('ZeusWeaponTrait')
assert zeus['names'] == {'zh-CN': '闪电攻击', 'en': 'Lightning Strike'}
assert 'ZeusUpgrade' in zeus['sources'] and zeus['kind'] == 'boon'
assert zeus['rarities'] == ['Common', 'Rare', 'Epic', 'Heroic']
assert get_entry('ZeusChargedBoltTrait')['rarities'] == ['Legendary']
assert get_entry('LightningCloudTrait')['isDuo']
assert get_entry('HermesWeaponTrait')['supportsLevel']
assert get_entry('SwordTwoComboTrait')['kind'] == 'hammer'
assert get_entry('ChaosBlessingMeleeTrait')['kind'] == 'chaos'
assert get_entry('MaxHealthKeepsakeTrait')['kind'] == 'keepsake'
assert get_entry('FuryAssistTrait')['kind'] == 'companion'
assert get_entry('ShopTier1Trait') is None
assert get_entry('ChaosCurseNoMoneyTrait') is None
assert catalog(language='en', query='宙斯 闪电攻击')[0]['name'] == 'Lightning Strike'
assert any(row['id'] == 'ZeusWeaponTrait' and row['name'] == '闪电攻击'
           for row in catalog(language='zh-CN', query='zeus lightning strike'))
assert all(row['kind'] == 'hammer' for row in catalog(kind='hammer'))
assert not catalog(query='nonexistent trait name')
resources = {row['id']: row for row in resource_catalog('en')}
assert resources['MetaPoints']['name'] == 'Darkness'
assert resources['SuperLockKeys']['names']['zh-CN'] == '泰坦之血'
assert len(resources) == 7 and len(catalog()) == 284
assert all(len(value) == 64 for value in data()['sourceEvidence']['files'].values())
assert all('{' not in row['name'] and '{' not in row['description'] for row in catalog())
assert trait_names()['GodModeTrait'] == {'zh-CN': '天外飞仙', 'en': 'Deus Ex Machina'}

with tempfile.TemporaryDirectory(prefix='mgt-hades-catalog-') as directory:
    content = Path(directory)
    scripts = content / 'Scripts'
    scripts.mkdir()
    (scripts / 'WeaponSets.lua').write_text('WeaponSets = {}\n')
    (scripts / 'TraitData.lua').write_text('''TraitData = {
      Base = { RarityLevels = { Common = {}, Heroic = {} } },
      NativeBoon = { InheritFrom = { "Base" } },
      NativeHammer = {}, NativeBlessing = {}, NativeGift = { Slot = "Keepsake" },
      NativeCompanion = { Slot = "Assist" }, EnemyOnlyTrait = {}, NativeCurse = {},
      NativeRuntimeTrait = { CustomTitle = "NativeRuntimeTitle" },
    }''')
    (scripts / 'LootData.lua').write_text('''LootData = {
      ZeusUpgrade = { Traits = { "NativeBoon" }, LinkedUpgrades = { NativeBoon = {} } },
      PoseidonUpgrade={}, AthenaUpgrade={}, AphroditeUpgrade={}, AresUpgrade={},
      ArtemisUpgrade={}, DionysusUpgrade={}, DemeterUpgrade={}, HermesUpgrade={},
      WeaponUpgrade={ Traits={"NativeHammer"} },
      TrialUpgrade={PermanentTraits={"NativeBlessing"}, TemporaryTraits={"NativeCurse"}},
    }''')
    (scripts / 'GiftData.lua').write_text('GiftOrdering = { "NativeGift", "NativeCompanion" }')
    for name in EVIDENCE_SCRIPTS:
        (scripts / name).write_text('-- provenance-only native source\n')
    for language in ('zh-CN', 'en'):
        text = content / 'Game/Text' / language
        text.mkdir(parents=True)
        names = ['NativeBoon', 'NativeHammer', 'NativeBlessing', 'NativeGift', 'NativeCompanion',
                 'ZeusUpgrade', 'WeaponUpgrade', 'TrialUpgrade', 'NativeRuntimeTitle', *RESOURCE_TEXT_IDS.values()]
        records = '\n'.join('{ Id = ' + json.dumps(name) + ' DisplayName = ' + json.dumps(language + ':' + name)
                            + ' Description = "Native {#BoldFormat}description{#PreviousFormat} {$TooltipData.Value}" }'
                            for name in names)
        (text / f'HelpText.{language}.sjson').write_text(records)
        (text / f'MiscText.{language}.sjson').write_text('{ Texts = [] }')
    result = generate(content, require_lua52('Hades catalog generation'))
    entries = {row['id']: row for row in result['entries']}
    assert set(entries) == {'NativeBoon', 'NativeHammer', 'NativeBlessing', 'NativeGift', 'NativeCompanion'}
    assert entries['NativeBoon']['rarities'] == ['Common', 'Heroic']
    assert entries['NativeCompanion']['kind'] == 'companion'
    assert entries['NativeBoon']['descriptions']['en'] == 'Native description …'
    assert entries['NativeBoon']['names']['zh-CN'] == 'zh-CN:NativeBoon'
    assert result['traitNames']['NativeRuntimeTrait']['en'] == 'en:NativeRuntimeTitle'
    assert 'NativeRuntimeTrait' not in entries, 'presentation identity must not grant acquisition capability'

print('hades_catalog_ok')
