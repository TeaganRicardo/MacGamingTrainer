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
}

_LINKED_PROVISIONAL_RULES = {
    # Variant ids reuse an officially localized base/resource name but do not
    # have an exact display string of their own. The modifier is therefore a
    # trainer-side composition and must remain distinguishable from official
    # localization provenance.
    'RoomMoneyTinyDrop': ('RoomMoneyDrop', '少量'),
    'EmptyMaxHealthSmallDrop': ('EmptyMaxHealthDrop', '小型'),
    'MetaCurrencyBigDrop': ('MetaCurrency', '大量'),
    'MetaCardPointsCommonBigDrop': ('MetaCardPointsCommon', '大量'),
    'MemPointsCommonBigDrop': ('MemPointsCommon', '大量'),
}

_PROVISIONAL_ZH_NAMES = {
    # The installed game's HelpText describes these exact pickups as the
    # essence of the corresponding element, but the hidden Essence traits have
    # no standalone DisplayName. Preserve that official terminology here.
    'FireBoost': '火元素精华',
    'WaterBoost': '水元素精华',
    'EarthBoost': '土元素精华',
    'AirBoost': '风元素精华',
}


def _clean(value):
    return localization._clean_display_name(value) if isinstance(value,str) else value


def _fallback_name(item, identifier, english_name, linked_zh):
    linked_id=_LINKED_OFFICIAL_NAME_IDS.get(identifier)
    if linked_id:
        linked_name=_clean(linked_zh.get(linked_id))
        if isinstance(linked_name,str) and linked_name:
            return linked_name, 'official_linked_zh'
    rule=_LINKED_PROVISIONAL_RULES.get(identifier)
    if rule:
        base_id,prefix=rule
        base_name=_clean(linked_zh.get(base_id))
        if isinstance(base_name,str) and base_name:
            return prefix + base_name, 'provisional_zh'
    provisional=_PROVISIONAL_ZH_NAMES.get(identifier)
    if provisional:
        return provisional, 'provisional_zh'
    if isinstance(english_name,str) and english_name:
        return english_name, 'official_en'
    runtime_name=_clean(item.get('name')) if isinstance(item,dict) else None
    if isinstance(runtime_name,str) and runtime_name:
        return runtime_name, 'runtime_fallback'
    return identifier, 'identifier'


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
    linked_ids.update(base_id for base_id,_ in _LINKED_PROVISIONAL_RULES.values())
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
        if isinstance(official_en,str) and official_en:item['englishName']=official_en
        if isinstance(official_zh,str) and official_zh:
            # Keep the item label exactly equal to the game's official Chinese
            # DisplayName. Source/person grouping belongs in sectionTitle.
            item['name']=official_zh
            item['officialName']=True
            item['nameSource']='official_zh'
        else:
            item['officialName']=False
            item['name'],item['nameSource']=_fallback_name(item,identifier,official_en,zh)
            if item.get('kind')=='trait':fallback_special.append(identifier)
    for item in resources:
        if not isinstance(item,dict) or not isinstance(item.get('id'),str):continue
        identifier=item['id']
        for key in ('name','englishName','sectionTitle'):
            if isinstance(item.get(key),str):item[key]=_clean(item[key])
        official_zh=_clean(zh.get(identifier)) if identifier in zh else None
        official_en=_clean(en.get(identifier)) if identifier in en else None
        if isinstance(official_en,str) and official_en:item['englishName']=official_en
        if isinstance(official_zh,str) and official_zh:
            item['name']=official_zh;item['officialName']=True;item['nameSource']='official_zh'
        else:
            item['officialName']=False
            item['name'],item['nameSource']=_fallback_name(item,identifier,official_en,zh)
    if fallback_special:
        missing=set(fallback_special)
        warnings=decoded.get('warnings') if isinstance(decoded.get('warnings'),list) else []
        message=(f'未从本机 {GAME_SPEC.display_name} 中文语言文件解析到 {len(missing)} 项特殊祝福的官方中文名称，'
                 '已保留并使用官方英文名或内部名称。')
        if message not in warnings:warnings.append(message)
        decoded['warnings']=warnings
    return decoded
