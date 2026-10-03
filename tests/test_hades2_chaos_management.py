import subprocess
import tempfile
import textwrap
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "Backend/games/hades2/runtime/hades.lua"
LUA = require_lua52("Chaos mounted-lifecycle runtime behavior tests")

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
UnitSetData = {}

CurrentRun = {
  Hero = {
    ObjectId = 1, Health = 100, MaxHealth = 100, Mana = 50, MaxMana = 50,
    HealthBuffer = 0, Elements = {}, Traits = {}, TraitDictionary = {},
    BoonData = { GameStateRequirements = {}, ReplaceChance = 0 },
  },
  CurrentRoom = {},
  NumRerolls = 0, SpellCharge = 0, PickedTraits = {}, BannedTraits = {},
}

local rarityValue = { Common = 1, Rare = 2, Epic = 3, Heroic = 4 }
TraitData = {
  ChaosDamageCurse = { Name = "ChaosDamageCurse" },
  ChaosHealthCurse = { Name = "ChaosHealthCurse" },
  ChaosHealthBlessing = {
    Name = "ChaosHealthBlessing",
    RarityLevels = { Common = {}, Rare = {}, Epic = {}, Heroic = {} },
  },
  ChaosWeaponBlessing = {
    Name = "ChaosWeaponBlessing",
    RarityLevels = { Common = {}, Rare = {}, Epic = {}, Heroic = {} },
  },
}
LootData = {
  TrialUpgrade = {
    Name = "TrialUpgrade", TransformingTraits = true,
    PermanentTraits = { "ChaosHealthBlessing", "ChaosWeaponBlessing" },
    TemporaryTraits = { "ChaosDamageCurse", "ChaosHealthCurse" },
  },
}

local nextId = 900
local addCalls = 0
local fromLootCalls = 0
local failRemoveAfterMutation = false

local function clone(value)
  if type(value) ~= "table" then return value end
  local result = {}
  for key, item in pairs(value) do result[key] = clone(item) end
  return result
end
DeepCopyTable = clone
ShallowCopyTable = clone

local function processed(name, rarity, stack)
  local definition = assert(TraitData[name], "missing trait definition " .. tostring(name))
  local value = clone(definition)
  value.Name = name
  value.Rarity = rarity or "Common"
  value.StackNum = stack or 1
  value.EffectValue = (stack or 1) * 100 + (rarityValue[rarity or "Common"] or 0)
  if definition.RarityLevels then value.RarityLevels = clone(definition.RarityLevels) end
  return value
end

GetProcessedTraitData = function(args)
  return processed(args.TraitName, args.Rarity, args.StackNum)
end
HeroHasTrait = function(name)
  for _, trait in ipairs(CurrentRun.Hero.Traits) do if trait.Name == name then return true end end
  return false
end
IsGodTrait = function() return false end
GetAllUpgradeableGodTraits = function() return {} end
GetLootSourceName = function(name)
  if string.find(name or "", "Chaos", 1, true) then return "TrialUpgrade" end
  return nil
end

