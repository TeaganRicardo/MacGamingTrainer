import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
sys.path.insert(0, str(ROOT / "tests"))

from games.hades2 import adapter as adapter_module
from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter
from lua_runtime_support import require_lua52

RUNTIME = ROOT / "Backend/games/hades2/runtime/hades.lua"
LUA = require_lua52("durable preference replay batch behavior")


def payload():
    return {
        "status": "ready",
        "scene": "run",
        "capabilities": {},
        "desiredFeatures": {},
        "activeFeatures": {},
        "dormantFeatures": {},
        "featureSupport": {},
        "featureErrors": {},
        "resources": [],
        "elements": [],
        "stats": {},
        "boonRarity": {
            "target": "Epic",
            "multiplier": 100.0,
            "forceLegendary": False,
            "forceDuo": False,
        },
        "gatheringProbabilities": {},
        "chaosGateProbability": None,
    }


class ReplayTransport:
    def __init__(self):
        self.pid = 4242
        self.last_duration = 0.001
        self.sources = []
        self.expression_timeouts = []
        self.tainted = False

    def alive(self):
        return True

    def execute(self, source, *, expression_timeout_seconds=None):
        self.sources.append(source)
        self.expression_timeouts.append(expression_timeout_seconds)
        return json.dumps(payload())


base = Path(tempfile.mkdtemp(prefix="mgt-replay-batch-"))
preparation.DATA = base
adapter_module.localize_catalog = lambda value: value

transport = ReplayTransport()
adapter = Hades2Adapter(transport=transport)
adapter._runtime_bootstrapped = True
adapter._catalog_initialized = True
adapter.preference_initialized = True
adapter.preference_dirty = False
adapter.execute(
    "replay_preferences",
    {},
    replay=True,
    batch=[
        ("set_feature", {"feature": "damageMultiplier", "value": 3.0}),
        ("set_feature", {"feature": "resourceMultiplier", "value": 4.0}),
        ("set_boon_rarity", {
            "target": "Heroic",
            "multiplier": 100.0,
            "forceLegendary": True,
            "forceDuo": True,
        }),
    ],
)

assert len(transport.sources) == 1
source = transport.sources[0]
assert "__MacGamingTrainerV1.dispatchBatch(" in source, (
    "durable replay still expands every preference into a full resident dispatch"
)
assert '__MacGamingTrainerV1.dispatch("set_feature"' not in source
assert transport.expression_timeouts == [5.0], (
    "durable replay did not receive its bounded recovery budget"
)

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
