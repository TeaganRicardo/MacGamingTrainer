"""Gift of Night: native room/point/Fear eligibility, reward claim and one-shot recovery (#729)."""
import subprocess
import tempfile
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
LUA = require_lua52("Hades II Gift of Night")
GATHERING = (ROOT / "tests/fixtures/hades2/gathering_room_model.lua").read_text().split(
    "local nativeCreate = CreateRoom"
)[0]
CHAOS = (ROOT / "tests/fixtures/hades2/chaos_gate_room_model.lua").read_text().split(
    "dofile(assert(arg[1]))"
)[0]
SHOPS = (ROOT / "tests/fixtures/hades2/chamber_facility_room_model.lua").read_text()
CHALLENGES = (ROOT / "tests/fixtures/hades2/challenge_facility_room_model.lua").read_text()
GIFT = (ROOT / "tests/fixtures/hades2/night_gift_room_model.lua").read_text()
PREFIX = GATHERING + CHAOS + SHOPS + CHALLENGES + GIFT + """
dofile(assert(arg[1])); dofile(assert(arg[2]))
local M = __MacGamingTrainerV1
local function room(name)
  draw = .95
  CurrentRun.CurrentRoom = CreateRoom(RoomData[name], {})
  roomData = RoomData[name]
  CurrentRun.CurrentRoom.MetaRewardStandSuccess = false
  return CurrentRun.CurrentRoom
end
local function options()
  return M.dispatch('status', {includeCatalogs=false}).facilityOptions
end
local function option(kind)
  for _, row in ipairs(options()) do if row.id==kind then return row end end
end
local function generate(kind, requestId)
  local row=assert(option(kind),'missing native facility '..kind)
  return M.dispatch('generate_chamber_facility',{
    facility=kind,scopeToken=row.scopeToken,requestId=requestId,includeCatalogs=false,
  }),row
end
"""


