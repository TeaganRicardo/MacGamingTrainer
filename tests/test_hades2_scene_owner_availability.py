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
local lastAmmoDelta
UpdateWeaponAmmo = function(_, delta)
  ammoCalls = ammoCalls + 1
  lastAmmoDelta = delta
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

-- A durable next-room reward may arm its native routing hooks before a live
-- Run room exists, but StartRoom itself is not proof that the reward routed.
-- Consumption belongs to the specific room that actually received the forced
-- reward, not to a Run-vs-Crossroads transition.
ChooseRoomReward = function() return "RoomMoneyDrop" end
StartRoom = function(_, room) return room end

CurrentRun = nil
CurrentHubRoom = {}
M.dispatch("set_next_room_reward", {
  reward = "WeaponUpgrade",
  token = "pre-run-token",
  includeCatalogs = false,
})
StartRoom(nil, { Name = "HubTransition" })
eq(M.nextRoomReward, "WeaponUpgrade",
  "pre-run StartRoom consumed an unrouted next-room reward")
eq(M.nextRoomRewardToken, "pre-run-token",
  "pre-run StartRoom cleared an unrouted next-room reward token")
check(M.lastConsumedNextRoomRewardToken ~= "pre-run-token",
  "pre-run StartRoom fabricated a next-room reward consumption receipt")
M.dispatch("set_next_room_reward", { reward = nil, includeCatalogs = false })

-- A retained CurrentRun.CurrentRoom is not the live room owner when a distinct
-- Hub room exists. Entering that Hub room must not consume the pending reward.
CurrentRun = newTrainingRun(90, 30, 50, 0, 0)
local staleRunRoom = CurrentRun.CurrentRoom
CurrentHubRoom = { Name = "CrossroadsHub" }
M.dispatch("set_next_room_reward", {
  reward = "WeaponUpgrade",
  token = "stale-run-token",
  includeCatalogs = false,
})
StartRoom(CurrentRun, CurrentHubRoom)
eq(M.nextRoomReward, "WeaponUpgrade",
  "distinct Hub room consumed reward armed against a stale Run room")
eq(M.nextRoomRewardToken, "stale-run-token",
  "distinct Hub room cleared the pending reward token")
check(M.lastConsumedNextRoomRewardToken ~= "stale-run-token",
  "distinct Hub room fabricated a next-room reward consumption receipt")
eq(CurrentRun.CurrentRoom, staleRunRoom, "test fixture unexpectedly replaced stale Run room")
M.dispatch("set_next_room_reward", { reward = nil, includeCatalogs = false })

-- Once native reward routing actually forces a target room, unrelated room
-- starts keep the one-shot pending; entering that exact target consumes it.
CurrentHubRoom = nil
CurrentRun = newTrainingRun(91, 30, 50, 0, 0)
local forcedTargetRoom = { Name = "ForcedTarget" }
M.dispatch("set_next_room_reward", {
  reward = "WeaponUpgrade",
  token = "routed-token",
  includeCatalogs = false,
})
local forcedReward = ChooseRoomReward(
  CurrentRun, forcedTargetRoom, nil, nil, { Door = {} }
)
eq(forcedReward, "WeaponUpgrade", "native reward route did not force requested reward")
StartRoom(CurrentRun, { Name = "DifferentRoom" })
eq(M.nextRoomReward, "WeaponUpgrade",
  "unrelated StartRoom consumed a routed reward for another room")
eq(M.nextRoomRewardToken, "routed-token",
  "unrelated StartRoom cleared a routed reward token")
StartRoom(CurrentRun, forcedTargetRoom)
eq(M.nextRoomReward, nil, "forced target room did not consume next-room reward")
eq(M.nextRoomRewardToken, nil, "forced target room did not clear next-room reward token")
eq(M.lastConsumedNextRoomRewardToken, "routed-token",
  "forced target room did not record the consumed token")

-- Restore the harness baseline before unrelated owner-family checks.
CurrentRun = nil
CurrentHubRoom = {}

