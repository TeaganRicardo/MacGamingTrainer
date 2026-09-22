from . import localization
from .config import GAME_SPEC


_SPECIAL_SOURCE_LOCALIZATION_IDS = {
    'Artemis': 'NPC_Artemis_Field_01',
    'Athena': 'NPC_Athena_01',
    'Dionysus': 'NPC_Dionysus_01',
    'Hades': 'NPC_Hades_01',
    'Arachne': 'NPC_Arachne_01',
    'Narcissus': 'NPC_Narcissus_01',
    'Echo': 'NPC_Echo_01',
    'Medea': 'NPC_Medea_01',
    'Circe': 'NPC_Circe_01',
    'Icarus': 'NPC_Icarus_01',
    'Chaos': 'NPC_Chaos_01',
    'Selene': 'NPC_Selene_01',
}

_NATIVE_CHOICE_TITLE_IDS = {
    'Artemis': 'UpgradeChoiceMenu_Artemis',
    'Athena': 'UpgradeChoiceMenu_Athena',
    'Dionysus': 'UpgradeChoiceMenu_Dionysus',
    'Hades': 'UpgradeChoiceMenu_Hades',
    'Arachne': 'ArachneCostumeMenu_Title',
    'Narcissus': 'NarcissusGiftsMenu_Title',
    'Echo': 'EchoChoiceMenu_Title',
    'Medea': 'MedeaCurseMenu_Title',
    'Circe': 'CirceChoiceMenu_Title',
    'Icarus': 'IcarusChoiceMenu_Title',
    'Chaos': 'UpgradeChoiceMenu_Chaos',
    'Selene': 'SpellScreenMenu_Title',
}

_OLYMPIAN_BOON_TITLE_ID = 'Boon'
_CHARACTER_REWARD_CATEGORY = '角色奖励'
_CHARACTER_REWARD_CATEGORY_EN = 'Character Rewards'
_OLYMPIAN_GROUP_TITLE = '奥林匹斯诸神'
_OLYMPIAN_GROUP_TITLE_EN = 'Olympians'
_OFFICIAL_CATEGORY_TITLE_IDS = {
    '卡戎之井': 'WellShop_Title',
}
_PRODUCT_LABEL_EN_BY_ZH = {
    '角色奖励': _CHARACTER_REWARD_CATEGORY_EN,
    '奥林匹斯诸神': _OLYMPIAN_GROUP_TITLE_EN,
    '资源与常规掉落': 'Resources & Standard Drops',
    '局外资源奖励': 'Meta Resources',
    '元素奖励': 'Element Rewards',
    '其他房间奖励': 'Other Room Rewards',
    '商店商品': 'Shop Items',
    '资源': 'Resources',
}


