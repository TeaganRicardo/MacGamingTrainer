import sys
import tempfile
from pathlib import Path

from runtime_revision_support import runtime_revision

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from games.hades2 import catalog, localization

lua = (ROOT / 'Backend/games/hades2/runtime/hades.lua').read_text()
card = (ROOT / 'Sources/Core/UI/Primitives/TrainerCard.swift').read_text()
view = (ROOT / 'Sources/Hades2/Hades2View.swift').read_text()
zh_presentation = (ROOT / 'Sources/Hades2/Presentation/Localization/hades2.zh-CN.json').read_text()
en_presentation = (ROOT / 'Sources/Hades2/Presentation/Localization/hades2.en.json').read_text()

# Known full-release room rewards that were missing from the curated spawn list.
for token in (
    'RoomMoneyTinyDrop', 'RoomMoneySmallDrop',
    'MaxManaDropSmall', 'MaxManaDrop', 'MaxManaDropBig',
    'MinorTalentDrop', 'TalentDrop', 'TalentBigDrop',
    'GiftDrop', 'MetaCurrencyDrop', 'MetaCurrencyBigDrop',
    'MetaCardPointsCommonDrop', 'MetaCardPointsCommonBigDrop',
    'MemPointsCommonDrop', 'MemPointsCommonBigDrop',
    'FireBoost', 'WaterBoost', 'EarthBoost', 'AirBoost',
):
    assert f'id = "{token}"' in lua, token

# Future-proofing: direct rewards from the game's RewardStoreData are added if
# they resolve to real ConsumableData/LootData entries.
assert 'if type(RewardStoreData) == "table" then' in lua
assert 'definition.Name' in lua
assert 'type(ConsumableData[id]) == "table"' in lua
assert 'type(LootData[id]) == "table"' in lua
assert 'RuntimeFutureReward' not in lua  # test-only name comes from the mock
assert runtime_revision(lua) >= 42

# Hades SJSON display strings contain presentation tags. They must never leak to
# the UI as literal (#Echo), #Echo or {#Echo} text.
examples = {
    '(#Echo) 回声祝福': '回声祝福',
    '（#Echo） 回声祝福': '回声祝福',
    '{#Echo}回声祝福': '回声祝福',
    '#Echo 回声祝福': '回声祝福',
    '{#Emph}Soul Tonic': 'Soul Tonic',
    '{!Icons.Mana} Moon Boon': 'Moon Boon',
    '{UnrenderableControl}Clean Name': 'Clean Name',
}
for raw, expected in examples.items():
    assert localization._clean_display_name(raw) == expected, (raw, localization._clean_display_name(raw))

# Exercise the installed-text parser too, not only the helper.
localization._OFFICIAL_TEXT_CACHE.clear()
with tempfile.TemporaryDirectory(prefix='mgt-catalog-loc-') as td:
    root = Path(td)
    text_dir = root / 'Contents/Resources/Content/Game/Text'
    text_dir.mkdir(parents=True)
    (text_dir / 'Traits.zh-CN.sjson').write_text('''
Thing = { Id = "EchoMockTrait" DisplayName = "(#Echo) 回声之赐" }
Mana = { Id = "MaxManaDrop" DisplayName = "{#Emph}灵魂滋补剂" }
Owner = { Id = "ArcanaOwner" DisplayName = "猎手" }
Child = { Id = "ArcanaMountedTrait" InheritFrom = "ArcanaOwner" }
Grandchild = { Id = "ArcanaTrayTrait" InheritFrom = "ArcanaMountedTrait" }
''', encoding='utf-8')
    names = localization.official_display_names(
        {'EchoMockTrait', 'MaxManaDrop', 'ArcanaMountedTrait', 'ArcanaTrayTrait'},
        'zh-CN',
        game_path=root,
    )
    assert names['EchoMockTrait'] == '回声之赐'
    assert names['MaxManaDrop'] == '灵魂滋补剂'
    assert names['ArcanaMountedTrait'] == '猎手'
    assert names['ArcanaTrayTrait'] == '猎手'

