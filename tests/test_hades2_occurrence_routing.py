import subprocess
import tempfile
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
LUA = require_lua52("native occurrence routing")
BASE = (
    ROOT / "tests/fixtures/hades2/gathering_room_model.lua"
).read_text(encoding="utf-8").split("local nativeCreate = CreateRoom")[0]
MODEL = (
    ROOT / "tests/fixtures/hades2/occurrence_routing_model.lua"
).read_text(encoding="utf-8")
PREFIX = BASE + MODEL


def run(code):
    with tempfile.TemporaryDirectory(prefix="mgt-occurrence-routing-") as directory:
        harness = Path(directory) / "routing.lua"
        harness.write_text(PREFIX + code, encoding="utf-8")
        result = subprocess.run(
            [
                LUA,
                str(harness),
                str(ROOT / "Backend/games/hades2/runtime/hades.lua"),
                str(RESIDENT_DISPATCH_CONTRACT),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode:
            print(result.stdout, result.stderr)
            raise SystemExit(result.returncode)
        assert "occurrence_routing_ok" in result.stdout


CASES = {
    "catalog_exposes_stable_identity_without_native_route_ids": r"""
local status = M.dispatch("status", { includeCatalogs = true })
assert(type(status.occurrenceTargets) == "table" and #status.occurrenceTargets == 13)
local seen = {}
for _, row in ipairs(status.occurrenceTargets) do
  assert(type(row.id) == "string" and type(row.kind) == "string" and type(row.sourceId) == "string")
  assert(row.rooms == nil and row.encounters == nil and row.room == nil and row.encounter == nil,
    "catalog leaked native routing internals")
  seen[row.id] = row
end
assert(seen["npc:Nemesis"].sourceId == "Nemesis" and seen["npc:Nemesis"].kind == "character")
assert(seen["shop:Charon"].sourceId == "Charon" and seen["shop:Charon"].kind == "shop")
print("occurrence_routing_ok")
""",
    "room_target_waits_for_native_eligibility_and_consumes_on_offer": r"""
setRoomSet("F")
roomEligible.F_Story01 = false
setOccurrence("npc:Arachne", "room-token")
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
assert(M.nextOccurrenceTarget == "npc:Arachne", "ineligible Story target was consumed")
for _, door in pairs(MapState.OfferedExitDoors) do
  assert(door.Room.Name ~= "F_Story01", "ineligible Story target was routed")
end

roomEligible.F_Story01 = true
MapState.OfferedExitDoors = {}
CurrentRun.RoomCreations = {}
CurrentRun.CurrentRoom.RoomCreations = {}
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
local offered = 0
for _, door in pairs(MapState.OfferedExitDoors) do
  if door.Room.Name == "F_Story01" then offered = offered + 1 end
end
assert(offered == 1, "Story target was not offered exactly once")
assert(M.nextOccurrenceTarget == nil and M.nextOccurrenceToken == nil,
  "offered room did not consume the one-shot")
assert(M.lastConsumedNextOccurrenceToken == "room-token",
  "room consumption receipt was not recorded")
-- The player has not entered any offered room. Consumption at this point proves
-- option A semantics rather than guarantee-until-entered behavior.
assert(CurrentRun.CurrentRoom.Name == "F_Start", "fixture unexpectedly entered the offered room")
print("occurrence_routing_ok")
""",
    "native_forced_room_competitor_is_preserved": r"""
setRoomSet("F")
nativeRoomForced.F_Forced01 = true
setOccurrence("npc:Arachne", "forced-competitor")
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
assert(M.nextOccurrenceTarget == "npc:Arachne",
  "Trainer suppressed a native forced room and consumed early")
assert(MapState.OfferedExitDoors[1].Room.Name == "F_Forced01",
  "native forced room lost priority in fixture")
nativeRoomForced.F_Forced01 = nil
MapState.OfferedExitDoors = {}
CurrentRun.RoomCreations = {}
CurrentRun.CurrentRoom.RoomCreations = {}
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
assert(M.nextOccurrenceTarget == nil
  and M.lastConsumedNextOccurrenceToken == "forced-competitor")
print("occurrence_routing_ok")
""",
    "room_target_does_not_cross_native_room_set": r"""
setRoomSet("G")
setOccurrence("npc:Arachne", "wrong-biome")
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
assert(M.nextOccurrenceTarget == "npc:Arachne", "cross-biome request was consumed")
for _, door in pairs(MapState.OfferedExitDoors) do
  assert(door.Room.RoomSetName == "G" and door.Room.Name ~= "F_Story01")
end
print("occurrence_routing_ok")
""",
    "field_encounter_waits_for_eligibility_and_consumes_on_selection": r"""
setRoomSet("F")
CurrentRun.CurrentRoom.LegalEncounters = { "CombatNormal", "NemesisCombatF" }
encounterEligible.NemesisCombatF = false
setOccurrence("npc:Nemesis", "encounter-token")
local first = ChooseEncounter(CurrentRun, CurrentRun.CurrentRoom)
assert(first.Name == "CombatNormal" and M.nextOccurrenceTarget == "npc:Nemesis",
  "ineligible field NPC was selected or consumed")
encounterEligible.NemesisCombatF = true
local second = ChooseEncounter(CurrentRun, CurrentRun.CurrentRoom)
assert(second.Name == "NemesisCombatF", "eligible field NPC was not selected")
assert(M.nextOccurrenceTarget == nil and M.nextOccurrenceToken == nil)
assert(M.lastConsumedNextOccurrenceToken == "encounter-token")
print("occurrence_routing_ok")
""",
    "native_forced_encounter_competitor_is_preserved": r"""
setRoomSet("F")
CurrentRun.CurrentRoom.LegalEncounters = { "CombatNormal", "NemesisCombatF" }
nativeEncounterForced.CombatNormal = true
setOccurrence("npc:Nemesis", "encounter-forced")
local first = ChooseEncounter(CurrentRun, CurrentRun.CurrentRoom)
assert(first.Name == "CombatNormal" and M.nextOccurrenceTarget == "npc:Nemesis",
  "Trainer displaced a native forced encounter")
nativeEncounterForced.CombatNormal = nil
local second = ChooseEncounter(CurrentRun, CurrentRun.CurrentRoom)
assert(second.Name == "NemesisCombatF")
assert(M.lastConsumedNextOccurrenceToken == "encounter-forced")
print("occurrence_routing_ok")
""",
    "bridge_echo_and_charon_are_distinct_targets": r"""
setRoomSet("H")
CurrentRun.CurrentRoom = DeepCopyTable(RoomData.H_Bridge01)
CurrentRun.CurrentRoom.ChosenRewardType = "Story"
CurrentRun.CurrentRoom.LegalEncounters = {
  "Story_Echo_01", "Story_Echo_01", "BridgeShop", "BridgeNemesisRandomEvent",
}
setOccurrence("npc:Echo", "echo-token")
local echo = ChooseEncounter(CurrentRun, CurrentRun.CurrentRoom)
assert(echo.Name == "Story_Echo_01")
assert(M.lastConsumedNextOccurrenceToken == "echo-token")

setOccurrence("shop:Charon", "shop-token")
local shop = ChooseEncounter(CurrentRun, CurrentRun.CurrentRoom)
assert(shop.Name == "BridgeShop", "Charon bridge target selected a different Story encounter")
assert(M.lastConsumedNextOccurrenceToken == "shop-token")
print("occurrence_routing_ok")
""",
    "dedicated_charon_room_and_native_force_are_separate": r"""
setRoomSet("F")
setOccurrence("shop:Charon", "charon-room")
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
local found = false
for _, door in pairs(MapState.OfferedExitDoors) do
  if door.Room.Name == "F_Shop01" then found = true end
end
assert(found and M.lastConsumedNextOccurrenceToken == "charon-room")

setOccurrence("npc:Nemesis", "native-force")
CurrentRun.CurrentRoom.LegalEncounters = { "CombatNormal", "NemesisCombatF" }
ForceNextEncounter = "CombatNormal"
local forced = ChooseEncounter(CurrentRun, CurrentRun.CurrentRoom)
assert(forced.Name == "CombatNormal" and M.nextOccurrenceTarget == "npc:Nemesis",
  "explicit native ForceNextEncounter was overridden or consumed")
print("occurrence_routing_ok")
""",
    "linked_room_native_force_precedes_trainer_target": r"""
setRoomSet("F")
CurrentRun.CurrentRoom.LinkedRooms = { "F_Story01", "F_Forced01" }
nativeRoomForced.F_Forced01 = true
setOccurrence("npc:Arachne", "linked-room-token")
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
assert(MapState.OfferedExitDoors[1].Room.Name == "F_Forced01")
assert(M.nextOccurrenceTarget == "npc:Arachne" and M.lastConsumedNextOccurrenceToken == nil,
  "Trainer displaced native forced linked-room routing")
nativeRoomForced.F_Forced01 = nil
MapState.OfferedExitDoors = {}
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
assert(MapState.OfferedExitDoors[1].Room.Name == "F_Story01")
assert(M.lastConsumedNextOccurrenceToken == "linked-room-token")
print("occurrence_routing_ok")
""",
    "explicit_native_room_force_precedes_trainer_target": r"""
setRoomSet("F")
ForceNextRoom = "F_Forced01"
setOccurrence("npc:Arachne", "explicit-force-token")
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
assert(MapState.OfferedExitDoors[1].Room.Name == "F_Forced01")
assert(M.nextOccurrenceTarget == "npc:Arachne",
  "Trainer displaced explicit ForceNextRoom")
ForceNextRoom = nil
MapState.OfferedExitDoors = {}
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
assert(M.lastConsumedNextOccurrenceToken == "explicit-force-token")
print("occurrence_routing_ok")
""",
    "unavailable_preexisting_target_door_does_not_consume": r"""
setRoomSet("F")
MapState.OfferedExitDoors = {
  [1] = { ObjectId = 1, Room = { Name = "F_Story01", RoomSetName = "F" } },
  [2] = { ObjectId = 2, Room = { Name = "F_Combat01", RoomSetName = "F" } },
}
CurrentRun.CurrentRoom.UnavailableDoorIds = { 1 }
setOccurrence("npc:Arachne", "unavailable-door-token")
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
assert(M.nextOccurrenceTarget == "npc:Arachne"
  and M.lastConsumedNextOccurrenceToken == nil,
  "unavailable persistent target-shaped door consumed pending request")
assert(not MapState.OfferedExitDoors[1].PreviewCreated and not MapState.OfferedExitDoors[1].ReadyToUse)
CurrentRun.CurrentRoom.UnavailableDoorIds = nil
MapState.OfferedExitDoors = {}
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
assert(M.lastConsumedNextOccurrenceToken == "unavailable-door-token",
  "subsequently genuinely offered target room did not consume")
print("occurrence_routing_ok")
""",
    "skip_unlock_target_door_waits_until_actually_offered": r"""
setRoomSet("F")
MapState.OfferedExitDoors = {
  [1] = { ObjectId = 1, SkipUnlock = true, ChooseRoomArgs = {} },
}
setOccurrence("npc:Arachne", "skip-unlock-token")
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
assert(MapState.OfferedExitDoors[1].Room.Name == "F_Story01",
  "fixture did not reserve target room on skipped door")
assert(M.nextOccurrenceTarget == "npc:Arachne"
  and M.lastConsumedNextOccurrenceToken == nil,
  "skipped/unusable exit falsely consumed the one-shot")
assert(not MapState.OfferedExitDoors[1].PreviewCreated
  and not MapState.OfferedExitDoors[1].ReadyToUse)
MapState.OfferedExitDoors[1].SkipUnlock = false
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
assert(MapState.OfferedExitDoors[1].PreviewCreated
  and MapState.OfferedExitDoors[1].ReadyToUse)
assert(M.lastConsumedNextOccurrenceToken == "skip-unlock-token",
  "genuinely unlocked door did not generate consumption receipt")
print("occurrence_routing_ok")
""",
    "cleanup_restores_native_routing_owners": r"""
setRoomSet("F")
setOccurrence("npc:Arachne", "cleanup-token")
assert(IsRoomForced ~= nativeIsRoomForced and DoUnlockRoomExits ~= nativeDoUnlockRoomExits)
assert(ChooseNextRoomData ~= nativeChooseNextRoomData and GetRandomValue ~= nativeGetRandomValue)
assert(CreateDoorRewardPreview ~= nativeCreateDoorRewardPreview)
M.dispatch("cleanup", { includeCatalogs = false })
assert(IsRoomForced == nativeIsRoomForced and DoUnlockRoomExits == nativeDoUnlockRoomExits)
assert(ChooseNextRoomData == nativeChooseNextRoomData and GetRandomValue == nativeGetRandomValue)
assert(CreateDoorRewardPreview == nativeCreateDoorRewardPreview)
assert(IsEncounterForced == nativeIsEncounterForced and ChooseEncounter == nativeChooseEncounter)
assert(M.nextOccurrenceTarget == nil and M.nextOccurrenceToken == nil)
print("occurrence_routing_ok")
""",
}

for code in CASES.values():
    run(code)

print("hades2_occurrence_routing_ok")
