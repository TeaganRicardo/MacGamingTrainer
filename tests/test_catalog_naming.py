from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from games.hades2 import catalog, localization

original = localization.official_display_names

def fake_names(ids, language='zh-CN', game_path=None):
    if language == 'zh-CN':
        return {
            'OfficialTrait': '官方祝福',
            'OfficialReward': '官方奖励',
            'GiftPoints': '蜜露',
            'MetaCurrency': '骨骸',
            'MetaCardPointsCommon': '尘灰',
            'MemPointsCommon': '魂魄',
            'RoomMoneyDrop': '金币',
            'EmptyMaxHealthDrop': '半人马之魂',
            'MaxHealthDrop': '半人马之心',
            'MaxHealthDropSmall': '半人马之心',
            'MaxManaDrop': '灵魂之水',
            'MaxManaDropSmall': '灵魂之水',
            'SpellDrop_Store': '月之礼赠',
            'ArmorBoost_Store': '护盾饰符',
            'RoomRewardHealDrop_Store': '新鲜食粮',
            'RoomRewardBigHealDrop_Store': '超大份新鲜食粮',
            'OreFSilver': '银矿',
            'MixerFBoss': '余烬',
            'GemPoints': '宝石',
        }
    if language == 'en':
        return {
            'EnglishTrait': 'English Trait',
            'EnglishReward': 'English Reward',
            'GiftPoints': 'Nectar',
            'MetaCurrency': 'Bones',
            'MetaCardPointsCommon': 'Ashes',
            'MemPointsCommon': 'Psyche',
            'RoomMoneyDrop': 'Gold Crowns',
            'EmptyMaxHealthDrop': 'Centaur Soul',
            'MaxHealthDrop': 'Centaur Heart',
            'MaxHealthDropSmall': 'Centaur Heart',
            'MaxManaDrop': 'Soul Tonic',
            'MaxManaDropSmall': 'Soul Tonic',
            'SpellDrop_Store': 'Gift of the Moon',
            'ArmorBoost_Store': 'Shield Charm',
            'RoomRewardHealDrop_Store': 'Fresh Sustenance',
            'RoomRewardBigHealDrop_Store': 'Big Fresh Sustenance',
            'OreFSilver': 'Silver',
            'MixerFBoss': 'Cinder',
            'GemPoints': 'Gemstones',
        }
    return {}

localization.official_display_names = fake_names
try:
    payload = {
        'rewards': [
            {'id':'trait:OfficialTrait','kind':'trait','trait':'OfficialTrait','name':'OfficialTrait','sourceName':'NPC'},
            {'id':'trait:EnglishTrait','kind':'trait','trait':'EnglishTrait','name':'EnglishTrait','sourceName':'NPC'},
            {'id':'trait:InternalOnlyTrait','kind':'trait','trait':'InternalOnlyTrait','name':'InternalOnlyTrait','sourceName':'NPC'},
            {'id':'OfficialReward','kind':'loot','name':'runtime reward'},
            {'id':'EnglishReward','kind':'loot','name':'runtime english reward'},
            {'id':'GiftDrop','kind':'consumable','name':'stale gift fallback'},
            {'id':'MetaCurrencyDrop','kind':'consumable','name':'骨头'},
            {'id':'MetaCurrencyBigDrop','kind':'consumable','name':'大量骨头'},
            {'id':'MetaCardPointsCommonDrop','kind':'consumable','name':'灰烬'},
            {'id':'MetaCardPointsCommonBigDrop','kind':'consumable','name':'大量灰烬'},
            {'id':'MemPointsCommonDrop','kind':'consumable','name':'心智'},
            {'id':'MemPointsCommonBigDrop','kind':'consumable','name':'大量心智'},
            {'id':'RoomMoneyTinyDrop','kind':'consumable','name':'tiny money'},
            {'id':'EmptyMaxHealthSmallDrop','kind':'consumable','name':'small soul'},
            {'id':'MaxHealthDrop','kind':'consumable','name':'heart'},
            {'id':'MaxHealthDropSmall','kind':'consumable','name':'small heart'},
            {'id':'MaxManaDrop','kind':'consumable','name':'tonic'},
            {'id':'MaxManaDropSmall','kind':'consumable','name':'small tonic'},
            {'id':'FireBoost','kind':'consumable','name':'FireBoost'},
            {'id':'WaterBoost','kind':'consumable','name':'WaterBoost'},
            {'id':'EarthBoost','kind':'consumable','name':'EarthBoost'},
            {'id':'AirBoost','kind':'consumable','name':'AirBoost'},
            {'id':'SpellDrop','kind':'loot','name':'stale spell fallback'},
            {'id':'ArmorBoost','kind':'consumable','name':'ArmorBoost'},
            {'id':'RoomRewardHealDrop','kind':'consumable','name':'RoomRewardHealDrop'},
            {'id':'ElementalBoost','kind':'consumable','name':'ElementalBoost'},
            {'id':'StoreRewardRandomStack','kind':'consumable','name':'StoreRewardRandomStack'},
            {'id':'HealBigDrop','kind':'consumable','name':'HealBigDrop'},
            {'id':'OreFSilverDrop','kind':'consumable','name':'OreFSilverDrop'},
            {'id':'MixerFBossDrop','kind':'consumable','name':'MixerFBossDrop'},
            {'id':'GemPointsDrop','kind':'consumable','name':'GemPointsDrop'},
            {'id':'GemPointsBigDrop','kind':'consumable','name':'GemPointsBigDrop'},
        ],
        'resources': [{'id':'UnknownResource','name':'已有中文兜底'}],
    }
    result = catalog.localize_catalog(payload)
