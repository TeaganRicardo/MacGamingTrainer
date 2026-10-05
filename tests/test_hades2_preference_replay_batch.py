import subprocess
import tempfile
from pathlib import Path

from lua_runtime_support import require_lua52

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "Backend/games/hades2/runtime/hades.lua"
LUA = require_lua52("durable preference replay batch behavior")

# Adapter/reconciliation planning is covered at the desired-reconciliation
# interface. This test retains only the resident-owned guarantee that a durable
# batch applies all calls and materializes full resident state once.

HARNESS = r'''
local runtimePath = assert(arg[1], "runtime path required")

SessionState = {}
SessionMapState = {}
GameState = { Resources = {}, LifetimeResourcesGained = {}, RunHistory = {} }
ResourceData = {}
ResourceDisplayOrderData = {}
TraitElementData = {}
EnemyData = {}
PresetEventArgs = {}
ScreenData = {}
MapState = { RoomRequiredObjects = {}, EquippedWeapons = {} }
LootObjects = {}
ConsumableData = {}
RewardStoreData = {}
UpdateTimers = function() end
CodexOrdering = { OlympianGods = {}, Order = {} }
TraitData = {}
LootData = {}
UnitSetData = {}

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
    BoonData = { GameStateRequirements = {}, ReplaceChance = 0 },
    Ammo = {},
  },
  CurrentRoom = {},
  NumRerolls = 0,
  SpellCharge = 0,
  PickedTraits = {},
  BannedTraits = {},
}

local stateBuilds = 0
GetHeroMaxAvailableMana = function()
  stateBuilds = stateBuilds + 1
  return CurrentRun.Hero.MaxMana
end

local function fail(message) error("ASSERTION FAILED: " .. message, 0) end
local function eq(actual, expected, message)
  if actual ~= expected then
    fail(message .. ": expected=" .. tostring(expected) .. " actual=" .. tostring(actual))
  end
end

dofile(runtimePath)
local M = assert(__MacGamingTrainerV1, "resident runtime did not initialize")
if type(M.dispatchBatch) ~= "function" then fail("resident durable replay batch API is missing") end

local result = M.dispatchBatch({
  { command = "set_feature", params = { feature = "damageMultiplier", value = 3 } },
  { command = "set_feature", params = { feature = "resourceMultiplier", value = 4 } },
  { command = "set_boon_rarity", params = {
      target = "Heroic", multiplier = 100, forceLegendary = true, forceDuo = true,
  } },
})

eq(result.damageMultiplier, 3, "damage multiplier replay failed")
eq(result.resourceMultiplier, 4, "resource multiplier replay failed")
eq(result.boonRarity.target, "Heroic", "boon rarity replay failed")
eq(result.boonRarity.forceLegendary, true, "legendary replay failed")
eq(result.boonRarity.forceDuo, true, "duo replay failed")
eq(stateBuilds, 1, "batch built full resident state more than once")
'''

with tempfile.TemporaryDirectory(prefix="mgt-replay-batch-lua-") as temporary:
    harness = Path(temporary) / "replay_batch.lua"
    harness.write_text(HARNESS, encoding="utf-8")
    completed = subprocess.run(
        [LUA, str(harness), str(RUNTIME)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise AssertionError(
            "resident replay batch harness failed:\n"
            + completed.stdout
            + completed.stderr
        )

print("hades2_preference_replay_batch_ok")
