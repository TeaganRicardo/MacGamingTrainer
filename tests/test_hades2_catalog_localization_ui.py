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
''', encoding='utf-8')
    names = localization.official_display_names({'EchoMockTrait', 'MaxManaDrop'}, 'zh-CN', game_path=root)
    assert names['EchoMockTrait'] == '回声之赐'
    assert names['MaxManaDrop'] == '灵魂滋补剂'

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

# Player-facing mounted effects without an official DisplayName use one curated
# effect label rather than their internal trait id. This is especially relevant
# to Familiar upgrade subtraits in #240.
original_display_names = localization.official_display_names
localization.official_display_names = lambda identifiers, language='zh-CN', game_path=None: {}
try:
    live_payload = {
        'currentRunTraits': [
            {'name': 'FamiliarFrogDamage', 'sourceId': '', 'family': 'familiar'},
            {'name': 'FamiliarCatAttacks', 'sourceId': '', 'family': 'familiar'},
        ]
    }
    catalog.localize_catalog(live_payload)
finally:
    localization.official_display_names = original_display_names

frog, cat = live_payload['currentRunTraits']
assert frog['displayName'] == '弗利诺斯·攻击伤害'
assert frog['englishName'] == 'Frinos · Attack Damage'
assert cat['displayName'] == '图拉·攻击次数'
assert cat['englishName'] == 'Toula · Attack Count'
assert frog['displayName'] != frog['name']
assert cat['displayName'] != cat['name']

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