-- GameState inventory editing in a Hero-less hub does not require native
-- resource transaction functions. A lock records durable intent and uses the
-- existing UpdateTimers owner until the AddResource/SpendResource hooks arrive.
do
  ResourceData.Money = {}
  GameState.Resources.Money = 12
  UpdateMoneyUI = function() end
  local before = status()
  check(before.capabilities.setResource, "Crossroads direct resource editing hidden")
  M.dispatch("set_resource", { resource = "Money", amount = 18,
    requestId = "crossroads-direct-resource", includeCatalogs = false })
  eq(GameState.Resources.Money, 18, "Crossroads direct inventory editing")
  local locked = M.dispatch("lock_resource", {
    resource = "Money", locked = true, includeCatalogs = false,
  })
  check(locked.moneyLocked and M.resourceLocks.Money == 18,
    "Crossroads resource lock could not be staged without native transaction hooks")
  check(M.hooks.AddResource == nil and M.hooks.SpendResource == nil,
    "missing transaction owner installed invalid resource hooks")
  GameState.Resources.Money = 1
  UpdateTimers(0)
  eq(GameState.Resources.Money, 18, "ownerless resource lock guard failed")
  AddResource = function(id, value)
    GameState.Resources[id] = (GameState.Resources[id] or 0) + value
  end
  SpendResource = function(id, value)
    GameState.Resources[id] = (GameState.Resources[id] or 0) - value
  end
  UpdateTimers(0)
  check(M.hooks.AddResource ~= nil and M.hooks.SpendResource ~= nil,
    "resource lock did not attach native hooks after function owner appeared")
  M.dispatch("lock_resource", { resource = "Money", locked = false, includeCatalogs = false })
  check(M.resourceLocks.Money == nil, "resource lock was not released")
  -- Native Money UI is a view observer, not the lock owner. Its temporary
  -- absence must not prevent exact inventory intent from being recorded.
  local moneyDisplay = UpdateMoneyUI
  UpdateMoneyUI = nil
  local relocked = M.dispatch("lock_resource", {
    resource = "Money", locked = true, includeCatalogs = false,
  })
  check(relocked.moneyLocked, "missing Money UI prevented resource lock ownership")
  M.dispatch("set_resource", {
    resource = "Money", amount = 19, requestId = "resource-without-ui",
    includeCatalogs = false,
  })
  eq(GameState.Resources.Money, 19,
    "Money inventory mutation was incorrectly owned by its optional UI observer")
  M.dispatch("lock_resource", { resource = "Money", locked = false, includeCatalogs = false })
  UpdateMoneyUI = moneyDisplay
end

-- GameState tables alone do not prove that a save/profile owner is loaded.
-- Main-menu presentation may retain containers, but without a Run or Hub scope
-- there is no current resource inventory owner and mutation must fail closed.
CurrentHubRoom = nil
local menuResource = status()
eq(menuResource.scene, "main_menu", "ownerless resource scene identity")
check(not menuResource.capabilities.setResource,
  "main menu fabricated a resource inventory owner from container tables alone")
M.resourceLocks.Money = 19
GameState.Resources.Money = 1
UpdateTimers(0)
eq(GameState.Resources.Money, 1,
  "staged resource lock bypassed the missing inventory owner in main menu")
M.resourceLocks.Money = nil
CurrentHubRoom = {}

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

-- Room generation probabilities are durable future-room intent. Missing
-- early native functions do not turn initial hub replay into a failed batch.
do
  local state = M.dispatch("set_gathering_probabilities", {
    probabilities = { flora = 45 }, includeCatalogs = false,
  })
  eq(state.gatheringProbabilities.flora, 45, "gathering pending intent")
  check(M.hooks["CreateRoom"] == nil, "room generation installed without native owner")
  CreateRoom = function(data) return data end
  DeepCopyTable = function(value) return value end
  ShallowCopyTable = function(value) return value end
  HasFamiliarTool = function() return false end
  GetTotalHeroTraitValue = function() return 0 end
  IsGameStateEligible = function() return true end
  UpdateTimers(0)
  check(M.hooks["CreateRoom"] ~= nil, "room generation did not remount when functions appeared")
  state = M.dispatch("set_chaos_gate_probability", {
    probability = 0, includeCatalogs = false,
  })
  eq(state.chaosGateProbability, 0, "Chaos probability lost without native door owner")
  check(M.hooks["CreateRoom"] ~= nil,
    "missing Chaos owner incorrectly removed the independently ready Gathering owner")
  check(M.hooks["IsSecretDoorEligible"] == nil,
    "missing Chaos native functions installed its invalid eligibility hook")
