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
    "named_room_request_cannot_steer_multiple_ready_exits": r"""
setRoomSet("F")
-- Model a repeatable native room candidate. One Trainer occurrence lease
-- must select only one exit even if native MaxCreationsThisRun does not bail us out.
RoomData.F_Story01.MaxCreationsThisRun = nil
setOccurrence("npc:Arachne", "one-room-on-two-exits")
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
local selected, claimed
for _, door in pairs(MapState.OfferedExitDoors) do
  if door.ReadyToUse and door.Room.Name == "F_Story01" then
    selected = (selected or 0) + 1
    claimed = door
  end
end
assert(selected == 1,
  "one named occurrence request forced multiple generated native exits")
assert(M.nextOccurrenceToken == "one-room-on-two-exits"
    and M.lastConsumedNextOccurrenceToken == nil,
  "offering one requested exit consumed the run-scoped request")
AttemptUseDoor(claimed)
assert(M.nextOccurrenceTarget == nil
    and M.lastConsumedNextOccurrenceToken == "one-room-on-two-exits",
  "named room one-shot did not consume on selected native admission")
print("occurrence_routing_ok")
""",
    "replaced_named_room_exit_releases_its_selection_claim": r"""
setRoomSet("F")
RoomData.F_Story01.MaxCreationsThisRun = nil
setOccurrence("npc:Arachne", "replace-before-entry")
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
local first
for _, door in pairs(MapState.OfferedExitDoors) do
  if door.Room.Name == "F_Story01" then first = door end
end
assert(first, "named story room was not offered")
AssignRoomToExitDoor(first, CreateRoom(RoomData.F_Combat01, {}))
assert(M.nextOccurrenceTarget == "npc:Arachne",
  "native replacement consumed an unentered room request")
MapState.OfferedExitDoors[3] = { ObjectId = 3, ChooseRoomArgs = {} }
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
assert(MapState.OfferedExitDoors[3].Room.Name == "F_Story01",
  "replaced native room kept the named occurrence trapped in its old door")
print("occurrence_routing_ok")
""",
    "room_target_waits_for_native_eligibility_and_commits_on_start": r"""
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
assert(M.nextOccurrenceTarget == "npc:Arachne" and M.nextOccurrenceToken == "room-token"
    and M.lastConsumedNextOccurrenceToken == nil,
  "offered but unentered room consumed the one-shot")
assert(CurrentRun.CurrentRoom.Name == "F_Start", "fixture unexpectedly entered the offered room")
for _, door in pairs(MapState.OfferedExitDoors) do
  if door.Room.Name == "F_Story01" then AttemptUseDoor(door) end
end
assert(M.nextOccurrenceTarget == nil and M.nextOccurrenceToken == nil
    and M.lastConsumedNextOccurrenceToken == "room-token",
  "matching room's native StartRoom did not consume the one-shot")
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
assert(M.nextOccurrenceTarget == "npc:Arachne" and M.lastConsumedNextOccurrenceToken == nil,
  "later offering consumed without entering")
for _, door in pairs(MapState.OfferedExitDoors) do
  if door.Room.Name == "F_Story01" then AttemptUseDoor(door) end
end
assert(M.nextOccurrenceTarget == nil and M.lastConsumedNextOccurrenceToken == "forced-competitor")
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
    "arachne_combat_variants_are_supported_native_strategies": r"""
local variants = {
  { biome = "F", name = "ArachneCombatF" },
  { biome = "G", name = "ArachneCombatG" },
  { biome = "N", name = "ArachneCombatN" },
}
for index, variant in ipairs(variants) do
  setRoomSet(variant.biome)
  CurrentRun.CurrentRoom.LegalEncounters = { "CombatNormal", variant.name }
  setOccurrence("npc:Arachne", "arachne-combat-" .. tostring(index))
  local selected = ChooseEncounter(CurrentRun, CurrentRun.CurrentRoom)
  assert(selected.Name == variant.name,
    "Arachne combat variant was omitted from its native occurrence strategy: " .. variant.name)
  assert(M.nextOccurrenceTarget == "npc:Arachne"
      and M.lastConsumedNextOccurrenceToken ~= "arachne-combat-" .. tostring(index),
    "Arachne combat selection consumed before native RecordEncounter")
  RecordEncounter(CurrentRun, selected)
  assert(M.nextOccurrenceTarget == nil
      and M.lastConsumedNextOccurrenceToken == "arachne-combat-" .. tostring(index),
    "Arachne combat variant did not consume at native RecordEncounter: " .. variant.name)
