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

-- ResourceLogic.lua: zero spends return false; ordinary positive spends
-- report success and update native accounting. A zero-amount call cannot
-- stand in for a successful non-consuming purchase.
SpendResource = function(id, amount, source, args)
  if GameState.Resources[id] == nil or GameState.Resources[id] < amount
      or amount == 0 then return false end
  GameState.Resources[id] = GameState.Resources[id] - amount
  GameState.LifetimeResourcesSpent[id] = (GameState.LifetimeResourcesSpent[id] or 0) + amount
  CurrentRun.ResourcesSpent[id] = (CurrentRun.ResourcesSpent[id] or 0) + amount
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
AddResource("Money", 7, "Reward")
eq(status().money, 32, "new income must survive the non-consuming mode")
eq(GameState.LifetimeResourcesGained.Money, 17, "native gain accounting must survive")
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
  if CurrentRun.NumRerolls < cost or cost < 0 then return false end
  CurrentRun.NumRerolls = CurrentRun.NumRerolls - cost
  UpdateRerollUI(CurrentRun.NumRerolls)
  coroutine.yield("native presentation")
  return true
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
