"""Exact-native Gift of Night physical reward stand and claim lifecycle (#729)."""
import subprocess
import tempfile
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
LUA = require_lua52("Hades II native Gift of Night")
GATHERING = (ROOT / "tests/fixtures/hades2/gathering_room_model.lua").read_text().split(
    "local nativeCreate = CreateRoom"
)[0]
CHAOS = (ROOT / "tests/fixtures/hades2/chaos_gate_room_model.lua").read_text().split(
    "dofile(assert(arg[1]))"
)[0]
SHOPS = (ROOT / "tests/fixtures/hades2/chamber_facility_room_model.lua").read_text()
GIFT = (ROOT / "tests/fixtures/hades2/gift_of_night_room_model.lua").read_text()
PREFIX = GATHERING + CHAOS + SHOPS + GIFT + """
dofile(assert(arg[1])); dofile(assert(arg[2]))
local M = __MacGamingTrainerV1
local function room(fields, fear)
  draw = .95
  fields.Name = fields.Name or 'I_Combat01'
  fields.RoomSetName = fields.RoomSetName or 'I'
  if fields.WellShopSpawnChance == nil then fields.WellShopSpawnChance = 0 end
  if fields.SellShopSpawnChance == nil then fields.SellShopSpawnChance = 0 end
  if fields.SurfaceShopSpawnChance == nil then fields.SurfaceShopSpawnChance = 0 end
  if fields.MetaRewardStandSpawnChance == nil then fields.MetaRewardStandSpawnChance = .15 end
  RoomData[fields.Name] = fields
  roomData = RoomData[fields.Name]  -- game OnAnyLoad global
  GameState.SpentShrinePointsCache = fear or 12
  CurrentRun.CurrentRoom = CreateRoom(fields, {})
  return CurrentRun.CurrentRoom
end
local function options()
  return M.dispatch('status',{includeCatalogs=false}).facilityOptions
end
local function option(kind)
  for _,row in ipairs(options()) do if row.id==kind then return row end end
end
local function generate(requestId)
  local entry=assert(option('gift'))
  return M.dispatch('generate_chamber_facility',{
   facility='gift',scopeToken=entry.scopeToken,requestId=requestId or 'gift-1',
   includeCatalogs=false,
  }),entry
end
"""


