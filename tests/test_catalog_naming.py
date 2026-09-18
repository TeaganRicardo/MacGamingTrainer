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
            'SpellDrop_Store': '月之礼赠',
        }
    if language == 'en':
        return {'EnglishTrait': 'English Trait', 'EnglishReward': 'English Reward'}
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
            {'id':'FireBoost','kind':'consumable','name':'FireBoost'},
            {'id':'WaterBoost','kind':'consumable','name':'WaterBoost'},
            {'id':'EarthBoost','kind':'consumable','name':'EarthBoost'},
            {'id':'AirBoost','kind':'consumable','name':'AirBoost'},
            {'id':'SpellDrop','kind':'loot','name':'stale spell fallback'},
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
for identifier,expected in {
    'GiftDrop':'蜜露',
    'MetaCurrencyDrop':'骨骸',
    'MetaCardPointsCommonDrop':'尘灰',
    'MemPointsCommonDrop':'魂魄',
    'SpellDrop':'月之礼赠',
}.items():
    assert rows[identifier]['name'] == expected
    assert rows[identifier]['officialName'] is False
    assert rows[identifier]['nameSource'] == 'official_linked_zh'
for identifier,expected in {
    'RoomMoneyTinyDrop':'少量金币',
    'EmptyMaxHealthSmallDrop':'小型半人马之魂',
    'MetaCurrencyBigDrop':'大量骨骸',
    'MetaCardPointsCommonBigDrop':'大量尘灰',
    'MemPointsCommonBigDrop':'大量魂魄',
    'FireBoost':'火元素精华',
    'WaterBoost':'水元素精华',
    'EarthBoost':'土元素精华',
    'AirBoost':'风元素精华',
}.items():
    assert rows[identifier]['name'] == expected
    assert rows[identifier]['officialName'] is False
    assert rows[identifier]['nameSource'] == 'provisional_zh'
assert result['resources'][0]['name'] == '已有中文兜底'
assert result['resources'][0]['officialName'] is False
assert any('已保留并使用官方英文名或内部名称' in warning for warning in result.get('warnings', []))
print('catalog_naming_ok')
