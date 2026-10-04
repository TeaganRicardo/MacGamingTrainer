from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LUA = (ROOT / "Backend/games/hades2/runtime/hades.lua").read_text()
CATALOG = (ROOT / "Backend/games/hades2/catalog.py").read_text()
TYPES = (ROOT / "Sources/Hades2/Hades2Types.swift").read_text()


def test_current_run_traits_reuse_official_bilingual_localization_seam():
    assert "currentRunTraits" in CATALOG
    assert "displayName" in CATALOG
    assert "englishName" in CATALOG
    assert "_SPECIAL_SOURCE_LOCALIZATION_IDS" in CATALOG
    assert "sourceName" in CATALOG
    assert "sourceEnglishName" in CATALOG

    assert "displayName" in TYPES
    assert "englishName" in TYPES
    assert "sourceName" in TYPES
    assert "sourceEnglishName" in TYPES


def test_special_npc_ownership_comes_from_native_source_data():
    source_block = LUA[LUA.index("local function specialTraitSourceId"):LUA.index("local function sellScreenEligible")]
    assert "nativeSpecialChoiceDefinitions" in source_block
    assert "EnemyData[definition.npc]" in source_block
    assert "PresetEventArgs[definition.choices]" in source_block
    assert "option.ItemName == name" in source_block
    assert "specialTraitSourceId(trait.Name)" in source_block
    assert "CheckEnemyData = true" in source_block

    family_block = LUA[LUA.index("local function traitFamily"):LUA.index("local function availableRarities")]
    assert 'nativeSpecialChoiceDefinitions[source] ~= nil' in family_block


def test_owner_family_controls_default_native_paths():
    family_block = LUA[LUA.index("local function traitFamily"):LUA.index("local function availableRarities")]
    capability_block = LUA[LUA.index("local function operationCapabilities"):LUA.index("local currentRunTraits = function()")]

    assert 'string.find(source, "NPC_", 1, true) == 1' in family_block
    assert 'return "directSpecial"' in family_block
    assert 'family == "olympianHermes" and nativeLevelEligible(trait)' in capability_block
    assert 'family == "olympianHermes" and sellEligible' in capability_block
    assert 'GetAllUpgradeableGodTraits, 1' in LUA

    # Only audited owner strategies may bypass ordinary menu eligibility.
    # Chaos (#236), Selene (#237), Hammer/weapon ownership (#238), Arachne,
    # Echo, and temporary-effect ownership (#239 children) are implemented;
    # the remaining families stay delegated to follow-up slices.
    assert 'CritBonusBoon = { sourceId = "Artemis", level = "increaseOne" }' in LUA
    assert 'OmegaExplodeBoon = { sourceId = "Icarus", rarity = "setExact", removal = "singleInstanceForce" }' in LUA
    assert 'family == "chaos"' in capability_block
    assert 'chaosLifecycleState' in LUA
    assert 'family == "hex"' in capability_block
    assert 'family == "hexTalent"' in capability_block
    assert "seleneModel.talentNodes" in LUA
    # Hammer/weaponAspect, Arachne costume, temporary-effect, Familiar, and
    # selected-Keepsake ownership have executable resident coverage.
    assert 'family == "temporary"' in capability_block
    assert 'family == "familiar"' in capability_block
    assert 'family == "keepsake"' in capability_block
    assert "familiarModel.isMounted(trait)" in family_block
    assert "keepsakeModel.isMounted(trait)" in family_block
    assert 'string.find(name, "Familiar", 1, true)' not in family_block
    for family, issue in (
        ("directSpecial", "239"), ("other", "221"),
    ):
        assert f"{family} = {issue}" in LUA
    assert "familiar = 240" not in LUA
    assert "keepsake = 329" not in LUA
    assert "keepsakeModel.rankReady(trait)" in capability_block
    assert "traitManagement.keepsake.rebuildRarity" in LUA


if __name__ == "__main__":
    test_current_run_traits_reuse_official_bilingual_localization_seam()
    test_special_npc_ownership_comes_from_native_source_data()
    test_owner_family_controls_default_native_paths()
    print("hades2_live_trait_management_ok")

# Executable resident-runtime behavior coverage belongs to this feature owner.
import subprocess
import tempfile
import textwrap
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "Backend/games/hades2/runtime/hades.lua"
LUA = require_lua52("resident-runtime behavior tests")