def run(code):
    with tempfile.TemporaryDirectory(prefix="mgt-night-gift-") as directory:
        harness = Path(directory) / "night.lua"
        harness.write_text(PREFIX + code)
        result = subprocess.run(
            [LUA, str(harness), str(ROOT / "Backend/games/hades2/runtime/hades.lua"),
             str(RESIDENT_DISPATCH_CONTRACT)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode:
            print(result.stdout, result.stderr)
            raise SystemExit(result.returncode)
        assert "native_night_gift_ok" in result.stdout


CASES = [
r"""
local source=room('I_Gift')
assert(option('gift') and option('gift').labelKey=='hades2.facility.gift')
assert(not option('well') and not option('shrine') and not option('purging'))
local beforeMeta=IsMetaRewardStandEligible
local beforeChance=source.MetaRewardStandSuccess
local beforeChallenge=source.ChallengeChanceSuccess
local reply,requested=generate('gift','night-gift-I')
assert(reply.applied and reply.actionOutcome=='completed')
local altar=assert(source.MetaRewardStand)
assert(altar.ObjectId==211 and altar.Name=='MetaRewardStand' and altar.ReadyToUse)
assert(altar.UseText==altar.AvailableUseText and altar.ChallengeSwitchUseFunctionName=='UseMetaRewardStand')
assert(MapState.ActiveObstacles[211]==altar and IsUseable({Id=211}))
assert(altar.ResourceData.Name=='NightCard' and altar.RewardAmount==1)
assert(altar.DisplayItemId==601 and nativeGiftDisplays==1 and nativeMetaChoice==1)
assert(source.ForceMetaRewardStand and CurrentRun.LastMetaRewardStandDepth==CurrentRun.RunDepthCache)
assert(nativeGiftUnlocks==1 and not source.ChallengeSwitch and not source.WellShop)
assert(source.MetaRewardStandSuccess==beforeChance and source.ChallengeChanceSuccess==beforeChallenge)
assert(IsMetaRewardStandEligible==beforeMeta and forcedTraits.ForceChallengeSwitch)
UseMetaRewardStand(altar)
assert(nativeGiftClaims==1 and GameState.NightCardsClaimed==1 and not IsUseable({Id=211}))
assert(not option('gift'))
local repeat=M.dispatch('generate_chamber_facility',{
 facility='gift',scopeToken=requested.scopeToken,requestId='night-gift-I',includeCatalogs=false,
})
assert(repeat.duplicate and repeat.applied and nativeGiftDisplays==1)
assert(not pcall(M.dispatch,'generate_chamber_facility',{
 facility='gift',scopeToken=requested.scopeToken,requestId='gift-I-second',includeCatalogs=false,
}))
print('native_night_gift_ok')
""",
r"""
local source=room('Q_Gift')
local reply=generate('gift','gift-Q')
assert(reply.applied and source.MetaRewardStand and source.MetaRewardStand.ReadyToUse)
assert(CurrentRun.LastMetaRewardStandDepth==CurrentRun.RunDepthCache)
UseMetaRewardStand(source.MetaRewardStand)
assert(nativeGiftClaims==1)
print('native_night_gift_ok')
""",
r"""
local source=room('I_Gift')
GameState.SpentShrinePointsCache=11
assert(not option('gift') and #options()==0)
assert(nativeGiftDisplays==0 and nativeGiftClaims==0)
GameState.SpentShrinePointsCache=12
assert(option('gift'))
source.MetaRewardStandRequirements={allow=false}
roomData.MetaRewardStandRequirements={allow=false}
assert(not option('gift'))
roomData.MetaRewardStandRequirements={allow=true}
source.MetaRewardStandRequirements={allow=true}
local token=assert(option('gift')).scopeToken
GameState.SpentShrinePointsCache=11
assert(not pcall(M.dispatch,'generate_chamber_facility',{
 facility='gift',scopeToken=token,requestId='fear-changed',includeCatalogs=false,
}))
assert(not source.MetaRewardStand and nativeGiftDisplays==0)
print('native_night_gift_ok')
""",
r"""
local source=room('I_Gift')
local row=assert(option('gift'))
facilityPoints={}
assert(not option('gift'))
assert(not pcall(M.dispatch,'generate_chamber_facility',{
 facility='gift',scopeToken=row.scopeToken,requestId='no-pedestal',includeCatalogs=false,
}))
facilityPoints={211}
MapState.ActiveObstacles[211]={Name='ChallengeSwitchBase',ObjectId=211,
 OnUsedFunctionName='AttemptUseChallengeSwitch'}
assert(not option('gift'))
MapState.ActiveObstacles[211]={Name='ChallengeSwitchBase',ObjectId=211}
roomData=RoomData.Q_Gift
assert(not option('gift'))
assert(nativeSpawns==0 and not source.ForceMetaRewardStand)
print('native_night_gift_ok')
""",
r"""
local source=room('I_Gift')
local token=assert(option('gift')).scopeToken
CurrentRun.CurrentRoom=CreateRoom(RoomData.Q_Gift,{})
roomData=RoomData.Q_Gift
assert(not pcall(M.dispatch,'generate_chamber_facility',{
 facility='gift',scopeToken=token,requestId='stale-room',includeCatalogs=false,
}))
assert(nativeGiftDisplays==0 and not source.ForceMetaRewardStand)
print('native_night_gift_ok')
""",
r"""
local source=room('I_Gift')
local token=assert(option('gift')).scopeToken
local originalSetup=SetupObstacle
local originalMeta=IsMetaRewardStandEligible
local originalChance=source.MetaRewardStandSuccess
SetupObstacle=function(stand)
 originalSetup(stand)
 error('simulated native altar error after object mutation')
end
assert(not pcall(M.dispatch,'generate_chamber_facility',{
 facility='gift',scopeToken=token,requestId='uncertain-gift',includeCatalogs=false,
}))
assert(M.terminalActionUnknown and source.MetaRewardStandSuccess==originalChance)
assert(IsMetaRewardStandEligible==originalMeta and nativeSpawns==1)
assert(not pcall(M.dispatch,'generate_chamber_facility',{
 facility='gift',scopeToken=token,requestId='uncertain-gift',
}))
print('native_night_gift_ok')
""",
]

for case in CASES:
    run(case)
print("hades2_night_gift_generation_ok")
