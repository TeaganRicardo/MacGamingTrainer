"""Minimum rarity is an on/off floor; retired probability values are inert."""
import subprocess
import sys
import tempfile
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
from games.hades2.preferences import Hades2PreferenceStore

defaults = Hades2PreferenceStore.defaults()["boonRarity"]
assert defaults["target"] == "Heroic", defaults
for multiplier in (0, 25, 1000):
    normalized = Hades2PreferenceStore.normalize({"boonRarity": {
        "target": "Rare", "multiplier": multiplier,
        "forceLegendary": True, "forceDuo": True,
    }})["boonRarity"]
    assert normalized == dict(defaults, target="Rare", forceLegendary=True, forceDuo=True), normalized

# Reuse the native room fixture's basic game tables, before its gathering model.
bootstrap = (ROOT / "tests/fixtures/hades2/gathering_room_model.lua").read_text().split("local function copy(value)")[0]
harness = bootstrap + r'''
TraitData = {
 Normal = { RarityLevels = { Common={}, Rare={}, Epic={}, Heroic={} } },
 Legend = { InheritFrom = { "LegendaryTrait" } },
 Duo = { InheritFrom = { "SynergyTrait" } },
}
local nativeChances = function() return { Common=.7, Rare=.2, Epic=.1, Heroic=0 } end
GetRarityChances = nativeChances
SetTraitsOnLoot = function(loot) return "native", nil, 42 end
GetEligibleUpgrades = function() return {} end
dofile(assert(arg[1])); dofile(assert(arg[2]))
local M = __MacGamingTrainerV1
local function dispatch(command, params)
 params = params or {}; params.includeCatalogs = false
 return M.dispatch(command, params)
end
assert(dispatch("status").boonRarity.target == "Heroic", "resident default is not Heroic")
local function loot()
 return { GodLoot=true, UpgradeOptions={
  {ItemName="Normal", Rarity="Common"}, {ItemName="Normal", Rarity="Heroic"},
  {ItemName="Legend", Rarity="Legendary"}, {ItemName="Duo", Rarity="Duo"},
 } }
end
dispatch("set_feature", {feature="boonRarityEnabled", value=true})
local data = loot()
local a,b,c = SetTraitsOnLoot(data)
assert(a == "native" and b == nil and c == 42, "native return tuple changed")
assert(data.UpgradeOptions[1].Rarity == "Heroic", "enabled minimum was not applied")
assert(data.UpgradeOptions[3].Rarity == "Legendary" and data.UpgradeOptions[4].Rarity == "Duo", "special rarities changed")
for _, multiplier in ipairs({0, 1000}) do
 dispatch("set_boon_rarity", {target="Rare", multiplier=multiplier, forceLegendary=false, forceDuo=false})
 assert(GetRarityChances == nativeChances, "retired probability control still hooks native chances")
 assert(GetRarityChances().Rare == .2 and GetRarityChances().Epic == .1, "native probability changed")
 data=loot(); SetTraitsOnLoot(data)
 assert(data.UpgradeOptions[1].Rarity == "Rare" and data.UpgradeOptions[2].Rarity == "Heroic", "minimum downgraded a higher rarity")
end
dispatch("set_feature", {feature="boonRarityEnabled", value=false})
data=loot(); SetTraitsOnLoot(data)
assert(data.UpgradeOptions[1].Rarity == "Common", "disabled control still changes rarity")
print("boon_rarity_control_ok")
'''
with tempfile.TemporaryDirectory(prefix="mgt-boon-rarity-") as temporary:
    script = Path(temporary) / "rarity.lua"
    script.write_text(harness)
    subprocess.run([require_lua52("boon rarity on/off control"), str(script),
                    str(ROOT / "Backend/games/hades2/runtime/hades.lua"),
                    str(RESIDENT_DISPATCH_CONTRACT)], check=True, timeout=30)
print("hades2_boon_rarity_control_ok")