_LINKED_OFFICIAL_NAME_IDS = {
    # These runtime reward identifiers intentionally do not carry their own
    # DisplayName. Resolve the player-facing object/resource that the game uses
    # for presentation instead of treating the internal reward id as a name.
    'GiftDrop': 'GiftPoints',
    'MetaCurrencyDrop': 'MetaCurrency',
    'MetaCardPointsCommonDrop': 'MetaCardPointsCommon',
    'MemPointsCommonDrop': 'MemPointsCommon',
    'SpellDrop': 'SpellDrop_Store',
    'ArmorBoost': 'ArmorBoost_Store',
    'RoomRewardHealDrop': 'RoomRewardHealDrop_Store',
    'HealBigDrop': 'RoomRewardBigHealDrop_Store',
    'OreFSilverDrop': 'OreFSilver',
    'PlantFMolyDrop': 'PlantFMoly',
    'PlantFNightshadeDrop': 'PlantFNightshade',
    'PlantGLotusDrop': 'PlantGLotus',
    'MetaFabricDrop': 'MetaFabric',
    'TrashPointsDrop': 'TrashPoints',
    'MixerFBossDrop': 'MixerFBoss',
    'MixerGBossDrop': 'MixerGBoss',
    'MixerHBossDrop': 'MixerHBoss',
    'MixerIBossDrop': 'MixerIBoss',
    'MixerNBossDrop': 'MixerNBoss',
    'MixerOBossDrop': 'MixerOBoss',
    'MixerPBossDrop': 'MixerPBoss',
    'MixerQBossDrop': 'MixerQBoss',
    'Mixer5CommonDrop': 'Mixer5Common',
    'Mixer6CommonDrop': 'Mixer6Common',
    'WeaponPointsRareDrop': 'WeaponPointsRare',
    'CardUpgradePointsDrop': 'CardUpgradePoints',
    'FamiliarPointsDrop': 'FamiliarPoints',
    'CharonPointsDrop': 'CharonPoints',
    'GemPointsDrop': 'GemPoints',
    'DreamPointsDrop': 'DreamPoints',
    'SeedMysteryDrop': 'SeedMystery',
    'MixerMythicDrop': 'MixerMythic',
    'WeaponUpgradeDrop': 'WeaponUpgrade',
    'ShopHermesUpgrade': 'HermesUpgrade_Store',
    'RerollDrop': 'ReRollAlt',
}

_LINKED_PROVISIONAL_RULES = {
    # Variant ids reuse an officially localized base/resource name but do not
    # have an exact display string of their own. The modifier is therefore a
    # trainer-side composition and must remain distinguishable from official
    # localization provenance.
    'RoomMoneyTinyDrop': ('RoomMoneyDrop', '少量', 'Small '),
    'EmptyMaxHealthSmallDrop': ('EmptyMaxHealthDrop', '小型', 'Small '),
    'MaxHealthDropSmall': ('MaxHealthDrop', '小型', 'Small '),
    'MaxManaDropSmall': ('MaxManaDrop', '小型', 'Small '),
    'MetaCurrencyBigDrop': ('MetaCurrency', '大量', 'Large '),
    'MetaCardPointsCommonBigDrop': ('MetaCardPointsCommon', '大量', 'Large '),
    'MemPointsCommonBigDrop': ('MemPointsCommon', '大量', 'Large '),
    'GemPointsBigDrop': ('GemPoints', '大量', 'Large '),
}

_PROVISIONAL_NAMES = {
    # No standalone DisplayName exists for these runtime reward ids. These
    # labels are deliberate trainer-side names built from terminology used by
    # the installed game's own descriptions and data.
    'FireBoost': ('火元素精华', 'Fire Essence'),
    'WaterBoost': ('水元素精华', 'Water Essence'),
    'EarthBoost': ('土元素精华', 'Earth Essence'),
    'AirBoost': ('风元素精华', 'Air Essence'),
    'ElementalBoost': ('元素精华', 'Elemental Essence'),
    'StoreRewardRandomStack': ('随机祝福强化', 'Random Boon Upgrade'),
    'HealDropMajor': ('大型生命恢复', 'Major Healing'),
    'HealDropMinor': ('少量治疗', 'Minor Healing'),
    'RandomLoot': ('随机奥林匹斯祝福', 'Random Olympian Boon'),
    'BoostedRandomLoot': ('强化随机祝福', 'Boosted Random Boon'),
}


def _clean(value):
    return localization._clean_display_name(value) if isinstance(value,str) else value