end
print("occurrence_routing_ok")
""",
    "one_arachne_request_claims_only_one_native_strategy": r"""
setRoomSet("F")
RoomData.F_Story01.MaxCreationsThisRun = nil
CurrentRun.CurrentRoom.LegalEncounters = { "ArachneCombatF", "CombatNormal" }
setOccurrence("npc:Arachne", "arachne-story-first")
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
local storyDoor
for _, door in pairs(MapState.OfferedExitDoors) do
  if door.Room.Name == "F_Story01" then storyDoor = door end
end
assert(storyDoor and M.occurrenceRouting.roomClaim,
  "Arachne story strategy did not claim one native opportunity")
local nativeEncounter = ChooseEncounter(CurrentRun, CurrentRun.CurrentRoom)
assert(nativeEncounter.Name == "CombatNormal",
  "a claimed Arachne story path also forced its combat strategy")
assert(M.nextOccurrenceTarget == "npc:Arachne"
    and M.lastConsumedNextOccurrenceToken == nil,
  "alternate Arachne strategy consumed the story claim")
AttemptUseDoor(storyDoor)
assert(M.nextOccurrenceTarget == nil
    and M.lastConsumedNextOccurrenceToken == "arachne-story-first",
  "claimed Arachne story path did not consume exactly once")

setRoomSet("F")
RoomData.F_Story01.MaxCreationsThisRun = nil
CurrentRun.CurrentRoom.LegalEncounters = { "CombatNormal", "ArachneCombatF" }
setOccurrence("npc:Arachne", "arachne-combat-first")
local combat = ChooseEncounter(CurrentRun, CurrentRun.CurrentRoom)
assert(combat.Name == "ArachneCombatF" and M.occurrenceRouting.encounterClaim,
  "Arachne combat strategy did not claim its native opportunity")
MapState.OfferedExitDoors = {}
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
for _, door in pairs(MapState.OfferedExitDoors) do
  assert(door.Room.Name ~= "F_Story01",
    "a claimed Arachne combat path also forced its story strategy")
end
RecordEncounter(CurrentRun, combat)
assert(M.nextOccurrenceTarget == nil
    and M.lastConsumedNextOccurrenceToken == "arachne-combat-first",
  "claimed Arachne combat path did not consume exactly once")
print("occurrence_routing_ok")
""",
    "field_encounter_waits_for_eligibility_and_commits_on_record": r"""
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
assert(M.nextOccurrenceTarget == "npc:Nemesis" and M.nextOccurrenceToken == "encounter-token"
    and M.lastConsumedNextOccurrenceToken == nil,
  "encounter selection consumed before native occurrence bookkeeping")
RecordEncounter(CurrentRun, second)
assert(M.nextOccurrenceTarget == nil and M.nextOccurrenceToken == nil)
assert(M.lastConsumedNextOccurrenceToken == "encounter-token")
print("occurrence_routing_ok")
""",
    "departed_source_releases_encounter_claim_even_with_stale_exit_map": r"""
setRoomSet("F")
CurrentRun.CurrentRoom.LegalEncounters = { "CombatNormal", "NemesisCombatF" }
setOccurrence("npc:Nemesis", "source-departure")
local selected = ChooseEncounter(CurrentRun, CurrentRun.CurrentRoom)
assert(selected.Name == "NemesisCombatF" and M.occurrenceRouting.encounterClaim,
  "fixture did not establish the original encounter claim")