# Exact acquisition rows keep the trait's official name while grouping by the
# official source identity in both languages. The group is product structure;
# it must not cause raw source IDs or one-language fallback headings.
original_display_names = localization.official_display_names
def fake_display_names(identifiers, language='zh-CN', game_path=None):
    zh = {
        'ZeusWeaponBoon': '雷霆打击',
        'ZeusUpgrade': '宙斯',
        'CritBonusBoon': '致命一击',
        'NPC_Artemis_Field_01': '阿耳忒弥斯',
        'Boon': '祝福',
    }
    en = {
        'ZeusWeaponBoon': 'Heaven Strike',
        'ZeusUpgrade': 'Zeus',
        'CritBonusBoon': 'Deadly Strike',
        'NPC_Artemis_Field_01': 'Artemis',
        'Boon': 'Boon',
    }
    source = zh if language == 'zh-CN' else en
    return {key: source[key] for key in identifiers if key in source}

localization.official_display_names = fake_display_names
try:
    payload = {
        'rewards': [
            {
                'id': 'exact:ZeusUpgrade:ZeusWeaponBoon', 'trait': 'ZeusWeaponBoon',
                'kind': 'trait', 'group': 'exact', 'sourceId': 'ZeusUpgrade',
                'sourceName': '宙斯', 'sectionTitle': '宙斯',
                'category': '奥林匹斯的祝福', 'acquisitionMode': 'ordinaryNative',
            },
            {
                'id': 'trait:CritBonusBoon', 'trait': 'CritBonusBoon',
                'kind': 'trait', 'group': 'exact', 'sourceId': 'Artemis',
                'sourceName': 'Artemis', 'sectionTitle': 'Artemis',
                'category': '角色奖励', 'acquisitionMode': 'direct',
            },
        ]
    }
    catalog.localize_catalog(payload)
finally:
    localization.official_display_names = original_display_names

ordinary, direct = payload['rewards']
assert ordinary['name'] == '雷霆打击' and ordinary['englishName'] == 'Heaven Strike'
assert ordinary['sourceName'] == '宙斯' and ordinary['sourceEnglishName'] == 'Zeus'
assert ordinary['sectionTitle'] == '宙斯' and ordinary['englishSectionTitle'] == 'Zeus'
assert direct['name'] == '致命一击' and direct['englishName'] == 'Deadly Strike'
assert direct['sourceName'] == '阿耳忒弥斯' and direct['sourceEnglishName'] == 'Artemis'
assert direct['sectionTitle'] == '阿耳忒弥斯' and direct['englishSectionTitle'] == 'Artemis'
assert direct['englishCategory'] == 'Character Rewards'

# The exact-acquisition picker is its own user-visible surface directly below
# Character Rewards and above the mounted-management affordance. Recognition
# labels must stay user-facing: backend strategy and raw TraitData ids are not
# presentation fields.
boon_panel = view[view.index('private var boonPanel: some View'):view.index('private func spawnRow', view.index('private var boonPanel: some View'))]
character_index = boon_panel.index('hades2.spawn.characterRewards')
exact_index = boon_panel.index('hades2.spawn.exactBoons')
purging_index = boon_panel.index('hades2.spawn.purgingPool')
assert character_index < exact_index < purging_index
assert '$model.selectedExactBoon' in boon_panel
assert '$exactSearch' in boon_panel
assert 'exactItemLabel' in boon_panel
exact_label = view[view.index('private func exactItemLabel'):view.index('private func spawnRow', view.index('private func exactItemLabel'))]
assert 'exactModeNative' not in exact_label
assert 'exactModeForced' not in exact_label
assert 'option.targetID' not in exact_label
assert 'nameFallback' not in exact_label

