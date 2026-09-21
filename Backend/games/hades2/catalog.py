from . import localization
from .config import GAME_SPEC


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
    'RoomRewardConsolationPrize': ('红洋葱', 'Red Onion'),
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
    localization_ids=unique | linked_ids
    zh=localization.official_display_names(localization_ids,'zh-CN')
    en=localization.official_display_names(localization_ids,'en')
    fallback_special=[]
    for item in entries:
        if not isinstance(item,dict):continue
        identifier=item.get('trait') if item.get('kind')=='trait' else item.get('id')
        if not isinstance(identifier,str):continue
        for key in ('name','englishName','sourceName','sectionTitle','category'):
            if isinstance(item.get(key),str):item[key]=_clean(item[key])
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
    for item in resources:
        if not isinstance(item,dict) or not isinstance(item.get('id'),str):continue
        identifier=item['id']
        for key in ('name','englishName','sectionTitle'):
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
        message=(f'未从本机 {GAME_SPEC.display_name} 中文语言文件解析到 {len(missing)} 项特殊祝福的官方中文名称，'
                 '已保留并使用官方英文名或内部名称。')
        if message not in warnings:warnings.append(message)
        decoded['warnings']=warnings
    return decoded
