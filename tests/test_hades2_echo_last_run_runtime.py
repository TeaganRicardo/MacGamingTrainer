from pathlib import Path
import subprocess
import tempfile
import textwrap

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "Backend/games/hades2/runtime/hades.lua"
LUA = require_lua52("Echo previous-run exact acquisition runtime tests")

HARNESS = r'''
local runtimePath = assert(arg[1], "runtime path required")
local contractPath = assert(arg[2], "dispatch contract path required")

SessionState = {}
GameState = {
  Resources = {},
  LifetimeResourcesGained = {},
  LootPickups = {},
  RunHistory = {
    {
      TraitRarityCache = {
        ZeusBoon = "Rare",
        HeraBoon = "Common",
        ExcludedBoon = "Epic",
        NonGodBoon = "Epic",
      },
    },
  },
}
ResourceData = {}
ResourceDisplayOrderData = {}
TraitElementData = {}
LootData = {}
ConsumableData = {}
RewardStoreData = {}
ScreenData = {}
MapState = { RoomRequiredObjects = {} }
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
  LootChoiceHistory = {},
}

EnemyData = {
  NPC_Echo_01 = {
    SpeakerName = "Echo",
    Traits = { "EchoLastRunBoon", "EchoDoubleLevelBoon" },
  },
}
PresetEventArgs = {
  EchoBenefitChoices = {
    UpgradeOptions = {
      { ItemName = "EchoLastRunBoon", Type = "Trait" },
      { ItemName = "EchoDoubleLevelBoon", Type = "Trait" },
    },
  },
}
UnitSetData = {
  NPC_Echo = {
    NPC_Echo_01 = EnemyData.NPC_Echo_01,
  },
}
CodexOrdering = { OlympianGods = {}, Order = {} }

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
  ZeusBoon = {
    Name = "ZeusBoon",
    Slot = "Melee",
    RarityLevels = {
      Common = { Multiplier = 1.0 }, Rare = { Multiplier = 1.2 },
      Epic = { Multiplier = 1.5 }, Heroic = { Multiplier = 2.0 },
    },
  },
  HeraBoon = {
    Name = "HeraBoon",
    Slot = "Secondary",
    RarityLevels = {
      Common = { Multiplier = 1.0 }, Rare = { Multiplier = 1.2 },
      Epic = { Multiplier = 1.5 }, Heroic = { Multiplier = 2.0 },
    },
  },
  ExcludedBoon = {
    Name = "ExcludedBoon",
    ExcludeTraitFromLastRunBoonPool = true,
    RarityLevels = { Common = {}, Rare = {}, Epic = {} },
  },
  NonGodBoon = {
    Name = "NonGodBoon",
    RarityLevels = { Common = {}, Rare = {}, Epic = {} },
  },
  OccupiedMelee = {
    Name = "OccupiedMelee",
    Slot = "Melee",
    RarityLevels = { Common = {} },
  },
  ElementalRarityUpgradeBoon = {
    Name = "ElementalRarityUpgradeBoon",
    Activated = true,
    RarityLevels = { Common = {} },
  },
  EchoLastRunBoon = {
    Name = "EchoLastRunBoon",
    InheritFrom = { "BaseEcho" },
    AcquireFunctionName = "EchoLastRunBoon",
  },
  EchoDoubleLevelBoon = {
    Name = "EchoDoubleLevelBoon",
    InheritFrom = { "BaseEcho" },
  },
}

local calls = {
  add = 0,
  openMenu = 0,
  waitUntil = 0,
  processed = {},
}
local nextId = 100
local failAddAfterMutation = false

local function rebuildDictionary()
  CurrentRun.Hero.TraitDictionary = {}
  for _, trait in ipairs(CurrentRun.Hero.Traits) do
    CurrentRun.Hero.TraitDictionary[trait.Name] =
      CurrentRun.Hero.TraitDictionary[trait.Name] or {}
    table.insert(CurrentRun.Hero.TraitDictionary[trait.Name], trait)
  end
end

local function clearHero()
  CurrentRun.Hero.Traits = {}
  CurrentRun.Hero.TraitDictionary = {}
end

local function mount(name, extra)
  local trait = deepCopy(assert(TraitData[name]))
  for key, value in pairs(extra or {}) do trait[key] = value end
  nextId = nextId + 1
  trait.Id = nextId
  trait.StackNum = trait.StackNum or 1
  trait.Rarity = trait.Rarity or "Common"
  table.insert(CurrentRun.Hero.Traits, trait)
  rebuildDictionary()
  return trait
end

HeroHasTrait = function(name)
  local values = CurrentRun.Hero.TraitDictionary[name]
  return type(values) == "table" and #values > 0
end

GetHeroTrait = function(name)
  local values = CurrentRun.Hero.TraitDictionary[name]
  return type(values) == "table" and values[1] or nil
end

HeroSlotFilled = function(slot)
  for _, trait in ipairs(CurrentRun.Hero.Traits) do
    if trait.Slot == slot then return true end
  end
  return false
end

IsGodTrait = function(name, args)
  if name == "ZeusBoon" or name == "HeraBoon" or name == "ExcludedBoon" then
    return args and args.ForShop == true and args.ForLastRunBoon == true
  end
  return false
end

IsTraitEligible = function(traitData)
  return type(traitData) == "table" and traitData.Blocked ~= true
end

GetProcessedTraitData = function(args)
  local source = TraitData[args.TraitName]
  if type(source) ~= "table" then return nil end
  local result = deepCopy(source)
  result.Name = args.TraitName
  result.Rarity = args.Rarity or "Common"
  result.StackNum = args.StackNum or 1
  calls.processed[#calls.processed + 1] = { name = result.Name, rarity = result.Rarity }
  return result
end

AddTraitToHero = function(args)
  calls.add = calls.add + 1
  local trait = args.TraitData and deepCopy(args.TraitData) or deepCopy(assert(TraitData[args.TraitName]))
  trait.Name = trait.Name or args.TraitName
  trait.Rarity = args.Rarity or trait.Rarity or "Common"
  trait.StackNum = trait.StackNum or 1
  nextId = nextId + 1
  trait.Id = nextId
  table.insert(CurrentRun.Hero.Traits, trait)
  rebuildDictionary()
  if failAddAfterMutation then
    failAddAfterMutation = false
    error("synthetic Echo post-mutation acknowledgement failure")
  end
  return trait
end

GetLootSourceName = function() return "ZeusUpgrade" end
LoadPackages = function() end
LoadVoiceBanks = function() end
OpenUpgradeChoiceMenu = function()
  calls.openMenu = calls.openMenu + 1
  error("exact Echo acquisition must not open a choice menu")
end
waitUntil = function()
  calls.waitUntil = calls.waitUntil + 1
  error("exact Echo acquisition must not wait for a choice menu")
end
GetAllUpgradeableGodTraits = function() return {} end
AddRarityToTraits = function(_, args)
  local trait = assert(args.ForceUpgrade and args.ForceUpgrade[1])
  trait.Rarity = args.TargetRarityName
  return trait
end
IncreaseTraitLevel = function(trait, amount)
  trait.StackNum = (trait.StackNum or 1) + (amount or 1)
  return trait
end
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

-- Exact targets are concrete previous-run boons, not the EchoLastRunBoon shell.
check(findReward("echo:lastRun:ZeusBoon") ~= nil, "previous-run Zeus exact target missing")
check(findReward("echo:lastRun:HeraBoon") ~= nil, "previous-run Hera exact target missing")
check(findReward("echo:lastRun:ExcludedBoon") == nil, "excluded previous-run boon leaked into catalog")
check(findReward("echo:lastRun:NonGodBoon") == nil, "non-God previous-run trait leaked into catalog")
check(findReward("trait:EchoLastRunBoon") == nil, "EchoLastRunBoon shell leaked as a direct exact target")

-- Direct exact materialization uses the previous-run rarity and never opens or
-- waits for Echo's native random choice screen.
local result = M.dispatch("spawn_reward", {
  reward = "echo:lastRun:ZeusBoon",
  requestId = "echo-last-run-zeus",
  includeCatalogs = false,
})
check(HeroHasTrait("ZeusBoon"), "Echo exact target did not materialize the actual boon")
check(not HeroHasTrait("EchoLastRunBoon"), "Echo shell trait was mounted instead of the actual boon")
eq(GetHeroTrait("ZeusBoon").Rarity, "Rare", "previous-run rarity was not preserved")
eq(calls.openMenu, 0, "exact Echo target opened the random/native choice menu")
eq(calls.waitUntil, 0, "exact Echo target waited on a nonexistent choice screen")
check(result.lootObjectId == nil, "Echo exact target leaked a trait object into action receipt")
local row = assert(findRow("ZeusBoon"), "materialized Echo boon missing from current-run manager")
check(row.family ~= "Echo", "materialized previous-run boon remained owned by Echo shell")

local beforeDuplicate = calls.add
local duplicate = M.dispatch("spawn_reward", {
  reward = "echo:lastRun:ZeusBoon",
  requestId = "echo-last-run-zeus",
  includeCatalogs = false,
})
check(duplicate.duplicate == true, "completed Echo exact request did not return prior receipt")
eq(calls.add, beforeDuplicate, "completed Echo exact request replayed")

-- Rarity floor applies to a Common previous-run target exactly as native Echo
-- does, without mutating the stored previous-run history.
clearHero()
mount("ElementalRarityUpgradeBoon", { Activated = true })
M.dispatch("spawn_reward", {
  reward = "echo:lastRun:HeraBoon",
  requestId = "echo-last-run-floor",
  includeCatalogs = false,
})
eq(GetHeroTrait("HeraBoon").Rarity, "Rare", "active rarity floor did not raise Common to Rare")
eq(GameState.RunHistory[1].TraitRarityCache.HeraBoon, "Common", "Echo exact mutated previous-run history")

-- A previously rendered target fails closed if its current slot becomes occupied.
clearHero()
check(findReward("echo:lastRun:ZeusBoon") ~= nil, "stale-slot target missing before transition")
mount("OccupiedMelee")
local beforeStale = calls.add
expectError("Echo previous-run boon is no longer eligible", function()
  M.dispatch("spawn_reward", {
    reward = "echo:lastRun:ZeusBoon",
    requestId = "echo-stale-slot",
    includeCatalogs = false,
  })
end)
eq(calls.add, beforeStale, "stale Echo target reached mutation")

-- The source is the last completed run. Changing/removing that source invalidates
-- cached exact targets before a new request can mutate.
clearHero()
check(findReward("echo:lastRun:ZeusBoon") ~= nil, "source-change target missing before transition")
GameState.RunHistory = { { TraitRarityCache = { HeraBoon = "Epic" } } }
check(findReward("echo:lastRun:ZeusBoon") == nil, "removed previous-run target survived catalog refresh")
local beforeSourceChange = calls.add
expectError("Echo previous-run boon is no longer eligible", function()
  M.dispatch("spawn_reward", {
    reward = "echo:lastRun:ZeusBoon",
    requestId = "echo-stale-source",
    includeCatalogs = false,
  })
end)
eq(calls.add, beforeSourceChange, "removed previous-run target reached mutation")

-- Catalog removal does not erase the action ledger. The original completed
-- request must still return its prior receipt without rerunning or revalidating.
local beforeHistoricalReplay = calls.add
local historicalDuplicate = M.dispatch("spawn_reward", {
  reward = "echo:lastRun:ZeusBoon",
  requestId = "echo-last-run-zeus",
  includeCatalogs = false,
})
check(historicalDuplicate.duplicate == true, "historical Echo request lost its completed receipt")
eq(calls.add, beforeHistoricalReplay, "historical Echo completed request replayed after source change")

-- Restore source and prove mutation-after-commit failure becomes outcome unknown
-- and is never replayed.
GameState.RunHistory = {
  { TraitRarityCache = { ZeusBoon = "Rare", HeraBoon = "Common" } },
}
clearHero()
failAddAfterMutation = true
local beforeUnknown = calls.add
expectError("MGT_OUTCOME_UNKNOWN", function()
  M.dispatch("spawn_reward", {
    reward = "echo:lastRun:ZeusBoon",
    requestId = "echo-outcome-unknown",
    includeCatalogs = false,
  })
end)
eq(calls.add, beforeUnknown + 1, "outcome-unknown Echo mutation did not run exactly once")
check(HeroHasTrait("ZeusBoon"), "outcome-unknown Echo mutation lost the materialized boon")
local beforeReplay = calls.add
expectError("Previous action outcome is unknown; do not retry", function()
  M.dispatch("spawn_reward", {
    reward = "echo:lastRun:ZeusBoon",
    requestId = "echo-outcome-unknown",
    includeCatalogs = false,
  })
end)
eq(calls.add, beforeReplay, "outcome-unknown Echo request replayed")

-- disable/reset never undoes a one-shot exact acquisition.
M.dispatch("disable_all", { includeCatalogs = false })
check(HeroHasTrait("ZeusBoon"), "disable_all removed one-shot Echo previous-run acquisition")

print("hades2_echo_last_run_runtime_ok")
'''

with tempfile.TemporaryDirectory(prefix="mgt-echo-last-run-") as td:
    td = Path(td)
    harness = td / "echo_last_run_runtime.lua"
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
    assert "hades2_echo_last_run_runtime_ok" in proc.stdout, proc.stdout
    print(proc.stdout.strip())
