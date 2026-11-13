"""Native-shaped room shop generation, one-shot ownership and interactions (#729)."""
import subprocess
import tempfile
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
LUA = require_lua52("Hades II native room shops")
GATHERING = (ROOT / "tests/fixtures/hades2/gathering_room_model.lua").read_text().split(
    "local nativeCreate = CreateRoom"
)[0]
CHAOS = (ROOT / "tests/fixtures/hades2/chaos_gate_room_model.lua").read_text().split(
    "dofile(assert(arg[1]))"
)[0]
SHOPS = (ROOT / "tests/fixtures/hades2/chamber_facility_room_model.lua").read_text()
PREFIX = GATHERING + CHAOS + SHOPS + """
dofile(assert(arg[1])); dofile(assert(arg[2]))
local M = __MacGamingTrainerV1
local function room(fields, roll)
  draw = roll or .95
  fields.Name = fields.Name or 'F_Combat01'
  fields.RoomSetName = fields.RoomSetName or 'F'
  CurrentRun.CurrentRoom = CreateRoom(fields, {})
  return CurrentRun.CurrentRoom
end
local function options()
  return M.dispatch('status', {includeCatalogs=false}).facilityOptions
end
local function option(kind)
  for _, row in ipairs(options()) do
    if row.id == kind then return row end
  end
end
local function generate(kind, id)
  local row = assert(option(kind), 'no available native facility: '..kind)
  return M.dispatch('generate_chamber_facility', {
    facility=kind, scopeToken=row.scopeToken, requestId=id or 'facility-1', includeCatalogs=false,
  }), row
end
"""


