"""Explicit garden maturity preserves native harvest and one-shot ownership."""
import subprocess
import tempfile
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
LUA = require_lua52("Hades garden maturity")

HARNESS = r'''
SessionState = {}
GameState = { Resources = {}, LifetimeResourcesGained = {}, RunHistory = {}, GardenPlots = {} }
ResourceData = {}; ResourceDisplayOrderData = {}; TraitElementData = {}; TraitData = {}
EnemyData = {}; PresetEventArgs = {}; ScreenData = {}; LootObjects = {}; LootData = {}
ConsumableData = {}; RewardStoreData = {}; CodexOrdering = { OlympianGods = {}, Order = {} }
MapState = { RoomRequiredObjects = {} }
CurrentRun = { Hero = { ObjectId = 1, Traits = {}, TraitDictionary = {}, Elements = {} },
  CurrentRoom = {}, NumRerolls = 0 }
CurrentHubRoom = { Name = "Hub" }
UpdateTimers = function() end
GardenData = { Seeds = { SeedA = { RandomOutcomes = { normal = { AddResources = { Flower = 1 } } } } } }
local function plant(id, remaining, ready)
  local plot = { ObjectId = id, PlantId = id + 1000, SeedName = "SeedA", OutcomeKey = "normal",
    StartingGrowTime = 8, GrowTimeRemaining = remaining, ReadyForHarvest = ready }
  GameState.GardenPlots[id] = plot
  return plot
end
local growing = plant(10, 4, false)
local mature = plant(11, 0, true)
local empty = { ObjectId = 12, GrowTimeRemaining = 3 }
GameState.GardenPlots[12] = empty
local otherGrowing = plant(13, 8, false)
local nativeUpdates = {}
GardenPlotTimeUpdatePresentation = function(plot)
  assert(plot.ReadyForHarvest, "presentation must observe native maturity")
  plot.UseText = "UseGardenPlotReady"
  nativeUpdates[plot.ObjectId] = true
end
-- GardenLogic's existing tick is the maturity owner. Its yielding harvest
-- remains separate and must still collect the planted seed's native outcome.
GardenTimeTick = function(args)
  for tick = 1, args.Ticks or 1 do
    for id, plot in pairs(GameState.GardenPlots) do
      if args.PlotId == nil or id == args.PlotId then
        if plot.GrowTimeRemaining and plot.GrowTimeRemaining > 0 then
          plot.GrowTimeRemaining = plot.GrowTimeRemaining - 1
          if plot.GrowTimeRemaining <= 0 then plot.ReadyForHarvest = true end
          if args.UpdatePlotPresentation then GardenPlotTimeUpdatePresentation(plot) end
        end
      end
    end
  end
end
UseGardenPlot = function(plot)
  if not plot.ReadyForHarvest then return false end
  coroutine.yield("harvest-presentation")
  local outcome = GardenData.Seeds[plot.SeedName].RandomOutcomes[plot.OutcomeKey]
  for resource, amount in pairs(outcome.AddResources) do
    GameState.Resources[resource] = (GameState.Resources[resource] or 0) + amount
  end
  plot.ReadyForHarvest, plot.SeedName, plot.PlantId = false, nil, nil
  return true
end
local nativeHarvest = UseGardenPlot
dofile(assert(arg[1])); dofile(assert(arg[2]))
local M = __MacGamingTrainerV1
local function status() return M.dispatch("status", { includeCatalogs = false }) end
local observed = status()
assert(observed.capabilities.matureGarden and type(observed.gardenScopeToken) == "string",
  "the live garden must expose an explicit action with owner identity")
if arg[3] == "presentationFailure" then
  GardenPlotTimeUpdatePresentation = function() error("native garden presentation failed") end
  local failed = M.dispatch("mature_garden", { requestId = "uncertain-maturity",
    scopeToken = observed.gardenScopeToken, includeCatalogs = false })
  assert(failed.actionOutcome == "outcome_unknown" and failed.runtimeOutcomeUnknown,
    "failure after native maturity must retain an uncertain one-shot receipt")
  assert(next(GameState.Resources) == nil)
  assert(not pcall(M.dispatch, "mature_garden", { requestId = "do-not-replay",
    scopeToken = observed.gardenScopeToken, includeCatalogs = false }),
    "uncertain maturity must never automatically repeat")
  print("garden_maturity_ok")
  return
end
assert(not pcall(M.dispatch, "set_feature", { feature = "gardenQoL", value = true,
  includeCatalogs = false }), "retired garden convenience must not remain a current feature")
assert(observed.desiredFeatures.gardenQoL == nil and observed.featureSupport.gardenQoL == nil)
local params = { requestId = "mature-existing-plants", scopeToken = observed.gardenScopeToken,
  includeCatalogs = false }
local result = M.dispatch("mature_garden", params)
assert(result.applied and result.actionOutcome == "completed")
assert(growing.ReadyForHarvest and otherGrowing.ReadyForHarvest,
  "all currently planted crops must mature")
assert(growing.StartingGrowTime == 8 and growing.OutcomeKey == "normal" and growing.SeedName == "SeedA",
  "maturation must retain the planted crop and native outcome")
assert(nativeUpdates[10] and nativeUpdates[13] and growing.UseText == "UseGardenPlotReady",
  "live native garden presentation must refresh")
assert(not nativeUpdates[11] and mature.ReadyForHarvest,
  "already mature plants must remain untouched")
assert(empty.SeedName == nil and not empty.ReadyForHarvest and empty.GrowTimeRemaining == 3,
  "an empty plot must not grow a manufactured crop")
assert(next(GameState.Resources) == nil, "maturity must not directly grant harvest rewards")
assert(not result.capabilities.matureGarden, "no immature crops must disable the one-shot action")
assert(M.dispatch("mature_garden", params).duplicate,
  "duplicate request must return its receipt after its target becomes unavailable")
assert(UseGardenPlot == nativeHarvest, "maturity must not replace the native harvest owner")
local harvest = coroutine.create(function() return UseGardenPlot(growing) end)
local resumed, value = coroutine.resume(harvest)
assert(resumed and value == "harvest-presentation" and coroutine.status(harvest) == "suspended",
  "native harvest presentation must remain yieldable")
resumed, value = coroutine.resume(harvest)
assert(resumed and value == true and coroutine.status(harvest) == "dead")
assert(GameState.Resources.Flower == 1 and growing.SeedName == nil and growing.PlantId == nil,
  "native harvest must grant its outcome and empty the matured plot")

-- A replacement profile/garden cannot adopt a request made against the old
-- observed garden, even while the same Hub and Run are still present.
local newGrowing = plant(14, 6, false)
local oldToken = status().gardenScopeToken
GameState = { Resources = {}, LifetimeResourcesGained = {}, RunHistory = {},
  GardenPlots = { [14] = newGrowing } }
local ok = pcall(M.dispatch, "mature_garden", {
  requestId = "stale-garden", scopeToken = oldToken, includeCatalogs = false,
})
assert(not ok and not newGrowing.ReadyForHarvest and newGrowing.GrowTimeRemaining == 6,
  "stale garden request must not mutate a replacement profile")
assert(not status().runtimeOutcomeUnknown, "preflight rejection must preserve runtime trust")
CurrentHubRoom = nil
assert(not status().capabilities.matureGarden, "live garden presentation requires the Hub")
print("garden_maturity_ok")
'''

with tempfile.TemporaryDirectory(prefix="mgt-garden-maturity-") as temporary:
    harness = Path(temporary) / "garden.lua"
    harness.write_text(HARNESS)
    for scenario in ("normal", "presentationFailure"):
        result = subprocess.run(
            [LUA, str(harness), str(ROOT / "Backend/games/hades2/runtime/hades.lua"),
             str(RESIDENT_DISPATCH_CONTRACT), scenario],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "garden_maturity_ok" in result.stdout
print("hades2_garden_maturity_ok")