AddTraitToHero = function(args)
  local value = args.TraitData and clone(args.TraitData)
    or processed(args.TraitName, "Common", 1)
  nextId = nextId + 1
  value.Id = value.Id or nextId
  addCalls = addCalls + 1
  if args.FromLoot then fromLootCalls = fromLootCalls + 1 end
  CurrentRun.Hero.Traits[#CurrentRun.Hero.Traits + 1] = value
  return value
end

RemoveTraitData = function(_, target, args)
  args = args or {}
  local kept = {}
  for _, trait in ipairs(CurrentRun.Hero.Traits) do
    if trait ~= target then kept[#kept + 1] = trait end
  end
  CurrentRun.Hero.Traits = kept
  if not args.SkipExpire and target.OnExpire and target.OnExpire.TraitData then
    local nextTrait = clone(target.OnExpire.TraitData)
    nextTrait.Id = target.Id
    nextTrait.FromLootObserved = true
    CurrentRun.Hero.Traits[#CurrentRun.Hero.Traits + 1] = nextTrait
    fromLootCalls = fromLootCalls + 1
  end
  if failRemoveAfterMutation then
    failRemoveAfterMutation = false
    error("synthetic Chaos post-mutation acknowledgement failure")
  end
end

local function makeCurse(id)
  local curse = processed("ChaosDamageCurse", "Rare", 1)
  curse.Id = id
  curse.RemainingUses = 2
  curse.TraitTitle = "ChaosCombo_ChaosDamageCurse_ChaosHealthBlessing"
  curse.OnExpire = {
    TraitData = processed("ChaosHealthBlessing", "Rare", 1),
  }
  return curse
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
local function contains(value, needle)
  return string.find(tostring(value), needle, 1, true) ~= nil
end
local function expectError(needle, fn)
  local ok, message = pcall(fn)
  if ok then fail("expected error containing " .. needle) end
  if not contains(message, needle) then
    fail("wrong error: expected '" .. needle .. "' got '" .. tostring(message) .. "'")
  end
end
local function row()
  local state = M.dispatch("status", { includeCatalogs = false })
  eq(#state.currentRunTraits, 1, "unexpected mounted Chaos row count")
  return state.currentRunTraits[1]
end
local function paramsFrom(value, requestId)
  return {
    requestId = requestId,
    generationId = value.generationId,
    runId = value.runId,
    instanceId = value.instanceId,
    trait = value.name,
    family = value.family,
    expectedLevel = value.level,
    expectedRarity = value.rarity,
    expectedSameNameCount = value.sameNameCount,
    includeCatalogs = false,
  }
end

CurrentRun.Hero.Traits = { makeCurse(501) }

-- Observation exposes lifecycle state and queued blessing without using the
-- internal trait id as the user-facing identity.
local observed = row()
eq(observed.family, "chaos", "Chaos family")
eq(observed.lifecycleState, "curse", "Chaos curse lifecycle state")
eq(observed.linkedTrait, "ChaosHealthBlessing", "queued blessing identity")
eq(observed.remainingUses, 2, "curse remaining encounters")
eq(observed.levelCapability, "increaseOne", "Chaos level capability")
eq(observed.rarityCapability, "setExact", "Chaos rarity capability")
eq(observed.removalCapability, "singleInstanceForce", "Chaos cancel capability")
check(observed.canAdvanceLifecycle == true, "Chaos curse did not expose immediate transform")
check(observed.deferredIssue == nil, "implemented Chaos row still deferred to #236")
eq(#observed.availableRarities, 4, "Chaos curse did not inherit blessing rarities")

-- Level rebuild updates the current curse and queued blessing together while
-- preserving current-run identity and RemainingUses.
local levelParams = paramsFrom(observed, "chaos-level")
levelParams.targetLevel = 3
M.dispatch("set_trait_level", levelParams)
local curse = CurrentRun.Hero.Traits[1]
eq(tostring(curse.Id), "501", "Chaos level edit changed instance identity")
eq(curse.StackNum, 3, "Chaos curse level not rebuilt")
eq(curse.EffectValue, 302, "Chaos curse effect not recalculated")
eq(curse.RemainingUses, 2, "Chaos level edit lost remaining encounters")
eq(curse.OnExpire.TraitData.StackNum, 3, "queued blessing level not rebuilt")
eq(curse.OnExpire.TraitData.EffectValue, 302, "queued blessing effect not recalculated")

-- Exact rarity likewise updates both phases without firing FromLoot acquire
-- behavior during an edit.
observed = row()
local rarityParams = paramsFrom(observed, "chaos-rarity")
rarityParams.rarity = "Epic"
local beforeFromLoot = fromLootCalls
M.dispatch("set_trait_rarity", rarityParams)
curse = CurrentRun.Hero.Traits[1]
eq(curse.Rarity, "Epic", "Chaos curse rarity not rebuilt")
eq(curse.OnExpire.TraitData.Rarity, "Epic", "queued blessing rarity not rebuilt")
eq(curse.RemainingUses, 2, "Chaos rarity edit lost remaining encounters")
eq(fromLootCalls, beforeFromLoot, "Chaos edit replayed acquisition lifecycle")

-- Generic Remove means cancel this pair: no queued blessing is granted.
observed = row()
M.dispatch("remove_trait", paramsFrom(observed, "chaos-cancel"))
eq(#CurrentRun.Hero.Traits, 0, "Chaos cancel left a mounted phase")
eq(fromLootCalls, beforeFromLoot, "Chaos cancel incorrectly granted blessing")

-- Immediate transform is distinct from cancel and uses native expiry semantics:
-- the queued blessing appears with the same runtime instance id.
CurrentRun.Hero.Traits = { makeCurse(777) }
observed = row()
local transformParams = paramsFrom(observed, "chaos-transform")
local transformedResult = M.dispatch("advance_trait_lifecycle", transformParams)
eq(#CurrentRun.Hero.Traits, 1, "Chaos transform left wrong row count")
local blessing = CurrentRun.Hero.Traits[1]
eq(blessing.Name, "ChaosHealthBlessing", "Chaos transform did not mount queued blessing")
eq(tostring(blessing.Id), "777", "Chaos transform did not preserve instance identity")
check(blessing.FromLootObserved == true, "Chaos transform did not use native expiry acquisition semantics")

local afterTransformFromLoot = fromLootCalls
local duplicate = M.dispatch("advance_trait_lifecycle", transformParams)
check(duplicate.duplicate == true, "completed Chaos transform request was not deduplicated")
eq(fromLootCalls, afterTransformFromLoot, "duplicate Chaos transform replayed expiry")

local staleParams = paramsFrom(observed, "chaos-transform-stale")
expectError("Trait target changed since selection", function()
  M.dispatch("advance_trait_lifecycle", staleParams)
end)

local transformed = row()
eq(transformed.lifecycleState, "blessing", "transformed Chaos row not identified as blessing")
eq(transformed.linkedTrait, "", "active blessing retained stale queued identity")
check(transformed.canAdvanceLifecycle == false, "active blessing exposed another transform")
eq(transformed.levelCapability, "increaseOne", "active Chaos blessing not level-editable")
eq(transformed.rarityCapability, "setExact", "active Chaos blessing not rarity-editable")
eq(transformed.removalCapability, "singleInstanceForce", "active Chaos blessing not removable")

-- A failure after native expiry is outcome-unknown rather than retryable. The
-- transformed live state remains authoritative and the same request id cannot
-- fire expiry a second time.
CurrentRun.Hero.Traits = { makeCurse(888) }
observed = row()
local unknownParams = paramsFrom(observed, "chaos-transform-unknown")
failRemoveAfterMutation = true
local beforeUnknownFromLoot = fromLootCalls
expectError("MGT_OUTCOME_UNKNOWN", function()
  M.dispatch("advance_trait_lifecycle", unknownParams)
end)
eq(#CurrentRun.Hero.Traits, 1, "outcome-unknown Chaos transform lost live state")
eq(CurrentRun.Hero.Traits[1].Name, "ChaosHealthBlessing", "outcome-unknown transform did not apply once")
eq(fromLootCalls, beforeUnknownFromLoot + 1, "outcome-unknown transform applied wrong number of expiries")
expectError("Previous action outcome is unknown; do not retry", function()
  M.dispatch("advance_trait_lifecycle", unknownParams)
end)
eq(fromLootCalls, beforeUnknownFromLoot + 1, "outcome-unknown request replayed expiry")

print("hades2_chaos_management_runtime_ok")
'''

with tempfile.TemporaryDirectory(prefix="mgt-chaos-management-") as td:
    td = Path(td)
    harness = td / "chaos_management.lua"
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
    if "hades2_chaos_management_runtime_ok" not in proc.stdout:
        raise SystemExit(proc.stdout)

print("hades2_chaos_management_ok")
