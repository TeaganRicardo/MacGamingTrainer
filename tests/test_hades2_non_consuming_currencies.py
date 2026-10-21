"""Non-consuming currencies retain gains through the public resident seam.

Native resource/UI entry points are in-memory fixtures of the supported build.
This does not launch Hades II or access a real save.
"""
import subprocess
import tempfile
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
LUA = require_lua52("non-consuming Hades currencies")

HARNESS = r'''
SessionState = {}
GameState = { Resources = { Money = 20, Ore = 8 }, LifetimeResourcesGained = {},
  LifetimeResourcesSpent = {}, RunHistory = {} }
ResourceData = { Money = {}, Ore = {} }
ResourceDisplayOrderData = { { "Ore" } }
TraitElementData = {}; TraitData = {}; EnemyData = {}; PresetEventArgs = {}
ScreenData = {}; MapState = { RoomRequiredObjects = {} }; LootObjects = {}
ConsumableData = {}; RewardStoreData = {}; LootData = {}
CodexOrdering = { OlympianGods = {}, Order = {} }
CurrentRun = { Hero = { ObjectId = 1, Health = 100, MaxHealth = 100,
  Traits = {}, TraitDictionary = {}, Elements = {} }, CurrentRoom = {},
  ResourcesGained = {}, ResourcesSpent = {}, NumRerolls = 5 }
UpdateTimers = function() end
UpdateMoneyUI = function() end
UpdateRerollUI = function() end
ShowRerollUI = function() end
round = function(value) return math.floor(value + 0.5) end
local questChecks, spentCallback = 0, nil

-- ResourceLogic.lua: zero spends return false; ordinary positive spends
-- report success and update native accounting. A zero-amount call cannot
-- stand in for a successful non-consuming purchase.
SpendResource = function(id, amount, source, args)
  if GameState.Resources[id] == nil or GameState.Resources[id] < amount
      or amount == 0 then return false end
  local rounded = round(amount)
  GameState.Resources[id] = GameState.Resources[id] - rounded
  GameState.LifetimeResourcesSpent[id] = (GameState.LifetimeResourcesSpent[id] or 0) + rounded
  CurrentRun.ResourcesSpent[id] = (CurrentRun.ResourcesSpent[id] or 0) + rounded
  questChecks = questChecks + 1
  spentCallback = { resource = id, amount = amount, source = source, args = args }
  if source == "BonusPurchase" then AddResource("Money", 2, "PurchaseBonus") end
  return true
end
AttemptPanelReroll = function(screen, button)
  local cost = button.Cost
  if not cost or CurrentRun.NumRerolls < cost or cost < 0 then return false end
  CurrentRun.NumRerolls = CurrentRun.NumRerolls - cost
  UpdateRerollUI(CurrentRun.NumRerolls)
  coroutine.yield("native presentation")
  return true
end
AttemptReroll = function(run, target)
  if run.NumRerolls <= 0 or not target.CanBeRerolled then return false end
  run.NumRerolls = run.NumRerolls - 1
  UpdateRerollUI(run.NumRerolls)
  coroutine.yield("native presentation")
  return true
end
AddResource = function(id, amount, source, args)
  GameState.Resources[id] = (GameState.Resources[id] or 0) + amount
  GameState.LifetimeResourcesGained[id] = (GameState.LifetimeResourcesGained[id] or 0) + amount
  CurrentRun.ResourcesGained[id] = (CurrentRun.ResourcesGained[id] or 0) + amount
end
dofile(assert(arg[1])); dofile(assert(arg[2]))
local M = __MacGamingTrainerV1
local function status() return M.dispatch("status", { includeCatalogs = false }) end
local function feature(key, value)
  return M.dispatch("set_feature", { feature = key, value = value, includeCatalogs = false })
end
local function eq(actual, expected, message)
  assert(actual == expected, message .. ": expected=" .. tostring(expected) .. " actual=" .. tostring(actual))
end

-- Protect the existing successful game path before selecting the new mode.
assert(SpendResource("Money", 5, "Shop"))
eq(status().money, 15, "ordinary purchase must spend gold")
AddResource("Money", 10, "Reward")
eq(status().money, 25, "ordinary reward must add gold")

M.dispatch("lock_resource", { resource = "Money", locked = true, includeCatalogs = false })
local enabled = feature("infiniteMoney", true)
assert(enabled.activeFeatures.infiniteMoney, "non-consuming gold must be observed active")
assert(not enabled.moneyLocked, "new mode must release the fixed-value gold lock")
assert(SpendResource("Money", 5, "Shop"), "free consumption must still report a successful purchase")
eq(status().money, 25, "purchase must not reduce gold")
eq(GameState.LifetimeResourcesSpent.Money, 10, "non-consuming purchase retains native lifetime accounting")
eq(CurrentRun.ResourcesSpent.Money, 10, "non-consuming purchase retains native run accounting")
eq(questChecks, 2, "non-consuming purchase retains the native quest check")
AddResource("Money", 7, "Reward")
eq(status().money, 32, "new income must survive the non-consuming mode")
eq(GameState.LifetimeResourcesGained.Money, 17, "native gain accounting must survive")
local purchaseArgs = { SkipResourceSpendPresentation = true }
assert(SpendResource("Money", 5.6, "BonusPurchase", purchaseArgs))
eq(status().money, 34, "purchase callback gains must not be overwritten by balance restoration")
eq(GameState.LifetimeResourcesSpent.Money, 16, "native rounded spend must be recorded")
assert(spentCallback.resource == "Money" and spentCallback.amount == 5.6
  and spentCallback.source == "BonusPurchase" and spentCallback.args == purchaseArgs,
  "native purchase callback must keep its actual amount, source and args")
assert(SpendResource("Ore", 3, "Craft"))
eq(GameState.Resources.Ore, 5, "gold mode must not affect other resources")
assert(not SpendResource("Money", 100, "Shop"), "native affordability remains applicable")
assert(not SpendResource("Money", 0, "Shop"), "zero spend keeps native result")

-- Explicit Trainer numeric edits remain deliberate absolute edits.
M.dispatch("set_resource", { resource = "Money", amount = 4,
  requestId = "edit-gold", includeCatalogs = false })
eq(status().money, 4, "explicit numeric edit must be able to lower gold")
feature("infiniteMoney", false)
assert(SpendResource("Money", 2, "Shop"))
eq(status().money, 2, "disabling must restore ordinary spending")

-- InteractLogic's panel/door paths subtract before UpdateRerollUI; the
-- panel then continues in its native yielding coroutine. Gains also publish
-- through UpdateRerollUI (ResourceLogic.AddRerolls).
local shownRerolls
UpdateRerollUI = function(value) shownRerolls = value end
local function addRerolls(amount)
  CurrentRun.NumRerolls = CurrentRun.NumRerolls + amount
  UpdateRerollUI(CurrentRun.NumRerolls)
end
local function nativeReroll(cost)
  return AttemptPanelReroll({}, { Cost = cost })
end
local function reroll(cost)
  local worker = coroutine.create(nativeReroll)
  local ok, result = coroutine.resume(worker, cost)
  assert(ok, result)
  if coroutine.status(worker) ~= "dead" then
    eq(result, "native presentation", "native reroll must retain its yield")
    ok, result = coroutine.resume(worker)
    assert(ok, result)
  end
  return result
end
assert(reroll(1))
eq(status().rerolls, 4, "ordinary reroll must consume")
addRerolls(3)
eq(status().rerolls, 7, "ordinary reroll gain must increase the balance")
M.dispatch("lock_rerolls", { locked = true, includeCatalogs = false })
enabled = feature("infiniteRerolls", true)
assert(enabled.activeFeatures.infiniteRerolls, "non-consuming rerolls must be observed active")
assert(not enabled.rerollsLocked, "new mode must release the fixed reroll lock")
assert(reroll(2))
eq(status().rerolls, 7, "reroll must not reduce currency")
addRerolls(5)
eq(status().rerolls, 12, "gained rerolls must remain available")
assert(reroll(3))
eq(status().rerolls, 12, "later spends must preserve the increased balance")
eq(shownRerolls, 12, "native UI must show the retained balance")
-- Native Arcana/pre-run owners can reset this same Run's counter directly.
CurrentRun.NumRerolls = 3
UpdateRerollUI(CurrentRun.NumRerolls)
eq(status().rerolls, 3, "a native reset must replace the old non-consuming balance")
assert(reroll(1))
eq(status().rerolls, 3, "reroll after a native reset must retain the new balance")
assert(not reroll(5), "unaffordable native attempts must remain failures")
CurrentRun.NumRerolls = 2
UpdateRerollUI(2)
eq(status().rerolls, 2, "an early return must not leave a pending spend behind")
local door = coroutine.create(function() return AttemptReroll(CurrentRun, { CanBeRerolled = true }) end)
local ok, value = coroutine.resume(door)
assert(ok and value == "native presentation" and coroutine.status(door) == "suspended")
eq(status().rerolls, 2, "door reroll must retain currency before native presentation yields")
assert(coroutine.resume(door))
local invalidDoor = coroutine.create(function() return AttemptReroll(CurrentRun, { CanBeRerolled = false }) end)
assert(coroutine.resume(invalidDoor))
CurrentRun.NumRerolls = 1
UpdateRerollUI(1)
eq(status().rerolls, 1, "invalid native target must clear its unspent frame")
local foreignRun = { NumRerolls = 9 }
local foreign = coroutine.create(function() return AttemptReroll(foreignRun, { CanBeRerolled = true }) end)
assert(coroutine.resume(foreign))
eq(CurrentRun.NumRerolls, 1, "a foreign native run publication must not mutate the current run")
eq(shownRerolls, 8, "a foreign native run publication must retain its native UI value")
assert(coroutine.resume(foreign))
M.dispatch("set_rerolls", { amount = 1, requestId = "edit-rerolls", includeCatalogs = false })
eq(status().rerolls, 1, "explicit reroll edit must replace the observed balance")
assert(reroll(1))
eq(status().rerolls, 1, "edited balance must become the new non-consuming baseline")
feature("infiniteRerolls", false)
assert(reroll(1))
eq(status().rerolls, 0, "disabling restores native consumption")
feature("infiniteRerolls", true)
CurrentRun = nil; CurrentHubRoom = {}
enabled = status()
assert(enabled.desiredFeatures.infiniteRerolls and not enabled.activeFeatures.infiniteRerolls,
  "missing run must retain desired mode without an active currency owner")
CurrentHubRoom = nil
CurrentRun = { Hero = { ObjectId = 2, Traits = {}, TraitDictionary = {}, Elements = {} },
  CurrentRoom = {}, NumRerolls = 3, ResourcesGained = {}, ResourcesSpent = {} }
eq(status().rerolls, 3, "a replacement run must not inherit the old balance")
assert(reroll(1))
eq(status().rerolls, 3, "non-consuming mode must remount on the new run")
print("non_consuming_currencies_ok")
'''

with tempfile.TemporaryDirectory(prefix="mgt-non-consuming-") as temporary:
    harness = Path(temporary) / "currencies.lua"
    harness.write_text(HARNESS)
    result = subprocess.run(
        [LUA, str(harness), str(ROOT / "Backend/games/hades2/runtime/hades.lua"),
         str(RESIDENT_DISPATCH_CONTRACT)],
        text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "non_consuming_currencies_ok" in result.stdout
print("hades2_non_consuming_currencies_ok")
