import sys
from pathlib import Path

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
            'SpellDrop': '塞勒涅',
            'SpellDrop_Store': '月之礼赠',
            'TrialUpgrade': '卡俄斯',
            'UpgradeChoiceMenu_Chaos': '卡俄斯的祝福',
            'ArmorBoost_Store': '护盾饰符',
            'RoomRewardHealDrop_Store': '新鲜食粮',
            'RoomRewardBigHealDrop_Store': '超大份新鲜食粮',
            'OreFSilver': '银矿',
            'MixerFBoss': '余烬',
            'GemPoints': '宝石',
            'WeaponUpgrade': '狄德勒斯之锤',
            'HermesUpgrade_Store': '赫尔墨斯的祝福',
            'HealDrop': '治疗',
            'ReRollAlt': '重塑命运',
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
            'SpellDrop': 'Selene',
            'SpellDrop_Store': 'Gift of the Moon',
            'TrialUpgrade': 'Chaos',
            'UpgradeChoiceMenu_Chaos': 'Boons of Chaos',
            'ArmorBoost_Store': 'Shield Charm',
            'RoomRewardHealDrop_Store': 'Fresh Sustenance',
            'RoomRewardBigHealDrop_Store': 'Big Fresh Sustenance',
            'OreFSilver': 'Silver',
            'MixerFBoss': 'Cinder',
            'GemPoints': 'Gemstones',
            'WeaponUpgrade': 'Daedalus Hammer',
            'HermesUpgrade_Store': 'Boon of Hermes',
            'HealDrop': 'Healing',
            'ReRollAlt': 'Change of Fate',
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
            {'id':'TrialUpgrade','kind':'loot','name':'stale chaos fallback'},
            {'id':'ArmorBoost','kind':'consumable','name':'ArmorBoost'},
            {'id':'RoomRewardHealDrop','kind':'consumable','name':'RoomRewardHealDrop'},
            {'id':'ElementalBoost','kind':'consumable','name':'ElementalBoost'},
            {'id':'StoreRewardRandomStack','kind':'consumable','name':'StoreRewardRandomStack'},
            {'id':'HealBigDrop','kind':'consumable','name':'HealBigDrop'},
            {'id':'HealDropMajor','kind':'consumable','name':'HealDropMajor'},
            {'id':'OreFSilverDrop','kind':'consumable','name':'OreFSilverDrop'},
            {'id':'MixerFBossDrop','kind':'consumable','name':'MixerFBossDrop'},
            {'id':'GemPointsDrop','kind':'consumable','name':'GemPointsDrop'},
            {'id':'GemPointsBigDrop','kind':'consumable','name':'GemPointsBigDrop'},
            {'id':'WeaponUpgradeDrop','kind':'consumable','name':'stale hammer wrapper'},
            {'id':'ShopHermesUpgrade','kind':'consumable','name':'stale Hermes wrapper'},
            {'id':'RandomLoot','kind':'consumable','name':'RandomLoot'},
            {'id':'BoostedRandomLoot','kind':'consumable','name':'BoostedRandomLoot'},
            {'id':'HealDrop','kind':'consumable','name':'stale healing'},
            {'id':'HealDropMinor','kind':'consumable','name':'stale minor healing'},
            {'id':'RerollDrop','kind':'consumable','name':'stale reroll'},
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
assert rows['InternalOnlyTrait']['name'] == '未命名效果'
assert rows['InternalOnlyTrait']['englishName'] == 'Unnamed Effect'
assert rows['InternalOnlyTrait']['officialName'] is False and rows['InternalOnlyTrait']['nameSource'] == 'trainer_generic_zh'
assert rows['EnglishReward']['name'] == 'English Reward' and rows['EnglishReward']['nameSource'] == 'official_en'
for identifier,expected_zh,expected_en in [
    ('GiftDrop','蜜露','Nectar'),
    ('MetaCurrencyDrop','骨骸','Bones'),
    ('MetaCardPointsCommonDrop','尘灰','Ashes'),
    ('MemPointsCommonDrop','魂魄','Psyche'),
    ('SpellDrop','月之礼赠','Gift of the Moon'),
    ('TrialUpgrade','卡俄斯的祝福','Boons of Chaos'),
    ('ArmorBoost','护盾饰符','Shield Charm'),
    ('RoomRewardHealDrop','新鲜食粮','Fresh Sustenance'),
    ('HealBigDrop','超大份新鲜食粮','Big Fresh Sustenance'),
    ('OreFSilverDrop','银矿','Silver'),
    ('MixerFBossDrop','余烬','Cinder'),
    ('GemPointsDrop','宝石','Gemstones'),
    ('WeaponUpgradeDrop','狄德勒斯之锤','Daedalus Hammer'),
    ('ShopHermesUpgrade','赫尔墨斯的祝福','Boon of Hermes'),
    ('RerollDrop','重塑命运','Change of Fate'),
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
    ('RandomLoot','随机奥林匹斯祝福','Random Olympian Boon'),
    ('BoostedRandomLoot','强化随机祝福','Boosted Random Boon'),
    ('HealDropMajor','大型生命恢复','Major Healing'),
    ('HealDropMinor','少量治疗','Minor Healing'),
]:
    assert rows[identifier]['name'] == expected_zh
    assert rows[identifier]['englishName'] == expected_en
    assert rows[identifier]['officialName'] is False
    assert rows[identifier]['nameSource'] == 'provisional_zh'
    assert rows[identifier]['englishNameSource'] == 'provisional_en'