def _fallback_names(item, identifier, english_name, linked_zh, linked_en):
    linked_id=_LINKED_OFFICIAL_NAME_IDS.get(identifier)
    if linked_id:
        linked_zh_name=_clean(linked_zh.get(linked_id))
        linked_en_name=_clean(linked_en.get(linked_id))
        if isinstance(linked_zh_name,str) and linked_zh_name:
            return linked_zh_name, 'official_linked_zh', linked_en_name or identifier, ('official_linked_en' if linked_en_name else 'identifier')
    rule=_LINKED_PROVISIONAL_RULES.get(identifier)
    if rule:
        base_id,zh_prefix,en_prefix=rule
        base_zh=_clean(linked_zh.get(base_id))
        base_en=_clean(linked_en.get(base_id))
        if isinstance(base_zh,str) and base_zh:
            return zh_prefix + base_zh, 'provisional_zh', (en_prefix + base_en) if base_en else identifier, ('provisional_en' if base_en else 'identifier')
    provisional=_PROVISIONAL_NAMES.get(identifier)
    if provisional:
        return provisional[0], 'provisional_zh', provisional[1], 'provisional_en'
    if isinstance(english_name,str) and english_name:
        return english_name, 'official_en', english_name, 'official_en'
    runtime_name=_clean(item.get('name')) if isinstance(item,dict) else None
    if isinstance(runtime_name,str) and runtime_name:
        return runtime_name, 'runtime_fallback', identifier, 'identifier'
    return identifier, 'identifier', identifier, 'identifier'


def _english_group_label(value, english_names):
    if not isinstance(value,str) or not value:
        return ''
    official_id=_OFFICIAL_CATEGORY_TITLE_IDS.get(value)
    if official_id:
        official=_clean(english_names.get(official_id))
        if isinstance(official,str) and official:
            return official
    return _PRODUCT_LABEL_EN_BY_ZH.get(value, '')