# Selene exact acquisition uses the official Hex menu title for main spells and
# the official Path of Stars title for generated current-tree talent targets.
original_display_names = localization.official_display_names
def selene_names(identifiers, language='zh-CN', game_path=None):
    table = {
        'zh-CN': {
            'SpellMeteorTrait': '月蚀',
            'MeteorDamageTalent': '毁灭之星',
            'NPC_Selene_01': '塞勒涅',
            'SpellScreenMenu_Title': '巫咒',
            'TalentScreenMenu_Title': '繁星之路',
        },
        'en': {
            'SpellMeteorTrait': 'Total Eclipse',
            'MeteorDamageTalent': 'Gloaming',
            'NPC_Selene_01': 'Selene',
            'SpellScreenMenu_Title': 'Hexes',
            'TalentScreenMenu_Title': 'Path of Stars',
        },
    }
    source = table.get(language, {})
    return {key: source[key] for key in identifiers if key in source}

localization.official_display_names = selene_names
try:
    selene_payload = {
        'rewards': [
            {
                'id': 'selene:spell:Meteor', 'trait': 'SpellMeteorTrait',
                'kind': 'trait', 'group': 'exact', 'sourceId': 'Selene',
                'sourceName': '塞勒涅', 'sectionTitle': '塞勒涅',
                'category': '角色奖励', 'acquisitionMode': 'seleneSpell',
            },
            {
                'id': 'selene:talent:Meteor:MeteorDamageTalent',
                'trait': 'MeteorDamageTalent', 'kind': 'trait', 'group': 'exact',
                'sourceId': 'Selene', 'sourceName': '塞勒涅',
                'sectionTitle': '繁星之路', 'category': '角色奖励',
                'acquisitionMode': 'seleneTalent',
            },
        ]
    }
    catalog.localize_catalog(selene_payload)
finally:
    localization.official_display_names = original_display_names

hex_row, talent_row = selene_payload['rewards']
assert hex_row['name'] == '月蚀' and hex_row['englishName'] == 'Total Eclipse'
assert hex_row['sourceName'] == '塞勒涅' and hex_row['sourceEnglishName'] == 'Selene'
assert hex_row['sectionTitle'] == '巫咒' and hex_row['englishSectionTitle'] == 'Hexes'
assert talent_row['name'] == '毁灭之星' and talent_row['englishName'] == 'Gloaming'
assert talent_row['sectionTitle'] == '繁星之路'
assert talent_row['englishSectionTitle'] == 'Path of Stars'

# Echo previous-run exact targets use the concrete boon identity, Echo as the
# source identity, and the native previous-run choice title as their section.
original_display_names = localization.official_display_names
def echo_names(identifiers, language='zh-CN', game_path=None):
    table = {
        'zh-CN': {
            'ZeusBoon': '雷霆打击',
            'NPC_Echo_01': '回声',
            'EchoChoiceMenu_LastRun': '上局祝福',
        },
        'en': {
            'ZeusBoon': 'Thunder Strike',
            'NPC_Echo_01': 'Echo',
            'EchoChoiceMenu_LastRun': 'Boons from Last Night',
        },
    }
    return {key: table.get(language, {}).get(key) for key in identifiers if table.get(language, {}).get(key)}
localization.official_display_names = echo_names
try:
    echo_payload = {
        'rewards': [{
            'id': 'echo:lastRun:ZeusBoon', 'name': 'ZeusBoon',
            'trait': 'ZeusBoon', 'kind': 'trait', 'group': 'exact',
            'sourceId': 'Echo', 'sourceName': '回声',
            'sectionTitle': '上局祝福', 'category': '角色奖励',
            'acquisitionMode': 'echoLastRunExact',
        }]
    }
    catalog.localize_catalog(echo_payload)
finally:
    localization.official_display_names = original_display_names

echo_exact = echo_payload['rewards'][0]
assert echo_exact['name'] == '雷霆打击' and echo_exact['englishName'] == 'Thunder Strike'
assert echo_exact['sourceName'] == '回声' and echo_exact['sourceEnglishName'] == 'Echo'
assert echo_exact['sectionTitle'] == '上局祝福'
assert echo_exact['englishSectionTitle'] == 'Boons from Last Night'

