import subprocess
import tempfile
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
LUA = require_lua52('Chaos Gate native room lifecycle')
PREFIX = (ROOT / 'tests/fixtures/hades2/gathering_room_model.lua').read_text().split('local nativeCreate = CreateRoom')[0]
PREFIX += (ROOT / 'tests/fixtures/hades2/chaos_gate_room_model.lua').read_text()


def run(code):
    with tempfile.TemporaryDirectory(prefix='mgt-chaos-gate-') as directory:
        harness = Path(directory) / 'room.lua'
        harness.write_text(PREFIX + code)
        result = subprocess.run([LUA, str(harness), str(ROOT / 'Backend/games/hades2/runtime/hades.lua'),
                                 str(RESIDENT_DISPATCH_CONTRACT)], capture_output=True, text=True, timeout=30)
        if result.returncode:
            print(result.stdout, result.stderr)
            raise SystemExit(result.returncode)
        assert 'chaos_gate_ok' in result.stdout


CASES = {'zero_blocks_ordinary_and_hero_force': r'''
heroForce = true
newRoom(0, 0)
HandleSecretSpawns(CurrentRun)
assert(spawns == 0 and forceUses == 0 and heroForce, 'zero consumed Hero Force or created gate')
print('chaos_gate_ok')
'''}

CASES['probability_boundaries_and_native_force_rules'] = r"""
for _, case in ipairs({ {0, 0, false}, {100, 1, true}, {25.5, .255, true}, {25.5, .25501, false} }) do
 local room = newRoom(case[1], case[2]); local before = draws
 assert(IsSecretDoorEligible(CurrentRun, room) == case[3], 'conditional occurrence boundary mismatch')
 assert(draws == before, 'eligibility preflight added a random draw')
end
heroForce = true
local forced = newRoom(25, .9)
assert(not forced.SecretChanceSuccess and IsSecretDoorEligible(CurrentRun, forced), 'nonzero overrode native Hero force eligibility')
GameState.ChaosUnlocked = false
assert(IsSecretDoorEligible(CurrentRun, forced), 'native Hero force progression rule changed')
newRoom(100, .5, {Name='F_Boss01', RoomSetName='F'})
assert(not IsSecretDoorEligible(CurrentRun, CurrentRun.CurrentRoom), 'native force boss rule bypassed')
heroForce = false
for _, data in ipairs({ {Name='F_Boss01', RoomSetName='F'}, {Name='Restricted', RoomSetName='F', SecretDoorRequirements={allow=false}} }) do
 local room = newRoom(100, .5, data); assert(not IsSecretDoorEligible(CurrentRun, room))
end
GameState.ChaosUnlocked = true
local room = newRoom(100, .5)
CurrentRun.RoomHistory = {{ForceSecretDoor=true}}
assert(not IsSecretDoorEligible(CurrentRun, room), 'native spacing bypassed')
print('chaos_gate_ok')
"""
CASES['native_routing_health_refusal_one_payment_and_return'] = r"""
local room = newRoom(100, .999)
HandleSecretSpawns(CurrentRun)
local door = assert(gate())
assert(spawns == 1 and room.ForceSecretDoor and door.Room.Name == 'Chaos_01')
assert(MapState.OfferedExitDoors[door.ObjectId] == door and room.ExitDoorRooms[door.ObjectId] == 'Chaos_01')
assert(door.Room.UsePreviousRoomSet and door.Room.PauseBiomeState and door.HealthCost == 14 and room.SecretDoorHealthCost == 14)
assert(door.OnUsedFunctionName == 'AttemptUseDoor', 'native door use owner missing')
CurrentRun.Hero.Health = 14; AttemptUseDoor(door)
assert(charges == 0 and CurrentRun.CurrentRoom == room, 'low health paid or entered early')
CurrentRun.Hero.Health = 100; exitsReady = false; AttemptUseDoor(door)
assert(charges == 0 and CurrentRun.CurrentRoom == room)
exitsReady = true; AttemptUseDoor(door); AttemptUseDoor(door)
assert(charges == 1 and CurrentRun.Hero.Health == 86 and CurrentRun.CurrentRoom == door.Room)
assert(ChooseNextRoomData(CurrentRun).Name == 'F_Next', 'Chaos lost native previous room set')
print('chaos_gate_ok')
"""
CASES['missing_transition_machinery_does_not_consume_force'] = r"""
heroForce = true
local room = newRoom(100, .5)
for _, change in ipairs({ function() points = {} end,
 function() RoomSets.Chaos = {} end,
 function() RoomData.Chaos_01.DebugOnly = true end,
 function() RoomData.Chaos_01.GameStateRequirements = {allow=false} end,
 function() RoomData.Chaos_01.UsePreviousRoomSet = false end,
 function() room.UsePreviousRoomSet = true end,
 function() room.RoomSetName = 'Missing' end,
 function() room.DoAnomalies = true end,
 function() ForceNextRoom = 'F_Next' end }) do
 points = {101}; RoomSets.Chaos = {'Chaos_01'}; RoomData.Chaos_01.DebugOnly = false
 RoomData.Chaos_01.GameStateRequirements = nil; RoomData.Chaos_01.UsePreviousRoomSet = true
 room.UsePreviousRoomSet = nil; room.RoomSetName = 'F'; room.DoAnomalies = nil; ForceNextRoom = nil
 change(); local before = draws; HandleSecretSpawns(CurrentRun)
 assert(draws == before, 'destination preflight added RNG')
 assert(spawns == 0 and forceUses == 0 and heroForce and not room.ForceSecretDoor, 'unsupported destination consumed or committed native force')
end
assert(ForceNextRoom == 'F_Next', 'preflight consumed native override')
ForceNextRoom = 'UnknownName'
assert(IsSecretDoorEligible(CurrentRun, room), 'native ignored override was treated as a routing conflict')
ForceNextRoom = 'Chaos_01'; HandleSecretSpawns(CurrentRun)
assert(spawns == 1 and gate().Room.Name == 'Chaos_01' and gate().HealthCost == 0 and forceUses == 1)
print('chaos_gate_ok')
"""
CASES['cached_setting_committed_owner_and_native_restore'] = r"""
heroForce = true
local room = newRoom(0, 0)
local before = draws
setChaos(100)
assert(not IsSecretDoorEligible(CurrentRun, room), 'changing setting rewrote cached zero room')
setChaos(nil)
assert(IsSecretDoorEligible == nativeEligible and IsSecretDoorEligible(CurrentRun, room), 'Native restore retained control predicate')
assert(draws == before and not room.SecretChanceSuccess and not room.ForceSecretDoor and forceUses == 0, 'Native restore redrew or consumed a cached room')
assert(M.json(M.dispatch('status', {includeCatalogs=false})):find('"chaosGateProbability":null', 1, true), 'full Native status omitted explicit null')
room = newRoom(100, .9); heroForce = false
setChaos(0)
assert(IsSecretDoorEligible(CurrentRun, room), 'new setting rewrote prepared successful room')
HandleSecretSpawns(CurrentRun)
local door = assert(gate()); local cost = door.HealthCost
setChaos(0)
assert(IsSecretDoorEligible(CurrentRun, room), 'committed Force owner was suppressed')
assert(room.SecretDoorHealthCost == cost and room.ExitDoorRooms[door.ObjectId] == 'Chaos_01')
print('chaos_gate_ok')
"""
CASES['gathering_coexistence_private_inputs_cleanup_and_actor_scope'] = r"""
setGathering({mining=0})
setChaos(100)
setGathering({})
assert(CreateRoom ~= nativeCreate and GetHarvestPointSpawnChance == nativeChance and IsSecretDoorEligible ~= nativeEligible, 'Gathering Native removed Chaos owner')
setGathering({mining=0})
setChaos(nil)
assert(CreateRoom ~= nativeCreate and GetHarvestPointSpawnChance ~= nativeChance and IsSecretDoorEligible == nativeEligible, 'Chaos Native removed Gathering owner')
setChaos(100)
local data = {Name='Both', RoomSetName='F', HasPickaxePoint=true, SecretSpawnChance=.1}
local overrides = {SecretSpawnChance=.3}; local args = {RoomOverrides=overrides}
draw = .5
local room = CreateRoom(data, args)
assert(room.SecretChanceSuccess and not room.PickaxePointSuccess)
assert(data.SecretSpawnChance == .1 and overrides.SecretSpawnChance == .3 and args.RoomOverrides == overrides and args.RewardStoreName == 'RunProgress')
for key in pairs(room) do assert(not tostring(key):find('Trainer') and key ~= 'chaosGateProbability') end
local oldRun = CurrentRun
CurrentRun = {Hero=oldRun.Hero, CurrentRoom=oldRun.CurrentRoom, BiomeHarvestPointsSeen={}}
room = CreateRoom(data, {})
assert(room.SecretChanceSuccess and not room.PickaxePointSuccess and M.run == oldRun, 'new run first room lost durable control or auto-adopted')
local session = SessionState; SessionState = {}
assert(not CreateRoom(data, {}).SecretChanceSuccess, 'foreign session controlled')
SessionState = session; M.terminalActionUnknown = true
assert(not CreateRoom(data, {}).SecretChanceSuccess, 'unknown action controlled new room')
M.dispatch('cleanup', {includeCatalogs=false})
assert(CreateRoom == nativeCreate and GetHarvestPointSpawnChance == nativeChance and IsSecretDoorEligible == nativeEligible, 'cleanup did not restore all owned hooks')
assert(M.chaosGateProbability == nil and next(M.gatheringProbabilities) == nil)
print('chaos_gate_ok')
"""