assert rows['HealDrop']['name'] == '治疗'
assert rows['HealDrop']['englishName'] == 'Healing'
assert rows['HealDrop']['officialName'] is True
assert rows['HealDrop']['nameSource'] == 'official_zh'
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
assert result['resources'][0]['name'] == '未知资源 · UnknownResource'
assert result['resources'][0]['englishName'] == 'Unknown Resource · UnknownResource'
assert result['resources'][0]['officialName'] is False
assert result['resources'][0]['nameSource'] == 'trainer_generic_zh'
assert result['resources'][0]['englishNameSource'] == 'trainer_generic_en'
assert any('已保留并使用官方英文名或内部名称' in warning for warning in result.get('warnings', []))

# Exact acquisition and mounted effects show official bilingual names, never
# raw trait or source IDs. Each case supplies the official game text it needs.
def localized(payload, zh, en):
    tables = {'zh-CN': zh, 'en': en}

    def names(identifiers, language='zh-CN', game_path=None):
        table = tables.get(language, {})
        return {key: table[key] for key in identifiers if key in table}

    localization.official_display_names = names
    try:
        catalog.localize_catalog(payload)
    finally:
        localization.official_display_names = original
    return payload


ordinary, direct = localized({'rewards': [
    {'id': 'exact:ZeusUpgrade:ZeusWeaponBoon', 'trait': 'ZeusWeaponBoon', 'kind': 'trait', 'group': 'exact',
     'sourceId': 'ZeusUpgrade', 'sourceName': '宙斯', 'sectionTitle': '宙斯', 'category': '奥林匹斯的祝福',
     'acquisitionMode': 'ordinaryNative', 'rarities': ['Common', 'Rare', 'Epic', 'Heroic'], 'supportsLevel': True},
    {'id': 'trait:CritBonusBoon', 'trait': 'CritBonusBoon', 'kind': 'trait', 'group': 'exact',
     'sourceId': 'Artemis', 'sourceName': 'Artemis', 'sectionTitle': 'Artemis', 'category': '角色奖励',
     'acquisitionMode': 'direct', 'rarities': ['Common', 'Rare'], 'supportsLevel': False},
]}, {'ZeusWeaponBoon': '雷霆打击', 'ZeusUpgrade': '宙斯', 'CritBonusBoon': '致命一击', 'NPC_Artemis_Field_01': '阿耳忒弥斯'},
   {'ZeusWeaponBoon': 'Heaven Strike', 'ZeusUpgrade': 'Zeus', 'CritBonusBoon': 'Deadly Strike',
    'NPC_Artemis_Field_01': 'Artemis'})['rewards']