# Hammer exact acquisition and mounted runtime ownership reuse one official
# WeaponUpgrade choice identity instead of exposing internal source ids.
original_display_names = localization.official_display_names
def hammer_names(identifiers, language='zh-CN', game_path=None):
    table = {
        'zh-CN': {
            'LobAmmoTrait': '巨量弹仓',
            'WeaponUpgradeChoiceMenu_Title': '狄德勒斯之锤',
        },
        'en': {
            'LobAmmoTrait': 'Mega Driver',
            'WeaponUpgradeChoiceMenu_Title': 'Daedalus Hammer',
        },
    }
    return {key: table.get(language, {}).get(key) for key in identifiers if table.get(language, {}).get(key)}
localization.official_display_names = hammer_names
try:
    hammer_payload = {
        'rewards': [{
            'id': 'hammer:LobAmmoTrait', 'name': 'LobAmmoTrait',
            'trait': 'LobAmmoTrait', 'kind': 'trait', 'group': 'exact',
            'sourceId': 'WeaponUpgrade', 'sourceName': '狄德勒斯之锤',
            'sectionTitle': '狄德勒斯之锤', 'category': '角色奖励',
            'acquisitionMode': 'hammerNative',
        }],
        'currentRunTraits': [{
            'name': 'LobAmmoTrait', 'sourceId': 'WeaponUpgrade', 'family': 'hammer',
        }],
    }
    catalog.localize_catalog(hammer_payload)
finally:
    localization.official_display_names = original_display_names

hammer_exact = hammer_payload['rewards'][0]
hammer_live = hammer_payload['currentRunTraits'][0]
assert hammer_exact['name'] == '巨量弹仓' and hammer_exact['englishName'] == 'Mega Driver'
assert hammer_exact['sectionTitle'] == '狄德勒斯之锤'
assert hammer_exact['englishSectionTitle'] == 'Daedalus Hammer'
assert hammer_live['displayName'] == '巨量弹仓'
assert hammer_live['englishName'] == 'Mega Driver'
assert hammer_live['sourceName'] == '狄德勒斯之锤'
assert hammer_live['sourceEnglishName'] == 'Daedalus Hammer'

# Player-facing mounted effects without an official DisplayName use one curated
# effect label rather than their internal trait id. This is especially relevant
# to Familiar upgrade subtraits in #240.
original_display_names = localization.official_display_names
def familiar_derived_names(identifiers, language='zh-CN', game_path=None):
    table = {
        'zh-CN': {'FrogFamiliar': '弗利诺斯', 'CatFamiliar': '图拉'},
        'en': {'FrogFamiliar': 'Frinos', 'CatFamiliar': 'Toula'},
    }
    return {key: table.get(language, {}).get(key) for key in identifiers if table.get(language, {}).get(key)}
localization.official_display_names = familiar_derived_names
try:
    live_payload = {
        'currentRunTraits': [
            {'name': 'FamiliarFrogDamage', 'sourceId': 'FrogFamiliar', 'family': 'familiar'},
            {'name': 'FamiliarCatAttacks', 'sourceId': 'CatFamiliar', 'family': 'familiar'},
        ]
    }
    catalog.localize_catalog(live_payload)
finally:
    localization.official_display_names = original_display_names

frog, cat = live_payload['currentRunTraits']
assert frog['displayName'] == '弗利诺斯 · 攻击伤害'
assert frog['englishName'] == 'Frinos · Attack Damage'
assert cat['displayName'] == '图拉 · 攻击次数'
assert cat['englishName'] == 'Toula · Attack Count'
assert frog['displayName'] != frog['name']
assert cat['displayName'] != cat['name']

# Familiar owner IDs are native localization IDs. The current-run source label
# must resolve through the same bilingual official-localization seam instead of
# exposing RavenFamiliar/CatFamiliar as product text.
original_display_names = localization.official_display_names
def familiar_owner_names(identifiers, language='zh-CN', game_path=None):
    table = {
        'zh-CN': {'CritFamiliar': '锐眼', 'RavenFamiliar': '拉奇'},
        'en': {'CritFamiliar': 'Sharp Eye', 'RavenFamiliar': 'Raki'},
    }
    return {key: table.get(language, {}).get(key) for key in identifiers if table.get(language, {}).get(key)}
