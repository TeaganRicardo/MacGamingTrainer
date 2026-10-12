import subprocess
import tempfile
import textwrap
from pathlib import Path

from lua_runtime_support import require_lua52

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "Backend/games/hades2/runtime/hades.lua"
LUA = require_lua52("scene owner availability runtime tests")

HARNESS = r'''
local runtimePath = assert(arg[1], "runtime path required")

SessionState = {}
GameState = {
  Resources = {},
  LifetimeResourcesGained = {},
  LifetimeResourcesSpent = {},
  RunHistory = {},
}
ResourceData = {}
ResourceDisplayOrderData = {}
TraitElementData = { Fire = { BaseElement = true } }
EnemyData = {}
PresetEventArgs = {}
ScreenData = {}
MapState = { RoomRequiredObjects = {} }
LootObjects = {}
ConsumableData = {}
RewardStoreData = {}
CodexOrdering = { OlympianGods = {}, Order = {} }
TraitData = {}
LootData = {}
UnitSetData = {}
ActiveEnemies = {}

local timerCalls = 0
UpdateTimers = function()
  timerCalls = timerCalls + 1
end

local unitPropertyCalls = {}
SetUnitProperty = function(args)
  unitPropertyCalls[#unitPropertyCalls + 1] = {
    DestinationId = args.DestinationId,
    Property = args.Property,
    Value = args.Value,
    ValueChangeType = args.ValueChangeType,
  }
end

local ammoCalls = 0
UpdateWeaponAmmo = function()
  ammoCalls = ammoCalls + 1
end
GetMaxAmmo = function() return 5 end

Damage = function() return "damage" end
SacrificeHealth = function() return "sacrifice" end
CalculateDamageMultipliers = function() return 1 end
UpdateHealthUI = function() end
UpdateRerollUI = function() end
ShowRerollUI = function() end
CheckActivatedTraits = function() end

CurrentHubRoom = {}
CurrentRun = nil

dofile(runtimePath)
local M = assert(__MacGamingTrainerV1, "resident runtime did not initialize")

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

local function status()
  return M.dispatch("status", { includeCatalogs = false })
end

local function setFeature(name, value)
  return M.dispatch("set_feature", {
    feature = name,
    value = value,
    includeCatalogs = false,
  })
end

local function newTrainingRun(objectId, health, maxHealth, rerolls, fire)
  return {
    Hero = {
      ObjectId = objectId,
      Health = health,
      MaxHealth = maxHealth,
      -- Deliberately no Mana field. Health, elements, rerolls and movement
      -- have their own owners and must not depend on unrelated mana state.
      Ammo = { WeaponSkull = 0 },
      Elements = { Fire = fire },
      Traits = {},
      TraitDictionary = {},
    },
    CurrentRoom = {},
    NumRerolls = rerolls,
    ResourcesGained = {},
    ResourcesSpent = {},
  }
end

-- Crossroads can expose global game functions while no run Hero exists.
-- Durable global hooks should arm immediately instead of waiting for the
-- combat-ready aggregate predicate.
do
  local state = setFeature("damageEnabled", true)
  check(state.desiredFeatures.damageEnabled, "damage desired state was not retained")
  check(state.activeFeatures.damageEnabled, "global damage hook did not arm in Crossroads")

  state = setFeature("infiniteHealth", true)
  check(state.desiredFeatures.infiniteHealth, "health desired state was not retained")
  check(state.activeFeatures.infiniteHealth, "global health hooks did not arm in Crossroads")

  state = setFeature("infiniteAmmo", true)
  check(state.desiredFeatures.infiniteAmmo, "ammo desired state was not retained")
  check(state.activeFeatures.infiniteAmmo, "global ammo hook did not arm in Crossroads")
  eq(ammoCalls, 0, "ammo install fabricated a Hero refill without a Hero owner")
end

-- Missing native functions must leave session intent dormant until the
-- actual global entry point appears. The next lifecycle reconciliation arms it.
do
  local state = setFeature("autoMiniGames", true)
  check(state.desiredFeatures.autoMiniGames, "missing fishing function discarded desired state")
  check(state.dormantFeatures.autoMiniGames, "missing native function was not shown as dormant")
  check(not state.activeFeatures.autoMiniGames, "missing native function reported active")
  WaitForFishingInput = function() end
  UpdateTimers(0)
  state = status()
  check(state.activeFeatures.autoMiniGames, "late native fishing entry point did not arm")
end

-- A training Hero can own health/elements/rerolls/movement even while an
-- unrelated mana field is absent. Each durable family must follow its actual
-- owner rather than the all-purpose ready() predicate.
CurrentHubRoom = nil
CurrentRun = newTrainingRun(101, 40, 100, 1, 2)
status()

-- A genuine Crossroads training owner must be recognized as such, even
-- when its active Hero has no Mana and a run-shaped CurrentRoom is present.
CurrentHubRoom = {}
local training = status()
eq(training.scene, "crossroads", "training scene identity")
eq(training.status, "ready", "training owner must be operational")
check(training.capabilities.setHealth, "health editor unavailable with valid Hero health")
check(not training.capabilities.setMana, "missing Mana exposed a writable Mana control")
check(training.capabilities.setRerolls, "run counter owner unavailable in training")
check(training.capabilities.setSpellCharge, "Hero spell charge unavailable in training")
CurrentHubRoom = nil

local statState = M.dispatch("set_stat", {
  stat = "moveSpeed",
  locked = true,
  value = 150,
  includeCatalogs = false,
})
check(statState.stats.moveSpeed.locked, "movement target was not retained")
eq(statState.stats.moveSpeed.target, 150, "movement target")
check(statState.statAvailable.moveSpeed, "movement owner was hidden by unrelated mana state")
check(#unitPropertyCalls > 0, "movement target was not applied")
eq(unitPropertyCalls[#unitPropertyCalls].DestinationId, 101, "movement applied to wrong Hero")
eq(unitPropertyCalls[#unitPropertyCalls].Value, 1.5, "movement multiplier")

local vitalState = M.dispatch("lock_vital", {
  vital = "health",
  locked = true,
  includeCatalogs = false,
})
check(vitalState.healthLocked, "health lock was rejected by unrelated mana state")

local elementState = M.dispatch("set_element", {
  element = "Fire",
  amount = 7,
  includeCatalogs = false,
})
eq(CurrentRun.Hero.Elements.Fire, 7, "element edit")
elementState = M.dispatch("lock_element", {
  element = "Fire",
  locked = true,
  includeCatalogs = false,
})
check(elementState.elements[1].locked, "element lock was rejected by unrelated mana state")

local rerollState = M.dispatch("lock_rerolls", {
  locked = true,
  includeCatalogs = false,
})
check(rerollState.rerollsLocked, "reroll lock was rejected by unrelated mana state")

-- Losing the Hero must release Hero-owned runtime state without erasing durable
-- intent. Global session hooks remain usable in the Crossroads.
CurrentRun = nil
CurrentHubRoom = {}
local hub = status()
check(hub.desiredFeatures.damageEnabled and hub.activeFeatures.damageEnabled,
  "global damage hook did not survive the Hero-less Crossroads")
check(hub.desiredFeatures.infiniteAmmo and hub.activeFeatures.infiniteAmmo,
  "global ammo hook did not survive the Hero-less Crossroads")
check(hub.stats.moveSpeed.locked, "movement target was erased when Hero disappeared")
check(not hub.statAvailable.moveSpeed, "movement reported available without a Hero owner")
check(hub.healthLocked, "health lock was erased when Hero disappeared")
check(hub.rerollsLocked, "reroll lock was erased when Hero disappeared")

-- A replacement Hero automatically receives the retained Hero-owned state.
CurrentHubRoom = nil
CurrentRun = newTrainingRun(202, 15, 80, 0, 1)
status()
UpdateTimers(0)
local restored = status()

eq(CurrentRun.Hero.Health, 40, "health lock did not migrate to replacement Hero")
eq(CurrentRun.Hero.MaxHealth, 100, "maximum health lock did not migrate to replacement Hero")
eq(CurrentRun.Hero.Elements.Fire, 7, "element lock did not migrate to replacement Hero")
eq(CurrentRun.NumRerolls, 1, "reroll lock did not migrate to replacement run")
check(restored.stats.moveSpeed.locked and restored.statAvailable.moveSpeed,
  "movement target did not become available on replacement Hero")

local reapplied = false
for _, call in ipairs(unitPropertyCalls) do
  if call.DestinationId == 202 and call.Property == "Speed" and call.Value == 1.5 then
    reapplied = true
    break
  end
end
check(reapplied, "movement target was not reapplied to replacement Hero")
check(timerCalls > 0, "scene guard did not run")

print("hades2_scene_owner_availability_ok")
'''

with tempfile.TemporaryDirectory(prefix="mgt-scene-owner-availability-") as td:
    harness = Path(td) / "scene_owner_availability.lua"
    harness.write_text(textwrap.dedent(HARNESS), encoding="utf-8")

    proc = subprocess.run(
        [LUA, str(harness), str(RUNTIME)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    assert "hades2_scene_owner_availability_ok" in proc.stdout, proc.stdout
    print(proc.stdout.strip())