local oldSource = CurrentRun.CurrentRoom
CurrentRun.CurrentRoom = DeepCopyTable(RoomData.G_Combat01)
CurrentRun.CurrentRoom.LegalEncounters = { "CombatNormal", "NemesisCombatG" }
MapState.OfferedExitDoors = {
  [99] = { ObjectId = 99, ReadyToUse = true, Room = oldSource },
}
local nextSelected = ChooseEncounter(CurrentRun, CurrentRun.CurrentRoom)
assert(nextSelected.Name == "NemesisCombatG",
  "stale OfferedExitDoors kept a departed source encounter claim authoritative")
assert(M.occurrenceRouting.encounterClaim
    and M.occurrenceRouting.encounterClaim.room == CurrentRun.CurrentRoom,
  "new native opportunity did not replace the abandoned encounter claim")
RecordEncounter(CurrentRun, nextSelected)
assert(M.lastConsumedNextOccurrenceToken == "source-departure",
  "replacement native encounter did not consume the original run-scoped request")
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
assert(M.nextOccurrenceTarget == "npc:Nemesis" and M.lastConsumedNextOccurrenceToken == nil)
RecordEncounter(CurrentRun, second)
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
assert(M.nextOccurrenceTarget == "npc:Echo" and M.lastConsumedNextOccurrenceToken == nil)
RecordEncounter(CurrentRun, echo)
assert(M.lastConsumedNextOccurrenceToken == "echo-token")

setOccurrence("shop:Charon", "shop-token")
local shop = ChooseEncounter(CurrentRun, CurrentRun.CurrentRoom)
assert(shop.Name == "BridgeShop", "Charon bridge target selected a different Story encounter")
assert(M.nextOccurrenceTarget == "shop:Charon" and M.lastConsumedNextOccurrenceToken == "echo-token")
RecordEncounter(CurrentRun, shop)
assert(M.lastConsumedNextOccurrenceToken == "shop-token")
print("occurrence_routing_ok")
""",
    "dedicated_charon_room_and_native_force_are_separate": r"""
setRoomSet("F")
setOccurrence("shop:Charon", "charon-room")
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
local selected
for _, door in pairs(MapState.OfferedExitDoors) do
  if door.Room.Name == "F_Shop01" then selected = door end
end
assert(selected and M.nextOccurrenceTarget == "shop:Charon" and M.lastConsumedNextOccurrenceToken == nil)
AttemptUseDoor(selected)
assert(M.lastConsumedNextOccurrenceToken == "charon-room")

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
assert(M.lastConsumedNextOccurrenceToken == nil)
AttemptUseDoor(MapState.OfferedExitDoors[1])
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
assert(M.lastConsumedNextOccurrenceToken == nil)
for _, door in pairs(MapState.OfferedExitDoors) do
  if door.Room.Name == "F_Story01" then AttemptUseDoor(door) end
end
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
assert(M.lastConsumedNextOccurrenceToken == nil,
  "subsequently offered target room consumed before use")
for _, door in pairs(MapState.OfferedExitDoors) do
  if door.ReadyToUse and door.Room.Name == "F_Story01" then AttemptUseDoor(door) end
end
assert(M.lastConsumedNextOccurrenceToken == "unavailable-door-token",
  "subsequent native StartRoom did not consume")
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
assert(M.lastConsumedNextOccurrenceToken == nil,
  "genuinely unlocked but unentered door consumed the request")
AttemptUseDoor(MapState.OfferedExitDoors[1])
assert(M.lastConsumedNextOccurrenceToken == "skip-unlock-token",
  "native StartRoom did not generate the consumption receipt")
print("occurrence_routing_ok")
""",
    "run_and_hero_identity_replacement_revokes_pending_occurrence": r"""
setRoomSet("F")
setOccurrence("npc:Arachne", "hero-owner")
local originalHero = CurrentRun.Hero
CurrentRun.Hero = { ObjectId = 998, Traits = {} }
-- A second explicit Apply must not be blocked by a stale lease from another
-- Hero identity; preflight retires the previous resident owner first.
setOccurrence("npc:Arachne", "replacement-hero-owner")
assert(M.nextOccurrenceToken == "replacement-hero-owner"
    and M.occurrenceRouting.ownerHero == CurrentRun.Hero,
  "Hero replacement retained or mis-owned the previous occurrence lease")

