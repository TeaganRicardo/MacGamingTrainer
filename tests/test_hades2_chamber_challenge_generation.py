"""Hades II native timed, perfect-clear and elite chamber challenge contract (#729)."""
import subprocess
import tempfile
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
LUA = require_lua52("current-room native challenge facilities")
GATHERING = (ROOT / "tests/fixtures/hades2/gathering_room_model.lua").read_text().split(
    "local nativeCreate = CreateRoom"
)[0]
CHAOS = (ROOT / "tests/fixtures/hades2/chaos_gate_room_model.lua").read_text().split(
    "dofile(assert(arg[1]))"
)[0]
SHOPS = (ROOT / "tests/fixtures/hades2/chamber_facility_room_model.lua").read_text()
CHALLENGES = (ROOT / "tests/fixtures/hades2/challenge_facility_room_model.lua").read_text()
PREFIX = GATHERING + CHAOS + SHOPS + CHALLENGES + """
dofile(assert(arg[1])); dofile(assert(arg[2]))
local M = __MacGamingTrainerV1
local function room(overrides)
  draw = .95
  local data = {
    Name='F_Combat01',RoomSetName='F',WellShopSpawnChance=0,
    ChallengeSpawnChance=.5,TimeChallengeEncounterOptions={'TimeChallengeF'},
    PerfectClearEncounterOptions={'PerfectClearChallengeF'},
    EliteChallengeEncounterOptions={'EliteChallengeF'},
  }
  for key,value in pairs(overrides or {}) do data[key] = value end
  CurrentRun.CurrentRoom = CreateRoom(data,{})
  CurrentRun.CurrentRoom.ChallengeChanceSuccess = false
  return CurrentRun.CurrentRoom
end
local function available()
  return M.dispatch('status',{includeCatalogs=false}).facilityOptions
end
local function option(kind)
  for _,row in ipairs(available()) do if row.id==kind then return row end end
end
local function generate(kind,id)
  local row=assert(option(kind),'missing native challenge family '..kind)
  return M.dispatch('generate_chamber_facility',{
    facility=kind,scopeToken=row.scopeToken,requestId=id,includeCatalogs=false,
  }),row
end
"""