localization.official_display_names = familiar_owner_names
try:
    familiar_owner_payload = {
        'currentRunTraits': [{
            'name': 'CritFamiliar', 'sourceId': 'RavenFamiliar', 'family': 'familiar',
        }]
    }
    catalog.localize_catalog(familiar_owner_payload)
finally:
    localization.official_display_names = original_display_names

familiar_owner = familiar_owner_payload['currentRunTraits'][0]
assert familiar_owner['displayName'] == '锐眼'
assert familiar_owner['englishName'] == 'Sharp Eye'
assert familiar_owner['sourceName'] == '拉奇'
assert familiar_owner['sourceEnglishName'] == 'Raki'
assert familiar_owner['sourceName'] != familiar_owner['sourceId']

# Arcana runtime rows have two presentation identities: the card title is a
# native game term, while the short functional descriptor is Trainer-owned and
# derived from the target build's official card Description. TraitName remains
# routing identity only.
original_display_names = localization.official_display_names
def arcana_names(identifiers, language='zh-CN', game_path=None):
    table = {
        'zh-CN': {'LowManaDamageBonus': '猎手'},
        'en': {'LowManaDamageBonus': 'The Huntress'},
    }
    return {key: table.get(language, {}).get(key) for key in identifiers if table.get(language, {}).get(key)}
localization.official_display_names = arcana_names
try:
    arcana_payload = {
        'currentRunTraits': [{
            'name': 'LowManaDamageMetaupgrade',
            'sourceId': 'LowManaDamageBonus',
            'family': 'arcana',
        }]
    }
    catalog.localize_catalog(arcana_payload)
finally:
    localization.official_display_names = original_display_names

arcana = arcana_payload['currentRunTraits'][0]
assert arcana['displayName'] == '猎手 · 魔力未满时攻击/特技增伤'
assert arcana['englishName'] == 'The Huntress · Attack/Special Damage Below Full Magick'
assert arcana['sourceName'] == '猎手'
assert arcana['sourceEnglishName'] == 'The Huntress'
assert arcana['sourceName'] != arcana['sourceId']
assert arcana['displayName'] != arcana['name']

# Other mounted owner-backed effects also receive a source/family recognition
# label instead of a generic unnamed row when no standalone native title exists.
original_display_names = localization.official_display_names
def owner_fallback_names(identifiers, language='zh-CN', game_path=None):
    table = {
        'zh-CN': {'NPC_Echo_01': '回声'},
        'en': {'NPC_Echo_01': 'Echo'},
    }
    return {key: table.get(language, {}).get(key) for key in identifiers if table.get(language, {}).get(key)}
localization.official_display_names = owner_fallback_names
try:
    owner_fallback_payload = {
        'currentRunTraits': [{
            'name': 'InternalEchoEffect',
            'sourceId': 'Echo',
            'family': 'directSpecial',
        }]
    }
    catalog.localize_catalog(owner_fallback_payload)
finally:
    localization.official_display_names = original_display_names

owner_fallback = owner_fallback_payload['currentRunTraits'][0]
assert owner_fallback['displayName'] == '回声 · 特殊角色效果'
assert owner_fallback['englishName'] == 'Echo · Special NPC Effect'
assert owner_fallback['displayName'] != '未命名效果'
assert owner_fallback['englishName'] != 'Unnamed Effect'

# The supported-target census owns every current-run trait that lacks a concrete
# native title. Family labels are emergency compatibility fallbacks only; none
# of these known 1.143476 traits may resolve to one.
derived_names = catalog._CURRENT_RUN_DERIVED_NAMES
assert len(derived_names) == 47
generic_zh = {'未命名效果', *[value[0] for value in catalog._CURRENT_RUN_FAMILY_LABELS.values()]}
generic_en = {'Unnamed Effect', *[value[1] for value in catalog._CURRENT_RUN_FAMILY_LABELS.values()]}
for trait_id, pair in derived_names.items():
    assert isinstance(pair, tuple) and len(pair) == 2, trait_id
    assert all(isinstance(value, str) and value.strip() for value in pair), trait_id
    assert trait_id not in pair, trait_id
    assert pair[0] not in generic_zh, trait_id
    assert pair[1] not in generic_en, trait_id