local sameHero = CurrentRun.Hero
local replacementRun = {}
for key, value in pairs(CurrentRun) do replacementRun[key] = value end
replacementRun.Hero = sameHero
CurrentRun = replacementRun
local observed = M.dispatch("status", { includeCatalogs = false })
assert(M.nextOccurrenceTarget == nil and M.nextOccurrenceToken == nil,
  "run replacement retained a resident occurrence lease")
assert(observed.worldActions.occurrence == nil,
  "status projected a stale occurrence after run replacement")
assert(ChooseNextRoomData == nativeChooseNextRoomData
    and StartRoom == nativeStartRoom and GetRandomValue == nativeGetRandomValue,
  "run replacement left occurrence routing hooks installed")
print("occurrence_routing_ok")
""",
    "active_target_is_locked_until_cancel_then_owner_can_change": r"""
setRoomSet("F")
setOccurrence("npc:Arachne", "room-first")
assert(StartRoom ~= nativeStartRoom and ChooseNextRoomData ~= nativeChooseNextRoomData)

local switched = pcall(function()
  setOccurrence("npc:Nemesis", "encounter-while-armed")
end)
assert(not switched and M.nextOccurrenceTarget == "npc:Arachne"
    and M.nextOccurrenceToken == "room-first",
  "a second Apply replaced an active occurrence lease")

M.dispatch("cancel_world_occurrence", {
  leaseToken = M.nextOccurrenceToken,
  requestId = "cancel-room-first",
  includeCatalogs = false,
})
assert(StartRoom == nativeStartRoom and ChooseNextRoomData == nativeChooseNextRoomData)

setOccurrence("npc:Nemesis", "encounter-next")
assert(StartRoom == nativeStartRoom and ChooseNextRoomData == nativeChooseNextRoomData
    and ChooseEncounter ~= nativeChooseEncounter and RecordEncounter ~= nativeRecordEncounter,
  "cancel then Apply did not move ownership to the encounter seam")

M.dispatch("cancel_world_occurrence", {
  leaseToken = M.nextOccurrenceToken,
  requestId = "cancel-encounter-next",
  includeCatalogs = false,
})
assert(StartRoom == nativeStartRoom and ChooseNextRoomData == nativeChooseNextRoomData
    and ChooseEncounter == nativeChooseEncounter and RecordEncounter == nativeRecordEncounter
    and GetRandomValue == nativeGetRandomValue,
  "cancellation retained native selection or commit owners")
print("occurrence_routing_ok")
""",
    "cleanup_restores_native_routing_owners": r"""
setRoomSet("F")
setOccurrence("npc:Arachne", "cleanup-token")
assert(IsRoomForced ~= nativeIsRoomForced and DoUnlockRoomExits == nativeDoUnlockRoomExits)
assert(ChooseNextRoomData ~= nativeChooseNextRoomData and GetRandomValue ~= nativeGetRandomValue)
assert(CreateDoorRewardPreview == nativeCreateDoorRewardPreview and StartRoom ~= nativeStartRoom)
M.dispatch("cleanup", { includeCatalogs = false })
assert(IsRoomForced == nativeIsRoomForced and DoUnlockRoomExits == nativeDoUnlockRoomExits)
assert(ChooseNextRoomData == nativeChooseNextRoomData and GetRandomValue == nativeGetRandomValue)
assert(CreateDoorRewardPreview == nativeCreateDoorRewardPreview and StartRoom == nativeStartRoom)
assert(IsEncounterForced == nativeIsEncounterForced and ChooseEncounter == nativeChooseEncounter
    and RecordEncounter == nativeRecordEncounter)
assert(M.nextOccurrenceTarget == nil and M.nextOccurrenceToken == nil)
print("occurrence_routing_ok")
""",
}

for code in CASES.values():
    run(code)

print("hades2_occurrence_routing_ok")