finally:
    localization.official_display_names = original

rows = {row.get('trait') or row.get('id'): row for row in result['rewards']}
assert {'OfficialTrait','EnglishTrait','InternalOnlyTrait','OfficialReward','EnglishReward'} <= set(rows)
assert rows['OfficialTrait']['name'] == '官方祝福'
assert rows['OfficialTrait']['officialName'] is True and rows['OfficialTrait']['nameSource'] == 'official_zh'
assert rows['EnglishTrait']['name'] == 'English Trait'
assert rows['EnglishTrait']['officialName'] is False and rows['EnglishTrait']['nameSource'] == 'official_en'
assert rows['InternalOnlyTrait']['name'] == 'InternalOnlyTrait'
assert rows['InternalOnlyTrait']['officialName'] is False and rows['InternalOnlyTrait']['nameSource'] == 'runtime_fallback'
assert rows['EnglishReward']['name'] == 'English Reward' and rows['EnglishReward']['nameSource'] == 'official_en'
for identifier,expected_zh,expected_en in [
    ('GiftDrop','蜜露','Nectar'),
    ('MetaCurrencyDrop','骨骸','Bones'),
    ('MetaCardPointsCommonDrop','尘灰','Ashes'),
    ('MemPointsCommonDrop','魂魄','Psyche'),
    ('SpellDrop','月之礼赠','Gift of the Moon'),
    ('ArmorBoost','护盾饰符','Shield Charm'),
    ('RoomRewardHealDrop','新鲜食粮','Fresh Sustenance'),
    ('HealBigDrop','超大份新鲜食粮','Big Fresh Sustenance'),
    ('OreFSilverDrop','银矿','Silver'),
    ('MixerFBossDrop','余烬','Cinder'),
    ('GemPointsDrop','宝石','Gemstones'),
]:
    assert rows[identifier]['name'] == expected_zh
    assert rows[identifier]['englishName'] == expected_en
    assert rows[identifier]['officialName'] is False
    assert rows[identifier]['nameSource'] == 'official_linked_zh'
    assert rows[identifier]['englishNameSource'] == 'official_linked_en'
for identifier,expected_zh,expected_en in [
    ('RoomMoneyTinyDrop','少量金币','Small Gold Crowns'),
    ('EmptyMaxHealthSmallDrop','小型半人马之魂','Small Centaur Soul'),
    ('MetaCurrencyBigDrop','大量骨骸','Large Bones'),
    ('MetaCardPointsCommonBigDrop','大量尘灰','Large Ashes'),
    ('MemPointsCommonBigDrop','大量魂魄','Large Psyche'),
    ('FireBoost','火元素精华','Fire Essence'),
    ('WaterBoost','水元素精华','Water Essence'),
    ('EarthBoost','土元素精华','Earth Essence'),
    ('AirBoost','风元素精华','Air Essence'),
    ('ElementalBoost','元素精华','Elemental Essence'),
    ('StoreRewardRandomStack','随机祝福强化','Random Boon Upgrade'),
    ('GemPointsBigDrop','大量宝石','Large Gemstones'),
]:
    assert rows[identifier]['name'] == expected_zh
    assert rows[identifier]['englishName'] == expected_en
    assert rows[identifier]['officialName'] is False
    assert rows[identifier]['nameSource'] == 'provisional_zh'
    assert rows[identifier]['englishNameSource'] == 'provisional_en'
assert rows['MaxHealthDrop']['name'] == '半人马之心'
assert rows['MaxHealthDropSmall']['name'] == '小型半人马之心'
assert rows['MaxHealthDropSmall']['englishName'] == 'Small Centaur Heart'
assert rows['MaxHealthDropSmall']['officialName'] is False
assert rows['MaxHealthDropSmall']['nameSource'] == 'provisional_zh'
assert rows['MaxManaDrop']['name'] == '灵魂之水'
assert rows['MaxManaDropSmall']['name'] == '小型灵魂之水'
assert rows['MaxManaDropSmall']['englishName'] == 'Small Soul Tonic'
assert rows['MaxManaDropSmall']['officialName'] is False
assert rows['MaxManaDropSmall']['nameSource'] == 'provisional_zh'
assert result['resources'][0]['name'] == '已有中文兜底'
assert result['resources'][0]['officialName'] is False
assert any('已保留并使用官方英文名或内部名称' in warning for warning in result.get('warnings', []))
print('catalog_naming_ok')