CASES['native_default_missing_api_and_owned_exception_cleanup'] = r"""
local initial = setChaos(nil)
assert(CreateRoom == nativeCreate and IsSecretDoorEligible == nativeEligible, 'Native installed a needless hook')
local before = draws
local input = {Name='Default', RoomSetName='F', SecretSpawnChance=0}
draw = 0
local room = CreateRoom(input, {})
assert(room.SecretChanceSuccess and draws == before + 1, 'Native inclusive-zero identity changed')
local cost = GetSecretDoorCost; GetSecretDoorCost = nil
assert(not pcall(setChaos, 100), 'missing native lifecycle API accepted controlled setup')
assert(CreateRoom == nativeCreate and IsSecretDoorEligible == nativeEligible and spawns == 0 and forceUses == 0)
GetSecretDoorCost = cost
setGathering({mining=0}); setChaos(0)
fault = true
local args = {RoomOverrides={SecretSpawnChance=.9}}
assert(not pcall(CreateRoom, {Name='Fault', RoomSetName='F', HasPickaxePoint=true}, args))
fault = false
assert(args.RoomOverrides.SecretSpawnChance == .9, 'exception rewrote caller override')
assert(GetHarvestPointSpawnChance(PickaxePointData, {}) == .2, 'room exception leaked private probability frame')
draw = 0
CurrentRun.CurrentRoom = nativeCreate({Name='Uncaptured', RoomSetName='F', SecretSpawnChance=1})
assert(IsSecretDoorEligible(CurrentRun, CurrentRun.CurrentRoom), 'exception leaked a captured room predicate')
local foreignCreate = function() return 'foreign' end
local foreignEligibility = function() return true end
CreateRoom, IsSecretDoorEligible = foreignCreate, foreignEligibility
M.dispatch('cleanup', {includeCatalogs=false})
assert(CreateRoom == foreignCreate and IsSecretDoorEligible == foreignEligibility and GetHarvestPointSpawnChance == nativeChance, 'cleanup overwrote foreign hooks')
print('chaos_gate_ok')
"""

for code in CASES.values():
    run(code)
print('hades2_chaos_gate_occurrence_ok')