end

-- A training Hero can own health/elements/rerolls/movement even while an
-- unrelated mana field is absent. Each durable family must follow its actual
-- owner rather than any aggregate scene-readiness predicate.
-- Replay-safe lock targets can be staged before any Hero exists. They must
-- automatically remount on the future Hero without another Host round trip.
local deferredLocks = M.dispatchBatch({
  { command = "stage_desired_locks", params = {
    statLocks = { moveSpeed = 150 },
    vitalLocks = { health = { current = 40, max = 100 } },
    resourceLocks = {}, elementLocks = { Fire = 7 }, rerollsLock = 1,
  } },
})
check(deferredLocks.healthLocked and deferredLocks.stats.moveSpeed.locked,
  "ownerless lock staging was lost")
eq(deferredLocks.residentDesiredLocks.statLocks.moveSpeed, 150, "staged stat intent")

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
local healthDisplay = UpdateHealthUI
UpdateHealthUI = nil
local healthWithoutUI = status()
check(healthWithoutUI.capabilities.setHealth,
  "health owner was incorrectly coupled to its optional UI observer")
M.dispatch("set_vital", {
  vital = "health", field = "current", value = 39, includeCatalogs = false,
})
eq(CurrentRun.Hero.Health, 39, "health mutation failed without optional UI observer")
M.dispatch("set_vital", {
  vital = "health", field = "current", value = 40, includeCatalogs = false,
})
UpdateHealthUI = healthDisplay
check(not training.capabilities.setMana, "missing Mana exposed a writable Mana control")
check(training.capabilities.setRerolls, "run counter owner unavailable in training")
check(training.capabilities.setSpellCharge, "Hero spell charge unavailable in training")
check(training.capabilities.traitInventory,
  "Hero trait inventory owner was hidden by the Crossroads label")
check(training.capabilities.traitMutation,
  "Hero trait mutation owner was hidden by the Crossroads label")
check(training.capabilities.acquireExactReward,
  "exact Trait acquisition was incorrectly coupled to Room/Reward Context")
check(not training.capabilities.spawnReward,
  "room-backed reward spawning escaped without a current Room owner")
check(training.capabilities.activeRun == nil,
  "aggregate activeRun capability survived owner decomposition")
check(training.currentRunTraitsReason ~= "noActiveRun",
  "trait inventory still depends on an adventure-run partition")
local trainingMenuOk, trainingMenuError = pcall(M.dispatch, "open_sell_traits", { includeCatalogs = false })
check(not trainingMenuOk and tostring(trainingMenuError):find("missing OpenSellTraitMenu", 1, true) ~= nil,
  "native sell menu was refused by scene partition instead of its own native prerequisites")

-- A room is current by object identity, not by a Crossroads-vs-run label.
-- If the hub pointer and CurrentRun.CurrentRoom identify the same room owner,
-- room/reward operations can expose their own capability.
CurrentHubRoom = CurrentRun.CurrentRoom
local sharedRoomOwner = status()
check(sharedRoomOwner.capabilities.roomContext,
  "current room owner was hidden because CurrentHubRoom exists")
check(sharedRoomOwner.capabilities.spawnReward,
  "reward context was hidden despite a resolvable room/Hero/map owner")
CurrentHubRoom = nil
-- The resident applies targets on the lifecycle tick, before any UI edit.
UpdateTimers(0)
eq(CurrentRun.Hero.Health, 40, "staged health not restored without Host event")
eq(CurrentRun.Hero.Elements.Fire, 7, "staged elements not restored without Host event")
eq(CurrentRun.NumRerolls, 1, "staged rerolls not restored without Host event")

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

-- A live adventure Run/Room/Hero is one owner even if an unrelated vital
-- is momentarily absent. A native menu can then independently reject missing
-- *native menu APIs*, not the entire live run because Mana is unavailable.
local runWithoutMana = status()
eq(runWithoutMana.scene, "run", "adventure owner scene identity")
check(runWithoutMana.capabilities.traitInventory,
  "trait inventory owner was incorrectly gated on missing Mana")