# Regression checks are deliberately selective: the production registry is the
# sole row-level source of truth, so the test must not mirror all 47 labels.
assert derived_names['ElementalEssence'] == ('元素', 'Element')
assert derived_names['SuitInherentSpeedBoon'] == ('冲刺速度加成', 'Sprint Speed Bonus')
assert derived_names['FamiliarFrogDamage'] == ('攻击伤害', 'Attack Damage')
assert derived_names['LowManaDamageMetaupgrade'] == (
    '魔力未满时攻击/特技增伤', 'Attack/Special Damage Below Full Magick'
)
assert derived_names['ChamberHealthMetaUpgrade'] == (
    '每5个房间增加生命值/魔力值上限', 'Max Life/Magick Every 5 Rooms'
)
assert derived_names['EffectVulnerabilityMetaUpgrade'] == (
    '至少2种奥林匹斯状态时增伤', 'Damage vs. 2+ Olympian Statuses'
)
assert derived_names['BossShieldMetaUpgrade'] == (
    '区域守卫战前几次受击免伤', 'First Guardian Hits Blocked'
)

governance_path = ROOT / 'docs/reference/hades2/1.143476-25481925/boon_management_effect_naming.md'
governance = governance_path.read_text(encoding='utf-8')
assert 'boon_management_effect_names.csv' not in governance
assert 'catalog._CURRENT_RUN_DERIVED_NAMES' in governance
assert not (ROOT / 'docs/reference/hades2/1.143476-25481925/boon_management_effect_names.csv').exists()

# Runtime presentation follows the same title identity the native Trait Tray uses.
# A CustomTitle / native tooltip title can therefore name an otherwise internal
# TraitData row without changing its routing identity.
original_display_names = localization.official_display_names
def native_title_names(identifiers, language='zh-CN', game_path=None):
    table = {
        'zh-CN': {'PlayerVisibleInternalTitle': '原生可辨识效果'},
        'en': {'PlayerVisibleInternalTitle': 'Native Recognizable Effect'},
    }
    return {key: table.get(language, {}).get(key) for key in identifiers if table.get(language, {}).get(key)}
localization.official_display_names = native_title_names
try:
    native_title_payload = {
        'currentRunTraits': [{
            'name': 'InternalImplementationTrait',
            'displayId': 'PlayerVisibleInternalTitle',
            'sourceId': '',
            'family': 'other',
        }]
    }
    catalog.localize_catalog(native_title_payload)
finally:
    localization.official_display_names = original_display_names

native_title = native_title_payload['currentRunTraits'][0]
assert native_title['displayName'] == '原生可辨识效果'
assert native_title['englishName'] == 'Native Recognizable Effect'
assert native_title['displayName'] != native_title['name']

# The selected Keepsake owner uses the native Keepsake localization identity.
# Runtime routing may retain the exact trait id, but the user-facing owner label
# must resolve from official bilingual game text.
original_display_names = localization.official_display_names
def keepsake_owner_names(identifiers, language='zh-CN', game_path=None):
    table = {
        'zh-CN': {'ReincarnationKeepsake': '更幸运的牙齿'},
        'en': {'ReincarnationKeepsake': 'Luckier Tooth'},
    }
    return {key: table.get(language, {}).get(key) for key in identifiers if table.get(language, {}).get(key)}
localization.official_display_names = keepsake_owner_names
try:
    keepsake_owner_payload = {
        'currentRunTraits': [{
            'name': 'ReincarnationKeepsake',
            'sourceId': 'ReincarnationKeepsake',
            'family': 'keepsake',
        }]
    }
    catalog.localize_catalog(keepsake_owner_payload)
finally:
    localization.official_display_names = original_display_names

keepsake_owner = keepsake_owner_payload['currentRunTraits'][0]
assert keepsake_owner['displayName'] == '更幸运的牙齿'
assert keepsake_owner['englishName'] == 'Luckier Tooth'
assert keepsake_owner['sourceName'] == '更幸运的牙齿'
assert keepsake_owner['sourceEnglishName'] == 'Luckier Tooth'
assert keepsake_owner['sourceName'] != keepsake_owner['sourceId']

