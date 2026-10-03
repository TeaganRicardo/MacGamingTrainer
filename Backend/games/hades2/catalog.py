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

_SELENE_TALENT_TITLE_ID = 'TalentScreenMenu_Title'
_HAMMER_TITLE_ID = 'WeaponUpgradeChoiceMenu_Title'

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
    '奖励选择界面': 'Reward Choice',
    '奥林匹斯诸神': _OLYMPIAN_GROUP_TITLE_EN,
    '资源与常规掉落': 'Resources & Standard Drops',
    '局外资源奖励': 'Meta Resources',
    '元素奖励': 'Element Rewards',
    '其他房间奖励': 'Other Room Rewards',
    '商店商品': 'Shop Items',
    '资源': 'Resources',
    '无敌模式': 'Invincibility',
}


_LINKED_OFFICIAL_NAME_IDS = {
    # These runtime reward identifiers may resolve through another official
    # presentation identity. Some direct ids duplicate the same player-facing
    # text; SpellDrop and TrialUpgrade are deliberate collisions whose direct
    # names identify the source character while the linked identity names the
    # reward presentation.
    'GiftDrop': 'GiftPoints',
    'MetaCurrencyDrop': 'MetaCurrency',
    'MetaCardPointsCommonDrop': 'MetaCardPointsCommon',
    'MemPointsCommonDrop': 'MemPointsCommon',
    'SpellDrop': 'SpellDrop_Store',
    'TrialUpgrade': 'UpgradeChoiceMenu_Chaos',
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

_PREFERRED_LINKED_OFFICIAL_NAME_IDS = {
    # The direct LootData DisplayName is the source character, not the reward
    # label shown by the Trainer. Keep sourceName/sectionTitle on the character
    # identity and resolve the item label through the official linked title.
    'SpellDrop',
    'TrialUpgrade',
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

    # Hidden Familiar upgrade traits have no standalone DisplayName in the
    # supported target build. These product labels are derived from the native
    # FamiliarData effect fields, never from prettifying the internal trait id.
    'FamiliarFrogResourceBonus': ('弗利诺斯·额外采集概率', 'Frinos · Bonus Gathering Chance'),
    'FamiliarFrogDamage': ('弗利诺斯·攻击伤害', 'Frinos · Attack Damage'),
    'FamiliarCatResourceBonus': ('图拉·额外采集概率', 'Toula · Bonus Gathering Chance'),
    'FamiliarCatAttacks': ('图拉·攻击次数', 'Toula · Attack Count'),
    'FamiliarRavenResourceBonus': ('拉奇·额外采集概率', 'Raki · Bonus Gathering Chance'),
    'FamiliarRavenAttackDuration': ('拉奇·攻击间隔', 'Raki · Attack Interval'),
    'FamiliarHoundResourceBonus': ('赫库芭·额外采集概率', 'Hecuba · Bonus Gathering Chance'),
    'FamiliarHoundBarkDuration': ('赫库芭·吠叫间隔', 'Hecuba · Bark Interval'),
    'FamiliarPolecatResourceBonus': ('加莉·额外采集概率', 'Gale · Bonus Gathering Chance'),
    'FamiliarPolecatDamage': ('加莉·攻击伤害', 'Gale · Attack Damage'),
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
    if isinstance(runtime_name,str) and runtime_name and runtime_name != identifier:
        return runtime_name, 'runtime_fallback', identifier, 'identifier'
    if isinstance(item,dict) and item.get('kind')=='trait':
        return '未命名效果', 'trainer_generic_zh', 'Unnamed Effect', 'trainer_generic_en'
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
    current_run_traits=decoded.get('currentRunTraits') if isinstance(decoded.get('currentRunTraits'),list) else []
    lookup=[]
    for item in entries:
        if not isinstance(item,dict):continue
        identifier=item.get('trait') if item.get('kind')=='trait' else item.get('id')
        if isinstance(identifier,str) and identifier:lookup.append(identifier)
        source_id=item.get('sourceId')
        if isinstance(source_id,str) and source_id:
            lookup.append(_SPECIAL_SOURCE_LOCALIZATION_IDS.get(source_id,source_id))
    for item in resources:
        if isinstance(item,dict) and isinstance(item.get('id'),str):lookup.append(item['id'])
    for item in current_run_traits:
        if not isinstance(item,dict):continue
        trait_id=item.get('name')
        linked_trait=item.get('linkedTrait')
        source_id=item.get('sourceId')
        if isinstance(trait_id,str) and trait_id:lookup.append(trait_id)
        if isinstance(linked_trait,str) and linked_trait:lookup.append(linked_trait)
        if isinstance(source_id,str) and source_id:
            lookup.append(_SPECIAL_SOURCE_LOCALIZATION_IDS.get(source_id,source_id))
    if not lookup:return decoded
    unique=set(lookup)
    linked_ids=set(_LINKED_OFFICIAL_NAME_IDS.values())
    linked_ids.update(base_id for base_id,_,_ in _LINKED_PROVISIONAL_RULES.values())
    localization_ids=unique | linked_ids | set(_SPECIAL_SOURCE_LOCALIZATION_IDS.values()) | set(_NATIVE_CHOICE_TITLE_IDS.values()) | set(_OFFICIAL_CATEGORY_TITLE_IDS.values()) | {_OLYMPIAN_BOON_TITLE_ID, _SELENE_TALENT_TITLE_ID, _HAMMER_TITLE_ID}
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
        official_zh=_clean(zh.get(identifier)) if identifier in zh else None
        official_en=_clean(en.get(identifier)) if identifier in en else None
        if identifier in _PREFERRED_LINKED_OFFICIAL_NAME_IDS:
            official_zh=None
            official_en=None
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
        elif group in ('special','exact'):
            if group=='special':
                item['category']=_CHARACTER_REWARD_CATEGORY
                item['englishCategory']=_CHARACTER_REWARD_CATEGORY_EN
            source_text_id = (
                _HAMMER_TITLE_ID
                if item.get('acquisitionMode') == 'hammerNative'
                else _SPECIAL_SOURCE_LOCALIZATION_IDS.get(source_id,source_id)
            )
            official_source=_clean(zh.get(source_text_id)) if source_text_id else None
            official_source_en=_clean(en.get(source_text_id)) if source_text_id else None
            preserve_exact_section = group=='exact' and item.get('acquisitionMode') in (
                'chaosBlessing','chaosCurse','seleneSpell','seleneTalent','hammerNative'
            )
            if isinstance(official_source,str) and official_source:
                item['sourceName']=official_source
                if not preserve_exact_section:
                    item['sectionTitle']=official_source
            if isinstance(official_source_en,str) and official_source_en:
                item['sourceEnglishName']=official_source_en
                if not preserve_exact_section:
                    item['englishSectionTitle']=official_source_en
            if preserve_exact_section:
                title_text_id = (
                    _SELENE_TALENT_TITLE_ID
                    if item.get('acquisitionMode') == 'seleneTalent'
                    else _HAMMER_TITLE_ID
                    if item.get('acquisitionMode') == 'hammerNative'
                    else _NATIVE_CHOICE_TITLE_IDS.get(source_id)
                )
                item['sectionTitle']=_clean(zh.get(title_text_id)) or item.get('sectionTitle','')
                item['englishSectionTitle']=_clean(en.get(title_text_id)) or item.get('englishSectionTitle','')
            if group=='special' or item.get('nativeChoice'):
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
        section_title=item.get('sectionTitle')
        item['englishSectionTitle']=_english_group_label(section_title,en)
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

    # Live trait rows keep their runtime identity in `name`, but presentation
    # reuses the same official language source as the acquisition catalog.
    for item in current_run_traits:
        if not isinstance(item,dict):continue
        identifier=item.get('name')
        if not isinstance(identifier,str) or not identifier:continue
        official_zh=_clean(zh.get(identifier)) if identifier in zh else None
        official_en=_clean(en.get(identifier)) if identifier in en else None
        if isinstance(official_zh,str) and official_zh:
            item['displayName']=official_zh
            item['englishName']=official_en or 'Unnamed Effect'
        elif isinstance(official_en,str) and official_en:
            item['displayName']=official_en
            item['englishName']=official_en
        else:
            fallback_zh,_,fallback_en,_=_fallback_names({'kind':'trait','name':identifier},identifier,None,zh,en)
            item['displayName']=fallback_zh
            item['englishName']=fallback_en
        linked_trait=item.get('linkedTrait')
        if isinstance(linked_trait,str) and linked_trait:
            linked_zh=_clean(zh.get(linked_trait)) if linked_trait in zh else None
            linked_en=_clean(en.get(linked_trait)) if linked_trait in en else None
            if isinstance(linked_zh,str) and linked_zh:
                item['linkedDisplayName']=linked_zh
                item['linkedEnglishName']=linked_en or linked_zh
            elif isinstance(linked_en,str) and linked_en:
                item['linkedDisplayName']=linked_en
                item['linkedEnglishName']=linked_en
            else:
                fallback_zh,_,fallback_en,_=_fallback_names({'kind':'trait','name':linked_trait},linked_trait,None,zh,en)
                item['linkedDisplayName']=fallback_zh
                item['linkedEnglishName']=fallback_en
        else:
            item['linkedDisplayName']=''
            item['linkedEnglishName']=''
        source_id=item.get('sourceId')
        if isinstance(source_id,str) and source_id:
            source_text_id = (
                _HAMMER_TITLE_ID
                if item.get('family') == 'hammer'
                else _SPECIAL_SOURCE_LOCALIZATION_IDS.get(source_id,source_id)
            )
            item['sourceName']=_clean(zh.get(source_text_id)) or source_id
            item['sourceEnglishName']=_clean(en.get(source_text_id)) or source_id
        else:
            item['sourceName']=''
            item['sourceEnglishName']=''
    if fallback_special:
        missing=set(fallback_special)
        warnings=decoded.get('warnings') if isinstance(decoded.get('warnings'),list) else []
        message=(f'未从本机 {GAME_SPEC.display_name} 中文语言文件解析到 {len(missing)} 项角色奖励的官方中文名称，'
                 '已保留并使用官方英文名或内部名称。')
        if message not in warnings:warnings.append(message)
        decoded['warnings']=warnings
    return decoded
