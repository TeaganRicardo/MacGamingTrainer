import subprocess
import tempfile
import textwrap
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "Backend/games/hades2/runtime/hades.lua"
LUA = require_lua52("Selene Hex owner lifecycle runtime tests")

HARNESS = r'''
local runtimePath = assert(arg[1], "runtime path required")
local contractPath = assert(arg[2], "dispatch contract path required")

SessionState = {}
SessionMapState = {}
GameState = { Resources = {}, LifetimeResourcesGained = {}, RunHistory = {} }
ResourceData = {}
ResourceDisplayOrderData = {}
TraitElementData = {}
EnemyData = {}
PresetEventArgs = {}
ScreenData = {}
LootObjects = {}
ConsumableData = {}
RewardStoreData = {}
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
    Weapons = {},
    BoonData = { GameStateRequirements = {}, ReplaceChance = 0 },
    SlottedSpell = nil,
  },
  CurrentRoom = {},
  NumRerolls = 0,
  NumTalentPoints = 7,
  SpellCharge = 42,
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
  SpellPolymorphTrait = {
    Name = "SpellPolymorphTrait",
    Slot = "Spell",
    PreEquipWeapons = { "WeaponSpellPolymorph" },
  },
  SpellMeteorTrait = {
    Name = "SpellMeteorTrait",
    Slot = "Spell",
    PreEquipWeapons = { "WeaponSpellMeteor" },
  },
  SpellMoonBeamTrait = {
    Name = "SpellMoonBeamTrait",
    Slot = "Spell",
    PreEquipWeapons = { "WeaponSpellMoonBeam" },
  },
  ChargeRegenTalent = {
    Name = "ChargeRegenTalent",
    RarityLevels = { Common = {}, Rare = {}, Epic = {}, Heroic = {} },
    AcquireFunctionName = "MockTalentAcquire",
    AcquireFunctionArgs = { Marker = "charge" },
  },
  PolymorphDamageTalent = {
    Name = "PolymorphDamageTalent",
    RarityLevels = { Common = {}, Rare = {}, Epic = {}, Heroic = {} },
  },
  MeteorDamageTalent = {
    Name = "MeteorDamageTalent",
    RarityLevels = { Common = {}, Rare = {}, Epic = {}, Heroic = {} },
  },
}

SpellData = {
  Polymorph = {
    Name = "Polymorph",
    TraitName = "SpellPolymorphTrait",
    MockTree = {
      {
        { Name = "ChargeRegenTalent", Rarity = "Common" },
        { Name = "PolymorphDamageTalent", Rarity = "Rare" },
      },
      {
        { Name = "ChargeRegenTalent", Rarity = "Common" },
      },
    },
  },
  Meteor = {
    Name = "Meteor",
    TraitName = "SpellMeteorTrait",
    MockTree = {
      {
        { Name = "ChargeRegenTalent", Rarity = "Common" },
        { Name = "MeteorDamageTalent", Rarity = "Rare" },
      },
      {
        { Name = "ChargeRegenTalent", Rarity = "Rare" },
      },
    },
  },
  MoonBeam = {
    Name = "MoonBeam",
    TraitName = "SpellMoonBeamTrait",
    GameStateRequirements = { Skip = true },
    MockTree = {},
  },
}

CreateTalentTree = function(spellData)
  return deepCopy(spellData.MockTree or {})
end

LootData = {}
UnitSetData = {}

local calls = {
  add = 0,
  remove = 0,
  unequip = {},
  talentCache = 0,
  talentAcquire = 0,
  rarity = 0,
  level = 0,
}
local nextId = 100
local failAddAfterMutation = false

local function rebuildDictionary()
  CurrentRun.Hero.TraitDictionary = {}
  for _, trait in ipairs(CurrentRun.Hero.Traits) do
    if trait.Name then
      CurrentRun.Hero.TraitDictionary[trait.Name] =
        CurrentRun.Hero.TraitDictionary[trait.Name] or {}
      table.insert(CurrentRun.Hero.TraitDictionary[trait.Name], trait)
    end
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

AddTraitToHero = function(args)
  calls.add = calls.add + 1
  local definition = TraitData[args.TraitName] or {}
  local trait = args.TraitData and deepCopy(args.TraitData) or deepCopy(definition)
  trait.Name = trait.Name or args.TraitName
  trait.Rarity = args.Rarity or trait.Rarity or "Common"
  trait.StackNum = trait.StackNum or 1
  trait.Slot = trait.Slot or definition.Slot
  trait.PreEquipWeapons = trait.PreEquipWeapons or deepCopy(definition.PreEquipWeapons)
  nextId = nextId + 1
  trait.Id = nextId
  table.insert(CurrentRun.Hero.Traits, trait)
  rebuildDictionary()
  for _, weaponName in ipairs(trait.PreEquipWeapons or {}) do
    MapState.EquippedWeapons[weaponName] = true
  end
  if failAddAfterMutation then
    failAddAfterMutation = false
    error("synthetic Selene post-mutation acknowledgement failure")
  end
  return trait
end

RemoveTrait = function(hero, name)
  calls.remove = calls.remove + 1
  for index, trait in ipairs(hero.Traits) do
    if trait.Name == name then
      table.remove(hero.Traits, index)
      rebuildDictionary()
      return
    end
  end
end

RemoveTraitData = function(hero, target)
  calls.remove = calls.remove + 1
  for index, trait in ipairs(hero.Traits) do
    if trait == target then
      table.remove(hero.Traits, index)
      rebuildDictionary()
      return
    end
  end
end

UnequipWeapon = function(args)
  calls.unequip[#calls.unequip + 1] = args.Name
  MapState.EquippedWeapons[args.Name] = nil
end

UpdateTalentPointInvestedCache = function()
  calls.talentCache = calls.talentCache + 1
end

IncreaseTraitLevel = function(trait, amount)
  calls.level = calls.level + 1
  trait.StackNum = (trait.StackNum or 1) + (amount or 1)
  return trait
end

AddRarityToTraits = function(_, args)
  calls.rarity = calls.rarity + 1
  local trait = assert(args.ForceUpgrade and args.ForceUpgrade[1])
  trait.Rarity = args.TargetRarityName
  return trait
end

CallFunctionName = function(name, args, trait)
  if name == "MockTalentAcquire" then
    calls.talentAcquire = calls.talentAcquire + 1
  end
end

IsGodTrait = function() return false end
GetAllUpgradeableGodTraits = function() return {} end

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

local function hasTrait(name)
  return HeroHasTrait(name)
end

local function resetSpell(spellName, investedNames)
  CurrentRun.Hero.Traits = {}
  CurrentRun.Hero.TraitDictionary = {}
  CurrentRun.Hero.SlottedSpell = deepCopy(SpellData[spellName])
  CurrentRun.Hero.SlottedSpell.Talents = CreateTalentTree(SpellData[spellName])
  CurrentRun.SpellCharge = 42
  CurrentRun.NumTalentPoints = 7
  MapState.EquippedWeapons = {}

  AddTraitToHero({ TraitName = SpellData[spellName].TraitName })
  for _, wanted in ipairs(investedNames or {}) do
    local investedOne = false
    for _, column in ipairs(CurrentRun.Hero.SlottedSpell.Talents) do
      if not investedOne then
        for _, node in pairs(column) do
          if node.Name == wanted and not node.Invested then
            node.Invested = true
            if HeroHasTrait(wanted) then
              IncreaseTraitLevel(GetHeroTrait(wanted))
            else
              AddTraitToHero({ TraitName = wanted, Rarity = node.Rarity, FromLoot = true })
            end
            investedOne = true
            break
          end
        end
      end
    end
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

-- Catalog: eight normal SpellData targets are eligible; hidden MoonBeam is not.
-- Talent targets come only from the current generated Path of Stars.
resetSpell("Polymorph", {})
check(findReward("selene:spell:Polymorph") ~= nil, "missing exact Polymorph Hex")
check(findReward("selene:spell:Meteor") ~= nil, "missing exact Meteor Hex")
check(findReward("selene:spell:MoonBeam") == nil, "hidden MoonBeam leaked into exact acquisition")
check(findReward("selene:talent:Polymorph:ChargeRegenTalent") ~= nil,
  "current Path of Stars talent missing")
check(findReward("selene:talent:Polymorph:MeteorDamageTalent") == nil,
  "talent from another spell leaked into current exact catalog")

-- With no slotted spell, main Hex targets remain available but no generated
-- Path of Stars talent can leak from the previous source.
CurrentRun.Hero.Traits = {}
CurrentRun.Hero.TraitDictionary = {}
CurrentRun.Hero.SlottedSpell = nil
MapState.EquippedWeapons = {}
check(findReward("selene:spell:Meteor") ~= nil, "main Hex disappeared without a slotted spell")
check(findReward("selene:talent:Polymorph:ChargeRegenTalent") == nil,
  "talent leaked into an empty/no-slotted-spell context")
resetSpell("Polymorph", {})

-- Exact talent acquisition invests a real current-tree node and adds the effect
-- without consuming native talent points.
do
  local beforePoints = CurrentRun.NumTalentPoints
  local result = M.dispatch("spawn_reward", {
    reward = "selene:talent:Polymorph:PolymorphDamageTalent",
    requestId = "selene-talent-exact",
    includeCatalogs = false,
  })
  check(hasTrait("PolymorphDamageTalent"), "exact talent did not mount its effect")
  local invested = 0
  for _, column in ipairs(CurrentRun.Hero.SlottedSpell.Talents) do
    for _, node in pairs(column) do
      if node.Name == "PolymorphDamageTalent" and node.Invested then invested = invested + 1 end
    end
  end
  eq(invested, 1, "exact talent did not invest one owner node")
  eq(CurrentRun.NumTalentPoints, beforePoints, "forced exact talent consumed native talent points")
  eq(result.actionOutcome, "completed", "exact talent outcome")
  check(findReward("selene:talent:Polymorph:PolymorphDamageTalent") == nil,
    "fully invested talent remained visible in the refreshed exact catalog")

  local afterFirstAdd = calls.add
  local duplicate = M.dispatch("spawn_reward", {
    reward = "selene:talent:Polymorph:PolymorphDamageTalent",
    requestId = "selene-talent-exact",
    includeCatalogs = false,
  })
  eq(calls.add, afterFirstAdd, "completed exact talent request replayed the mutation")
  check(duplicate.duplicate == true, "completed exact talent request did not return prior receipt")
end

-- Exact spell replacement tears down the previous owner: its main trait,
-- invested talents and pre-equipped weapons cannot survive the transition.
do
  resetSpell("Polymorph", { "ChargeRegenTalent" })
  local beforePoints = CurrentRun.NumTalentPoints
  local result = M.dispatch("spawn_reward", {
    reward = "selene:spell:Meteor",
    requestId = "selene-spell-replace",
    includeCatalogs = false,
  })
  eq(CurrentRun.Hero.SlottedSpell.Name, "Meteor", "SlottedSpell did not change")
  check(hasTrait("SpellMeteorTrait"), "new Hex trait not mounted")
  check(not hasTrait("SpellPolymorphTrait"), "old Hex trait survived replacement")
  check(not hasTrait("ChargeRegenTalent"), "old Path of Stars talent survived replacement")
  check(MapState.EquippedWeapons.WeaponSpellPolymorph == nil, "old spell weapon remained equipped")
  eq(CurrentRun.SpellCharge, 0, "spell charge was not reset on replacement")
  eq(CurrentRun.NumTalentPoints, beforePoints, "spell replacement rewrote talent-point progression")
  eq(result.actionOutcome, "completed", "spell replacement outcome")
end

-- A game callback that mutates and then fails acknowledgement leaves a coherent
-- Selene owner state, records outcome-unknown, and the same request is never
-- replayed.
do
  resetSpell("Polymorph", {})
  local beforeAdd = calls.add
  failAddAfterMutation = true
  expectError("MGT_OUTCOME_UNKNOWN", function()
    M.dispatch("spawn_reward", {
      reward = "selene:spell:Meteor",
      requestId = "selene-spell-outcome-unknown",
      includeCatalogs = false,
    })
  end)
  eq(calls.add, beforeAdd + 1, "outcome-unknown spell mutation did not run exactly once")
  check(CurrentRun.Hero.SlottedSpell and CurrentRun.Hero.SlottedSpell.Name == "Meteor",
    "mutated outcome-unknown spell lost its owner pointer")
  check(hasTrait("SpellMeteorTrait"), "mutated outcome-unknown spell lost its mounted trait")
  check(not hasTrait("SpellPolymorphTrait"), "old spell survived outcome-unknown replacement")
  local beforeReplay = calls.add
  expectError("Previous action outcome is unknown; do not retry", function()
    M.dispatch("spawn_reward", {
      reward = "selene:spell:Meteor",
      requestId = "selene-spell-outcome-unknown",
      includeCatalogs = false,
    })
  end)
  eq(calls.add, beforeReplay, "outcome-unknown Selene request replayed")
end

-- Mounted talent operations stay synchronized with the owning tree.
do
  resetSpell("Meteor", { "ChargeRegenTalent" })
  local row = assert(findRow("ChargeRegenTalent"), "missing mounted talent row")
  eq(row.family, "hexTalent", "talent family")
  eq(row.levelCapability, "increaseOne", "repeatable talent level capability")
  eq(row.rarityCapability, "setExact", "talent rarity capability")
  eq(row.removalCapability, "singleInstanceForce", "talent removal capability")

  local rarityParams = paramsFrom(row, "selene-talent-rarity")
  rarityParams.rarity = "Epic"
  M.dispatch("set_trait_rarity", rarityParams)
  eq(GetHeroTrait("ChargeRegenTalent").Rarity, "Epic", "runtime talent rarity")

  row = assert(findRow("ChargeRegenTalent"))
  local levelParams = paramsFrom(row, "selene-talent-level")
  levelParams.targetLevel = row.level + 1
  M.dispatch("set_trait_level", levelParams)
  local levelled = assert(GetHeroTrait("ChargeRegenTalent"))
  eq(levelled.StackNum, 2, "runtime talent level")
  local investedCount, commonNodes, rareNodes = 0, 0, 0
  for _, column in ipairs(CurrentRun.Hero.SlottedSpell.Talents) do
    for _, node in pairs(column) do
      if node.Name == "ChargeRegenTalent" and node.Invested then
        investedCount = investedCount + 1
        if node.Rarity == "Common" then commonNodes = commonNodes + 1 end
        if node.Rarity == "Rare" then rareNodes = rareNodes + 1 end
      end
    end
  end
  eq(investedCount, 2, "repeatable talent tree investment")
  eq(commonNodes, 1, "forced runtime rarity rewrote the first generated node")
  eq(rareNodes, 1, "repeatable level edit rewrote the next generated node rarity")
  eq(GetHeroTrait("ChargeRegenTalent").Rarity, "Epic",
    "runtime rarity did not survive a later repeatable level investment")
  check(calls.talentAcquire > 0, "repeatable talent acquire callback did not run")

  row = assert(findRow("ChargeRegenTalent"))
  M.dispatch("remove_trait", paramsFrom(row, "selene-talent-remove"))
  check(not hasTrait("ChargeRegenTalent"), "runtime talent survived removal")
  for _, column in ipairs(CurrentRun.Hero.SlottedSpell.Talents) do
    for _, node in pairs(column) do
      if node.Name == "ChargeRegenTalent" then
        check(not node.Invested, "removed talent remained invested in owner tree")
      end
    end
  end
end

-- Main Hex common level/rarity controls are not fabricated. Removal is owner
-- teardown and clears the SlottedSpell pointer plus linked talent state.
do
  resetSpell("Meteor", { "MeteorDamageTalent" })
  local row = assert(findRow("SpellMeteorTrait"), "missing main Hex row")
  eq(row.family, "hex", "main Hex family")
  eq(row.levelCapability, "none", "main Hex fabricated a level edit")
  eq(row.rarityCapability, "none", "main Hex fabricated a rarity edit")
  eq(row.removalCapability, "singleInstanceForce", "main Hex removal capability")

  M.dispatch("remove_trait", paramsFrom(row, "selene-spell-remove"))
  check(CurrentRun.Hero.SlottedSpell == nil, "SlottedSpell survived removal")
  check(not hasTrait("SpellMeteorTrait"), "main Hex trait survived removal")
  check(not hasTrait("MeteorDamageTalent"), "linked talent survived main Hex removal")
  check(MapState.EquippedWeapons.WeaponSpellMeteor == nil, "main Hex weapon survived removal")
  eq(CurrentRun.SpellCharge, 0, "spell charge survived main Hex removal")
end

print("hades2_selene_runtime_ok")
'''

with tempfile.TemporaryDirectory(prefix="mgt-selene-runtime-") as td:
    td = Path(td)
    harness = td / "selene_runtime.lua"
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
    assert "hades2_selene_runtime_ok" in proc.stdout, proc.stdout
    print(proc.stdout.strip())
