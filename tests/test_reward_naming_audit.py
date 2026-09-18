from pathlib import Path

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
