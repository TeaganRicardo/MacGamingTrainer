import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
lua = (ROOT / "Backend/games/hades2/runtime/hades.lua").read_text()

reward_block = lua.split("local rewardDefinitions = {", 1)[1].split("  local elementNames =", 1)[0]
rows = {}
for line in reward_block.splitlines():
    if '{ id = "' not in line:
        continue
    fields = dict(re.findall(r'(\w+) = "([^"]+)"', line))
    if fields.get("id"):
        rows[fields["id"]] = fields

# Target build 1.139672 StoreData exposes the Anvil of Fates as the concrete
# ConsumableData id ChaosWeaponUpgrade. The trainer catalog must expose that
# legal shop reward through its normal one-shot spawn interface.
assert "ChaosWeaponUpgrade" in rows
anvil = rows["ChaosWeaponUpgrade"]
assert anvil.get("kind") == "consumable"
assert anvil.get("group") == "pickup"
assert anvil.get("category") == "商店商品"
assert anvil.get("family") == "shop"
assert anvil.get("name") == "命运铁砧"


well_consumables = {
    "ArmorBoostStore", "DamageSelfDrop", "EmptyMaxHealthShopItem",
    "HealDropRange", "LastStandShopItem", "LimitedManaRegenDrop",
    "LimitedSwapTraitDrop", "MemPointsCommonRange", "MetaCardPointsCommonRange",
    "MetaCurrencyRange", "RandomStoreItem", "SeedMysteryRange",
}
shop_consumables = {
    "BlindBoxLoot", "BoostedRandomLoot", "ChaosWeaponUpgrade",
    "RandomLoot", "ShopHermesUpgrade", "WeaponUpgradeDrop",
}
store_traits = {
    "ExtendedShopTrait", "FirstHitHealTrait",
    "TemporaryBoonRarityTrait", "TemporaryDiscountTrait",
    "TemporaryDoorHealTrait", "TemporaryEmptySlotDamageTrait",
    "TemporaryForcedSecretDoorTrait", "TemporaryHealExpirationTrait",
    "TemporaryImprovedCastTrait", "TemporaryImprovedDefenseTrait",
    "TemporaryImprovedExTrait", "TemporaryImprovedSecondaryTrait",
    "TemporaryMoveSpeedTrait",
}

for identifier in ("HealDrop", "HealDropMinor"):
    row = rows[identifier]
    assert row.get("kind") == "consumable", identifier
    assert row.get("family") == "healing", identifier
    assert row.get("category") == "资源与常规掉落", identifier

assert rows["RerollDrop"].get("name") == "重塑命运"
assert rows["WeaponUpgradeDrop"].get("spawnMode") == "weapon_loot"
assert rows["ShopHermesUpgrade"].get("spawnMode") == "hermes_loot"

for identifier in well_consumables:
    row = rows[identifier]
    assert row.get("kind") == "consumable", identifier
    assert row.get("family") == "well", identifier
    assert row.get("category") == "卡戎之井", identifier

for identifier in shop_consumables:
    row = rows[identifier]
    assert row.get("kind") == "consumable", identifier
    assert row.get("family") == "shop", identifier
    assert row.get("category") == "商店商品", identifier

for trait_name in store_traits:
    identifier = "trait:" + trait_name
    row = rows[identifier]
    assert row.get("kind") == "trait", identifier
    assert row.get("family") == "well", identifier
    assert row.get("category") == "卡戎之井", identifier

for identifier in (
    "HealDropSuperMinor",
    "MedeaMoneyTinyDrop", "PowerDrinkDrop", "BloodDrop",
    "ManaDropMinorPoseidon", "ManaDropMinor", "ManaDropZeus", "ManaDropMinorHound",
    "Boon", "Devotion",
):
    assert identifier not in rows, identifier

print("hades2_store_reward_catalog_ok")