def run(code):
    with tempfile.TemporaryDirectory(prefix="mgt-facility-") as directory:
        script = Path(directory) / "room.lua"
        script.write_text(PREFIX + code)
        result = subprocess.run(
            [LUA, str(script), str(ROOT / "Backend/games/hades2/runtime/hades.lua"),
             str(RESIDENT_DISPATCH_CONTRACT)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode:
            print(result.stdout, result.stderr)
            raise SystemExit(result.returncode)
        assert "chamber_facility_ok" in result.stdout


CASES = [
r"""
local source=room({WellShopSpawnChance=.5}, .95)
local entry=assert(option('well'))
assert(entry.scopeToken and entry.labelKey=='hades2.facility.well')
assert(not option('shrine') and not option('purging'))
assert(not source.WellShopChanceSuccess and source.Store==nil)
local reply=M.dispatch('generate_chamber_facility',{
 facility='well',scopeToken=entry.scopeToken,requestId='well-1',includeCatalogs=false,
})
assert(reply.applied and reply.actionOutcome=='completed' and nativeSpawns==1)
assert(nativeShopStock==1 and #source.Store.StoreOptions==2)
assert(source.Store.StoreOptions[1].Name=='charonPotion')
assert(source.WellShop.ObjectId==211 and IsUseable({Id=211}))
assert(MapState.ActiveObstacles[211]==source.WellShop)
assert(source.WellShop.ChallengeSwitchUseFunctionName=='UseWellShop')
assert(source.ForceWellShop and CurrentRun.LastWellShopDepth==CurrentRun.RunDepthCache)
assert(source.WellShopChanceSuccess==false and source.AnomalyDoorChanceSuccess==false)
assert(unrelatedChallenges==0 and setupHarvestCalls==0)
CurrentRun.Hero.Money=100
UseWellShop(source.Store.StoreOptions[1])
assert(CurrentRun.Hero.Money==70 and nativePurchases==1)
assert(not option('well'))
local duplicate=M.dispatch('generate_chamber_facility',{
 facility='well',scopeToken=entry.scopeToken,requestId='well-1',includeCatalogs=false,
})
assert(duplicate.duplicate and duplicate.applied and nativeSpawns==1 and nativeShopStock==1)
assert(not pcall(M.dispatch,'generate_chamber_facility',{
 facility='well',scopeToken=entry.scopeToken,requestId='well-2',
}))
print('chamber_facility_ok')
""",
r"""
local source=room({Name='N_Combat01',RoomSetName='N',
 WellShopSpawnChance=0,SurfaceShopSpawnChance=.4},.95)
assert(option('shrine') and not option('well') and not option('purging'))
local reply=generate('shrine','shrine-1')
assert(reply.applied and nativeSpawns==1 and nativeShopStock==1)
assert(source.SurfaceShop.ObjectId==211 and IsUseable({Id=211}))
assert(source.SurfaceShop.ChallengeSwitchUseFunctionName=='ShowSurfaceShopScreen')
assert(source.Store.StoreOptions[1].Name=='hermesPotion')
CurrentRun.Hero.Money=100
ShowSurfaceShopScreen(source.Store.StoreOptions[1])
assert(CurrentRun.Hero.Money==70 and nativePurchases==1)
assert(source.SurfaceShopChanceSuccess==false and source.WellShopChanceSuccess==false)
print('chamber_facility_ok')
""",
r"""
CurrentRun.Hero.Traits={{Name='ZeusBoon',Rarity='Rare'}}
local source=room({Name='F_PostBoss01',SellShopSpawnChance=1,WellShopSpawnChance=0},.95)
assert(option('purging') and not option('well') and not option('shrine'))
local reply=generate('purging','purge-1')
assert(reply.applied and nativeSpawns==1 and nativeSellMenus==0)
assert(source.SellTraitShop.ObjectId==211 and IsUseable({Id=211}))
assert(source.SellTraitShop.ChallengeSwitchUseFunctionName=='OpenSellTraitMenu')
assert(#source.SellOptions==1 and source.SellOptions[1].Name=='ZeusBoon')
OpenSellTraitMenu()
assert(nativeSellMenus==1)
assert(source.SellShopChanceSuccess and source.ForceSellShop)
print('chamber_facility_ok')
""",
r"""
local source=room({WellShopSpawnChance=.5},.95)
facilityPoints={}
assert(#options()==0)
facilityPoints={211}
MapState.ActiveObstacles[211]={Name='ChallengeSwitchBase',ObjectId=211,
 OnUsedFunctionName='AttemptUseChallengeSwitch'}
assert(#options()==0 and nativeShopStock==0)
MapState.ActiveObstacles[211]={Name='ChallengeSwitchBase',ObjectId=211}
source.WellShopRequirements={allow=false}
assert(#options()==0)
source.WellShopRequirements={allow=true}
source.Store={StoreOptions={{Name='existing'}}}
assert(#options()==0)
assert(nativeSpawns==0)
print('chamber_facility_ok')
""",
r"""
local source=room({WellShopSpawnChance=.5},.95)
local target=assert(option('well'))
CurrentRun.CurrentRoom=CreateRoom({Name='F_Second',RoomSetName='F',WellShopSpawnChance=.5},{})
assert(not pcall(M.dispatch,'generate_chamber_facility',{
  facility='well',scopeToken=target.scopeToken,requestId='wrong-room',
}))
assert(nativeSpawns==0 and nativeShopStock==0 and not source.ForceWellShop)
CurrentRun.CurrentRoom=source
CurrentRun.Hero={ObjectId=4,Health=100,Mana=50,Traits={},TraitDictionary={},
 Elements={},BoonData={}}
assert(not pcall(M.dispatch,'generate_chamber_facility',{
  facility='well',scopeToken=target.scopeToken,requestId='wrong-hero',
}))
assert(nativeSpawns==0 and nativeShopStock==0)
print('chamber_facility_ok')
""",
r"""
CurrentRun.Hero.Traits={{Name='Unknown',Rarity='Epic'}}
room({Name='F_PostBoss01',SellShopSpawnChance=1,WellShopSpawnChance=0},.95)
assert(#options()==0 and nativeSpawns==0)
print('chamber_facility_ok')
""",
r"""
local source=room({WellShopSpawnChance=.5,AnomalyDoorChanceSuccess=true},.95)
source.AnomalyDoorChanceSuccess=true
local target=assert(option('well'))
local originalSetup=SetupObstacle
local originalEligible=IsWellShopEligible
local originalIds=GetIdsByType
local originalHarvest=SetupHarvestPoints
SetupObstacle=function(object)
 originalSetup(object)
 error('simulated native stock-to-obstacle failure')
end
assert(not pcall(M.dispatch,'generate_chamber_facility',{
 facility='well',scopeToken=target.scopeToken,requestId='uncertain',
}))
assert(M.terminalActionUnknown and source.WellShopChanceSuccess==false)
assert(source.AnomalyDoorChanceSuccess and not source.DoAnomalies)
assert(GetIdsByType==originalIds and SetupHarvestPoints==originalHarvest)
assert(IsWellShopEligible==originalEligible)
assert(nativeSpawns==1)
assert(not pcall(M.dispatch,'generate_chamber_facility',{
 facility='well',scopeToken=target.scopeToken,requestId='uncertain',
}))
print('chamber_facility_ok')
""",
]

for scenario in CASES:
    run(scenario)
print("hades2_chamber_facility_generation_ok")
