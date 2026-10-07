from pathlib import Path
import subprocess
import tempfile
import textwrap

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52, terminal_case_sources

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
  LootPickups = {},
  WorldUpgrades = { Costume_Default = true },
}
ResourceData = {}
ResourceDisplayOrderData = {}
TraitElementData = {}
LootData = {}
ConsumableData = {}
RewardStoreData = {}
ScreenData = {}
MapState = {
  RoomRequiredObjects = {},
  HealthBufferSources = {},
  TemporaryHealthBufferSources = {},
}
LootObjects = {}
UpdateTimers = function() end
FrameState = {}

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
  },
  CurrentRoom = {},
  NumRerolls = 0,
  SpellCharge = 0,
  PickedTraits = {},
}

EnemyData = {
  NPC_Arachne_01 = {
    SpeakerName = "Arachne",
    Traits = { "AgilityCostume", "ManaCostume" },
  },
}
PresetEventArgs = {
  ArachneCostumeChoices = {
    UpgradeOptions = {
      { ItemName = "AgilityCostume", Type = "Trait" },
      { ItemName = "ManaCostume", Type = "Trait" },
    },
  },
}
UnitSetData = {
  NPC_Arachne = {
    NPC_Arachne_01 = EnemyData.NPC_Arachne_01,
  },
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
  AgilityCostume = {
    Name = "AgilityCostume",
    InheritFrom = { "CostumeTrait", "ForceCommonAppearanceTrait" },
    CostumeTrait = true,
    Costume = "Texture_Agility",
    SetupFunction = {
      Name = "CostumeArmor",
      Args = { Source = "Robe", BaseAmount = 20 },
    },
    RarityLevels = { Common = { Multiplier = 1.0 }, Rare = { Multiplier = 1.5 } },
  },
  ManaCostume = {
    Name = "ManaCostume",
    InheritFrom = { "CostumeTrait", "ForceCommonAppearanceTrait" },
    CostumeTrait = true,
    Costume = "Texture_Mana",
    SetupFunction = {
      Name = "CostumeArmor",
      Args = { Source = "Robe", BaseAmount = 30 },
    },
    RarityLevels = { Common = { Multiplier = 1.0 }, Rare = { Multiplier = 1.5 } },
  },
}
CostumeData = {
  Costume_Default = { GrannyTexture = "" },
}

local calls = {
  add = 0,
  remove = 0,
  setupCostume = 0,
  thingProperty = 0,
}
local nextId = 100
local failSetupAfterMutation = false

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