HARNESS = r'''
local runtimePath = assert(arg[1], "runtime path required")
local contractPath = assert(arg[2], "dispatch contract path required")

SessionState = {}
GameState = {
  Resources = {},
  LifetimeResourcesGained = {},
  RunHistory = {},
  EquippedFamiliar = nil,
  FamiliarsUnlocked = { CatFamiliar = true, RavenFamiliar = true },
  FamiliarUpgrades = { PersistentCatUpgrade = true },
  LastAwardTrait = nil,
  KeepsakeChambers = { ReincarnationKeepsake = 42, BonusMoneyKeepsake = 17 },
  MetaUpgradeState = {
    LowManaDamageBonus = {
      Unlocked = true, Equipped = true, Level = 2,
      AdjacencyBonuses = { CustomMultiplier = 0.5 },
    },
    BonusHealth = {
      Unlocked = true, Equipped = true, Level = 2,
      AdjacencyBonuses = {},
    },
    DoorReroll = {
      Unlocked = true, Equipped = true, Level = 2,
      AdjacencyBonuses = {},
    },
    ChanneledBlock = {
      Unlocked = true, Equipped = true, Level = 2,
      AdjacencyBonuses = {},
    },
  },
}
ResourceData = {}
ResourceDisplayOrderData = {}
TraitElementData = {}
EnemyData = {
  NPC_Artemis_Field_01 = {
    Traits = {
      "DynamicDirectLevel", "DynamicDirectRarity", "DynamicDirectRemoval",
      "DynamicDirectOneShot", "DynamicDirectSetup",
    },
  },
  NPC_Icarus_01 = {
    Traits = { "DynamicIcarusArmor" },
  },
}
PresetEventArgs = {}
ScreenData = {}
MapState = { RoomRequiredObjects = {} }
FrameState = {}
PersistentKeepsakeKeys = { "DoorHealReserve", "CustomTrayText" }
MetaUpgradeCardData = {
  LowManaDamageBonus = {
    TraitName = "LowManaDamageMetaupgrade",
  },
  BonusHealth = {
    TraitName = "HealthManaBonusMetaUpgrade",
  },
  DoorReroll = {
    TraitName = "DoorRerollMetaUpgrade",
    OnGrantedFunctionName = "GrantMetaUpgradeRerolls",
    OnUpgradedFunctionName = "UpgradeMetaUpgradeRerolls",
  },
  ChanneledBlock = {
    TraitName = "BossShieldMetaUpgrade",
  },
}
TraitRarityData = {
  RarityUpgradeOrder = { "Common", "Rare", "Epic", "Heroic" },
}
round = function(value) return math.floor(value + 0.5) end
LootObjects = {}
UpdateTimers = function() end

CurrentRun = {
  Hero = {
    ObjectId = 1,
    Health = 100,
    MaxHealth = 100,
    Mana = 50,
    MaxMana = 50,
    HealthBuffer = 0,
    Elements = {},
    Traits = {},
  },
  CurrentRoom = {},
  NumRerolls = 0,
  SpellCharge = 0,
}

local calls = {
  level = 0,
  rarity = 0,
  nativeRemove = 0,
  directRemove = 0,
  familiarRemove = 0,
  lastStandRemove = 0,
  familiarDestroy = 0,
  lifePips = 0,
  keepsakeUnequip = 0,
  keepsakeEquip = 0,
  traitNumber = 0,
  arcanaAdd = 0,
  validateHealth = 0,
  validateMana = 0,
  weaponAnim = 0,
  costumeSetup = 0,
}
local failLevelAfterMutation = false
local failFamiliarDestroyAfterMutation = false
local failKeepsakeUnequipAfterMutation = false
local failKeepsakeEquipAfterMutation = false
local failArcanaAddAfterMutation = false
local skipNativeRemoval = false
local skipDirectRemoval = false
local lastDirectRemoveArgs = nil

local rarityValue = {
  Common = 1,
  Rare = 2,
  Epic = 3,
  Heroic = 4,
}

local function removeMatching(predicate)
  local kept = {}
  for _, trait in ipairs(CurrentRun.Hero.Traits) do
    if not predicate(trait) then kept[#kept + 1] = trait end
  end
  CurrentRun.Hero.Traits = kept
end

IsGodTrait = function(name, args)
  return string.find(name or "", "Ordinary", 1, true) == 1
end

GetAllUpgradeableGodTraits = function()
  local result = {}
  for _, trait in ipairs(CurrentRun.Hero.Traits) do
    if string.find(trait.Name or "", "Ordinary", 1, true) == 1 and not trait.BlockStacking then
      result[trait.Name] = true
    end
  end
  return result
end

GetProcessedTraitData = function(args)
  local definition = TraitData and TraitData[args.TraitName] or {}
  local stack = args.StackNum or 1
  local value = definition.SyntheticStackEffect and (stack * 10) or 10
  return {
    Name = args.TraitName,
    StackNum = stack,
    Rarity = args.Rarity or "Common",
    ExtractData = { SyntheticValue = value },
  }
end

ExtractValues = function(unit, source, target)
  return target and target.ExtractData
end

IncreaseTraitLevel = function(trait, amount)
  calls.level = calls.level + 1
  trait.StackNum = (trait.StackNum or 1) + amount
  trait.EffectValue = (trait.EffectValue or 0) + 100 * amount
  if failLevelAfterMutation then
    failLevelAfterMutation = false
    error("synthetic post-mutation failure")
  end
  return trait
end

AddRarityToTraits = function(_, args)
  calls.rarity = calls.rarity + 1
  local trait = assert(args.ForceUpgrade and args.ForceUpgrade[1], "missing force-upgrade target")
  trait.Rarity = args.TargetRarityName
  trait.EffectValue = rarityValue[args.TargetRarityName] * 1000
  return trait
end

RemoveWeaponTrait = function(name, args)
  calls.nativeRemove = calls.nativeRemove + 1
  if not skipNativeRemoval then
    removeMatching(function(trait) return trait.Name == name end)
  end
end

local nextArcanaId = 9000
AddTraitToHero = function(args)
  calls.arcanaAdd = calls.arcanaAdd + 1
  nextArcanaId = nextArcanaId + 1
  local trait = {
    Name = args.TraitName,
    Id = nextArcanaId,
    StackNum = 1,
    Rarity = args.Rarity or "Common",
    EffectValue = rarityValue[args.Rarity or "Common"] * 1000,
    SourceName = args.SourceName,
    CustomMultiplier = args.CustomMultiplier,
  }
  table.insert(CurrentRun.Hero.Traits, trait)
  if failArcanaAddAfterMutation then
    failArcanaAddAfterMutation = false
    error("synthetic Arcana add acknowledgement failure")
  end
  return trait
end

RemoveTraitData = function(hero, target, args)
  calls.directRemove = calls.directRemove + 1
  lastDirectRemoveArgs = args
  if not skipDirectRemoval then
    removeMatching(function(trait) return trait == target end)
  end
end

RemoveTrait = function(hero, name)
  calls.familiarRemove = calls.familiarRemove + 1
  removeMatching(function(trait) return trait.Name == name end)
end

UnequipKeepsake = function(hero, name, args)
  calls.keepsakeUnequip = calls.keepsakeUnequip + 1
  removeMatching(function(trait) return trait.Name == name end)
  if name == "ReincarnationKeepsake" then
    RemoveLastStand(hero, "ReincarnationKeepsake")
    if hero.MaxLastStands and hero.MaxLastStands > 0 then
      hero.MaxLastStands = hero.MaxLastStands - 1
    end
  end
  if failKeepsakeUnequipAfterMutation then
    failKeepsakeUnequipAfterMutation = false
    error("synthetic Keepsake unequip acknowledgement failure")
  end
end

local nextKeepsakeId = 8000
EquipKeepsake = function(hero, name, args)
  args = args or {}
  calls.keepsakeEquip = calls.keepsakeEquip + 1
  nextKeepsakeId = nextKeepsakeId + 1
  local trait = {
    Name = name,
    Id = nextKeepsakeId,
    StackNum = 1,
    Rarity = args.ForceRarity or "Common",
    EffectValue = rarityValue[args.ForceRarity or "Common"] * 1000,
    DoorHealReserve = 999,
    CustomTrayText = "fresh",
  }
  table.insert(hero.Traits, trait)
  if name == "ReincarnationKeepsake" then
    hero.MaxLastStands = (hero.MaxLastStands or 0) + 1
  end
  if failKeepsakeEquipAfterMutation then
    failKeepsakeEquipAfterMutation = false
    error("synthetic Keepsake equip acknowledgement failure")
  end
  return trait
end

UpdateTraitNumber = function(trait)
  calls.traitNumber = calls.traitNumber + 1
end
ValidateMaxMana = function()
  calls.validateMana = calls.validateMana + 1
end
ValidateMaxHealth = function()
  calls.validateHealth = calls.validateHealth + 1
end
HandleWeaponAnimSwaps = function()
  calls.weaponAnim = calls.weaponAnim + 1
end
SetupCostume = function()
  calls.costumeSetup = calls.costumeSetup + 1
end
AddHealthBuffer = function() end
IsTraitActive = function() return true end

RemoveLastStand = function(hero, name)
  calls.lastStandRemove = calls.lastStandRemove + 1
end

UpdateLifePips = function(hero)
  calls.lifePips = calls.lifePips + 1
end

Destroy = function(args)
  calls.familiarDestroy = calls.familiarDestroy + 1
  if failFamiliarDestroyAfterMutation then
    failFamiliarDestroyAfterMutation = false
    error("synthetic Familiar destroy acknowledgement failure")
  end
end

FamiliarData = {
  CatFamiliar = {
    TraitNames = { "LastStandFamiliar", "FamiliarCatResourceBonus", "FamiliarCatAttacks" },
  },
  RavenFamiliar = {
    TraitNames = { "CritFamiliar", "FamiliarRavenResourceBonus", "FamiliarRavenAttackDuration" },
  },
}

TraitData = {}

local function defineRarities(name)
  TraitData[name] = {
    RarityLevels = {
      Common = {},
      Rare = {},
      Epic = {},
      Heroic = {},
    },
  }
end

for _, name in ipairs({
  "OrdinaryLevel",
  "OrdinaryRarity",
  "OrdinaryRemove",
  "OrdinaryDuplicate",
  "OrdinaryStale",
  "OrdinaryReplay",
  "OrdinaryOutcomeUnknown",
  "CritBonusBoon",
  "OmegaExplodeBoon",
  "DynamicDirectLevel",
  "DynamicDirectRarity",
  "DynamicDirectRemoval",
  "DynamicDirectOneShot",
  "DynamicDirectSetup",
}) do
  defineRarities(name)
end
TraitData.DynamicDirectLevel.SyntheticStackEffect = true
TraitData.DynamicDirectOneShot.SyntheticStackEffect = true
TraitData.DynamicDirectOneShot.AcquireFunctionName = "SyntheticOneShotAcquire"
TraitData.DynamicDirectSetup.SyntheticStackEffect = true
TraitData.DynamicDirectSetup.SetupFunction = {
  Name = "SyntheticExternalSetup",
  Args = {},
}
TraitData.DynamicIcarusArmor = {
  InheritFrom = { "BaseIcarus", "CostumeTrait" },
  Uses = 1,
  SetupFunctions = {
    {
      Name = "CostumeArmor",
      Args = { Source = "Icarus", BaseAmount = 40 },
    },
  },
}

for _, name in ipairs({
  "LastStandFamiliar",
  "FamiliarCatResourceBonus",
  "FamiliarCatAttacks",
  "CritFamiliar",
  "FamiliarRavenResourceBonus",
  "FamiliarRavenAttackDuration",
  "RestedFamiliarResourceBonus",
  "DoubleFamiliarTrait",
  "ReincarnationKeepsake",
  "BonusMoneyKeepsake",
  "DoorHealReserveKeepsake",
}) do
  TraitData[name] = TraitData[name] or {}
end
TraitData.ReincarnationKeepsake.InheritFrom = { "GiftTrait" }
TraitData.ReincarnationKeepsake.RarityLevels = { Common = {}, Rare = {}, Epic = {}, Heroic = {} }
TraitData.BonusMoneyKeepsake.InheritFrom = { "GiftTrait" }
TraitData.BonusMoneyKeepsake.RarityLevels = { Common = {}, Rare = {}, Epic = {} }
TraitData.DoorHealReserveKeepsake.InheritFrom = { "GiftTrait" }
TraitData.DoorHealReserveKeepsake.RarityLevels = { Common = {}, Rare = {}, Epic = {}, Heroic = {} }

for _, name in ipairs({
  "LowManaDamageMetaupgrade",
  "HealthManaBonusMetaUpgrade",
  "DoorRerollMetaUpgrade",
  "BossShieldMetaUpgrade",
  "UnownedMetaUpgradeTrait",
}) do
  TraitData[name] = {
    InheritFrom = { "MetaUpgradeTrait" },
    RarityLevels = { Common = {}, Rare = {}, Epic = {}, Heroic = {} },
  }
end
TraitData.DoorRerollMetaUpgrade.RerollCount = { BaseValue = 1 }
TraitData.BossShieldMetaUpgrade.BossEncounterShieldHits = { BaseValue = 1 }

dofile(runtimePath)
local M = assert(__MacGamingTrainerV1, "resident runtime did not initialize")
-- Route every dispatch through the production JSON boundary.
dofile(contractPath)
M.session = SessionState
M.run = CurrentRun
M.hero = CurrentRun.Hero

local function fail(message)
  error("ASSERTION FAILED: " .. message, 0)
end

local function check(condition, message)
  if not condition then fail(message) end
end

local function eq(actual, expected, message)
  if actual ~= expected then
    fail(message .. ": expected=" .. tostring(expected) .. " actual=" .. tostring(actual))
  end
end

local function contains(text, needle)
  return string.find(tostring(text), needle, 1, true) ~= nil
end

local function expectError(needle, fn)
  local ok, message = pcall(fn)
  if ok then fail("expected error containing: " .. needle) end
  if not contains(message, needle) then
    fail("wrong error; expected '" .. needle .. "', got '" .. tostring(message) .. "'")
  end
end

local function setTraits(...)
  CurrentRun.Hero.Traits = { ... }
end

local function newTrait(name, id, level, rarity, extra)
  local trait = {
    Name = name,
    Id = id,
    StackNum = level or 1,
    Rarity = rarity or "Common",
    EffectValue = 0,
  }
  if extra then
    for key, value in pairs(extra) do trait[key] = value end
  end
  return trait
end

local function status()
  return M.dispatch("status", { includeCatalogs = false })
end

local function maybeFindRow(name, instanceId)
  for _, row in ipairs(status().currentRunTraits or {}) do
    if row.name == name and (instanceId == nil or row.instanceId == tostring(instanceId)) then
      return row
    end
  end
  return nil
end

local function findRow(name, instanceId)
  local row = maybeFindRow(name, instanceId)
  if row ~= nil then return row end
  fail("missing observed trait row " .. tostring(name) .. "/" .. tostring(instanceId))
end

local function findMountedTrait(name)
  for _, trait in ipairs(CurrentRun.Hero.Traits or {}) do
    if type(trait) == "table" and trait.Name == name then return trait end
  end
  fail("missing mounted trait " .. tostring(name))
end

local function paramsFrom(row, requestId, targetLevel)
  local params = {
    requestId = requestId,
    generationId = row.generationId,
    runId = row.runId,
    instanceId = row.instanceId,
    trait = row.name,
    family = row.family,
    expectedLevel = row.level,
    expectedRarity = row.rarity,
    expectedSameNameCount = row.sameNameCount,
    includeCatalogs = false,
  }
  if targetLevel ~= nil then params.targetLevel = targetLevel end
  return params
end

-- Native Pom-eligible level change: execute the resident command and verify
-- the game-owned callback changed both observed level and an effect sentinel.
do
  local trait = newTrait("OrdinaryLevel", 101, 1, "Rare")
  setTraits(trait)
  local row = findRow("OrdinaryLevel", 101)
  eq(row.family, "olympianHermes", "ordinary level family")
  eq(row.levelCapability, "increaseOne", "ordinary level capability")
  local beforeCalls = calls.level
  local result = M.dispatch("set_trait_level", paramsFrom(row, "native-level", 4))
  eq(calls.level, beforeCalls + 1, "native level callback count")
  eq(trait.StackNum, 4, "native target-level mutation")
  eq(trait.EffectValue, 300, "native target-level effect recomputation")
  eq(result.currentRunTraits[1].level, 4, "native target-level observed result")
  eq(result.actionOutcome, "completed", "native level receipt")
end

-- A normal God boon may use CostumeTrait as an implementation detail (for
-- example Hephaestus armor). Native sell/Pom ownership must win over that
-- inheritance marker so ordinary management capabilities are not stolen by the
-- special-costume lifecycle.
do
  local trait = newTrait("OrdinaryArmorBoon", 151, 1, "Rare", {
    InheritFrom = { "CostumeTrait" },
  })
  defineRarities("OrdinaryArmorBoon")
  setTraits(trait)
  local row = findRow("OrdinaryArmorBoon", 151)
  eq(row.family, "olympianHermes", "ordinary CostumeTrait boon owner family")
  eq(row.levelCapability, "increaseOne", "ordinary CostumeTrait level capability")
  eq(row.rarityCapability, "setExact", "ordinary CostumeTrait rarity capability")
  eq(row.removalCapability, "nameLevelAllMatching", "ordinary CostumeTrait removal capability")
end

-- Artemis direct example: native Pom eligibility deliberately says false, so
-- this proves the bounded direct strategy rather than a widened native gate.
do
  local trait = newTrait("CritBonusBoon", 201, 1, "Rare")
  setTraits(trait)
  local row = findRow("CritBonusBoon", 201)
  eq(row.family, "directSpecial", "Artemis direct family")
  eq(row.levelCapability, "increaseOne", "Artemis direct level capability")
  check(GetAllUpgradeableGodTraits(1)[trait.Name] ~= true, "Artemis unexpectedly native-Pom eligible")
  M.dispatch("set_trait_level", paramsFrom(row, "direct-level", 3))
  eq(trait.StackNum, 3, "direct target-level mutation")
  eq(trait.EffectValue, 200, "direct target-level effect mutation")
end

-- Direct special ownership/capability is derived from the current native NPC
-- source, not from a hardcoded trait allowlist. A stack edit is exposed only
-- when processing the next StackNum changes an extracted effect value.
do
  local trait = newTrait("DynamicDirectLevel", 251, 1, "Rare")
  setTraits(trait)
  local row = findRow("DynamicDirectLevel", 251)
  eq(row.family, "directSpecial", "dynamic direct-special family")
  eq(row.sourceId, "Artemis", "dynamic direct-special source")
  eq(row.levelCapability, "increaseOne", "dynamic direct-special level capability")
  local before = calls.level
  M.dispatch("set_trait_level", paramsFrom(row, "dynamic-direct-level", 3))
  eq(calls.level, before + 1, "dynamic direct-special level callback")
  eq(trait.StackNum, 3, "dynamic direct-special target level")
end

-- Exact rarity for direct special traits is also derived from current native
-- ownership and the trait's real rarity model rather than a hardcoded strategy.
do
  local trait = newTrait("DynamicDirectRarity", 275, 1, "Common")
  setTraits(trait)
  local row = findRow("DynamicDirectRarity", 275)
  eq(row.family, "directSpecial", "dynamic direct rarity family")
  eq(row.rarityCapability, "setExact", "dynamic direct rarity capability")
  local params = paramsFrom(row, "dynamic-direct-rarity")
  params.rarity = "Epic"
  local before = calls.rarity
  M.dispatch("set_trait_rarity", params)
  eq(calls.rarity, before + 1, "dynamic direct rarity recompute callback")
  eq(trait.Rarity, "Epic", "dynamic direct rarity target")
  eq(trait.EffectValue, 3000, "dynamic direct rarity effect recomputation")
end

-- Native rarity change must run the game recomputation callback rather than
-- assigning only the displayed rarity field.
do
  local trait = newTrait("OrdinaryRarity", 301, 1, "Common")
  setTraits(trait)
  local row = findRow("OrdinaryRarity", 301)
  eq(row.rarityCapability, "setExact", "ordinary rarity capability")
  local params = paramsFrom(row, "native-rarity")
  params.rarity = "Epic"
  local beforeCalls = calls.rarity
  local result = M.dispatch("set_trait_rarity", params)
  eq(calls.rarity, beforeCalls + 1, "native rarity recompute count")
  eq(trait.Rarity, "Epic", "native rarity mutation")
  eq(trait.EffectValue, 3000, "native rarity effect recomputation")
  eq(result.currentRunTraits[1].rarity, "Epic", "native rarity observed result")
end

-- Icarus direct rarity is intentionally not shop/native eligible and still
-- follows AddRarityToTraits so mounted effect values are recomputed.
do
  local trait = newTrait("OmegaExplodeBoon", 401, 1, "Common")
  setTraits(trait)
  local row = findRow("OmegaExplodeBoon", 401)
  eq(row.family, "directSpecial", "Icarus direct family")
  eq(row.rarityCapability, "setExact", "Icarus direct rarity capability")
  check(not IsGodTrait(trait.Name, { ForShop = true }), "Icarus unexpectedly native-shop eligible")
  local params = paramsFrom(row, "direct-rarity")
  params.rarity = "Heroic"
  M.dispatch("set_trait_rarity", params)
  eq(trait.Rarity, "Heroic", "direct rarity mutation")
  eq(trait.EffectValue, 4000, "direct rarity effect recomputation")
end

-- A direct special whose runtime ownership is fully trait-local can be force
-- removed as one exact instance even though native SellTraits rejects it.
do
  local first = newTrait("DynamicDirectRemoval", 451, 1, "Rare")
  local second = newTrait("DynamicDirectRemoval", 452, 1, "Rare")
  setTraits(first, second)
  local row = findRow("DynamicDirectRemoval", 451)
  eq(row.family, "directSpecial", "dynamic direct removal family")
  eq(row.removalCapability, "singleInstanceForce", "dynamic direct removal capability")
  check(row.removalScopeAllMatching == false, "dynamic direct removal widened scope")
  local before = calls.directRemove
  M.dispatch("remove_trait", paramsFrom(row, "dynamic-direct-remove"))
  eq(calls.directRemove, before + 1, "dynamic direct removal callback")
  eq(#CurrentRun.Hero.Traits, 1, "dynamic direct removal removed wrong count")
  eq(CurrentRun.Hero.Traits[1].Id, 452, "dynamic direct removal removed wrong instance")
  check(lastDirectRemoveArgs and lastDirectRemoveArgs.SkipExpire == true,
    "dynamic direct removal did not suppress expiration")
end

-- Icarus armor/coating traits are direct-special owned but carry a native
-- CostumeArmor setup lifecycle. They are not generic declarative rows: removal
-- must perform exact RemoveTraitData teardown and then refresh costume owner
-- presentation/state instead of silently disabling the operation.
do
  local trait = newTrait("DynamicIcarusArmor", 475, 1, "Common", {
    InheritFrom = { "BaseIcarus", "CostumeTrait" },
    Uses = 1,
    SetupFunctions = {
      {
        Name = "CostumeArmor",
        Args = { Source = "Icarus", BaseAmount = 40 },
      },
    },
    CurrentArmor = 40,
  })
  setTraits(trait)
  local row = findRow("DynamicIcarusArmor", 475)
  eq(row.family, "directSpecial", "Icarus armor owner family")
  eq(row.levelCapability, "none", "Icarus armor exposed generic level editing")
  eq(row.rarityCapability, "none", "Icarus armor exposed generic rarity editing")
  eq(row.removalCapability, "singleInstanceForce", "Icarus armor removal capability")
  local beforeRemove = calls.directRemove
  local beforeSetup = calls.costumeSetup
  M.dispatch("remove_trait", paramsFrom(row, "icarus-armor-remove"))
  eq(calls.directRemove, beforeRemove + 1, "Icarus armor teardown callback")
  eq(calls.costumeSetup, beforeSetup + 1, "Icarus armor costume refresh")
  eq(#CurrentRun.Hero.Traits, 0, "Icarus armor remained mounted")
  check(lastDirectRemoveArgs and lastDirectRemoveArgs.SkipExpire == true,
    "Icarus armor removal did not suppress expiration")
end

-- Native SellTraits-equivalent removal is explicitly name-level/all-matching.
do
  local first = newTrait("OrdinaryRemove", 501, 1, "Rare")
  local second = newTrait("OrdinaryRemove", 502, 1, "Rare")
  setTraits(first, second)
  local row = findRow("OrdinaryRemove", 501)
  eq(row.sameNameCount, 2, "native removal duplicate count")
  eq(row.removalCapability, "nameLevelAllMatching", "native removal capability")
  check(row.removalScopeAllMatching == true, "native removal scope not explicit")
  local beforeCalls = calls.nativeRemove
  local result = M.dispatch("remove_trait", paramsFrom(row, "native-remove"))
  eq(calls.nativeRemove, beforeCalls + 1, "native removal callback count")
  eq(#CurrentRun.Hero.Traits, 0, "native removal did not clean every same-name instance")
  eq(#result.currentRunTraits, 0, "native removal observed inventory not empty")
end

-- Direct Icarus removal is single-instance and executes RemoveTraitData cleanup
-- with SkipExpire so no one-shot expiration/reward path is replayed.
do
  local first = newTrait("OmegaExplodeBoon", 601, 1, "Rare")
  local second = newTrait("OmegaExplodeBoon", 602, 1, "Rare")
  setTraits(first, second)
  local row = findRow("OmegaExplodeBoon", 601)
  eq(row.sameNameCount, 2, "direct removal duplicate count")
  eq(row.removalCapability, "singleInstanceForce", "direct removal capability")
  check(row.removalScopeAllMatching == false, "direct removal scope widened")
  local beforeCalls = calls.directRemove
  M.dispatch("remove_trait", paramsFrom(row, "direct-remove"))
  eq(calls.directRemove, beforeCalls + 1, "direct removal callback count")
  eq(#CurrentRun.Hero.Traits, 1, "direct removal removed wrong number of instances")
  eq(CurrentRun.Hero.Traits[1].Id, 602, "direct removal removed wrong instance")
  check(lastDirectRemoveArgs and lastDirectRemoveArgs.SkipExpire == true, "direct removal did not suppress expiration path")
end

-- Identical-name instances are deliberately ambiguous for object-sensitive
-- level/rarity operations; the runtime must fail before calling the mutator.
do
  local first = newTrait("OrdinaryDuplicate", 701, 1, "Rare")
  local second = newTrait("OrdinaryDuplicate", 702, 1, "Rare")
  setTraits(first, second)
  local row = findRow("OrdinaryDuplicate", 701)
  eq(row.levelCapability, "none", "duplicate-name level capability")
  eq(row.rarityCapability, "none", "duplicate-name rarity capability")
  local beforeLevel = calls.level
  expectError("Trait level editing is unavailable", function()
    M.dispatch("set_trait_level", paramsFrom(row, "duplicate-level", row.level + 1))
  end)
  eq(calls.level, beforeLevel, "duplicate-name level reached mutator")
end

-- Stale generation/run/changed target snapshots are rejected during preflight,
-- before any game-owned mutation callback is reached.
do
  local trait = newTrait("OrdinaryStale", 801, 1, "Rare")
  setTraits(trait)
  local row = findRow("OrdinaryStale", 801)
  local beforeLevel = calls.level

  local staleGeneration = paramsFrom(row, "stale-generation", row.level + 1)
  staleGeneration.generationId = "old-generation"
  expectError("stale runtime generation", function()
    M.dispatch("set_trait_level", staleGeneration)
  end)

  local staleRun = paramsFrom(row, "stale-run", row.level + 1)
  staleRun.runId = "old-run"
  expectError("stale run", function()
    M.dispatch("set_trait_level", staleRun)
  end)

  local changed = paramsFrom(row, "changed-target", row.level + 1)
  trait.StackNum = 2
  expectError("Trait target changed since selection", function()
    M.dispatch("set_trait_level", changed)
  end)
  eq(calls.level, beforeLevel, "stale target reached level mutator")
end

-- Completed request IDs deduplicate before stale-target revalidation. The live
-- target has changed after the first mutation, but retry returns the receipt and
-- never applies the non-idempotent operation twice.
do
  local trait = newTrait("OrdinaryReplay", 901, 1, "Rare")
  setTraits(trait)
  local row = findRow("OrdinaryReplay", 901)
  local params = paramsFrom(row, "dedup-level", row.level + 1)
  local beforeLevel = calls.level
  local first = M.dispatch("set_trait_level", params)
  local second = M.dispatch("set_trait_level", params)
  eq(calls.level, beforeLevel + 1, "completed request replayed mutation")
  check(first.duplicate == false, "first request marked duplicate")
  check(second.duplicate == true, "duplicate request not identified")
  eq(second.actionOutcome, "completed", "duplicate receipt lost outcome")
end

-- A post-mutation exception makes the result outcome-unknown. Reissuing the
-- same request ID must fail before mutation even though the first call already
-- changed the live object.
do
  local trait = newTrait("OrdinaryOutcomeUnknown", 1001, 1, "Rare")
  setTraits(trait)
  local row = findRow("OrdinaryOutcomeUnknown", 1001)
  local params = paramsFrom(row, "unknown-level", row.level + 1)
  local beforeLevel = calls.level
  failLevelAfterMutation = true
  expectError("MGT_OUTCOME_UNKNOWN", function()
    M.dispatch("set_trait_level", params)
  end)
  eq(calls.level, beforeLevel + 1, "outcome-unknown mutation did not execute once")
  eq(trait.StackNum, 2, "outcome-unknown sentinel did not model applied mutation")
  expectError("Previous action outcome is unknown; do not retry", function()
    M.dispatch("set_trait_level", params)
  end)
  eq(calls.level, beforeLevel + 1, "outcome-unknown request auto-replayed")
end

-- The runtime verifies removal cleanup instead of trusting the callback return.
do
  local trait = newTrait("OmegaExplodeBoon", 1101, 1, "Rare")
  setTraits(trait)
  local row = findRow("OmegaExplodeBoon", 1101)
  local beforeRemove = calls.directRemove
  skipDirectRemoval = true
  expectError("MGT_OUTCOME_UNKNOWN", function()
    M.dispatch("remove_trait", paramsFrom(row, "direct-cleanup-failure"))
  end)
  skipDirectRemoval = false
  eq(calls.directRemove, beforeRemove + 1, "direct cleanup callback count")
  eq(#CurrentRun.Hero.Traits, 1, "cleanup-failure fixture unexpectedly removed trait")
end

-- Direct strategies with acquisition/expiration lifecycle markers fail closed;
-- changing level must not rerun or bypass those one-shot paths.
do
  local trait = newTrait("CritBonusBoon", 1201, 1, "Rare", {
    AcquireFunctionName = "SyntheticOneShotAcquire",
  })
  setTraits(trait)
  local row = findRow("CritBonusBoon", 1201)
  eq(row.levelCapability, "none", "unsafe direct lifecycle exposed level mutation")
  local beforeLevel = calls.level
  expectError("Trait level editing is unavailable", function()
    M.dispatch("set_trait_level", paramsFrom(row, "unsafe-direct-level", row.level + 1))
  end)
  eq(calls.level, beforeLevel, "unsafe direct lifecycle reached level mutator")
end

-- A one-shot acquisition trait without the game's own level/rarity
-- reconciliation callback must not expose edits that only change the mounted
-- row while leaving the already-granted external reward stale.
do
  local trait = newTrait("DynamicDirectOneShot", 1251, 1, "Rare")
  setTraits(trait)
  local row = findRow("DynamicDirectOneShot", 1251)
  eq(row.family, "directSpecial", "one-shot direct-special family")
  eq(row.levelCapability, "none", "one-shot direct-special level capability")
  eq(row.rarityCapability, "none", "one-shot direct-special rarity capability")
  eq(row.removalCapability, "none", "one-shot direct-special removal capability")
end

-- Unsupported setup ownership is an explicit not-applicable disposition,
-- not a deferred #239 bucket. Safe declarative and one-shot rows likewise have
-- complete supported/not-applicable capability results with no residual issue.
do
  local setupTrait = newTrait("DynamicDirectSetup", 1275, 1, "Rare", {
    SetupFunction = { Name = "SyntheticExternalSetup", Args = {} },
  })
  setTraits(setupTrait)
  local setupRow = findRow("DynamicDirectSetup", 1275)
  eq(setupRow.family, "directSpecial", "setup direct-special family")
  eq(setupRow.levelCapability, "none", "setup direct-special level capability")
  eq(setupRow.rarityCapability, "none", "setup direct-special rarity capability")
  eq(setupRow.removalCapability, "none", "setup direct-special removal capability")
  eq(setupRow.deferredIssue, nil, "setup direct-special remained deferred")

  local declarative = newTrait("DynamicDirectRemoval", 1276, 1, "Rare")
  setTraits(declarative)
  eq(findRow("DynamicDirectRemoval", 1276).deferredIssue, nil,
    "safe direct-special remained deferred")

  local oneShot = newTrait("DynamicDirectOneShot", 1277, 1, "Rare", {
    AcquireFunctionName = "SyntheticOneShotAcquire",
  })
  setTraits(oneShot)
  eq(findRow("DynamicDirectOneShot", 1277).deferredIssue, nil,
    "one-shot direct-special remained deferred")
end

-- Familiar ownership comes from the equipped Familiar's declared trait bundle,
-- not from a substring match. A Circe trait whose ID happens to contain
-- "Familiar" is not re-owned by the Familiar lifecycle.
do
  GameState.EquippedFamiliar = "RavenFamiliar"
  MapState.FamiliarUnit = { Name = "RavenFamiliar", ObjectId = 7001 }
  local primary = newTrait("CritFamiliar", 1301, 1, nil)
  local resource = newTrait("FamiliarRavenResourceBonus", 1302, 1, nil)
  local duration = newTrait("FamiliarRavenAttackDuration", 1303, 1, nil)
  local circe = newTrait("DoubleFamiliarTrait", 1304, 1, nil)
  local rested = newTrait("RestedFamiliarResourceBonus", 1305, 1, nil)
  setTraits(primary, resource, duration, circe, rested)

  local row = findRow("CritFamiliar", 1301)
  eq(row.family, "familiar", "equipped Familiar primary family")
  eq(row.levelCapability, "increaseOne", "Familiar primary level capability")
  eq(row.rarityCapability, "none", "Familiar fabricated rarity capability")
  eq(row.removalCapability, "singleInstanceForce", "Familiar owner removal capability")
  check(findRow("DoubleFamiliarTrait", 1304).family ~= "familiar", "substring trait stolen by Familiar owner")
  local restedRow = findRow("RestedFamiliarResourceBonus", 1305)
  eq(restedRow.family, "familiar", "rested bonus owner family")
  eq(restedRow.levelCapability, "none", "rested bonus fabricated level editing")

  local beforeLevel = calls.level
  M.dispatch("set_trait_level", paramsFrom(row, "familiar-level", 3))
  eq(calls.level, beforeLevel + 1, "Familiar level did not use native trait recomputation")
  eq(primary.StackNum, 3, "Familiar target level")
  eq(primary.EffectValue, 200, "Familiar level did not recompute effect sentinel")

  -- The owner survives a room object transition and remains manageable.
  CurrentRun.CurrentRoom = { Name = "B_TestRoom" }
  local roomRow = findRow("CritFamiliar", 1301)
  M.dispatch("set_trait_level", paramsFrom(roomRow, "familiar-room-level", 4))
  eq(primary.StackNum, 4, "Familiar level failed after room transition")

  -- Replacing the native owner invalidates the old observed selection before
  -- any mutator can touch the no-longer-owned Raven trait.
  local staleOwnerRow = findRow("CritFamiliar", 1301)
  local beforeStaleLevel = calls.level
  GameState.EquippedFamiliar = "CatFamiliar"
  MapState.FamiliarUnit = { Name = "CatFamiliar", ObjectId = 7002 }
  expectError("Trait target changed since selection", function()
    M.dispatch("set_trait_level", paramsFrom(staleOwnerRow, "familiar-owner-stale", 5))
  end)
  eq(calls.level, beforeStaleLevel, "stale Familiar owner reached level mutator")
  GameState.EquippedFamiliar = "RavenFamiliar"
  MapState.FamiliarUnit = { Name = "RavenFamiliar", ObjectId = 7001 }

  -- Trainer-wide cleanup is not an implicit undo/unequip path for game-owned
  -- Familiar state.
  M.dispatch("disable_all", { includeCatalogs = false })
  eq(GameState.EquippedFamiliar, "RavenFamiliar", "disable_all unequipped Familiar owner")
  check(MapState.FamiliarUnit ~= nil, "disable_all cleared live Familiar unit")
  check(findRow("CritFamiliar", 1301).family == "familiar", "disable_all removed Familiar runtime state")
end

-- Removing any mounted member of the owner bundle tears down the equipped
-- Familiar runtime owner as one unit while leaving durable unlock/upgrades
-- untouched. Cat/Toula additionally owns a Last Stand entry.
do
  GameState.EquippedFamiliar = "CatFamiliar"
  MapState.FamiliarUnit = { Name = "CatFamiliar", ObjectId = 7101 }
  CurrentRun.Hero.MaxLastStands = 2
  local primary = newTrait("LastStandFamiliar", 1401, 1, nil)
  local resource = newTrait("FamiliarCatResourceBonus", 1402, 1, nil)
  local attacks = newTrait("FamiliarCatAttacks", 1403, 1, nil)
  local unrelated = newTrait("DoubleFamiliarTrait", 1404, 1, nil)
  setTraits(primary, resource, attacks, unrelated)

  local row = findRow("FamiliarCatAttacks", 1403)
  eq(row.family, "familiar", "Familiar helper owner family")
  local beforeUnlock = GameState.FamiliarsUnlocked.CatFamiliar
  local beforeUpgrade = GameState.FamiliarUpgrades.PersistentCatUpgrade
  local beforeLastStand = calls.lastStandRemove
  local beforeDestroy = calls.familiarDestroy
  local result = M.dispatch("remove_trait", paramsFrom(row, "familiar-owner-remove"))

  check(GameState.EquippedFamiliar == nil, "Familiar owner remained equipped")
  check(MapState.FamiliarUnit == nil, "live Familiar owner remained mounted")
  eq(calls.lastStandRemove, beforeLastStand + 1, "Cat Familiar Last Stand not removed")
  eq(calls.familiarDestroy, beforeDestroy + 1, "live Familiar entity not cleaned")
  eq(CurrentRun.Hero.MaxLastStands, 1, "Cat Familiar MaxLastStands not restored")
  eq(#CurrentRun.Hero.Traits, 1, "Familiar owner teardown did not remove exactly its bundle")
  eq(CurrentRun.Hero.Traits[1].Name, "DoubleFamiliarTrait", "Familiar teardown removed unrelated trait")
  eq(GameState.FamiliarsUnlocked.CatFamiliar, beforeUnlock, "Familiar unlock ownership mutated")
  eq(GameState.FamiliarUpgrades.PersistentCatUpgrade, beforeUpgrade, "Familiar durable upgrade mutated")
  eq(#result.currentRunTraits, 1, "post-teardown observed inventory mismatch")

  local removeCalls = calls.familiarRemove
  local duplicate = M.dispatch("remove_trait", paramsFrom(row, "familiar-owner-remove"))
  check(duplicate.duplicate == true, "Familiar owner teardown replay not deduplicated")
  eq(calls.familiarRemove, removeCalls, "Familiar owner teardown replayed mutation")
end

-- A post-mutation failure still finishes the distinct owner cleanup steps so
-- runtime ownership is coherent, then reports outcome-unknown. The same request
-- can never replay the non-idempotent teardown.
do
  GameState.EquippedFamiliar = "RavenFamiliar"
  MapState.FamiliarUnit = { Name = "RavenFamiliar", ObjectId = 7201 }
  local primary = newTrait("CritFamiliar", 1501, 1, nil)
  local resource = newTrait("FamiliarRavenResourceBonus", 1502, 1, nil)
  local duration = newTrait("FamiliarRavenAttackDuration", 1503, 1, nil)
  setTraits(primary, resource, duration)

  local row = findRow("CritFamiliar", 1501)
  local params = paramsFrom(row, "familiar-owner-unknown")
  local beforeDestroy = calls.familiarDestroy
  local beforeRemove = calls.familiarRemove
  failFamiliarDestroyAfterMutation = true
  expectError("MGT_OUTCOME_UNKNOWN", function()
    M.dispatch("remove_trait", params)
  end)
  eq(GameState.EquippedFamiliar, nil, "outcome-unknown left Familiar equipped")
  eq(MapState.FamiliarUnit, nil, "outcome-unknown left live Familiar pointer")
  eq(#CurrentRun.Hero.Traits, 0, "outcome-unknown left Familiar traits mounted")
  eq(calls.familiarDestroy, beforeDestroy + 1, "outcome-unknown destroy call count")
  check(calls.familiarRemove > beforeRemove, "outcome-unknown skipped trait teardown")

  local removeAfterUnknown = calls.familiarRemove
  local destroyAfterUnknown = calls.familiarDestroy
  expectError("Previous action outcome is unknown; do not retry", function()
    M.dispatch("remove_trait", params)
  end)
  eq(calls.familiarRemove, removeAfterUnknown, "outcome-unknown Familiar request replayed trait teardown")
  eq(calls.familiarDestroy, destroyAfterUnknown, "outcome-unknown Familiar request replayed entity teardown")
end

-- Keepsake ownership is the selected native LastAwardTrait, not GiftTrait
-- inheritance. Runtime force removal delegates to UnequipKeepsake and leaves
-- permanent Keepsake progression untouched.
do
  GameState.LastAwardTrait = "ReincarnationKeepsake"
  CurrentRun.Hero.MaxLastStands = 2
  local selected = newTrait("ReincarnationKeepsake", 1601, 1, "Rare")
  local unselected = newTrait("BonusMoneyKeepsake", 1602, 1, "Epic")
  setTraits(selected, unselected)

  local row = findRow("ReincarnationKeepsake", 1601)
  eq(row.family, "keepsake", "selected Keepsake owner family")
  eq(row.removalCapability, "singleInstanceForce", "Keepsake removal capability")
  eq(row.levelCapability, "none", "Keepsake fabricated stack-level editing")
  eq(row.rarityCapability, "setExact", "Keepsake runtime rank capability")
  check(findRow("BonusMoneyKeepsake", 1602).family ~= "keepsake", "unselected GiftTrait stolen by Keepsake owner")

  -- Room changes do not change the selected owner.
  CurrentRun.CurrentRoom = { Name = "C_TestRoom" }
  eq(findRow("ReincarnationKeepsake", 1601).family, "keepsake", "Keepsake owner lost across room transition")

  -- Global trainer cleanup must not silently unequip game-owned Keepsake state.
  M.dispatch("disable_all", { includeCatalogs = false })
  eq(GameState.LastAwardTrait, "ReincarnationKeepsake", "disable_all changed selected Keepsake")
  check(findRow("ReincarnationKeepsake", 1601) ~= nil, "disable_all removed Keepsake")

  -- Native owner replacement invalidates the old observed row before teardown.
  local staleRow = findRow("ReincarnationKeepsake", 1601)
  local beforeStaleUnequip = calls.keepsakeUnequip
  GameState.LastAwardTrait = "BonusMoneyKeepsake"
  expectError("Trait target changed since selection", function()
    M.dispatch("remove_trait", paramsFrom(staleRow, "keepsake-stale-owner"))
  end)
  eq(calls.keepsakeUnequip, beforeStaleUnequip, "stale Keepsake owner reached native teardown")
  GameState.LastAwardTrait = "ReincarnationKeepsake"

  local progressBefore = GameState.KeepsakeChambers.ReincarnationKeepsake
  local beforeUnequip = calls.keepsakeUnequip
  local result = M.dispatch("remove_trait", paramsFrom(findRow("ReincarnationKeepsake", 1601), "keepsake-remove"))
  eq(calls.keepsakeUnequip, beforeUnequip + 1, "Keepsake removal did not use native owner teardown")
  check(maybeFindRow("ReincarnationKeepsake", 1601) == nil, "Keepsake owner remained mounted")
  eq(GameState.LastAwardTrait, "ReincarnationKeepsake", "runtime Keepsake removal rewrote selected durable owner")
  eq(GameState.KeepsakeChambers.ReincarnationKeepsake, progressBefore, "runtime Keepsake removal changed progression")
  eq(CurrentRun.Hero.MaxLastStands, 1, "Keepsake native teardown did not remove linked Last Stand")
  check(findRow("BonusMoneyKeepsake", 1602) ~= nil, "Keepsake teardown removed unrelated GiftTrait")

  local duplicateUnequip = calls.keepsakeUnequip
  local duplicate = M.dispatch("remove_trait", paramsFrom(row, "keepsake-remove"))
  check(duplicate.duplicate == true, "Keepsake removal replay not deduplicated")
  eq(calls.keepsakeUnequip, duplicateUnequip, "Keepsake removal replayed native teardown")
  check(result.actionOutcome == "completed", "Keepsake removal outcome")
end

-- Late native acknowledgement is outcome-unknown and never replayed. The
-- selected durable owner/progression remain game-owned while the current-run
-- trait stays removed.
do
  GameState.LastAwardTrait = "ReincarnationKeepsake"
  CurrentRun.Hero.MaxLastStands = 2
  local selected = newTrait("ReincarnationKeepsake", 1701, 1, "Rare")
  setTraits(selected)
  local row = findRow("ReincarnationKeepsake", 1701)
  local params = paramsFrom(row, "keepsake-remove-unknown")
  local progressBefore = GameState.KeepsakeChambers.ReincarnationKeepsake
  failKeepsakeUnequipAfterMutation = true
  expectError("MGT_OUTCOME_UNKNOWN", function()
    M.dispatch("remove_trait", params)
  end)
  check(maybeFindRow("ReincarnationKeepsake", 1701) == nil, "unknown Keepsake teardown left trait mounted")
  eq(GameState.LastAwardTrait, "ReincarnationKeepsake", "unknown Keepsake teardown rewrote durable selection")
  eq(GameState.KeepsakeChambers.ReincarnationKeepsake, progressBefore, "unknown Keepsake teardown changed progression")
  local afterUnknown = calls.keepsakeUnequip
  expectError("Previous action outcome is unknown; do not retry", function()
    M.dispatch("remove_trait", params)
  end)
  eq(calls.keepsakeUnequip, afterUnknown, "unknown Keepsake teardown replayed")
end

-- Keepsake rank is the runtime rarity model. Exact rank override rebuilds the
-- selected owner through native Unequip/Equip semantics while durable chamber
-- progression and selection remain untouched.
do
  GameState.LastAwardTrait = "ReincarnationKeepsake"
  GameState.KeepsakeChambers.ReincarnationKeepsake = 42
  CurrentRun.Hero.MaxLastStands = 2
  local selected = newTrait("ReincarnationKeepsake", 1801, 1, "Rare", {
    CustomTrayText = "spent-state",
  })
  setTraits(selected)
  CurrentRun.CurrentRoom = { Name = "D_TestRoom" }
  local row = findRow("ReincarnationKeepsake", 1801)
  eq(row.levelCapability, "none", "Keepsake fabricated StackNum level editing")
  eq(row.rarityCapability, "setExact", "Keepsake rank override unavailable")
  local progressBefore = GameState.KeepsakeChambers.ReincarnationKeepsake
  local beforeUnequip = calls.keepsakeUnequip
  local beforeEquip = calls.keepsakeEquip
  local params = paramsFrom(row, "keepsake-rank")
  params.rarity = "Epic"
  local result = M.dispatch("set_trait_rarity", params)
  eq(calls.keepsakeUnequip, beforeUnequip + 1, "Keepsake rank did not use native unequip")
  eq(calls.keepsakeEquip, beforeEquip + 1, "Keepsake rank did not use native equip")
  eq(GameState.LastAwardTrait, "ReincarnationKeepsake", "Keepsake rank rewrote selected owner")
  eq(GameState.KeepsakeChambers.ReincarnationKeepsake, progressBefore, "Keepsake rank advanced durable progression")
  eq(CurrentRun.Hero.MaxLastStands, 2, "Keepsake rank duplicated or lost Last Stand ownership")
  local rebuilt = findRow("ReincarnationKeepsake")
  eq(rebuilt.rarity, "Epic", "Keepsake rank did not reach target rarity")
  eq(result.actionOutcome, "completed", "Keepsake rank outcome")

  CurrentRun.CurrentRoom = { Name = "E_TestRoom" }
  eq(findRow("ReincarnationKeepsake").rarity, "Epic", "Keepsake rank lost across room transition")

  local unequipAfter = calls.keepsakeUnequip
  local equipAfter = calls.keepsakeEquip
  local duplicate = M.dispatch("set_trait_rarity", params)
  check(duplicate.duplicate == true, "Keepsake rank replay was not deduplicated")
  eq(calls.keepsakeUnequip, unequipAfter, "Keepsake rank replayed native unequip")
  eq(calls.keepsakeEquip, equipAfter, "Keepsake rank replayed native equip")

  M.dispatch("disable_all", { includeCatalogs = false })
  eq(findRow("ReincarnationKeepsake").rarity, "Epic", "disable_all reverted game-owned Keepsake rank")
end

-- Native Keepsake rebuild preserves the same explicit runtime fields that
-- AdvanceKeepsake preserves. A forced rank must not reset partially consumed
-- owner state such as Charon's DoorHealReserve.
do
  GameState.LastAwardTrait = "DoorHealReserveKeepsake"
  GameState.KeepsakeChambers.DoorHealReserveKeepsake = 19
  local selected = newTrait("DoorHealReserveKeepsake", 1901, 1, "Rare", {
    DoorHealReserve = 37.4,
    CustomTrayText = "reserve-state",
  })
  setTraits(selected)
  local row = findRow("DoorHealReserveKeepsake", 1901)
  local progressBefore = GameState.KeepsakeChambers.DoorHealReserveKeepsake
  local params = paramsFrom(row, "keepsake-persistent-rank")
  params.rarity = "Heroic"
  M.dispatch("set_trait_rarity", params)
  local rebuilt = findMountedTrait("DoorHealReserveKeepsake")
  eq(rebuilt.Rarity, "Heroic", "Keepsake persistent-state rank")
  eq(rebuilt.DoorHealReserve, 37, "Keepsake rank did not preserve native rounded reserve")
  eq(rebuilt.CustomTrayText, "reserve-state", "Keepsake rank reset persistent tray state")
  eq(GameState.KeepsakeChambers.DoorHealReserveKeepsake, progressBefore, "Keepsake persistent rank changed progression")
end

-- Native owner replacement invalidates a rank request before teardown/rebuild.
do
  GameState.LastAwardTrait = "ReincarnationKeepsake"
  local selected = newTrait("ReincarnationKeepsake", 1951, 1, "Rare")
  setTraits(selected)
  local row = findRow("ReincarnationKeepsake", 1951)
  local params = paramsFrom(row, "keepsake-rank-stale-owner")
  params.rarity = "Epic"
  local beforeUnequip = calls.keepsakeUnequip
  GameState.LastAwardTrait = "BonusMoneyKeepsake"
  expectError("Trait target changed since selection", function()
    M.dispatch("set_trait_rarity", params)
  end)
  eq(calls.keepsakeUnequip, beforeUnequip, "stale Keepsake rank reached owner teardown")
end

-- Unsupported target ranks fail before owner teardown.
do
  GameState.LastAwardTrait = "BonusMoneyKeepsake"
  local selected = newTrait("BonusMoneyKeepsake", 2001, 1, "Rare")
  setTraits(selected)
  local row = findRow("BonusMoneyKeepsake", 2001)
  local params = paramsFrom(row, "keepsake-unsupported-rank")
  params.rarity = "Heroic"
  local beforeUnequip = calls.keepsakeUnequip
  expectError("Trait rarity editing is unavailable for the selected target", function()
    M.dispatch("set_trait_rarity", params)
  end)
  eq(calls.keepsakeUnequip, beforeUnequip, "unsupported Keepsake rank mutated owner")
end

-- Arcana ownership is exact and progression-backed: only an equipped card
-- whose native TraitName matches the mounted effect owns that row. Inheritance
-- alone is never sufficient, and runtime removal stays unavailable because the
-- durable Equipped state would allow the native lifecycle to resurrect it.
do
  local owned = newTrait("LowManaDamageMetaupgrade", 2201, 1, "Rare")
  local inheritedOnly = newTrait("UnownedMetaUpgradeTrait", 2202, 1, "Rare")
  setTraits(owned, inheritedOnly)

  local row = findRow("LowManaDamageMetaupgrade", 2201)
  eq(row.family, "arcana", "equipped Arcana owner family")
  eq(row.sourceId, "LowManaDamageBonus", "Arcana card owner identity")
  eq(row.owner, "LowManaDamageBonus", "Arcana owner projection")
  eq(row.levelCapability, "none", "Arcana fabricated StackNum editing")
  eq(row.rarityCapability, "setExact", "safe Arcana runtime rank capability")
  eq(row.removalCapability, "none", "Arcana runtime removal must fail closed")
  check(findRow("UnownedMetaUpgradeTrait", 2202).family ~= "arcana",
    "MetaUpgradeTrait inheritance fabricated Arcana ownership")

  local durable = GameState.MetaUpgradeState.LowManaDamageBonus
  local levelBefore = durable.Level
  local equippedBefore = durable.Equipped
  local unlockedBefore = durable.Unlocked
  local adjacencyBefore = durable.AdjacencyBonuses.CustomMultiplier
  local genericRarityBefore = calls.rarity
  local nativeRemoveBefore = calls.nativeRemove
  local addBefore = calls.arcanaAdd
  local healthBefore = calls.validateHealth
  local manaBefore = calls.validateMana
  local animBefore = calls.weaponAnim

  local params = paramsFrom(row, "arcana-runtime-rank")
  params.rarity = "Epic"
  local result = M.dispatch("set_trait_rarity", params)

  eq(calls.rarity, genericRarityBefore, "Arcana rank used generic rarity mutator")
  eq(calls.nativeRemove, nativeRemoveBefore + 1, "Arcana rank skipped owner teardown")
  eq(calls.arcanaAdd, addBefore + 1, "Arcana rank skipped owner rebuild")
  eq(calls.validateHealth, healthBefore + 1, "Arcana rank skipped health refresh")
  eq(calls.validateMana, manaBefore + 1, "Arcana rank skipped mana refresh")
  eq(calls.weaponAnim, animBefore + 1, "Arcana rank skipped weapon animation refresh")
  eq(durable.Level, levelBefore, "Arcana runtime rank rewrote durable level")
  eq(durable.Equipped, equippedBefore, "Arcana runtime rank rewrote equipped state")
  eq(durable.Unlocked, unlockedBefore, "Arcana runtime rank rewrote unlock state")
  eq(durable.AdjacencyBonuses.CustomMultiplier, adjacencyBefore,
    "Arcana runtime rank rewrote adjacency ownership")

  local rebuilt = findMountedTrait("LowManaDamageMetaupgrade")
  eq(rebuilt.Rarity, "Epic", "Arcana runtime rank target")
  eq(rebuilt.SourceName, "LowManaDamageBonus", "Arcana rebuild lost card owner")
  eq(rebuilt.CustomMultiplier, 1.5, "Arcana rebuild lost adjacency multiplier")
  eq(result.actionOutcome, "completed", "Arcana rank outcome")

  CurrentRun.CurrentRoom = { Name = "F_TestRoom" }
  eq(findRow("LowManaDamageMetaupgrade").rarity, "Epic",
    "Arcana runtime rank lost across room transition")

  local removeAfter = calls.nativeRemove
  local addAfter = calls.arcanaAdd
  local duplicate = M.dispatch("set_trait_rarity", params)
  check(duplicate.duplicate == true, "Arcana rank replay was not deduplicated")
  eq(calls.nativeRemove, removeAfter, "Arcana duplicate replayed owner teardown")
  eq(calls.arcanaAdd, addAfter, "Arcana duplicate replayed owner rebuild")

  M.dispatch("disable_all", { includeCatalogs = false })
  eq(findRow("LowManaDamageMetaupgrade").rarity, "Epic",
    "disable_all reverted game-owned Arcana runtime rank")
end

-- Changing the native owner after observation invalidates the selection before
-- any owner rebuild. A card with one-shot grant/upgrade callbacks is recognized
-- as Arcana but exposes no generic runtime rank mutation.
do
  local owned = newTrait("LowManaDamageMetaupgrade", 2301, 1, "Rare")
  local reroll = newTrait("DoorRerollMetaUpgrade", 2302, 1, "Rare")
  setTraits(owned, reroll)

  local row = findRow("LowManaDamageMetaupgrade", 2301)
  local beforeRemove = calls.nativeRemove
  local beforeAdd = calls.arcanaAdd
  GameState.MetaUpgradeState.LowManaDamageBonus.Equipped = false
  local stale = paramsFrom(row, "arcana-stale-owner")
  stale.rarity = "Epic"
  expectError("Trait target changed since selection", function()
    M.dispatch("set_trait_rarity", stale)
  end)
  eq(calls.nativeRemove, beforeRemove, "stale Arcana owner reached teardown")
  eq(calls.arcanaAdd, beforeAdd, "stale Arcana owner reached rebuild")
  GameState.MetaUpgradeState.LowManaDamageBonus.Equipped = true

  local unsafe = findRow("DoorRerollMetaUpgrade", 2302)
  eq(unsafe.family, "arcana", "callback Arcana owner classification")
  eq(unsafe.rarityCapability, "none", "one-shot Arcana exposed rank mutation")
  eq(unsafe.removalCapability, "none", "one-shot Arcana exposed removal")

  local bossShield = newTrait("BossShieldMetaUpgrade", 2303, 1, "Rare")
  setTraits(bossShield)
  local bossRow = findRow("BossShieldMetaUpgrade", 2303)
  eq(bossRow.family, "arcana", "Boss shield Arcana owner classification")
  eq(bossRow.rarityCapability, "none",
    "Arcana rank exposed without synchronizing materialized boss shield state")
end

-- Adjacency and durable card level may change through native Arcana ownership
-- after the row was observed. A runtime rank edit uses the current adjacency
-- multiplier and never rewrites the game's newer durable level.
do
  local owned = newTrait("LowManaDamageMetaupgrade", 2351, 1, "Rare")
  setTraits(owned)
  local row = findRow("LowManaDamageMetaupgrade", 2351)
  local durable = GameState.MetaUpgradeState.LowManaDamageBonus
  durable.Level = 3
  durable.AdjacencyBonuses.CustomMultiplier = 0.25

  local params = paramsFrom(row, "arcana-owner-state-changed")
  params.rarity = "Heroic"
  M.dispatch("set_trait_rarity", params)

  local rebuilt = findMountedTrait("LowManaDamageMetaupgrade")
  eq(rebuilt.Rarity, "Heroic", "Arcana changed-owner-state target rarity")
  eq(rebuilt.CustomMultiplier, 1.25, "Arcana rebuild used stale adjacency multiplier")
  eq(durable.Level, 3, "Arcana runtime edit rewrote newer durable card level")
  eq(durable.AdjacencyBonuses.CustomMultiplier, 0.25,
    "Arcana runtime edit rewrote newer adjacency state")

  -- Restore the fixture's durable native state for later run-reset coverage.
  durable.Level = 2
  durable.AdjacencyBonuses.CustomMultiplier = 0.5
end

-- If owner rebuild mounts the replacement and acknowledges late, the request is
-- outcome-unknown and never replayed. Durable card progression is still untouched.
do
  local owned = newTrait("HealthManaBonusMetaUpgrade", 2401, 1, "Rare")
  setTraits(owned)
  local row = findRow("HealthManaBonusMetaUpgrade", 2401)
  local params = paramsFrom(row, "arcana-rank-unknown")
  params.rarity = "Epic"
  local durable = GameState.MetaUpgradeState.BonusHealth
  local levelBefore = durable.Level
  local removeBefore = calls.nativeRemove
  local addBefore = calls.arcanaAdd
  failArcanaAddAfterMutation = true
  expectError("MGT_OUTCOME_UNKNOWN", function()
    M.dispatch("set_trait_rarity", params)
  end)
  eq(findMountedTrait("HealthManaBonusMetaUpgrade").Rarity, "Epic",
    "unknown Arcana rebuild lost mounted target")
  eq(durable.Level, levelBefore, "unknown Arcana rebuild rewrote durable level")
  eq(calls.nativeRemove, removeBefore + 1, "unknown Arcana teardown count")
  eq(calls.arcanaAdd, addBefore + 1, "unknown Arcana add count")
  local removeAfter = calls.nativeRemove
  local addAfter = calls.arcanaAdd
  expectError("Previous action outcome is unknown; do not retry", function()
    M.dispatch("set_trait_rarity", params)
  end)
  eq(calls.nativeRemove, removeAfter, "unknown Arcana request replayed teardown")
  eq(calls.arcanaAdd, addAfter, "unknown Arcana request replayed rebuild")
end

-- If native EquipKeepsake mutates then acknowledges late, restore persistent
-- values on the newly mounted owner before surfacing outcome-unknown. The
-- uncertain request must never replay.
do
  GameState.LastAwardTrait = "DoorHealReserveKeepsake"
  local selected = newTrait("DoorHealReserveKeepsake", 2101, 1, "Rare", {
    DoorHealReserve = 23,
    CustomTrayText = "unknown-state",
  })
  setTraits(selected)
  local row = findRow("DoorHealReserveKeepsake", 2101)
  local params = paramsFrom(row, "keepsake-rank-unknown")
  params.rarity = "Epic"
  failKeepsakeEquipAfterMutation = true
  expectError("MGT_OUTCOME_UNKNOWN", function()
    M.dispatch("set_trait_rarity", params)
  end)
  local rebuilt = findMountedTrait("DoorHealReserveKeepsake")
  eq(rebuilt.Rarity, "Epic", "unknown Keepsake rank left wrong target")
  eq(rebuilt.DoorHealReserve, 23, "unknown Keepsake rank lost persistent reserve")
  eq(rebuilt.CustomTrayText, "unknown-state", "unknown Keepsake rank lost persistent tray state")
  local unequipAfter = calls.keepsakeUnequip
  local equipAfter = calls.keepsakeEquip
  expectError("Previous action outcome is unknown; do not retry", function()
    M.dispatch("set_trait_rarity", params)
  end)
  eq(calls.keepsakeUnequip, unequipAfter, "unknown Keepsake rank replayed unequip")
  eq(calls.keepsakeEquip, equipAfter, "unknown Keepsake rank replayed equip")
end

-- A new run/death reset receives native durable Arcana state again. The
-- previous run's forced rank is ephemeral, and an old selection cannot mutate
-- the replacement run.
do
  GameState.LastAwardTrait = nil
  local previous = newTrait("LowManaDamageMetaupgrade", 2501, 1, "Epic")
  setTraits(previous)
  local oldRow = findRow("LowManaDamageMetaupgrade", 2501)
  local stale = paramsFrom(oldRow, "arcana-old-run")
  stale.rarity = "Heroic"

  CurrentRun = {
    Hero = {
      ObjectId = 2,
      Health = 100, MaxHealth = 100,
      Mana = 50, MaxMana = 50,
      HealthBuffer = 0, Elements = {},
      Traits = { newTrait("LowManaDamageMetaupgrade", 2502, 1, "Rare") },
    },
    CurrentRoom = {},
    NumRerolls = 0,
    SpellCharge = 0,
  }

  local resetRow = findRow("LowManaDamageMetaupgrade", 2502)
  eq(resetRow.family, "arcana", "Arcana owner lost after run reset")
  eq(resetRow.rarity, "Rare", "runtime Arcana override leaked into replacement run")
  eq(GameState.MetaUpgradeState.LowManaDamageBonus.Level, 2,
    "run reset changed durable Arcana level")
  expectError("stale run", function()
    M.dispatch("set_trait_rarity", stale)
  end)
end

print("hades2_live_trait_runtime_behavior_ok")
'''

with tempfile.TemporaryDirectory(prefix="mgt-live-trait-runtime-") as td:
    td = Path(td)
    harness = td / "live_trait_runtime_behavior.lua"
    harness.write_text(textwrap.dedent(HARNESS), encoding="utf-8")

    proc = subprocess.run(
        [LUA, str(harness), str(RUNTIME), str(RESIDENT_DISPATCH_CONTRACT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    assert "hades2_live_trait_runtime_behavior_ok" in proc.stdout, proc.stdout
    print(proc.stdout.strip())
