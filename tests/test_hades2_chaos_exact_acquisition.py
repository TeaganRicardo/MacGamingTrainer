import subprocess
import tempfile
import textwrap
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "Backend/games/hades2/runtime/hades.lua"
LUA = require_lua52("Chaos exact-acquisition runtime behavior tests")

HARNESS = r'''
local runtimePath = assert(arg[1], "runtime path required")
local contractPath = assert(arg[2], "dispatch contract path required")

SessionState = {}
SessionMapState = {}
GameState = { Resources = {}, LifetimeResourcesGained = {}, RunHistory = {}, TraitsTaken = {} }
ResourceData = {}
ResourceDisplayOrderData = {}
TraitElementData = {}
EnemyData = {}
PresetEventArgs = {}
ScreenData = {}
MapState = { RoomRequiredObjects = {} }
LootObjects = {}
ConsumableData = {}
RewardStoreData = {}
UpdateTimers = function() end
CodexOrdering = { OlympianGods = {}, Order = {} }

CurrentRun = {
  Hero = {
    ObjectId = 1, Health = 100, MaxHealth = 100, Mana = 50, MaxMana = 50,
    HealthBuffer = 0, Elements = {}, Traits = {}, TraitDictionary = {},
    BoonData = { GameStateRequirements = {}, ReplaceChance = 0 },
  },
  CurrentRoom = {},
  NumRerolls = 0, SpellCharge = 0, PickedTraits = {}, BannedTraits = {},
}

TraitData = {
  ChaosWeaponBlessing = {
    Name = "ChaosWeaponBlessing",
    RarityLevels = { Common = {}, Rare = {}, Epic = {}, Heroic = {} },
  },
  ChaosHealthBlessing = {
    Name = "ChaosHealthBlessing",
    RarityLevels = { Common = {}, Rare = {}, Epic = {}, Heroic = {} },
  },
  ChaosNoMoneyCurse = { Name = "ChaosNoMoneyCurse", RemainingUses = 3 },
  ChaosDamageCurse = { Name = "ChaosDamageCurse", RemainingUses = 4 },
}

LootData = {
  TrialUpgrade = {
    Name = "TrialUpgrade",
    TransformingTraits = true,
    PermanentTraits = { "ChaosWeaponBlessing", "ChaosHealthBlessing" },
    TemporaryTraits = { "ChaosNoMoneyCurse", "ChaosDamageCurse" },
  },
}
UnitSetData = {}

local calls = { setTraits = 0, add = 0 }
local nextId = 100
local ineligibleTrait = nil
local failAddAfterMutation = false

local function clone(value)
  if type(value) ~= "table" then return value end
  local result = {}
  for key, item in pairs(value) do result[key] = clone(item) end
  return result
end
DeepCopyTable = clone
ShallowCopyTable = clone

IsTraitEligible = function(_) return true end
GetEligibleTransformingTrait = function(names)
  local result = {}
  for _, name in ipairs(names or {}) do
    if name ~= ineligibleTrait then result[#result + 1] = name end
  end
  return result
end
HeroHasTrait = function(name)
  for _, trait in ipairs(CurrentRun.Hero.Traits) do
    if trait.Name == name then return true end
  end
  return false
end
IsGodTrait = function() return false end
GetAllUpgradeableGodTraits = function() return {} end

SetTraitsOnLoot = function(loot)
  calls.setTraits = calls.setTraits + 1
  local blessing = assert(loot.PermanentTraits and loot.PermanentTraits[1], "missing blessing pool")
  local curse = assert(loot.TemporaryTraits and loot.TemporaryTraits[1], "missing curse pool")
  loot.UpgradeOptions = {
    {
      ItemName = blessing,
      SecondaryItemName = curse,
      Type = "TransformingTrait",
      Rarity = "Rare",
    },
  }
  return loot.UpgradeOptions
end

GetProcessedTraitData = function(args)
  local base = assert(TraitData[args.TraitName], "unknown processed trait")
  local value = clone(base)
  value.Name = args.TraitName
  value.Rarity = args.Rarity or "Common"
  value.StackNum = args.StackNum or 1
  return value
end

GetExtractData = function() return {} end
SetTraitTextData = function() end

AddTraitToHero = function(args)
  calls.add = calls.add + 1
  local value = args.TraitData and clone(args.TraitData)
    or GetProcessedTraitData({ TraitName = args.TraitName, Rarity = "Common" })
  nextId = nextId + 1
  value.Id = value.Id or nextId
  value.FromLootObserved = args.FromLoot == true
  CurrentRun.Hero.Traits[#CurrentRun.Hero.Traits + 1] = value
  if failAddAfterMutation then
    failAddAfterMutation = false
    error("synthetic Chaos pair post-mutation acknowledgement failure")
  end
  return value
end

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
local function findReward(id)
  local state = M.dispatch("status", { includeCatalogs = true })
  for _, row in ipairs(state.rewards or {}) do
    if row.id == id then return row end
  end
  fail("missing reward " .. tostring(id))
end
local function resetTraits()
  CurrentRun.Hero.Traits = {}
  CurrentRun.Hero.TraitDictionary = {}
end

-- The target-build TrialUpgrade pools are projected as recognizable exact
-- targets, but acquisitionMode remains backend-only routing metadata.
local blessingRow = findReward("chaos:blessing:ChaosHealthBlessing")
eq(blessingRow.group, "exact", "Chaos blessing group")
eq(blessingRow.trait, "ChaosHealthBlessing", "Chaos blessing target")
eq(blessingRow.sourceId, "Chaos", "Chaos blessing source")
eq(blessingRow.acquisitionMode, "chaosBlessing", "Chaos blessing route")

local curseRow = findReward("chaos:curse:ChaosDamageCurse")
eq(curseRow.group, "exact", "Chaos curse group")
eq(curseRow.trait, "ChaosDamageCurse", "Chaos curse target")
eq(curseRow.acquisitionMode, "chaosCurse", "Chaos curse route")

-- Selecting an exact blessing still acquires through one native-shaped
-- TransformingTrait pair. The selected blessing is queued on the curse rather
-- than directly mounted.
resetTraits()
local beforeAdd = calls.add
M.dispatch("spawn_reward", {
  reward = blessingRow.id,
  requestId = "chaos-exact-blessing",
  includeCatalogs = false,
})
eq(calls.add, beforeAdd + 1, "Chaos blessing acquisition added wrong number of runtime traits")
eq(#CurrentRun.Hero.Traits, 1, "Chaos exact acquisition mounted more than the curse")
local mounted = CurrentRun.Hero.Traits[1]
eq(mounted.Name, "ChaosNoMoneyCurse", "Chaos blessing target bypassed paired curse")
check(type(mounted.OnExpire) == "table" and type(mounted.OnExpire.TraitData) == "table",
  "Chaos curse lost queued blessing")
eq(mounted.OnExpire.TraitData.Name, "ChaosHealthBlessing", "wrong queued exact blessing")
eq(mounted.Rarity, "Rare", "Chaos curse rarity drifted")
eq(mounted.OnExpire.TraitData.Rarity, "Rare", "queued Chaos blessing rarity drifted")
check(mounted.FromLootObserved, "Chaos pair did not preserve FromLoot acquisition")

-- Selecting an exact curse mirrors the same native pair shape with an eligible
-- blessing counterpart; the requested curse itself is the mounted phase.
resetTraits()
M.dispatch("spawn_reward", {
  reward = curseRow.id,
  requestId = "chaos-exact-curse",
  includeCatalogs = false,
})
mounted = CurrentRun.Hero.Traits[1]
eq(mounted.Name, "ChaosDamageCurse", "wrong exact Chaos curse mounted")
check(type(mounted.OnExpire) == "table" and type(mounted.OnExpire.TraitData) == "table",
  "exact Chaos curse has no queued blessing")
eq(mounted.OnExpire.TraitData.Name, "ChaosWeaponBlessing", "Chaos curse counterpart was not native-pool blessing")

-- #347: the primary product route carries both identities in one one-shot
-- request. Runtime must mount exactly the selected curse and queue exactly the
-- selected blessing, with the same native-shaped metadata as TrialUpgrade.
resetTraits()
local beforePairAdd = calls.add
local pair = M.dispatch("acquire_chaos_pair", {
  blessing = "ChaosHealthBlessing",
  curse = "ChaosDamageCurse",
  requestId = "chaos-pair-exact",
  includeCatalogs = false,
})
eq(calls.add, beforePairAdd + 1, "Chaos pair added wrong number of runtime traits")
eq(#CurrentRun.Hero.Traits, 1, "Chaos pair mounted more than one phase")
mounted = CurrentRun.Hero.Traits[1]
eq(mounted.Name, "ChaosDamageCurse", "Chaos pair mounted the wrong curse")
eq(mounted.OnExpire.TraitData.Name, "ChaosHealthBlessing", "Chaos pair queued the wrong blessing")
eq(mounted.TraitTitle, "ChaosCombo_ChaosDamageCurse_ChaosHealthBlessing", "Chaos pair title drifted")
check(mounted.FromLootObserved, "Chaos pair did not preserve FromLoot")
eq(pair.actionOutcome, "completed", "Chaos pair did not complete")

local duplicate = M.dispatch("acquire_chaos_pair", {
  blessing = "ChaosHealthBlessing",
  curse = "ChaosDamageCurse",
  requestId = "chaos-pair-exact",
  includeCatalogs = false,
})
check(duplicate.duplicate == true, "Chaos pair duplicate request was not deduplicated")
eq(calls.add, beforePairAdd + 1, "Chaos pair duplicate request mutated twice")

-- Current-pool and eligibility checks are both immediate fail-closed gates.
resetTraits()
ineligibleTrait = "ChaosHealthBlessing"
local beforeIneligible = calls.add
local okIneligible = pcall(M.dispatch, "acquire_chaos_pair", {
  blessing = "ChaosHealthBlessing",
  curse = "ChaosDamageCurse",
  requestId = "chaos-pair-ineligible",
  includeCatalogs = false,
})
check(not okIneligible, "ineligible Chaos pair unexpectedly succeeded")
eq(calls.add, beforeIneligible, "ineligible Chaos pair mutated")
ineligibleTrait = nil

local originalTemporary = LootData.TrialUpgrade.TemporaryTraits
LootData.TrialUpgrade.TemporaryTraits = { "ChaosNoMoneyCurse" }
local beforeRemoved = calls.add
local okRemoved = pcall(M.dispatch, "acquire_chaos_pair", {
  blessing = "ChaosHealthBlessing",
  curse = "ChaosDamageCurse",
  requestId = "chaos-pair-removed",
  includeCatalogs = false,
})
check(not okRemoved, "removed Chaos curse unexpectedly succeeded")
eq(calls.add, beforeRemoved, "removed Chaos curse mutated")
LootData.TrialUpgrade.TemporaryTraits = originalTemporary

-- If mutation happened but acknowledgement became unknown, the same request id
-- must never replay.
resetTraits()
failAddAfterMutation = true
local beforeUnknown = calls.add
local okUnknown, unknownMessage = pcall(M.dispatch, "acquire_chaos_pair", {
  blessing = "ChaosWeaponBlessing",
  curse = "ChaosNoMoneyCurse",
  requestId = "chaos-pair-unknown",
  includeCatalogs = false,
})
check(not okUnknown and string.find(tostring(unknownMessage), "MGT_OUTCOME_UNKNOWN", 1, true),
  "Chaos pair did not surface outcome-unknown")
eq(calls.add, beforeUnknown + 1, "Chaos outcome-unknown mutation did not execute exactly once")
local okReplay, replayMessage = pcall(M.dispatch, "acquire_chaos_pair", {
  blessing = "ChaosWeaponBlessing",
  curse = "ChaosNoMoneyCurse",
  requestId = "chaos-pair-unknown",
  includeCatalogs = false,
})
check(not okReplay and string.find(tostring(replayMessage), "do not retry", 1, true),
  "Chaos outcome-unknown request was replayable")
eq(calls.add, beforeUnknown + 1, "Chaos outcome-unknown request replayed")

print("hades2_chaos_exact_acquisition_runtime_ok")
'''

with tempfile.TemporaryDirectory(prefix="mgt-chaos-exact-") as td:
    td = Path(td)
    harness = td / "chaos_exact.lua"
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
    if "hades2_chaos_exact_acquisition_runtime_ok" not in proc.stdout:
        raise SystemExit(proc.stdout)

print("hades2_chaos_exact_acquisition_ok")