def run(code):
    with tempfile.TemporaryDirectory(prefix="mgt-challenge-") as directory:
        harness = Path(directory) / "chamber.lua"
        harness.write_text(PREFIX + code)
        result = subprocess.run(
            [LUA, str(harness), str(ROOT / "Backend/games/hades2/runtime/hades.lua"),
             str(RESIDENT_DISPATCH_CONTRACT)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode:
            print(result.stdout, result.stderr)
            raise SystemExit(result.returncode)
        assert "chamber_challenge_ok" in result.stdout


CASES = [
r"""
local source=room()
assert(option('trove') and option('sigil') and option('monument'))
assert(not option('well') and not option('shrine') and not option('purging'))
local originalTime,originalSigil,originalMoon=IsTimeChallengeForced,IsPerfectClearChallengeForced,IsEliteChallengeForced
local oldTime,oldSigil,oldMoon=EncounterSets.TimeChallengeOptions,EncounterSets.PerfectClearOptions,EncounterSets.EliteChallengeOptions
local reply,token=generate('trove','challenge-trove')
assert(reply.applied and reply.actionOutcome=='completed')
local switch=source.ChallengeSwitch
assert(switch and switch.Name=='TimeChallengeSwitch_Money' and switch.ObjectId==211)
assert(IsUseable({Id=211}) and MapState.ActiveObstacles[211]==switch)
assert(switch.ReadyToUse and switch.UseText==switch.ChallengeAvailableUseText)
local encounter=source.ChallengeEncounter
assert(encounter.Name=='TimeChallengeF' and encounter.Switch==switch and encounter.SpawnNearId==211)
assert(CurrentRun.LastChallengeDepth==CurrentRun.RunDepthCache)
assert(nativeChallengeGen>0 and forcedUses.ForceChallengeSwitch==1)
assert(not forcedUses.ForcePerfectClearSwitch and not forcedUses.ForceEliteSwitch)
assert(not source.ChallengeChanceSuccess and not source.DoAnomalies)
assert(EncounterSets.TimeChallengeOptions==oldTime and EncounterSets.PerfectClearOptions==oldSigil and EncounterSets.EliteChallengeOptions==oldMoon)
assert(IsTimeChallengeForced==originalTime and IsPerfectClearChallengeForced==originalSigil and IsEliteChallengeForced==originalMoon)
AttemptUseChallengeSwitch(switch)
assert(encounter.InProgress and nativeChallengeUses==1)
CompleteChallenge()
assert(encounter.Completed and nativeRewards==1)
assert(not option('trove') and not option('sigil') and not option('monument'))
local repeated=M.dispatch('generate_chamber_facility',{facility='trove',scopeToken=token.scopeToken,requestId='challenge-trove'})
assert(repeated.duplicate and repeated.applied and nativeSpawns==1)
print('chamber_challenge_ok')
""",
r"""
local source=room({ChallengeChanceSuccess=false})
local result=generate('sigil','sigil-1')
assert(result.applied and source.ChallengeSwitch.Name=='PerfectClearChallengeSwitch_Pom')
assert(source.ChallengeSwitch.ReadyToUse)
assert(source.ChallengeEncounter.Name=='PerfectClearChallengeF')
assert(source.ChallengeSwitch.RewardType=='StackUpgrade')
AttemptUseChallengeSwitch(source.ChallengeSwitch)
assert(source.ChallengeEncounter.InProgress)
CompleteChallenge()
assert(source.ChallengeEncounter.Completed and nativeRewards==1)
assert(not forcedUses.ForceChallengeSwitch and forcedUses.ForcePerfectClearSwitch==1)
print('chamber_challenge_ok')
""",
r"""
local source=room()
local result=generate('monument','moon-1')
assert(result.applied and source.ChallengeSwitch.Name=='EliteChallengeSwitch_Talent')
assert(source.ChallengeSwitch.ReadyToUse)
assert(source.ChallengeEncounter.Name=='EliteChallengeF')
assert(source.ChallengeSwitch.RewardType=='TalentDrop')
assert(forcedUses.ForceEliteSwitch==1 and not forcedUses.ForceChallengeSwitch)
AttemptUseChallengeSwitch(source.ChallengeSwitch)
CompleteChallenge()
assert(source.ChallengeEncounter.Completed and nativeRewards==1)
print('chamber_challenge_ok')
""",
r"""
local source=room()
local row=assert(option('trove'))
source.ExitsUnlocked=false
assert(not option('trove'))
assert(not pcall(M.dispatch,'generate_chamber_facility',{
 facility='trove',scopeToken=row.scopeToken,requestId='before-clear',
}))
assert(nativeSpawns==0)
source.ExitsUnlocked=true
source.BlockExits=true
assert(#available()==0)
source.BlockExits=false
local result=generate('trove','unlocked-trove')
assert(result.applied and source.ChallengeSwitch.ReadyToUse)
print('chamber_challenge_ok')
""",
r"""
local source=room({ChallengeSpawnRequirements={allow=false}})
assert(not option('trove') and not option('sigil') and not option('monument'))
source.ChallengeSpawnRequirements={allow=true}
source.TimeChallengeSwitchRequirements={allow=false}
assert(not option('trove') and option('sigil') and option('monument'))
source.TimeChallengeSwitchRequirements={allow=true}
source.TimeChallengeEncounterOptions={}
assert(not option('trove') and option('monument') and option('sigil'))
assert(nativeSpawns==0 and nativeChallengeGen==0)
print('chamber_challenge_ok')
""",
r"""
local source=room()
local target=assert(option('monument'))
facilityPoints={}
assert(#available()==0)
assert(not pcall(M.dispatch,'generate_chamber_facility',{
  facility='monument',scopeToken=target.scopeToken,requestId='no-point',
}))
assert(nativeSpawns==0 and CurrentRun.LastChallengeDepth==nil)
facilityPoints={211}
CurrentRun.CurrentRoom=CreateRoom({Name='F_Second',RoomSetName='F'}, {})
assert(not pcall(M.dispatch,'generate_chamber_facility',{
  facility='monument',scopeToken=target.scopeToken,requestId='stale-room',
}))
assert(nativeSpawns==0 and CurrentRun.LastChallengeDepth==nil)
print('chamber_challenge_ok')
""",
r"""
local source=room()
local target=assert(option('trove'))
local originalSetup=SetupObstacle
local originalTime,originalPerfect,originalElite=IsTimeChallengeForced,IsPerfectClearChallengeForced,IsEliteChallengeForced
local oldTime,oldPerfect,oldElite=EncounterSets.TimeChallengeOptions,EncounterSets.PerfectClearOptions,EncounterSets.EliteChallengeOptions
SetupObstacle=function(object)
 originalSetup(object)
 error('native switch setup failed after mutation')
end
assert(not pcall(M.dispatch,'generate_chamber_facility',{
 facility='trove',scopeToken=target.scopeToken,requestId='unknown-1',
}))
assert(M.terminalActionUnknown and not source.ChallengeChanceSuccess)
assert(IsTimeChallengeForced==originalTime and IsPerfectClearChallengeForced==originalPerfect and IsEliteChallengeForced==originalElite)
assert(EncounterSets.TimeChallengeOptions==oldTime and EncounterSets.PerfectClearOptions==oldPerfect and EncounterSets.EliteChallengeOptions==oldElite)
assert(nativeSpawns==1)
assert(not pcall(M.dispatch,'generate_chamber_facility',{
 facility='trove',scopeToken=target.scopeToken,requestId='unknown-1',
}))
print('chamber_challenge_ok')
""",
]

for scenario in CASES:
    run(scenario)
print("hades2_chamber_challenge_generation_ok")