GetHeroTraitValues = function(key)
  local result = {}
  if key ~= "Costume" then return result end
  for _, trait in ipairs(CurrentRun.Hero.Traits) do
    if trait.Costume ~= nil then result[#result + 1] = trait.Costume end
  end
  return result
end

SetThingProperty = function(args)
  calls.thingProperty = calls.thingProperty + 1
  if args.Property == "GrannyTexture" then
    CurrentRun.Hero.ActiveCostume = args.Value
  end
end

SetupCostume = function()
  calls.setupCostume = calls.setupCostume + 1
  local default = CostumeData.Costume_Default
  if GameState.WorldUpgrades.Costume_Default and default and default.GrannyTexture ~= nil then
    SetThingProperty({
      Property = "GrannyTexture",
      Value = default.GrannyTexture,
      DestinationId = CurrentRun.Hero.ObjectId,
    })
  end
  local costumes = GetHeroTraitValues("Costume")
  if costumes[1] ~= nil then
    SetThingProperty({
      Property = "GrannyTexture",
      Value = costumes[1],
      DestinationId = CurrentRun.Hero.ObjectId,
    })
  end
  if failSetupAfterMutation then
    failSetupAfterMutation = false
    error("synthetic Arachne post-mutation setup failure")
  end
end

local function refreshHealthBuffer()
  local total = 0
  for _, amount in pairs(MapState.HealthBufferSources) do total = total + amount end
  CurrentRun.Hero.HealthBuffer = total
end

AddTraitToHero = function(args)
  calls.add = calls.add + 1
  local definition = TraitData[args.TraitName]
  local trait = args.TraitData and deepCopy(args.TraitData) or deepCopy(assert(definition))
  trait.Name = trait.Name or args.TraitName
  trait.Rarity = args.Rarity or trait.Rarity or "Common"
  trait.StackNum = trait.StackNum or 1
  nextId = nextId + 1
  trait.Id = nextId
  table.insert(CurrentRun.Hero.Traits, trait)
  rebuildDictionary()
  local setup = trait.SetupFunction
  if type(setup) == "table" and setup.Name == "CostumeArmor" then
    trait.CurrentArmor = trait.CurrentArmor or setup.Args.BaseAmount
    MapState.HealthBufferSources[trait.Name] = trait.CurrentArmor
    refreshHealthBuffer()
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
  MapState.HealthBufferSources[target.Name] = nil
  refreshHealthBuffer()
  rebuildDictionary()
end

AddRarityToTraits = function(_, args)
  local trait = assert(args.ForceUpgrade and args.ForceUpgrade[1])
  trait.Rarity = args.TargetRarityName
  return trait
end
IncreaseTraitLevel = function(trait, amount)
  trait.StackNum = (trait.StackNum or 1) + (amount or 1)
  return trait
end
GetAllUpgradeableGodTraits = function() return {} end
IsGodTrait = function() return false end
GetLootSourceName = function() return "" end
UpdateTraitNumber = function() end

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

-- Exact acquisition is projected from the real Arachne choice family.
check(findReward("trait:AgilityCostume") ~= nil, "Arachne exact costume missing")
check(findReward("trait:ManaCostume") ~= nil, "second Arachne exact costume missing")

local result = M.dispatch("spawn_reward", {
  reward = "trait:AgilityCostume",
  requestId = "arachne-costume-acquire",
  includeCatalogs = false,
})
check(HeroHasTrait("AgilityCostume"), "exact costume did not mount trait")
eq(CurrentRun.Hero.ActiveCostume, "Texture_Agility", "exact costume did not apply appearance")
eq(CurrentRun.Hero.HealthBuffer, 20, "exact costume did not apply armor owner state")
check(result.lootObjectId == nil, "costume exact acquisition leaked a trait object")

local duplicate = M.dispatch("spawn_reward", {
  reward = "trait:AgilityCostume",
  requestId = "arachne-costume-acquire",
  includeCatalogs = false,
})
check(duplicate.duplicate == true, "costume acquisition replay did not deduplicate")

local row = assert(findRow("AgilityCostume"), "mounted costume row missing")
eq(row.family, "costume", "Arachne costume family")
eq(row.levelCapability, "none", "costume fabricated level editing")
eq(row.rarityCapability, "none", "costume fabricated rarity editing")
eq(row.removalCapability, "singleInstanceForce", "costume removal capability")

-- Capturing a mounted-row identity before replacement must become stale after
-- the selected costume is replaced by another valid Arachne owner target.
local staleAgilityRow = row

-- Forced exact acquisition defines replacement semantics for the non-native
-- case where another Arachne costume is still mounted. The shared "Robe"
-- source must transfer to the newly selected owner without stacking armor or
-- leaving the previous appearance/trait alive.
local replaceResult = M.dispatch("spawn_reward", {
  reward = "trait:ManaCostume",
  requestId = "arachne-costume-replace",
  includeCatalogs = false,
})
check(not HeroHasTrait("AgilityCostume"), "old costume survived exact replacement")
check(HeroHasTrait("ManaCostume"), "replacement costume did not mount")
check(MapState.HealthBufferSources.AgilityCostume == nil, "old costume armor source survived replacement")
eq(CurrentRun.Hero.HealthBuffer, 30, "replacement did not own the expected armor")
eq(CurrentRun.Hero.ActiveCostume, "Texture_Mana", "replacement did not own appearance")
check(replaceResult.lootObjectId == nil, "costume replacement leaked a trait object")

expectError("no longer present", function()
  M.dispatch("remove_trait", paramsFrom(staleAgilityRow, "arachne-stale-row"))
end)

-- A target that was visible in a previously rendered catalog fails closed if
-- the native Arachne choice context changes before commit.
PresetEventArgs.ArachneCostumeChoices.UpgradeOptions = {
  { ItemName = "ManaCostume", Type = "Trait" },
}
local beforeMissingContext = calls.add
expectError("Exact costume target is unavailable", function()
  M.dispatch("spawn_reward", {
    reward = "trait:AgilityCostume",
    requestId = "arachne-missing-owner-context",
    includeCatalogs = false,
  })
end)
eq(calls.add, beforeMissingContext, "missing owner context reached costume mutation")
PresetEventArgs.ArachneCostumeChoices.UpgradeOptions = {
  { ItemName = "AgilityCostume", Type = "Trait" },
  { ItemName = "ManaCostume", Type = "Trait" },
}

-- disable_all is not an undo path for one-shot exact acquisition.
M.dispatch("disable_all", { includeCatalogs = false })
check(HeroHasTrait("ManaCostume"), "disable_all removed one-shot costume acquisition")
eq(CurrentRun.Hero.HealthBuffer, 30, "disable_all desynchronized costume armor")
eq(CurrentRun.Hero.ActiveCostume, "Texture_Mana", "disable_all desynchronized costume appearance")

-- If native presentation/setup mutates and then fails acknowledgement, owner
-- state stays coherent, the action is outcome-unknown, and the same request
-- is never replayed.
failSetupAfterMutation = true
local beforeUnknownAdd = calls.add
expectError("MGT_OUTCOME_UNKNOWN", function()
  M.dispatch("spawn_reward", {
    reward = "trait:AgilityCostume",
    requestId = "arachne-outcome-unknown",
    includeCatalogs = false,
  })
end)
eq(calls.add, beforeUnknownAdd + 1, "outcome-unknown costume mutation did not run exactly once")
check(HeroHasTrait("AgilityCostume"), "outcome-unknown replacement lost new costume owner")
check(not HeroHasTrait("ManaCostume"), "outcome-unknown replacement left old costume owner")
eq(CurrentRun.Hero.HealthBuffer, 20, "outcome-unknown replacement left incoherent armor")
eq(CurrentRun.Hero.ActiveCostume, "Texture_Agility", "outcome-unknown replacement left incoherent appearance")
local beforeReplay = calls.add
expectError("Previous action outcome is unknown; do not retry", function()
  M.dispatch("spawn_reward", {
    reward = "trait:AgilityCostume",
    requestId = "arachne-outcome-unknown",
    includeCatalogs = false,
  })
end)
eq(calls.add, beforeReplay, "outcome-unknown costume request replayed")

-- Explicit removal restores the default appearance and tears down the selected
-- costume's armor source through the owner lifecycle.
row = assert(findRow("ManaCostume"), "replacement costume row missing")
local beforeSetup = calls.setupCostume
M.dispatch("remove_trait", paramsFrom(row, "arachne-costume-remove"))
check(not HeroHasTrait("ManaCostume"), "costume trait survived removal")
check(MapState.HealthBufferSources.ManaCostume == nil, "costume armor source survived removal")
eq(CurrentRun.Hero.HealthBuffer, 0, "costume armor survived removal")
eq(CurrentRun.Hero.ActiveCostume, "", "costume appearance did not return to default owner")
eq(calls.setupCostume, beforeSetup + 1, "costume removal did not refresh native appearance owner")

print("hades2_arachne_costume_runtime_ok")
'''

TERMINAL_CASES = [
    ('-- If native presentation/setup mutates and then fails acknowledgement', '-- Explicit removal restores the default appearance'),
]

with tempfile.TemporaryDirectory(prefix="mgt-arachne-costume-") as td:
    td = Path(td)
    for source in terminal_case_sources(HARNESS, TERMINAL_CASES, 'hades2_arachne_costume_runtime_ok'):
        harness = td / "arachne_costume_runtime.lua"
        harness.write_text(textwrap.dedent(source), encoding="utf-8")
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
        assert "hades2_arachne_costume_runtime_ok" in proc.stdout, proc.stdout
        print(proc.stdout.strip())
