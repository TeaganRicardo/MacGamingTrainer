from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
lua = (ROOT / 'Backend/games/hades2/runtime/hades.lua').read_text()
catalog = (ROOT / 'Backend/games/hades2/catalog.py').read_text()

# Raw resident fallbacks must use current Hades II Chinese terminology even
# before the Python localization layer annotates their provenance.
for old in ('骨头', '大量骨头', '灰烬', '大量灰烬', '心智', '大量心智', '月神巫咒'):
    assert old not in lua
for expected in ('骨骸', '大量骨骸', '尘灰', '大量尘灰', '魂魄', '大量魂魄', '月之礼赠'):
    assert expected in lua

# Known no-direct-DisplayName rewards are resolved through live official keys
# or explicitly marked trainer-side compositions; they are never misreported
# as an exact official localization for their internal reward id.
for linked in ('GiftPoints', 'MetaCurrency', 'MetaCardPointsCommon', 'MemPointsCommon', 'SpellDrop_Store'):
    assert linked in catalog
assert "'official_linked_zh'" in catalog
assert "'provisional_zh'" in catalog
for essence in ('火元素精华', '水元素精华', '土元素精华', '风元素精华'):
    assert essence in catalog

print('reward_naming_audit_ok')


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

for identifier in (
    'EmptyMaxHealthDrop', 'EmptyMaxHealthSmallDrop',
    'MaxHealthDropSmall', 'MaxHealthDrop', 'MaxHealthDropBig',
    'MaxManaDropSmall', 'MaxManaDrop', 'MaxManaDropBig',
    'RoomRewardHealDrop', 'HealBigDrop',
    'StoreRewardRandomStack', 'RerollDrop', 'LastStandDrop',
    'ArmorBoost', 'ArmorBigBoost', 'ElementalBoost',
):
    assert identifier in reward_rows, identifier

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

assert reward_rows['ElementalBoost'].get('family') == 'element'
assert reward_rows['ElementalBoost'].get('category') == '元素奖励'
assert reward_rows['MinorTalentDrop'].get('name') == '黯淡繁星之路'
assert reward_rows['TalentBigDrop'].get('name') == '闪耀繁星之路'