assert (ordinary['name'], ordinary['englishName']) == ('雷霆打击', 'Heaven Strike')
assert (ordinary['sourceName'], ordinary['sourceEnglishName']) == ('宙斯', 'Zeus')
assert (ordinary['sectionTitle'], ordinary['englishSectionTitle']) == ('宙斯', 'Zeus')
assert (direct['name'], direct['englishName']) == ('致命一击', 'Deadly Strike')
assert (direct['sourceName'], direct['sourceEnglishName']) == ('阿耳忒弥斯', 'Artemis')
assert (direct['sectionTitle'], direct['englishSectionTitle']) == ('阿耳忒弥斯', 'Artemis')
assert direct['englishCategory'] == 'Character Rewards'
assert ordinary['rarities'] == ['Common', 'Rare', 'Epic', 'Heroic'] and ordinary['supportsLevel'] is True

# Selene: Hexes use the Hex menu title, talents the Path of Stars title.
hex_row, talent_row = localized({'rewards': [
    {'id': 'selene:spell:Meteor', 'trait': 'SpellMeteorTrait', 'kind': 'trait', 'group': 'exact',
     'sourceId': 'Selene', 'sourceName': '塞勒涅', 'sectionTitle': '塞勒涅', 'category': '角色奖励',
     'acquisitionMode': 'seleneSpell'},
    {'id': 'selene:talent:Meteor:MeteorDamageTalent', 'trait': 'MeteorDamageTalent', 'kind': 'trait',
     'group': 'exact', 'sourceId': 'Selene', 'sourceName': '塞勒涅', 'sectionTitle': '繁星之路',
     'category': '角色奖励', 'acquisitionMode': 'seleneTalent'},
]}, {'SpellMeteorTrait': '月蚀', 'MeteorDamageTalent': '毁灭之星', 'NPC_Selene_01': '塞勒涅',
     'SpellScreenMenu_Title': '巫咒', 'TalentScreenMenu_Title': '繁星之路'},
   {'SpellMeteorTrait': 'Total Eclipse', 'MeteorDamageTalent': 'Gloaming', 'NPC_Selene_01': 'Selene',
    'SpellScreenMenu_Title': 'Hexes', 'TalentScreenMenu_Title': 'Path of Stars'})['rewards']
assert (hex_row['name'], hex_row['englishName']) == ('月蚀', 'Total Eclipse')
assert (hex_row['sourceName'], hex_row['sourceEnglishName']) == ('塞勒涅', 'Selene')
assert (hex_row['sectionTitle'], hex_row['englishSectionTitle']) == ('巫咒', 'Hexes')
assert (talent_row['name'], talent_row['englishName']) == ('毁灭之星', 'Gloaming')
assert (talent_row['sectionTitle'], talent_row['englishSectionTitle']) == ('繁星之路', 'Path of Stars')

