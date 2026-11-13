"""Room-scoped native Chaos Gate generation, issue #729."""
import subprocess
import tempfile
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
LUA = require_lua52("direct Chaos Gate generation")
PREFIX = (ROOT / "tests/fixtures/hades2/gathering_room_model.lua").read_text().split("local nativeCreate = CreateRoom")[0]
PREFIX += (ROOT / "tests/fixtures/hades2/chaos_gate_room_model.lua").read_text()


def run(code):
    with tempfile.TemporaryDirectory(prefix="mgt-direct-chaos-") as directory:
        harness = Path(directory) / "room.lua"
        harness.write_text(PREFIX + code)
        result = subprocess.run(
            [LUA, str(harness), str(ROOT / "Backend/games/hades2/runtime/hades.lua"),
             str(RESIDENT_DISPATCH_CONTRACT)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode:
            print(result.stdout, result.stderr)
            raise SystemExit(result.returncode)
        assert "direct_chaos_ok" in result.stdout


CASES = [
r"""
local room = newRoom(0, .95)
assert(not room.SecretChanceSuccess)
local target = M.dispatch('status', {includeCatalogs=false}).chaosGateTarget
assert(target.available and target.scopeToken, '0% disabled independent one-shot')
local params = {scopeToken=target.scopeToken, requestId='one', includeCatalogs=false}
local result = M.dispatch('generate_chaos_gate', params)
assert(result.applied and result.actionOutcome=='completed' and spawns==1)
assert(result.chaosGateProbability==0 and room.SecretChanceSuccess==false)
local door = assert(gate())
assert(door.HealthCost==14 and door.Room.UsePreviousRoomSet and door.Room.PauseBiomeState)
assert(door.ReadyToUse and unlockedDoors==1 and previewDoors==1)
assert(room.ExitDoorRooms[door.ObjectId]=='Chaos_01')
assert(not result.chaosGateTarget.available and result.chaosGateTarget.reason=='hades2.chaosGate.unavailable.existing')
assert(M.dispatch('generate_chaos_gate', params).duplicate and spawns==1)
assert(not pcall(M.dispatch, 'generate_chaos_gate', {scopeToken=params.scopeToken,requestId='two'}))
CurrentRun.Hero.Health = 14; AttemptUseDoor(door); assert(charges==0)
CurrentRun.Hero.Health = 100; AttemptUseDoor(door); assert(charges==1)
assert(CurrentRun.CurrentRoom==door.Room and ChooseNextRoomData(CurrentRun).Name=='F_Next')
print('direct_chaos_ok')
""",
r"""
local room=newRoom(0,.95)
local token=M.dispatch('status',{includeCatalogs=false}).chaosGateTarget.scopeToken
assert(type(token)=='string')
room.ExitsUnlocked=false
local denied=M.dispatch('status',{includeCatalogs=false}).chaosGateTarget
assert(not denied.available and denied.reason=='hades2.chaosGate.unavailable.scene')
assert(not pcall(M.dispatch,'generate_chaos_gate',{
 scopeToken=token,requestId='before-clear',includeCatalogs=false,
}))
assert(spawns==0 and unlockedDoors==0)
room.ExitsUnlocked=true
room.BlockExits=true
assert(not M.dispatch('status',{includeCatalogs=false}).chaosGateTarget.available)
room.BlockExits=false
local restored=M.dispatch('status',{includeCatalogs=false}).chaosGateTarget
assert(restored.available)
local nativeHandle=HandleSecretSpawns
HandleSecretSpawns=function(run)
 nativeHandle(run)
 local door=gate()
 if door then door.ReadyToUse=false end
end
local result=M.dispatch('generate_chaos_gate',{
 scopeToken=restored.scopeToken,requestId='unlock-after-clear',includeCatalogs=false,
})
assert(result.applied and gate().ReadyToUse and unlockedDoors==1)
print('direct_chaos_ok')
""",
r"""
heroForce=true
newRoom(0, .99)
local target = M.dispatch('status', {includeCatalogs=false}).chaosGateTarget
assert(target.available)
local result = M.dispatch('generate_chaos_gate', {scopeToken=target.scopeToken,requestId='force',includeCatalogs=false})
assert(result.applied and spawns==1 and forceUses==1 and not heroForce and gate().HealthCost==0)
assert(result.chaosGateProbability==0)
print('direct_chaos_ok')
""",
r"""
heroForce=true
newRoom(0, .9)
local token=M.dispatch('status',{includeCatalogs=false}).chaosGateTarget.scopeToken
local old=CurrentRun.CurrentRoom
CurrentRun.CurrentRoom=CreateRoom({Name='F_Combat02',RoomSetName='F'}, {})
assert(not pcall(M.dispatch,'generate_chaos_gate',{scopeToken=token,requestId='stale'}))
assert(spawns==0 and forceUses==0 and heroForce)
CurrentRun.CurrentRoom=old; points={}
local observation=M.dispatch('status',{includeCatalogs=false}).chaosGateTarget
assert(not observation.available and observation.reason=='hades2.chaosGate.unavailable.placement')
print('direct_chaos_ok')
""",
r"""
local room=newRoom(0,.95)
RoomSets.Chaos={}
local target=M.dispatch('status',{includeCatalogs=false}).chaosGateTarget
assert(not target.available and target.reason=='hades2.chaosGate.unavailable.route')
RoomSets.Chaos={'Chaos_01'}
room.SecretDoorRequirements={allow=false}
target=M.dispatch('status',{includeCatalogs=false}).chaosGateTarget
assert(not target.available and target.reason=='hades2.chaosGate.unavailable.progression')
assert(spawns==0 and not room.ForceSecretDoor)
print('direct_chaos_ok')
""",
r"""
newRoom(0,.99)
local nativeHandle,nativeIds=HandleSecretSpawns,GetIdsByType
local facility,harvest=0,0
GetIdsByType=function(args)
 if args.Name=='ChallengeSwitchBase' then return {333} end
 return nativeIds(args)
end
local beforeIds=GetIdsByType
SetupHarvestPoints=function() harvest=harvest+1 end
local beforeHarvest=SetupHarvestPoints
HandleSecretSpawns=function(run)
 if #GetIdsByType({Name='ChallengeSwitchBase'})>0 then facility=facility+1 end
 SetupHarvestPoints(run.CurrentRoom)
 return nativeHandle(run)
end
local target=M.dispatch('status',{includeCatalogs=false}).chaosGateTarget
local result=M.dispatch('generate_chaos_gate',{scopeToken=target.scopeToken,requestId='isolate'})
assert(result.applied and facility==0 and harvest==0 and spawns==1)
assert(GetIdsByType==beforeIds and SetupHarvestPoints==beforeHarvest)
print('direct_chaos_ok')
""",
]

for scenario in CASES:
    run(scenario)
print("hades2_chaos_gate_generation_ok")
