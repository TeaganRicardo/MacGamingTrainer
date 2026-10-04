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
_ECHO_LAST_RUN_TITLE_ID = 'EchoChoiceMenu_LastRun'

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

_CURRENT_RUN_FAMILY_LABELS = {
    'arcana': ('阿卡那牌', 'Arcana'),
    'biomeState': ('环境状态', 'Biome States'),
    'chaos': ('卡俄斯效果', 'Chaos Effect'),
    'costume': ('服装效果', 'Costume Effect'),
    'directSpecial': ('特殊角色效果', 'Special NPC Effect'),
    'familiar': ('魔宠效果', 'Familiar Effect'),
    'hammer': ('代达罗斯 / 武器效果', 'Daedalus / Weapon Effect'),
    'hex': ('巫咒', 'Hex'),
    'hexTalent': ('繁星之路天赋', 'Path of Stars Talent'),
    'keepsake': ('信物效果', 'Keepsake Effect'),
    'olympianHermes': ('奥林匹斯 / 赫尔墨斯祝福', 'Olympian / Hermes Boon'),
    'other': ('其他效果', 'Other Effect'),
    'temporary': ('临时效果', 'Temporary Effect'),
    'weaponAspect': ('武器形态效果', 'Weapon Aspect Effect'),
}

# Current-target (1.143476 / Steam 25481925) mounted TraitData rows that do not
# have a sufficiently specific standalone native title. Values are Trainer
# Product Terms derived from the target build's effect data/descriptions. Arcana
# and Familiar entries are descriptors only; their native owner title is composed
# dynamically at presentation time.
_CURRENT_RUN_DERIVED_NAMES = {
    # Element essence traits are installed by the matching *Boost consumables.
    'AirEssence': ('风元素', 'Air Element'),
    'FireEssence': ('火元素', 'Fire Element'),
    'EarthEssence': ('土元素', 'Earth Element'),
    'WaterEssence': ('水元素', 'Water Element'),
    'ElementalEssence': ('元素', 'Element'),

    # Direct current-run state/effect traits.
    'MinorArmorBoon': ('护甲加成', 'Armor Bonus'),
    'RoomRewardMaxHealthTrait': ('最大生命值增加', 'Max Life Increase'),
    'RoomRewardEmptyMaxHealthTrait': ('最大生命值增加（不恢复生命）', 'Max Life Increase (No Healing)'),
    'RoomRewardMaxManaTrait': ('最大魔力值增加', 'Max Magick Increase'),
    'SuitInherentSpeedBoon': ('冲刺速度加成', 'Sprint Speed Bonus'),
    'VanillaState': ('默认环境', 'Default Environment'),
    'WetState': ('雨天环境', 'Rainy Environment'),

    # Hidden Familiar upgrade traits; descriptors follow target FamiliarData fields.
    # The native Familiar owner name is resolved dynamically and composed at
    # presentation time.
    'FamiliarFrogResourceBonus': ('额外采集概率', 'Bonus Gathering Chance'),
    'FamiliarFrogDamage': ('攻击伤害', 'Attack Damage'),
    'FamiliarCatResourceBonus': ('额外采集概率', 'Bonus Gathering Chance'),
    'FamiliarCatAttacks': ('攻击次数', 'Attack Count'),
    'FamiliarRavenResourceBonus': ('额外采集概率', 'Bonus Gathering Chance'),
    'FamiliarRavenAttackDuration': ('攻击间隔', 'Attack Interval'),
    'FamiliarHoundResourceBonus': ('额外采集概率', 'Bonus Gathering Chance'),
    'FamiliarHoundBarkDuration': ('吠叫间隔', 'Bark Interval'),
    'FamiliarPolecatResourceBonus': ('额外采集概率', 'Bonus Gathering Chance'),
    'FamiliarPolecatDamage': ('攻击伤害', 'Attack Damage'),

    # Arcana mounted traits: concise functional descriptors derived from the
    # official target-build card Description. Native card titles remain sourceName.
    'ChannelSlowMetaUpgrade': ('Ω招式加速', 'Faster Omega Moves'),
    'DoorHealMetaUpgrade': ('离开房间恢复生命', 'Post-Room Healing'),
    'LowManaDamageMetaupgrade': ('魔力未满时攻击/特技增伤', 'Attack/Special Damage Below Full Magick'),
    'CastDamageMetaUpgrade': ('Ω蓄力时减缓时间', 'Time Slow While Channeling Ω'),
    'SorceryRegenMetaUpgrade': ('巫咒自动充能', 'Automatic Hex Charge'),
    'InsideCastBuffMetaUpgrade': ('法阵内敌人增伤', 'Cast-Area Enemy Damage'),
    'HealthManaBonusMetaUpgrade': ('最大生命值/魔力值增加', 'Max Life/Magick Increase'),
    'DodgeBonusMetaUpgrade': ('施展法阵时短暂无敌并提高移速', 'Cast Invulnerability & Move Speed'),
    'ManaOverTimeMetaUpgrade': ('魔力值自动恢复', 'Magick Regeneration'),
    'MagicCritMetaUpgrade': ('Ω组合技暴击率', 'Omega Combo Critical Chance'),
    'SprintShieldMetaUpgrade': ('冲刺加速并穿过敌人', 'Faster Sprint & Phasing'),
    'LastStandSlowTimeMetaUpgrade': ('增加死里逃生次数', 'Extra Death Defiance'),
    'ChamberHealthMetaUpgrade': ('每5个房间增加生命值/魔力值上限', 'Max Life/Magick Every 5 Rooms'),
    'EffectVulnerabilityMetaUpgrade': ('至少2种奥林匹斯状态时增伤', 'Damage vs. 2+ Olympian Statuses'),
    'BossShieldMetaUpgrade': ('区域守卫战前几次受击免伤', 'First Guardian Hits Blocked'),
    'DoorRerollMetaUpgrade': ('重塑地点奖励', 'Location Reward Rerolls'),
    'StartingGoldMetaUpgrade': ('增加初始金币', 'Starting Gold Increase'),
    'MetaToRunMetaUpgrade': ('局外奖励转化为局内奖励', 'Meta-to-Run Reward Conversion'),
    'RarityBoostMetaUpgrade': ('提高稀有/传奇祝福概率', 'Higher Rare/Legendary Boon Chance'),
    'DuoRarityBoostMetaUpgrade': ('提高双重祝福概率', 'Higher Duo Boon Chance'),
    'RerollTradeOffMetaUpgrade': ('增加重塑命运次数', 'Extra Reroll Uses'),
    'PanelRerollMetaUpgrade': ('重塑祝福及其他选项', 'Boon/Choice Rerolls'),
    'LowHealthBuffMetaUpgrade': ('无死里逃生时增伤减伤', 'No-Death-Defiance Damage & Defense'),
    'EpicRarityBoostMetaUpgrade': ('提高史诗祝福概率', 'Higher Epic Boon Chance'),
    'BossProgressionMetaUpgrade': ('击败区域守卫后随机激活阿卡那', 'Random Arcana Activation After Guardian'),
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
        display_id=item.get('displayId')
        linked_trait=item.get('linkedTrait')
        source_id=item.get('sourceId')
        if isinstance(trait_id,str) and trait_id:lookup.append(trait_id)
        if isinstance(display_id,str) and display_id:lookup.append(display_id)
        if isinstance(linked_trait,str) and linked_trait:lookup.append(linked_trait)
        if isinstance(source_id,str) and source_id:
            lookup.append(_SPECIAL_SOURCE_LOCALIZATION_IDS.get(source_id,source_id))
    if not lookup:return decoded
    unique=set(lookup)
    linked_ids=set(_LINKED_OFFICIAL_NAME_IDS.values())
    linked_ids.update(base_id for base_id,_,_ in _LINKED_PROVISIONAL_RULES.values())
    localization_ids=unique | linked_ids | set(_SPECIAL_SOURCE_LOCALIZATION_IDS.values()) | set(_NATIVE_CHOICE_TITLE_IDS.values()) | set(_OFFICIAL_CATEGORY_TITLE_IDS.values()) | {_OLYMPIAN_BOON_TITLE_ID, _SELENE_TALENT_TITLE_ID, _HAMMER_TITLE_ID, _ECHO_LAST_RUN_TITLE_ID}
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
                'chaosBlessing','chaosCurse','seleneSpell','seleneTalent','hammerNative','echoLastRunExact'
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
                    else _ECHO_LAST_RUN_TITLE_ID
                    if item.get('acquisitionMode') == 'echoLastRunExact'
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

    # Live trait rows keep runtime routing identity in `name`, but every row
    # presented to Boon Management needs a player-recognizable label. Resolve
    # the owner/source first so owner-backed systems can recover when the
    # concrete mounted implementation trait has no standalone DisplayName.
    for item in current_run_traits:
        if not isinstance(item,dict):continue
        identifier=item.get('name')
        if not isinstance(identifier,str) or not identifier:continue
        family=item.get('family') if isinstance(item.get('family'),str) else 'other'
        source_id=item.get('sourceId')
        if isinstance(source_id,str) and source_id:
            source_text_id = (
                _HAMMER_TITLE_ID
                if family == 'hammer'
                else _SPECIAL_SOURCE_LOCALIZATION_IDS.get(source_id,source_id)
            )
            official_source_zh=_clean(zh.get(source_text_id)) if source_text_id else None
            official_source_en=_clean(en.get(source_text_id)) if source_text_id else None
            # sourceId remains the routing identity. Raw internal owner ids are
            # never promoted to user-facing copy merely because localization is
            # missing.
            item['sourceName']=official_source_zh or ''
            item['sourceEnglishName']=official_source_en or ''
        else:
            item['sourceName']=''
            item['sourceEnglishName']=''

        presentation_id=item.get('displayId')
        if not isinstance(presentation_id,str) or not presentation_id:
            presentation_id=identifier
        official_zh=_clean(zh.get(presentation_id)) if presentation_id in zh else None
        official_en=_clean(en.get(presentation_id)) if presentation_id in en else None
        derived_name=_CURRENT_RUN_DERIVED_NAMES.get(identifier)
        if derived_name:
            # The registry is intentionally more specific than either a missing
            # native title or (for Arcana) an inherited card title. Card/source
            # identity is retained separately and composed below.
            display_zh,display_en=derived_name
        elif isinstance(official_zh,str) and official_zh:
            display_zh=official_zh
            display_en=official_en or ''
        elif isinstance(official_en,str) and official_en:
            display_zh=official_en
            display_en=official_en
        else:
            display_zh,_,display_en,_=_fallback_names(
                {'kind':'trait','name':identifier},identifier,None,zh,en
            )

        source_zh=item['sourceName']
        source_en=item['sourceEnglishName']
        family_zh,family_en=_CURRENT_RUN_FAMILY_LABELS.get(
            family, ('其他效果','Other Effect')
        )

        # Arcana keeps its native card title; Familiar derived rows keep the native
        # familiar owner. Only the Trainer-owned function descriptor comes from
        # the exception registry.
        if family == 'arcana' and source_zh:
            if display_zh == '未命名效果' or not display_zh:
                display_zh=source_zh
            elif display_zh != source_zh:
                display_zh=f'{source_zh} · {display_zh}'
        elif family == 'familiar' and derived_name and source_zh:
            display_zh=f'{source_zh} · {display_zh}'
        elif display_zh == '未命名效果' or not display_zh:
            display_zh=f'{source_zh} · {family_zh}' if source_zh else family_zh

        if family == 'arcana' and source_en:
            if display_en == 'Unnamed Effect' or not display_en:
                display_en=source_en
            elif display_en != source_en:
                display_en=f'{source_en} · {display_en}'
        elif family == 'familiar' and derived_name and source_en:
            display_en=f'{source_en} · {display_en}'
        elif display_en == 'Unnamed Effect' or not display_en:
            display_en=f'{source_en} · {family_en}' if source_en else family_en

        item['displayName']=display_zh
        item['englishName']=display_en

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
    if fallback_special:
        missing=set(fallback_special)
        warnings=decoded.get('warnings') if isinstance(decoded.get('warnings'),list) else []
        message=(f'未从本机 {GAME_SPEC.display_name} 中文语言文件解析到 {len(missing)} 项角色奖励的官方中文名称，'
                 '已保留并使用官方英文名或内部名称。')
        if message not in warnings:warnings.append(message)
        decoded['warnings']=warnings
    return decoded