# Echo: direct targets use the Echo reward-page title; previous-run targets
# keep the concrete boon name under the previous-run choice title.
echo_direct, echo_last_run = localized({'rewards': [
    {'id': 'trait:EchoDoubleLevelBoon', 'name': 'EchoDoubleLevelBoon', 'trait': 'EchoDoubleLevelBoon',
     'kind': 'trait', 'group': 'exact', 'sourceId': 'Echo', 'sourceName': '回声', 'sectionTitle': '回声',
     'category': '角色奖励', 'nativeChoice': True, 'acquisitionMode': 'direct'},
    {'id': 'echo:lastRun:ZeusBoon', 'name': 'ZeusBoon', 'trait': 'ZeusBoon', 'kind': 'trait', 'group': 'exact',
     'sourceId': 'Echo', 'sourceName': '回声', 'sectionTitle': '上局祝福', 'category': '角色奖励',
     'acquisitionMode': 'echoLastRunExact'},
]}, {'EchoDoubleLevelBoon': '再来一次', 'NPC_Echo_01': '回声', 'EchoChoiceMenu_Title': '凄楚回声',
     'ZeusBoon': '雷霆打击', 'EchoChoiceMenu_LastRun': '上局祝福'},
   {'EchoDoubleLevelBoon': 'Encore', 'NPC_Echo_01': 'Echo', 'EchoChoiceMenu_Title': 'Plaintive Echoes',
    'ZeusBoon': 'Thunder Strike', 'EchoChoiceMenu_LastRun': 'Boons from Last Night'})['rewards']
assert (echo_direct['sourceName'], echo_direct['sourceEnglishName']) == ('回声', 'Echo')
assert (echo_direct['sectionTitle'], echo_direct['englishSectionTitle']) == ('凄楚回声', 'Plaintive Echoes')
assert (echo_last_run['name'], echo_last_run['englishName']) == ('雷霆打击', 'Thunder Strike')
assert (echo_last_run['sectionTitle'], echo_last_run['englishSectionTitle']) == ('上局祝福', 'Boons from Last Night')

# Hammer: exact acquisition and the mounted trait share the official Hammer title.
hammer_payload = localized({
    'rewards': [{'id': 'hammer:LobAmmoTrait', 'name': 'LobAmmoTrait', 'trait': 'LobAmmoTrait', 'kind': 'trait',
                 'group': 'exact', 'sourceId': 'WeaponUpgrade', 'sourceName': '狄德勒斯之锤',
                 'sectionTitle': '狄德勒斯之锤', 'category': '角色奖励', 'acquisitionMode': 'hammerNative'}],
    'currentRunTraits': [{'name': 'LobAmmoTrait', 'sourceId': 'WeaponUpgrade', 'family': 'hammer'}],
}, {'LobAmmoTrait': '巨量弹仓', 'WeaponUpgradeChoiceMenu_Title': '狄德勒斯之锤'},
   {'LobAmmoTrait': 'Mega Driver', 'WeaponUpgradeChoiceMenu_Title': 'Daedalus Hammer'})
hammer_exact, hammer_live = hammer_payload['rewards'][0], hammer_payload['currentRunTraits'][0]
assert (hammer_exact['name'], hammer_exact['englishName']) == ('巨量弹仓', 'Mega Driver')
assert (hammer_exact['sectionTitle'], hammer_exact['englishSectionTitle']) == ('狄德勒斯之锤', 'Daedalus Hammer')
assert (hammer_live['displayName'], hammer_live['englishName']) == ('巨量弹仓', 'Mega Driver')
assert (hammer_live['sourceName'], hammer_live['sourceEnglishName']) == ('狄德勒斯之锤', 'Daedalus Hammer')

