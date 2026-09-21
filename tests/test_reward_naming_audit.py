from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
lua = (ROOT / 'Backend/games/hades2/runtime/hades.lua').read_text()
catalog = (ROOT / 'Backend/games/hades2/catalog.py').read_text()

# Raw resident fallbacks must use current Hades II Chinese terminology even
# before the Python localization layer annotates their provenance.
for old in ('骨头', '大量骨头', '灰烬', '大量灰烬', '心智', '大量心智', '月神巫咒',
            '代达罗斯之锤', '德墨忒尔', '阿佛洛狄忒'):
    assert old not in lua
for expected in ('骨骸', '大量骨骸', '尘灰', '大量尘灰', '魂魄', '大量魂魄', '月之礼赠',
                 '狄德勒斯之锤', '得墨忒尔', '阿弗洛狄忒'):
    assert expected in lua

# Known no-direct-DisplayName rewards are resolved through live official keys
# or explicitly marked trainer-side compositions; they are never misreported
# as an exact official localization for their internal reward id.
for linked in ('GiftPoints', 'MetaCurrency', 'MetaCardPointsCommon', 'MemPointsCommon',
               'SeedMystery', 'MixerMythic', 'SpellDrop_Store', 'ReRollAlt'):
    assert linked in catalog
assert "'official_linked_zh'" in catalog
assert "'provisional_zh'" in catalog
for essence in ('火元素精华', '水元素精华', '土元素精华', '风元素精华'):
    assert essence in catalog

# Parse the declarative reward table and protect the audited full-release
# spawn catalog. A missing row or wrong grouping is a user-visible catalog bug.
reward_block = lua.split('local rewardDefinitions = {', 1)[1].split('  local elementNames =', 1)[0]
reward_rows = {}
for line in reward_block.splitlines():
    if '{ id = "' not in line:
        continue
    fields = dict(re.findall(r'(\w+) = "([^"]+)"', line))
    identifier = fields.get('id')
    if identifier:
        reward_rows[identifier] = fields

audited_debug_spawn_consumables = (
    # Money
    'RoomMoneyDrop', 'RoomMoneyBigDrop', 'RoomMoneyTripleDrop', 'RoomMoneySmallDrop', 'RoomMoneyTinyDrop',
    # Health / mana / Selene path points
    'MaxHealthDrop', 'MaxHealthDropSmall', 'MaxHealthDropBig', 'EmptyMaxHealthDrop', 'EmptyMaxHealthSmallDrop',
    'MaxManaDrop', 'MaxManaDropSmall', 'MaxManaDropBig',
    'TalentDrop', 'MinorTalentDrop', 'TalentBigDrop',
    # Healing / partial rewards
    'RoomRewardHealDrop', 'HealBigDrop', 'HealDropMajor', 'HealDrop', 'HealDropMinor', 'RoomRewardConsolationPrize',
    'StoreRewardRandomStack', 'RerollDrop', 'LastStandDrop', 'ArmorBoost', 'ArmorBigBoost',
    'FireBoost', 'AirBoost', 'EarthBoost', 'WaterBoost', 'ElementalBoost',
    # Meta, basic / harvest / boss / advanced
    'MetaCardPointsCommonDrop', 'MetaCardPointsCommonBigDrop', 'MemPointsCommonDrop', 'MemPointsCommonBigDrop',
    'MetaCurrencyDrop', 'MetaCurrencyBigDrop', 'GiftDrop',
    'OreFSilverDrop', 'PlantFMolyDrop', 'PlantFNightshadeDrop', 'PlantGLotusDrop', 'MetaFabricDrop', 'TrashPointsDrop',
    'MixerFBossDrop', 'MixerGBossDrop', 'MixerHBossDrop', 'MixerIBossDrop',
    'MixerNBossDrop', 'MixerOBossDrop', 'MixerPBossDrop', 'MixerQBossDrop', 'Mixer5CommonDrop', 'Mixer6CommonDrop',
    'WeaponPointsRareDrop', 'CardUpgradePointsDrop', 'FamiliarPointsDrop', 'CharonPointsDrop',
    'GemPointsDrop', 'GemPointsBigDrop', 'DreamPointsDrop',
)
assert len(audited_debug_spawn_consumables) == 62
for identifier in audited_debug_spawn_consumables:
    assert identifier in reward_rows, identifier

# HealDrop and HealDropMinor have verified normal gameplay callers. The 1-HP
# super-minor variant remains test/debug-only; trait-produced transient drops
# stay excluded as standalone Trainer targets.
for identifier in ('HealDropSuperMinor',
                   'MedeaMoneyTinyDrop', 'PowerDrinkDrop', 'BloodDrop',
                   'ManaDropMinorPoseidon', 'ManaDropMinor', 'ManaDropZeus', 'ManaDropMinorHound'):
    assert identifier not in reward_rows, identifier

for identifier in ('MinorTalentDrop', 'TalentDrop', 'TalentBigDrop'):
    row = reward_rows[identifier]
    assert row.get('group') == 'special', (identifier, row)
    assert row.get('family') == 'Selene', (identifier, row)
    assert row.get('sourceId') == 'Selene', (identifier, row)
    assert row.get('sourceName') == '塞勒涅', (identifier, row)

assert reward_rows['EmptyMaxHealthDrop'].get('family') == 'centaurSoul'
assert reward_rows['EmptyMaxHealthSmallDrop'].get('family') == 'centaurSoul'
for identifier in ('MaxHealthDropSmall', 'MaxHealthDrop', 'MaxHealthDropBig'):
    assert reward_rows[identifier].get('family') == 'centaurHeart'

assert reward_rows['SeedMysteryDrop'].get('family') == 'metaHarvest'
assert reward_rows['SeedMysteryDrop'].get('category') == '局外资源奖励'
assert reward_rows['MixerMythicDrop'].get('family') == 'metaBoss'
assert reward_rows['MixerMythicDrop'].get('category') == '局外资源奖励'
assert 'LobAmmoPack' not in reward_rows

assert reward_rows['ElementalBoost'].get('family') == 'element'
assert reward_rows['ElementalBoost'].get('category') == '元素奖励'
assert reward_rows['MinorTalentDrop'].get('name') == '黯淡繁星之路'
assert reward_rows['TalentBigDrop'].get('name') == '闪耀繁星之路'

print('reward_naming_audit_ok')