def run(code):
    with tempfile.TemporaryDirectory(prefix="mgt-gift-") as directory:
        harness = Path(directory) / "gift.lua"
        harness.write_text(PREFIX + code)
        result = subprocess.run(
            [LUA, str(harness), str(ROOT / "Backend/games/hades2/runtime/hades.lua"),
             str(RESIDENT_DISPATCH_CONTRACT)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode:
            print(result.stdout, result.stderr)
            raise SystemExit(result.returncode)
        assert "gift_of_night_ok" in result.stdout


CASES = [
r"""
local source=room({Name='I_Combat01',RoomSetName='I'})
local target=assert(option('gift'))
assert(target.labelKey=='hades2.facility.gift')
assert(not option('well') and not option('shrine') and not option('purging'))
assert(not source.MetaRewardStandSuccess and source.MetaRewardStand==nil)
local reply=M.dispatch('generate_chamber_facility',{
 facility='gift',scopeToken=target.scopeToken,requestId='gift-main',includeCatalogs=false,
})
assert(reply.applied and reply.actionOutcome=='completed')
assert(nativeRewardSpawns==1 and nativeSpawns==1 and nativeRewardDisplays==1)
assert(nativeRewardPresentations==1)
local stand=assert(source.MetaRewardStand)
assert(stand.ObjectId==211 and MapState.ActiveObstacles[211]==stand)
assert(stand.ChallengeSwitchUseFunctionName=='UseMetaRewardStand')
assert(stand.ReadyToUse and stand.UseText==stand.AvailableUseText and IsUseable({Id=211}))
assert(stand.ResourceData.Name=='CardUpgradePoints' and stand.RewardAmount==1)
assert(IsAlive({Id=stand.DisplayItemId}) and stand.DisplayItemId~=211)
assert(source.ForceMetaRewardStand and CurrentRun.LastMetaRewardStandDepth==CurrentRun.RunDepthCache)
assert(not source.MetaRewardStandSuccess and unrelatedChallenges==0)
local duplicate=M.dispatch('generate_chamber_facility',{
 facility='gift',scopeToken=target.scopeToken,requestId='gift-main',includeCatalogs=false,
})
assert(duplicate.applied and duplicate.duplicate and nativeRewardSpawns==1)
UseMetaRewardStand(stand)
assert(nativeRewardClaims==1 and GameState.Resources.CardUpgradePoints==1)
assert(not IsAlive({Id=stand.DisplayItemId}) and not IsUseable({Id=211}))
assert(not option('gift'))
print('gift_of_night_ok')
""",
r"""
local source=room({Name='Q_Combat01',RoomSetName='Q'},20)
assert(option('gift'))
local reply=generate('gift-q')
assert(reply.applied and source.MetaRewardStand.ReadyToUse)
UseMetaRewardStand(source.MetaRewardStand)
assert(GameState.Resources.CardUpgradePoints==1)
print('gift_of_night_ok')
""",
r"""
room({Name='F_Combat01',RoomSetName='F'},20)
assert(not option('gift') and nativeRewardSpawns==0 and nativeSpawns==0)
CurrentRun.CurrentRoom=CreateRoom({Name='I_Other',RoomSetName='I',WellShopSpawnChance=0}, {})
assert(not option('gift'))
print('gift_of_night_ok')
""",
r"""
local source=room({Name='I_Combat01',RoomSetName='I'},11)
assert(not option('gift'))
assert(nativeRewardSpawns==0 and CurrentRun.LastMetaRewardStandDepth==nil)
GameState.SpentShrinePointsCache=12
assert(option('gift'))
source.MetaRewardStandRequirements={allow=false}
assert(not option('gift'))
source.MetaRewardStandRequirements={allow=true}
assert(option('gift'))
source.ExitsUnlocked=false
assert(not option('gift'))
source.ExitsUnlocked=true
source.BlockExits=true
assert(not option('gift'))
source.BlockExits=false
assert(option('gift'))
print('gift_of_night_ok')
""",
r"""
local source=room({Name='I_Combat01',RoomSetName='I'})
MapState.ActiveObstacles[211]={Name='OtherNativeObject',ObjectId=211}
assert(not option('gift') and nativeRewardSpawns==0)
MapState.ActiveObstacles[211]={Name='ChallengeSwitchBase',ObjectId=211}
SessionMapState.SpawnPointsUsed={ [211]=true }
assert(not option('gift'))
SessionMapState.SpawnPointsUsed={}
local entry=assert(option('gift'))
roomData={Name='I_NotThisMap'}
assert(not option('gift'))
assert(not pcall(M.dispatch,'generate_chamber_facility',{
 facility='gift',scopeToken=entry.scopeToken,requestId='stale-map-global',
}))
assert(nativeRewardSpawns==0 and not source.ForceMetaRewardStand)
print('gift_of_night_ok')
""",
r"""
local source=room({Name='I_Combat01',RoomSetName='I'})
local original=MetaRewardStandData.WeightedOptions
MetaRewardStandData.WeightedOptions={}
assert(not option('gift'))
MetaRewardStandData.WeightedOptions={{Name='Missing',Amount=1,Animation='Missing',Weight=1}}
assert(not option('gift'))
MetaRewardStandData.WeightedOptions=original
assert(option('gift'))
local entry=assert(option('gift'))
CurrentRun.CurrentRoom=CreateRoom({Name='I_Different',RoomSetName='I',MetaRewardStandSpawnChance=.5,WellShopSpawnChance=0}, {})
assert(not pcall(M.dispatch,'generate_chamber_facility',{
 facility='gift',scopeToken=entry.scopeToken,requestId='stale-room',
}))
assert(nativeRewardSpawns==0 and nativeSpawns==0)
print('gift_of_night_ok')
""",
r"""
local source=room({Name='I_Combat01',RoomSetName='I'})
local entry=assert(option('gift'))
local originalSetup,originalMeta=SetupObstacle,IsMetaRewardStandEligible
local originalTime,originalIds=IsTimeChallengeForced,GetIdsByType
SetupObstacle=function(object)
 originalSetup(object)
 error('native stand setup uncertain after obstacle commit')
end
assert(not pcall(M.dispatch,'generate_chamber_facility',{
 facility='gift',scopeToken=entry.scopeToken,requestId='unknown-gift',
}))
assert(M.terminalActionUnknown and nativeSpawns==1)
assert(not source.MetaRewardStandSuccess)
assert(IsMetaRewardStandEligible==originalMeta and IsTimeChallengeForced==originalTime)
assert(GetIdsByType==originalIds)
assert(not pcall(M.dispatch,'generate_chamber_facility',{
 facility='gift',scopeToken=entry.scopeToken,requestId='unknown-gift',
}))
print('gift_of_night_ok')
""",
]

for scenario in CASES:
    run(scenario)
print("hades2_gift_of_night_generation_ok")