# Mounted effects without their own official title get "owner · effect"
# labels, and owners resolve through official text (#240).
frog, cat, raven, arcana, echo_owned, keepsake = localized({'currentRunTraits': [
    {'name': 'FamiliarFrogDamage', 'sourceId': 'FrogFamiliar', 'family': 'familiar'},
    {'name': 'FamiliarCatAttacks', 'sourceId': 'CatFamiliar', 'family': 'familiar'},
    {'name': 'CritFamiliar', 'sourceId': 'RavenFamiliar', 'family': 'familiar'},
    {'name': 'LowManaDamageMetaupgrade', 'sourceId': 'LowManaDamageBonus', 'family': 'arcana'},
    {'name': 'InternalEchoEffect', 'sourceId': 'Echo', 'family': 'directSpecial'},
    {'name': 'ReincarnationKeepsake', 'sourceId': 'ReincarnationKeepsake', 'family': 'keepsake'},
]}, {'FrogFamiliar': '弗利诺斯', 'CatFamiliar': '图拉', 'CritFamiliar': '锐眼', 'RavenFamiliar': '拉奇',
     'LowManaDamageBonus': '猎手', 'NPC_Echo_01': '回声', 'ReincarnationKeepsake': '更幸运的牙齿'},
   {'FrogFamiliar': 'Frinos', 'CatFamiliar': 'Toula', 'CritFamiliar': 'Sharp Eye', 'RavenFamiliar': 'Raki',
    'LowManaDamageBonus': 'The Huntress', 'NPC_Echo_01': 'Echo', 'ReincarnationKeepsake': 'Luckier Tooth'},
)['currentRunTraits']
assert (frog['displayName'], frog['englishName']) == ('弗利诺斯 · 攻击伤害', 'Frinos · Attack Damage')
assert (cat['displayName'], cat['englishName']) == ('图拉 · 攻击次数', 'Toula · Attack Count')
assert (raven['displayName'], raven['englishName']) == ('锐眼', 'Sharp Eye')
assert (raven['sourceName'], raven['sourceEnglishName']) == ('拉奇', 'Raki')
assert (arcana['displayName'], arcana['englishName']) == (
    '猎手 · 魔力未满时攻击/特技增伤', 'The Huntress · Attack/Special Damage Below Full Magick')
assert (arcana['sourceName'], arcana['sourceEnglishName']) == ('猎手', 'The Huntress')
assert (echo_owned['displayName'], echo_owned['englishName']) == ('回声 · 特殊角色效果', 'Echo · Special NPC Effect')
assert (keepsake['displayName'], keepsake['englishName']) == ('更幸运的牙齿', 'Luckier Tooth')
assert (keepsake['sourceName'], keepsake['sourceEnglishName']) == ('更幸运的牙齿', 'Luckier Tooth')

# A native display title names an otherwise internal trait; linked Chaos
# phases resolve both halves through official text.
native_title, chaos = localized({'currentRunTraits': [
    {'name': 'InternalImplementationTrait', 'displayId': 'PlayerVisibleInternalTitle', 'sourceId': '',
     'family': 'other'},
    {'name': 'ChaosDamageCurse', 'linkedTrait': 'ChaosHealthBlessing', 'sourceId': 'Chaos', 'family': 'chaos'},
]}, {'PlayerVisibleInternalTitle': '原生可辨识效果', 'ChaosDamageCurse': '受难', 'ChaosHealthBlessing': '丰盛',
     'NPC_Chaos_01': '卡俄斯'},
   {'PlayerVisibleInternalTitle': 'Native Recognizable Effect', 'ChaosDamageCurse': 'Maimed',
    'ChaosHealthBlessing': 'Affluence', 'NPC_Chaos_01': 'Chaos'})['currentRunTraits']
assert (native_title['displayName'], native_title['englishName']) == ('原生可辨识效果', 'Native Recognizable Effect')
assert (chaos['displayName'], chaos['englishName']) == ('受难', 'Maimed')
assert (chaos['linkedDisplayName'], chaos['linkedEnglishName']) == ('丰盛', 'Affluence')

# Every known current-run trait without a native title has a curated
# bilingual label, never a generic "Unnamed Effect" or family fallback.
generic_zh = {'未命名效果', *[value[0] for value in catalog._CURRENT_RUN_FAMILY_LABELS.values()]}
generic_en = {'Unnamed Effect', *[value[1] for value in catalog._CURRENT_RUN_FAMILY_LABELS.values()]}
for trait_id, pair in catalog._CURRENT_RUN_DERIVED_NAMES.items():
    assert isinstance(pair, tuple) and len(pair) == 2 and all(isinstance(v, str) and v.strip() for v in pair), trait_id
    assert trait_id not in pair and pair[0] not in generic_zh and pair[1] not in generic_en, trait_id

print('catalog_naming_ok')