check(runWithoutMana.capabilities.traitMutation,
  "trait mutation owner was incorrectly gated on missing Mana")
check(runWithoutMana.capabilities.roomContext,
  "room owner was incorrectly gated on missing Mana")
check(runWithoutMana.capabilities.activeRun == nil,
  "aggregate activeRun capability survived owner decomposition")
check(runWithoutMana.currentRunTraitsReason ~= "noActiveRun",
  "trait inventory was incorrectly gated on missing Mana")
local menuOk, menuError = pcall(M.dispatch, "open_sell_traits", { includeCatalogs = false })
check(not menuOk and tostring(menuError):find("missing OpenSellTraitMenu", 1, true) ~= nil,
  "native sell menu was refused by an unrelated vital rather than its own missing native API")

-- Filling in Mana changes only Mana capability, not the already-live run owner.
CurrentRun.Hero.Mana, CurrentRun.Hero.MaxMana = 20, 50
local afterMana = status()
check(afterMana.capabilities.traitInventory and afterMana.capabilities.roomContext,
  "unrelated Mana owner changed existing trait/room owners")

-- Native KillHero leaves CurrentRun.Hero.IsDead=true after the next Hub map
-- reattaches that SAME Hero table to its live _PlayerUnit in SetupHeroObject.
-- The original tests used fresh training Heroes without a death record, which
-- hid both resident owner rejection and run-scoped hooks silently bypassing
-- their body even when reported active.
ManaDelta = function(delta)
  CurrentRun.Hero.Mana = CurrentRun.Hero.Mana + delta
end
GetHeroMaxAvailableMana = function() return CurrentRun.Hero.MaxMana end
UpdateWeaponMana = function() end
UpdateManaMeterUI = function() end
local runMana = setFeature("infiniteMana", true)
check(runMana.activeFeatures.infiniteMana, "in-run infinite mana setup failed")
setFeature("infiniteAmmo", false)
local runAmmo = setFeature("infiniteAmmo", true)
check(runAmmo.activeFeatures.infiniteAmmo, "run-owned infinite ammo setup failed")
check(M.hooks.UpdateWeaponAmmo ~= nil and M.hooks.UpdateWeaponAmmo.scope == "run",
  "fixture did not arm a run-captured hook")

CurrentRun.Hero.IsDead = true
local deadRun = status()
check(not deadRun.capabilities.setMana and not deadRun.activeFeatures.infiniteMana,
  "dead adventure Hero was incorrectly resolved before Hub adoption")
CurrentRun.Hero.ObjectId = nil
CurrentHubRoom = { Name = "Hub_Main" }
local beforeHubAttach = status()
check(not beforeHubAttach.capabilities.setMana,
  "Hub transition fabricated a Hero before SetupHeroObject reattached it")

-- SetupHeroObject establishes a current ObjectId, resets native flags, and
-- equips the playable actor. The prior run's IsDead marker is NOT cleared.
CurrentRun.Hero.ObjectId = 101
CurrentRun.Hero.InvulnerableFlags = {}
CurrentRun.Hero.ImmuneToForceFlags = {}
local resumedHub = status()
check(resumedHub.capabilities.setHealth and resumedHub.capabilities.setMana,
  "post-death reattached Hub Hero lost Health/Mana owners")
check(resumedHub.capabilities.traitMutation and resumedHub.capabilities.setElements,
  "post-death reattached Hub Hero lost independent Trait/Element owners")
check(resumedHub.activeFeatures.infiniteMana,
  "post-death Hub Hero kept infinite mana dormant despite native reattachment")
eq(CurrentRun.Hero.Mana, 50, "reattached infinite mana did not replenish the live Hero")
ManaDelta(-8)
eq(CurrentRun.Hero.Mana, 50,
  "post-death Hub infinite-mana hook silently called native without refilling")
lastAmmoDelta = nil
UpdateWeaponAmmo("WeaponSkull", -2)
eq(lastAmmoDelta, 0,
  "run-captured global ammo hook reported active but bypassed in playable Hub")

CurrentRun.Hero.IsDead = nil
CurrentHubRoom = nil

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
