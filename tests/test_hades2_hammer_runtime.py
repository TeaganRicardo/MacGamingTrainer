import subprocess
import tempfile
import textwrap
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "Backend/games/hades2/runtime/hades.lua"
LUA = require_lua52("Hammer weapon-owner runtime tests")

HARNESS = r'''
local runtimePath = assert(arg[1], "runtime path required")
local contractPath = assert(arg[2], "dispatch contract path required")

SessionState = {}
SessionMapState = {}
GameState = {
  Resources = {},
  LifetimeResourcesGained = {},
  RunHistory = {},
  LastWeaponUpgradeName = { WeaponLob = "LobAmmoBoostAspect" },
}
ResourceData = {}
ResourceDisplayOrderData = {}
TraitElementData = {}
EnemyData = {}
PresetEventArgs = {}
ScreenData = {}
LootObjects = {}
ConsumableData = {}
RewardStoreData = {}
SpellData = {}
SpellTalentData = {}
UnitSetData = {}
UpdateTimers = function() end
CodexOrdering = { OlympianGods = {}, Order = {} }

MapState = {
  RoomRequiredObjects = {},
  EquippedWeapons = {},
}

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
    TraitDictionary = {},
    Weapons = { WeaponLob = true },
    BoonData = { GameStateRequirements = {}, ReplaceChance = 0 },
    Ammo = { WeaponLob = 4 },
  },
  CurrentRoom = {},
  NumRerolls = 0,
  SpellCharge = 0,
  PickedTraits = {},
  BannedTraits = {},
}

local function deepCopy(value)
  if type(value) ~= "table" then return value end
  local result = {}
  for key, item in pairs(value) do result[key] = deepCopy(item) end
  return result
end
DeepCopyTable = deepCopy
ShallowCopyTable = function(value)
  local result = {}
  for key, item in pairs(value or {}) do result[key] = item end
  return result
end

TraitData = {
  LobAmmoTrait = {
    Name = "LobAmmoTrait",
    IsHammerTrait = true,
    CodexWeapon = "WeaponLob",
    RarityLevels = { Common = { Multiplier = 1 }, Legendary = { Multiplier = 2 } },
    WeaponAmmoModification = { Name = "WeaponLob" },
  },
  LobPulseAmmoTrait = {
    Name = "LobPulseAmmoTrait",
    IsHammerTrait = true,
    CodexWeapon = "WeaponLob",
    RarityLevels = { Common = { Multiplier = 1 }, Legendary = { Multiplier = 1.5 } },
    PreEquipWeapons = { "WeaponLobPulse" },
    WeaponDataOverride = { WeaponLob = { MockOverride = "pulse" } },
  },
  LobPulseAmmoCollectTrait = {
    Name = "LobPulseAmmoCollectTrait",
    IsHammerTrait = true,
    CodexWeapon = "WeaponLob",
    PreEquipWeapons = { "WeaponLobPulse" },
  },
  LobGunOverheatTrait = {
    Name = "LobGunOverheatTrait",
    IsHammerTrait = true,
    CodexWeapon = "WeaponLob",
    RarityLevels = { Common = { Multiplier = 1 }, Legendary = { Multiplier = 2 } },
    WeaponDataOverride = { WeaponLob = { MockOverride = "gun" } },
  },
  StaffDoubleAttackTrait = {
    Name = "StaffDoubleAttackTrait",
    IsHammerTrait = true,
    CodexWeapon = "WeaponStaffSwing",
    RarityLevels = { Common = { Multiplier = 1 }, Legendary = { Multiplier = 2 } },
  },
  LobAmmoBoostAspect = {
    Name = "LobAmmoBoostAspect",
    IsWeaponEnchantment = true,
    Slot = "Aspect",
    RequiredWeapon = "WeaponLob",
    RarityLevels = { Common = {}, Rare = {}, Epic = {}, Heroic = {}, Legendary = {} },
  },
  LobGunAspect = {
    Name = "LobGunAspect",
    IsWeaponEnchantment = true,
    Slot = "Aspect",
    RequiredWeapon = "WeaponLob",
    RarityLevels = { Common = {}, Rare = {}, Epic = {}, Heroic = {}, Legendary = {} },
  },
}

LootData = {
  WeaponUpgrade = {
    Name = "WeaponUpgrade",
    ForceCommon = true,
    Traits = {
      "LobAmmoTrait",
      "LobPulseAmmoTrait",
      "LobPulseAmmoCollectTrait",
      "LobGunOverheatTrait",
      "StaffDoubleAttackTrait",
    },
    PriorityUpgrades = {},
    WeaponUpgrades = {},
  },
}

local calls = {
  add = 0,
  remove = 0,
  rarity = 0,
  resetAmmo = 0,
  unequip = {},
  eligible = 0,
  fromLoot = 0,
}
local nextId = 200
local failAddAfterMutation = false

-- Minimal engine seams for coexistence with the existing Cast and ammo
-- features.  Hammer work must not replace or release these hooks.
local castProperties = {
  IgnoreOwnerAttackDisabled = false,
  Cooldown = 0.75,
  AllowMultiFireRequest = false,
  IgnoreForceCooldown = false,
  ActiveProjectileCap = 1,
}
GetWeaponDataValue = function(args)
  if args.WeaponName ~= "WeaponCast" then return nil end
  return castProperties[args.Property]
end
SetWeaponProperty = function(args)
  if args.WeaponName == "WeaponCast" then castProperties[args.Property] = args.Value end
end
SetEffectProperty = function() return true end
GetMaxAmmo = function(weaponName)
  return weaponName == "WeaponLob" and 4 or 0
end
UpdateWeaponAmmo = function(weaponName, delta)
  CurrentRun.Hero.Ammo[weaponName] = (CurrentRun.Hero.Ammo[weaponName] or 0) + delta
end

local function rebuildDictionary()
  CurrentRun.Hero.TraitDictionary = {}
  for _, trait in ipairs(CurrentRun.Hero.Traits) do
    CurrentRun.Hero.TraitDictionary[trait.Name] =
      CurrentRun.Hero.TraitDictionary[trait.Name] or {}
    table.insert(CurrentRun.Hero.TraitDictionary[trait.Name], trait)
  end
end

HeroHasTrait = function(name)
  local values = CurrentRun.Hero.TraitDictionary[name]
  return type(values) == "table" and #values > 0
end

GetHeroTrait = function(name)
  local values = CurrentRun.Hero.TraitDictionary[name]
  return type(values) == "table" and values[1] or nil
end

GetEquippedWeapon = function()
  if CurrentRun.Hero.Weapons.WeaponLob then return "WeaponLob" end
  if CurrentRun.Hero.Weapons.WeaponStaffSwing then return "WeaponStaffSwing" end
  return nil
end

local function targetEligible(name)
  local definition = TraitData[name]
  if type(definition) ~= "table" or not definition.IsHammerTrait then return false end
  if definition.CodexWeapon ~= GetEquippedWeapon() then return false end
  if HeroHasTrait(name) then return false end
  if name == "LobGunOverheatTrait" then
    return GameState.LastWeaponUpgradeName.WeaponLob == "LobGunAspect"
  end
  return true
end

GetEligibleUpgrades = function(_, source)
  calls.eligible = calls.eligible + 1
  local result = {}
  for _, name in ipairs(source.Traits or {}) do
    if targetEligible(name) then
      result[#result + 1] = { ItemName = name, Type = "Trait" }
    end
  end
  return result
end

GetProcessedTraitData = function(args)
  local definition = assert(TraitData[args.TraitName], "unknown trait " .. tostring(args.TraitName))
  local result = deepCopy(definition)
  result.Name = args.TraitName
  result.Rarity = args.Rarity or result.Rarity or "Common"
  result.StackNum = args.StackNum or 1
  local multiplier = result.Rarity == "Legendary" and 2 or 1
  result.MockEffectValue = 100 * multiplier
  return result
end

AddTraitToHero = function(args)
  calls.add = calls.add + 1
  if args.FromLoot then calls.fromLoot = calls.fromLoot + 1 end
  local trait = args.TraitData and deepCopy(args.TraitData)
    or GetProcessedTraitData({
      TraitName = args.TraitName,
      Rarity = args.Rarity,
      StackNum = args.StackNum,
    })
  nextId = nextId + 1
  trait.Id = nextId
  table.insert(CurrentRun.Hero.Traits, trait)
  rebuildDictionary()
  for _, weaponName in ipairs(trait.PreEquipWeapons or {}) do
    MapState.EquippedWeapons[weaponName] = true
  end
  if trait.WeaponDataOverride then
    CurrentRun.Hero.WeaponDataOverride = CurrentRun.Hero.WeaponDataOverride or {}
    for weaponName, data in pairs(trait.WeaponDataOverride) do
      CurrentRun.Hero.WeaponDataOverride[weaponName] = deepCopy(data)
    end
  end
  if failAddAfterMutation then
    failAddAfterMutation = false
    error("synthetic Hammer post-mutation acknowledgement failure")
  end
  return trait
end

RemoveTraitData = function(hero, target)
  calls.remove = calls.remove + 1
  for index, trait in ipairs(hero.Traits) do
    if trait == target then
      table.remove(hero.Traits, index)
      break
    end
  end
  if target.WeaponAmmoModification then calls.resetAmmo = calls.resetAmmo + 1 end
  if target.WeaponDataOverride and hero.WeaponDataOverride then
    for weaponName in pairs(target.WeaponDataOverride) do
      hero.WeaponDataOverride[weaponName] = nil
    end
    for _, trait in ipairs(hero.Traits) do
      for weaponName, data in pairs(trait.WeaponDataOverride or {}) do
        hero.WeaponDataOverride[weaponName] = deepCopy(data)
      end
    end
  end
  rebuildDictionary()
end

RemoveTrait = function(hero, name)
  for _, trait in ipairs(hero.Traits) do
    if trait.Name == name then
      RemoveTraitData(hero, trait)
      return
    end
  end
end

UnequipWeapon = function(args)
  calls.unequip[#calls.unequip + 1] = args.Name
  MapState.EquippedWeapons[args.Name] = nil
end

AddRarityToTraits = function(_, args)
  calls.rarity = calls.rarity + 1
  local old = assert(args.ForceUpgrade and args.ForceUpgrade[1], "missing rarity target")
  local name, stack = old.Name, old.StackNum or 1
  RemoveTraitData(CurrentRun.Hero, old, { SkipExpire = true })
  local fresh = GetProcessedTraitData({
    TraitName = name,
    Rarity = args.TargetRarityName,
    StackNum = stack,
  })
  return AddTraitToHero({ TraitData = fresh, SkipSetup = true })
end

IncreaseTraitLevel = function(trait, amount)
  trait.StackNum = (trait.StackNum or 1) + (amount or 1)
  return trait
end

IsGodTrait = function() return false end
GetAllUpgradeableGodTraits = function() return {} end
UpdateTalentPointInvestedCache = function() end
thread = function(fn, ...) if type(fn) == "function" then return fn(...) end end

dofile(runtimePath)
local M = assert(__MacGamingTrainerV1, "resident runtime did not initialize")
dofile(contractPath)
M.session = SessionState
M.run = CurrentRun
M.hero = CurrentRun.Hero

local function fail(message) error("ASSERTION FAILED: " .. message, 0) end
local function check(value, message) if not value then fail(message) end end
local function eq(actual, expected, message)
  if actual ~= expected then
    fail(message .. ": expected=" .. tostring(expected) .. " actual=" .. tostring(actual))
  end
end
local function contains(value, needle)
  return string.find(tostring(value), needle, 1, true) ~= nil
end
local function expectError(needle, fn)
  local ok, message = pcall(fn)
  if ok then fail("expected error containing " .. needle) end
  if not contains(message, needle) then
    fail("wrong error; expected '" .. needle .. "', got '" .. tostring(message) .. "'")
  end
end

local function status(includeCatalogs)
  return M.dispatch("status", { includeCatalogs = includeCatalogs ~= false })
end
local function findReward(id)
  for _, row in ipairs(status(true).rewards or {}) do
    if row.id == id then return row end
  end
  return nil
end
local function findRow(name)
  for _, row in ipairs(status(false).currentRunTraits or {}) do
    if row.name == name then return row end
  end
  return nil
end
local function paramsFrom(row, requestId)
  return {
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
end
local function clearRunTraits()
  CurrentRun.Hero.Traits = {}
  CurrentRun.Hero.TraitDictionary = {}
  CurrentRun.Hero.WeaponDataOverride = {}
  MapState.EquippedWeapons = {}
end

-- Exact catalog is current-weapon/current-aspect dynamic, not a flat 92-item list.
clearRunTraits()
CurrentRun.Hero.Weapons = { WeaponLob = true }
GameState.LastWeaponUpgradeName.WeaponLob = "LobAmmoBoostAspect"
check(findReward("hammer:LobAmmoTrait") ~= nil, "eligible Lob Hammer missing")
check(findReward("hammer:StaffDoubleAttackTrait") == nil, "wrong-weapon Hammer leaked into catalog")
check(findReward("hammer:LobGunOverheatTrait") == nil, "wrong-aspect Hammer leaked into catalog")

GameState.LastWeaponUpgradeName.WeaponLob = "LobGunAspect"
check(findReward("hammer:LobGunOverheatTrait") ~= nil,
  "aspect transition did not invalidate Hammer catalog")
GameState.LastWeaponUpgradeName.WeaponLob = "LobAmmoBoostAspect"

-- Exact native acquisition uses current eligibility, FromLoot, and action deduplication.
do
  local beforeAdd = calls.add
  local beforeFromLoot = calls.fromLoot
  local result = M.dispatch("spawn_reward", {
    reward = "hammer:LobAmmoTrait",
    requestId = "hammer-exact",
    includeCatalogs = false,
  })
  eq(calls.add, beforeAdd + 1, "Hammer exact acquisition did not add exactly once")
  eq(calls.fromLoot, beforeFromLoot + 1, "Hammer exact acquisition skipped FromLoot semantics")
  check(HeroHasTrait("LobAmmoTrait"), "Hammer exact acquisition did not mount trait")
  check(result.lootObjectId == nil, "Hammer exact acquisition leaked trait table in action receipt")
  local duplicate = M.dispatch("spawn_reward", {
    reward = "hammer:LobAmmoTrait",
    requestId = "hammer-exact",
    includeCatalogs = false,
  })
  eq(calls.add, beforeAdd + 1, "completed Hammer request replayed mutation")
  check(duplicate.duplicate == true, "completed Hammer request lost duplicate receipt")
end

-- A stale target is rejected when weapon ownership changes.
do
  clearRunTraits()
  CurrentRun.Hero.Weapons = { WeaponLob = true }
  check(findReward("hammer:LobPulseAmmoTrait") ~= nil, "stale-target fixture missing")
  CurrentRun.Hero.Weapons = { WeaponStaffSwing = true }
  local beforeAdd = calls.add
  expectError("Unknown or unsupported reward", function()
    M.dispatch("spawn_reward", {
      reward = "hammer:LobPulseAmmoTrait",
      requestId = "hammer-stale-weapon",
      includeCatalogs = false,
    })
  end)
  eq(calls.add, beforeAdd, "stale Hammer target reached mutator")
  check(findReward("hammer:StaffDoubleAttackTrait") ~= nil,
    "weapon transition did not refresh Hammer catalog")
end

-- Mounted Hammer is distinct from a runtime aspect. Hammer levels are not
-- fabricated; rarity is only offered when the Hammer exposes native rarity data.
do
  clearRunTraits()
  CurrentRun.Hero.Weapons = { WeaponLob = true }
  AddTraitToHero({ TraitName = "LobAmmoBoostAspect", Rarity = "Legendary" })
  AddTraitToHero({ TraitName = "LobAmmoTrait", Rarity = "Common" })
  local hammer = assert(findRow("LobAmmoTrait"), "mounted Hammer row missing")
  local aspect = assert(findRow("LobAmmoBoostAspect"), "runtime aspect row missing")
  eq(hammer.family, "hammer", "Hammer owner family")
  eq(hammer.levelCapability, "none", "Hammer fabricated Pom/level support")
  eq(hammer.rarityCapability, "setExact", "upgradable Hammer rarity capability")
  eq(hammer.removalCapability, "singleInstanceForce", "Hammer removal capability")
  eq(aspect.family, "weaponAspect", "runtime aspect owner family")
  eq(aspect.levelCapability, "none", "runtime aspect fabricated level support")
  eq(aspect.rarityCapability, "none", "runtime aspect diverged from permanent rank")
  eq(aspect.removalCapability, "none", "runtime aspect exposed unsafe removal")

  local params = paramsFrom(hammer, "hammer-rarity")
  params.rarity = "Legendary"
  local beforeRarity = calls.rarity
  M.dispatch("set_trait_rarity", params)
  eq(calls.rarity, beforeRarity + 1, "Hammer rarity did not use game recomputation")
  local upgraded = assert(GetHeroTrait("LobAmmoTrait"), "Hammer disappeared after rarity edit")
  eq(upgraded.Rarity, "Legendary", "Hammer rarity target not reached")
  eq(upgraded.MockEffectValue, 200, "Hammer rarity did not recompute mounted effect")
end

-- Removal delegates weapon/modifier/ammo cleanup to RemoveTraitData.
do
  local hammer = assert(findRow("LobAmmoTrait"))
  local beforeRemove = calls.remove
  local beforeReset = calls.resetAmmo
  M.dispatch("remove_trait", paramsFrom(hammer, "hammer-remove"))
  eq(calls.remove, beforeRemove + 1, "Hammer removal skipped game teardown")
  eq(calls.resetAmmo, beforeReset + 1, "Hammer ammo teardown did not reset ammo")
  check(not HeroHasTrait("LobAmmoTrait"), "Hammer survived removal")
  check(HeroHasTrait("LobAmmoBoostAspect"), "Hammer removal damaged runtime aspect owner")
end

-- Pre-equipped helper weapons are released only after the final owning Hammer
-- is removed.
do
  clearRunTraits()
  CurrentRun.Hero.Weapons = { WeaponLob = true }
  AddTraitToHero({ TraitName = "LobPulseAmmoTrait", Rarity = "Common" })
  AddTraitToHero({ TraitName = "LobPulseAmmoCollectTrait", Rarity = "Common" })
  check(MapState.EquippedWeapons.WeaponLobPulse == true, "helper weapon was not mounted")
  local first = assert(findRow("LobPulseAmmoTrait"))
  M.dispatch("remove_trait", paramsFrom(first, "hammer-pre-equip-first"))
  check(MapState.EquippedWeapons.WeaponLobPulse == true,
    "shared helper weapon was released while another Hammer still owned it")
  local second = assert(findRow("LobPulseAmmoCollectTrait"))
  M.dispatch("remove_trait", paramsFrom(second, "hammer-pre-equip-last"))
  check(MapState.EquippedWeapons.WeaponLobPulse == nil,
    "orphaned Hammer helper weapon survived final owner removal")
end

-- Hammer acquisition/rarity/removal coexists with the existing Cast recast
-- and infinite-ammo hooks; this slice never reimplements or releases them.
do
  clearRunTraits()
  CurrentRun.Hero.Weapons = { WeaponLob = true }
  CurrentRun.Hero.Ammo = { WeaponLob = 4 }
  M.dispatch("set_feature", { feature = "instantCastCooldown", value = true, includeCatalogs = false })
  M.dispatch("set_feature", { feature = "infiniteAmmo", value = true, includeCatalogs = false })
  local before = status(false)
  check(before.activeFeatures.instantCastCooldown == true, "Cast recast fixture did not arm")
  check(before.activeFeatures.infiniteAmmo == true, "infinite-ammo fixture did not arm")

  M.dispatch("spawn_reward", {
    reward = "hammer:LobAmmoTrait",
    requestId = "hammer-coexist-acquire",
    includeCatalogs = false,
  })
  local row = assert(findRow("LobAmmoTrait"))
  local rarityParams = paramsFrom(row, "hammer-coexist-rarity")
  rarityParams.rarity = "Legendary"
  M.dispatch("set_trait_rarity", rarityParams)
  row = assert(findRow("LobAmmoTrait"))
  M.dispatch("remove_trait", paramsFrom(row, "hammer-coexist-remove"))

  local after = status(false)
  check(after.activeFeatures.instantCastCooldown == true,
    "Hammer mutation released the Cast recast hook")
  check(after.activeFeatures.infiniteAmmo == true,
    "Hammer mutation released the infinite-ammo hook")
end

-- One-shot Hammer acquisition is not undone by disable_all.
do
  clearRunTraits()
  CurrentRun.Hero.Weapons = { WeaponLob = true }
  M.dispatch("spawn_reward", {
    reward = "hammer:LobPulseAmmoTrait",
    requestId = "hammer-before-disable",
    includeCatalogs = false,
  })
  M.dispatch("disable_all", { includeCatalogs = false })
  check(HeroHasTrait("LobPulseAmmoTrait"), "disable_all removed one-shot Hammer acquisition")
end

-- Post-mutation acknowledgement failure is outcome-unknown and never replayed.
do
  clearRunTraits()
  CurrentRun.Hero.Weapons = { WeaponLob = true }
  local beforeAdd = calls.add
  failAddAfterMutation = true
  expectError("MGT_OUTCOME_UNKNOWN", function()
    M.dispatch("spawn_reward", {
      reward = "hammer:LobAmmoTrait",
      requestId = "hammer-outcome-unknown",
      includeCatalogs = false,
    })
  end)
  eq(calls.add, beforeAdd + 1, "outcome-unknown Hammer mutation did not execute once")
  check(HeroHasTrait("LobAmmoTrait"), "outcome-unknown Hammer lost applied mutation")
  expectError("Previous action outcome is unknown; do not retry", function()
    M.dispatch("spawn_reward", {
      reward = "hammer:LobAmmoTrait",
      requestId = "hammer-outcome-unknown",
      includeCatalogs = false,
    })
  end)
  eq(calls.add, beforeAdd + 1, "outcome-unknown Hammer request replayed")
end

print("hades2_hammer_runtime_ok")
'''

with tempfile.TemporaryDirectory(prefix="mgt-hammer-runtime-") as td:
    td = Path(td)
    harness = td / "hammer_runtime.lua"
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
    assert "hades2_hammer_runtime_ok" in proc.stdout, proc.stdout
    print(proc.stdout.strip())