# Linked Chaos phases use the same official presentation seam; the raw linked
# trait id remains routing/diagnostic identity and is not a user label.
original_display_names = localization.official_display_names
def chaos_names(identifiers, language='zh-CN', game_path=None):
    table = {
        'zh-CN': {
            'ChaosDamageCurse': '受难',
            'ChaosHealthBlessing': '丰盛',
            'NPC_Chaos_01': '卡俄斯',
        },
        'en': {
            'ChaosDamageCurse': 'Maimed',
            'ChaosHealthBlessing': 'Affluence',
            'NPC_Chaos_01': 'Chaos',
        },
    }
    return {key: table.get(language, {}).get(key) for key in identifiers if table.get(language, {}).get(key)}
localization.official_display_names = chaos_names
try:
    chaos_payload = {
        'currentRunTraits': [{
            'name': 'ChaosDamageCurse',
            'linkedTrait': 'ChaosHealthBlessing',
            'sourceId': 'Chaos',
            'family': 'chaos',
        }]
    }
    catalog.localize_catalog(chaos_payload)
finally:
    localization.official_display_names = original_display_names
chaos = chaos_payload['currentRunTraits'][0]
assert chaos['displayName'] == '受难'
assert chaos['englishName'] == 'Maimed'
assert chaos['linkedDisplayName'] == '丰盛'
assert chaos['linkedEnglishName'] == 'Affluence'
assert chaos['linkedDisplayName'] != chaos['linkedTrait']

# Arcana cards share one player-facing family section instead of each exact card
# owner becoming its own section. The full mounted inventory remains visible.
source_label = view[view.index('private func traitSourceLabel'):view.index('private var currentRunTraitPickerSections')]
assert 'trait.family == "arcana"' in source_label
assert '"biomeState"' in lua
assert 'hades2.traits.family.arcana' in zh_presentation
assert '"hades2.traits.family.arcana": "阿卡那牌"' in zh_presentation
assert '"hades2.traits.family.arcana": "Arcana"' in en_presentation
for family in (
    'arcana', 'biomeState', 'chaos', 'costume', 'directSpecial', 'familiar', 'hammer',
    'hex', 'hexTalent', 'keepsake', 'olympianHermes', 'other',
    'temporary', 'weaponAspect',
):
    assert f'"hades2.traits.family.{family}"' in zh_presentation, family
    assert f'"hades2.traits.family.{family}"' in en_presentation, family

trait_manager = view[view.index('private var currentRunTraitsPanel'):view.index('private var resourceSection')]
assert 'currentRunTraitRow' not in trait_manager
assert 'hades2.traits.manager' in trait_manager
assert '$managedTraitSelection' in trait_manager
assert '$traitSearch' in trait_manager
assert 'currentRunTraitPickerSections' in trait_manager
assert 'currentRunTraitContextualControls' in trait_manager
assert 'currentRunTraitCommonControls' in trait_manager
assert 'TextField(text("hades2.traits.targetRarity")' not in trait_manager
assert 'Picker(text("hades2.traits.targetRarity")' in trait_manager
assert 'TraitManagerLayout.commonControlsWidth' in trait_manager
assert 'TraitManagerLayout.levelControlsWidth' in trait_manager
assert 'TraitManagerLayout.rarityControlsWidth' in trait_manager
assert 'TraitManagerLayout.removeControlWidth' in trait_manager
assert 'traitLimitationRows' not in trait_manager
assert 'deferredIssue' not in trait_manager
assert 'model.advanceTraitLifecycle(trait)' in trait_manager
assert 'hades2.traits.chaos.cancelPair' in trait_manager

# Metric cards are content-sized; no hidden min-height is allowed to re-create
# the empty strip above title/lock controls.
metric = card[card.index('struct TrainerMetricCard'):]
assert 'minHeight: 82' not in metric
assert '.padding(.top, 6)' in metric and '.padding(.bottom, 8)' in metric
assert '.frame(maxWidth: .infinity, alignment: .leading)' in metric

print('hades2_catalog_localization_ui_ok')