def localize_catalog(decoded):
    entries=decoded.get('rewards')
    if not isinstance(entries,list):entries=decoded.get('boons')
    if not isinstance(entries,list):entries=[]
    resources=decoded.get('resources') if isinstance(decoded.get('resources'),list) else []
    lookup=[]
    for item in entries:
        if not isinstance(item,dict):continue
        identifier=item.get('trait') if item.get('kind')=='trait' else item.get('id')
        if isinstance(identifier,str) and identifier:lookup.append(identifier)
    for item in resources:
        if isinstance(item,dict) and isinstance(item.get('id'),str):lookup.append(item['id'])
    if not lookup:return decoded
    unique=set(lookup)
    linked_ids=set(_LINKED_OFFICIAL_NAME_IDS.values())
    linked_ids.update(base_id for base_id,_,_ in _LINKED_PROVISIONAL_RULES.values())
    localization_ids=unique | linked_ids | set(_SPECIAL_SOURCE_LOCALIZATION_IDS.values()) | set(_NATIVE_CHOICE_TITLE_IDS.values()) | set(_OFFICIAL_CATEGORY_TITLE_IDS.values()) | {_OLYMPIAN_BOON_TITLE_ID}
    zh=localization.official_display_names(localization_ids,'zh-CN')
    en=localization.official_display_names(localization_ids,'en')
    fallback_special=[]
    for item in entries:
        if not isinstance(item,dict):continue
        identifier=item.get('trait') if item.get('kind')=='trait' else item.get('id')
        if not isinstance(identifier,str):continue
        for key in ('name','englishName','sourceName','sourceEnglishName','sectionTitle','englishSectionTitle','category','englishCategory','nativeChoiceTitle','nativeChoiceEnglishTitle'):
            if isinstance(item.get(key),str):item[key]=_clean(item[key])
        section_title=item.get('sectionTitle')
        item['englishSectionTitle']=_english_group_label(section_title,en)
        official_zh=_clean(zh.get(identifier)) if identifier in zh else None
        official_en=_clean(en.get(identifier)) if identifier in en else None
        variant_rule=_LINKED_PROVISIONAL_RULES.get(identifier)
        if variant_rule and isinstance(official_zh,str) and official_zh:
            base_zh=_clean(zh.get(variant_rule[0]))
            if isinstance(base_zh,str) and base_zh and official_zh==base_zh:
                official_zh=None
        if isinstance(official_en,str) and official_en:
            item['englishName']=official_en
            item['englishNameSource']='official_en'
        if isinstance(official_zh,str) and official_zh:
            # Keep the item label exactly equal to the game's official Chinese
            # DisplayName. Source/person grouping belongs in sectionTitle.
            item['name']=official_zh
            item['officialName']=True
            item['nameSource']='official_zh'
            if not item.get('englishName'):
                item['englishName']=identifier
                item['englishNameSource']='identifier'
        else:
            item['officialName']=False
            item['name'],item['nameSource'],item['englishName'],item['englishNameSource']=_fallback_names(item,identifier,official_en,zh,en)
            if item.get('kind')=='trait':fallback_special.append(identifier)
        category=item.get('category')
        section_title=item.get('sectionTitle')
        item['englishCategory']=_english_group_label(category,en)
        item['englishSectionTitle']=_english_group_label(section_title,en)
        group=item.get('group')
        source_id=item.get('sourceId')
        if group=='olympian':
            item['category']=_clean(zh.get(_OLYMPIAN_BOON_TITLE_ID)) or '奥林匹斯的祝福'
            item['englishCategory']=_clean(en.get(_OLYMPIAN_BOON_TITLE_ID)) or 'Boon of Olympus'
            item['sectionTitle']=_OLYMPIAN_GROUP_TITLE
            item['englishSectionTitle']=_OLYMPIAN_GROUP_TITLE_EN
        elif group=='special':
            item['category']=_CHARACTER_REWARD_CATEGORY
            item['englishCategory']=_CHARACTER_REWARD_CATEGORY_EN
            source_text_id=_SPECIAL_SOURCE_LOCALIZATION_IDS.get(source_id)
            official_source=_clean(zh.get(source_text_id)) if source_text_id else None
            official_source_en=_clean(en.get(source_text_id)) if source_text_id else None
            if isinstance(official_source,str) and official_source:
                item['sourceName']=official_source
                item['sectionTitle']=official_source
            if isinstance(official_source_en,str) and official_source_en:
                item['sourceEnglishName']=official_source_en
                item['englishSectionTitle']=official_source_en
            title_text_id=_NATIVE_CHOICE_TITLE_IDS.get(source_id)
            official_title=_clean(zh.get(title_text_id)) if title_text_id else None
            official_title_en=_clean(en.get(title_text_id)) if title_text_id else None
            if isinstance(official_title,str) and official_title:
                item['nativeChoiceTitle']=official_title
            if isinstance(official_title_en,str) and official_title_en:
                item['nativeChoiceEnglishTitle']=official_title_en
    for item in resources:
        if not isinstance(item,dict) or not isinstance(item.get('id'),str):continue
        identifier=item['id']
        for key in ('name','englishName','sectionTitle','englishSectionTitle'):
            if isinstance(item.get(key),str):item[key]=_clean(item[key])
        official_zh=_clean(zh.get(identifier)) if identifier in zh else None
        official_en=_clean(en.get(identifier)) if identifier in en else None
        if isinstance(official_en,str) and official_en:
            item['englishName']=official_en
            item['englishNameSource']='official_en'
        if isinstance(official_zh,str) and official_zh:
            item['name']=official_zh;item['officialName']=True;item['nameSource']='official_zh'
            if not item.get('englishName'):
                item['englishName']=identifier;item['englishNameSource']='identifier'
        else:
            item['officialName']=False
            item['name'],item['nameSource'],item['englishName'],item['englishNameSource']=_fallback_names(item,identifier,official_en,zh,en)
    if fallback_special:
        missing=set(fallback_special)
        warnings=decoded.get('warnings') if isinstance(decoded.get('warnings'),list) else []
        message=(f'未从本机 {GAME_SPEC.display_name} 中文语言文件解析到 {len(missing)} 项角色奖励的官方中文名称，'
                 '已保留并使用官方英文名或内部名称。')
        if message not in warnings:warnings.append(message)
        decoded['warnings']=warnings
    return decoded
