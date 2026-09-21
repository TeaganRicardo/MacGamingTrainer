from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
lua = (ROOT / "Backend/games/hades2/runtime/hades.lua").read_text()

spawn = lua.split('if command == "spawn_reward" then', 1)[1].split('if command == "set_resource" then', 1)[0]

# Store traits must follow the same processed-duration and stacking semantics as
# native Well purchases rather than the simpler special-NPC TraitName path.
for marker in (
    'GetProcessedTraitData({ Unit = CurrentRun.Hero, TraitName = entry.trait })',
    'RecalculateStoreTraitDurations(traitData)',
    'traitData.IncreaseUsesOnStack',
    'UseHeroTraitsWithValue("BossExtension", true)',
):
    assert marker in spawn, marker

# A store-price trait must invalidate already-instantiated shop options so the
# current room observes the new StoreCostMultiplier just like native purchase.
for marker in (
    'traitData.StoreCostMultiplier',
    'currentUpgradeData.Processed = nil',
    'currentUpgradeData.DataOverrides = ShallowCopyTable(currentUpgradeData)',
    'currentUpgradeData.DataOverrides.ResourceCosts = nil',
):
    assert marker in spawn, marker
assert 'and type(currentUpgradeData.ResourceCosts) == "table"' not in spawn

# ExtendedShopTrait turns only its native allowlisted Well items into boss-duration
# traits. The trainer must reconstruct the same eligibility that StoreLogic sets
# on upgradeData before HandleStorePurchase runs.
for marker in (
    'extension.ValidPermanentItemsLookup[entry.trait]',
    'IsTraitActive(extension)',
    'traitData.MakePermanent = true',
):
    assert marker in spawn, marker

# Shop-specific wrapper ids must use the same native creation functions as
# StoreLogic instead of falling through generic CreateConsumableItem.
for marker in (
    'entry.spawnMode == "weapon_loot"',
    'CreateWeaponLoot({',
    'entry.spawnMode == "hermes_loot"',
    'CreateHermesLoot({',
    'BoughtFromShop = true',
):
    assert marker in spawn, marker

# Store random-boon wrappers are resolved before spawning. The boosted variant
# preserves the game's rarity override instead of becoming an inert consumable.
for marker in (
    'GetEligibleInteractedGod()',
    'entry.spawnMode == "boosted_random_loot"',
    'BoonRaritiesOverride = { Legendary = 0.1, Epic = 0.25, Rare = 0.90 }',
    'GiveLoot(lootArgs)',
):
    assert marker in spawn, marker

print("hades2_store_reward_spawn_semantics_ok")
