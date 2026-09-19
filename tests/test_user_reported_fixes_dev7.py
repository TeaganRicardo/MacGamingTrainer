#!/usr/bin/env python3
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from games.hades2.preferences import DESIRED_STATE_SCHEMA_VERSION, Hades2PreferenceStore
from games.hades2.profile_service import PROFILE_SCHEMA_VERSION
from games.hades2.schema import TOGGLES
from games.hades2.localization import _clean_display_name


def read(relative):
    return (ROOT / relative).read_text(encoding='utf-8')


def main():
    # Native boon-choice count is retired instead of pretending to support >3.
    view = read('Sources/Hades2/Hades2View.swift')
    assert '祝福选项数量' not in view
    assert '强制传奇 Legendary' in view
    assert '强制双重 Duo' in view
    assert view.count('enabled: model.canEditDesired && model.boonRarityEnabled') >= 2
    assert 'boonChoiceEnabled' not in TOGGLES
    assert 'boonChoiceCount' not in Hades2PreferenceStore.defaults()
    assert Hades2PreferenceStore.defaults()['boonRarity']['forceLegendary'] is False
    assert Hades2PreferenceStore.defaults()['boonRarity']['forceDuo'] is False
    assert DESIRED_STATE_SCHEMA_VERSION == 3
    assert PROFILE_SCHEMA_VERSION == 4

    # Legacy allow=true must not silently turn into a force action after upgrade.
    prefs = read('Backend/games/hades2/preferences.py')
    assert "rarity['forceLegendary']=False" in prefs
    assert "rarity['forceDuo']=False" in prefs
    assert "rarity.pop('allowLegendary',None)" in prefs
    assert "rarity.pop('allowDuo',None)" in prefs
    assert 'boonChoiceCount' not in prefs

    lua = read('Backend/games/hades2/runtime/hades.lua')
    assert 'local function forceSpecialBoonOption' in lua
    assert 'GetEligibleUpgrades' in lua
    assert 'forceSpecialBoonOption(lootData, args, "Legendary")' in lua
    assert 'forceSpecialBoonOption(lootData, args, "Duo")' in lua
    assert 'optionAllowedByRarityConfig' not in lua
    # Forcing is eligibility-based and must not increase the native choice count.
    force_block = lua[lua.index('local function forceSpecialBoonOption'):lua.index('local function installBoonRarity')]
    assert 'GetTotalLootChoices' not in force_block
    assert 'lootData.UpgradeOptions[replacement] = candidate' in force_block
    assert 'lootData.UpgradeOptions[#lootData.UpgradeOptions + 1] = candidate' in force_block

    # Selene must use the room-reward pipeline, not the old bare GiveLoot path.
    special_start = lua.index('if rewardId == "SpellDrop" then')
    special_end = lua.index('requireFunctions("loot spawning"', special_start)
    selene = lua[special_start:special_end]
    assert 'SpawnRoomReward' in selene
    assert 'RewardOverride = "SpellDrop"' in selene
    assert 'LootName = "SpellDrop"' not in selene
    assert 'local loot = GiveLoot' not in selene

    # Inventory uses game-owned InventoryScreen grouping/order and keeps sort order through Swift.
    assert 'ScreenData.InventoryScreen.ItemCategories' in lua
    assert 'inventoryResourceLayout' in lua
    types = read('Sources/Hades2/Hades2Types.swift')
    backend_state = read('Sources/Hades2/Hades2BackendState.swift')
    assert 'let sortOrder: Int' in types
    assert 'let sortSection: Int' in types
    assert 'let sortGroup: Int' in types
    assert 'sortOrder: row["sortOrder"] as? Int ?? Int.max' in backend_state
    assert 'sortSection: row["sortSection"] as? Int ?? Int.max' in backend_state
    assert 'sortGroup: row["sortGroup"] as? Int ?? Int.max' in backend_state
    assert 'private func sortedBoons' in view

    # Display localization must strip Hades formatting tokens/braces entirely.
    for sample, expected in (
        ('{#Echo} 月光', '月光'),
        ('(#Echo) {#Emph}月光{#Prev}', '月光'),
        ('{!Icons.Mana} 魔力', '魔力'),
        ('{UnrenderableControl} 名称', '名称'),
    ):
        cleaned = _clean_display_name(sample)
        assert cleaned == expected, (sample, cleaned)
        assert '{' not in cleaned and '}' not in cleaned

    catalog = read('Backend/games/hades2/catalog.py')
    assert "item['name']=official_zh" in catalog
    assert "item['nameSource']='official_zh'" in catalog
    # Source belongs in grouping metadata, not prefixed into the official item name.
    assert "source_name} ·" not in catalog

    # Feature icon and switch use the same phase/state tint; metric card is optically centered.
    toggle = read('Sources/Core/UI/Primitives/TrainerToggleControl.swift')
    feature_controls = read('Sources/Core/UI/Components/TrainerFeatureControls.swift')
    card = read('Sources/Core/UI/Primitives/TrainerCard.swift')
    assert '.tint(tint ?? theme.accent)' in toggle
    assert feature_controls.count('tint: state.indicatorColor') >= 3
    assert '.padding(.top, 6)' in card
    assert '.padding(.bottom, 8)' in card

    print('user_reported_fixes_dev7_ok')


if __name__ == '__main__':
    main()
