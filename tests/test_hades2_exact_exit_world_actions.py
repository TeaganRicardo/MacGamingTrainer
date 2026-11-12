"""Direction B: Hades II world actions own one exact generated exit."""
import subprocess
import tempfile
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
LUA = require_lua52("Hades II exact-exit world actions")
BASE = (
    ROOT / "tests/fixtures/hades2/gathering_room_model.lua"
).read_text(encoding="utf-8").split("local nativeCreate = CreateRoom")[0]
MODEL = (
    ROOT / "tests/fixtures/hades2/occurrence_routing_model.lua"
).read_text(encoding="utf-8")

scenario = r"""
setRoomSet("F")
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)

local function world()
  local status = M.dispatch("status", { includeCatalogs = true })
  assert(type(status.worldActions) == "table", "status lacks game-owned World Actions observation")
  assert(type(status.worldActions.exits) == "table", "status lacks exact generated exits")
  return status.worldActions
end

local function exitByObject(id)
  for _, row in ipairs(world().exits) do
    if row.objectId == id then return row end
  end
  error("missing observed exit " .. tostring(id))
end

local function targetExists(row, kind, target)
  for _, candidate in ipairs(row.targets or {}) do
    if candidate.kind == kind and candidate.id == target then return true end
  end
  return false
end

local door1, door2 = MapState.OfferedExitDoors[1], MapState.OfferedExitDoors[2]
assert(door1 and door2 and door1.Room and door2.Room)

-- Seed ordinary native rewards after room creation so both exact exits expose a
-- meaningful current descriptor and an exact OfferedRewards snapshot.
door1.Room.ChosenRewardType = "RoomMoneyDrop"
door2.Room.ChosenRewardType = "MaxManaDrop"
AssignRoomToExitDoor(door1, door1.Room)
AssignRoomToExitDoor(door2, door2.Room)
CreateDoorRewardPreview(door1)
CreateDoorRewardPreview(door2)

assert(RoomData.F_Combat01.Tags == nil, "fixture started with normalized candidate Tags")
local first, second = exitByObject(1), exitByObject(2)
assert(RoomData.F_Combat01.Tags == nil,
  "World Actions catalog probing mutated native RoomData")
assert(type(first.doorToken) == "string" and first.doorToken ~= "")
assert(type(second.doorToken) == "string" and second.doorToken ~= ""
    and first.doorToken ~= second.doorToken,
  "exact exits do not have independent native identity")
assert(first.reward == "RoomMoneyDrop" and second.reward == "MaxManaDrop")
assert(targetExists(first, "reward", "MaxHealthDrop"),
  "selected exit lacks a native-eligible ordinary reward target")
assert(targetExists(first, "roomCategory", "combat"),
  "selected exit lacks a native-eligible generic room-category target")

-- IsRoomRewardEligible calls native game-state requirements, which may count
-- checks and sample ChanceToPlay. Catalog inspection must do neither and must
-- hide rewards whose eligibility depends on native RNG.
local previousSession, nativeRewardEligible = SessionMapState, IsRoomRewardEligible
local rewardUsesRandom = false
SessionMapState = { RequirementChecksThisFrame = 17 }
local observedSession = SessionMapState
IsRoomRewardEligible = function(run, room, reward, previously, args)
  SessionMapState.RequirementChecksThisFrame =
    SessionMapState.RequirementChecksThisFrame + 1
  if rewardUsesRandom and reward.Name == "MaxHealthDrop" then
    return GetRandomValue({ true, false })
  end
  return nativeRewardEligible(run, room, reward, previously, args)
end
local beforeRewardProbeRNG = nativeRandomCalls
assert(targetExists(exitByObject(1), "reward", "MaxHealthDrop"))
assert(SessionMapState == observedSession
    and SessionMapState.RequirementChecksThisFrame == 17
    and nativeRandomCalls == beforeRewardProbeRNG,
  "reward catalog inspection mutated native frame counters or RNG")
rewardUsesRandom = true
assert(not targetExists(exitByObject(1), "reward", "MaxHealthDrop"),
  "random-dependent native reward eligibility was presented as guaranteed")
assert(SessionMapState == observedSession
    and SessionMapState.RequirementChecksThisFrame == 17
    and nativeRandomCalls == beforeRewardProbeRNG,
  "random-dependent reward probe leaked native RNG or frame counter state")
IsRoomRewardEligible = nativeRewardEligible
SessionMapState = previousSession

-- Native eligibility and force predicates are probed without advancing the
-- game's RNG. Random-dependent predicates fail closed for generic categories.
probeEligibilityUsesRandom = true
local beforeEligibilityProbe = nativeRandomCalls
assert(not targetExists(exitByObject(1), "roomCategory", "combat"))
assert(nativeRandomCalls == beforeEligibilityProbe,
  "IsRoomEligible inspection consumed native RNG")
probeEligibilityUsesRandom = false
assert(targetExists(exitByObject(1), "roomCategory", "combat"))
RoomData.F_Forced01.RandomForced = true
probeForceUsesRandom = true
local beforeForceProbe = nativeRandomCalls
assert(not targetExists(exitByObject(1), "roomCategory", "combat"),
  "random-dependent native force logic exposed a generic route")
assert(nativeRandomCalls == beforeForceProbe,
  "IsRoomForced inspection consumed native RNG")
probeForceUsesRandom = false
RoomData.F_Forced01.RandomForced = nil
assert(targetExists(exitByObject(1), "roomCategory", "combat"))

-- Reward edits mutate only the selected native exit and retain the same
-- physical-door/target identity. Cancel restores the exact original descriptor.
local originalRoom1, originalRoom2 = door1.Room, door2.Room
local originalOffered1 = DeepCopyTable(CurrentRun.CurrentRoom.OfferedRewards[1])
local originalOffered2 = DeepCopyTable(CurrentRun.CurrentRoom.OfferedRewards[2])
local rewardReply = M.dispatch("apply_world_exit", {
  doorToken = first.doorToken,
  kind = "reward",
  target = "MaxHealthDrop",
  requestId = "reward-exit-1",
  includeCatalogs = true,
})
local rewardLease = rewardReply.worldActions.exits[1].activeLease
assert(type(rewardLease) == "table" and rewardLease.kind == "reward"
    and rewardLease.target == "MaxHealthDrop"
    and type(rewardLease.leaseToken) == "string")
assert(door1.Room == originalRoom1 and door1.Room.ChosenRewardType == "MaxHealthDrop")
assert(door2.Room == originalRoom2 and door2.Room.ChosenRewardType == "MaxManaDrop",
  "editing exit 1 changed a competing exit")
assert(exitByObject(1).doorToken == first.doorToken,
  "reward-field mutation changed stable exact-exit identity")

M.dispatch("cancel_world_exit", {
  doorToken = first.doorToken,
  leaseToken = rewardLease.leaseToken,
  requestId = "cancel-reward-exit-1",
  includeCatalogs = true,
})
assert(door1.Room == originalRoom1 and door1.Room.ChosenRewardType == "RoomMoneyDrop")
assert(door2.Room == originalRoom2 and door2.Room.ChosenRewardType == "MaxManaDrop")
assert(CurrentRun.CurrentRoom.OfferedRewards[1].Type == originalOffered1.Type
    and CurrentRun.CurrentRoom.OfferedRewards[1].ForceLootName == originalOffered1.ForceLootName)
assert(CurrentRun.CurrentRoom.OfferedRewards[2].Type == originalOffered2.Type
    and CurrentRun.CurrentRoom.OfferedRewards[2].ForceLootName == originalOffered2.ForceLootName)
assert(exitByObject(1).activeLease == nil)
assert(door1.PreviewRoomName == originalRoom1.Name
    and door1.PreviewReward == originalRoom1.ChosenRewardType,
  "route cancellation did not restore the native preview descriptor")

-- Native map tables may be absent or be populated by another exit while a
-- lease is active. Snapshot must be read-only and Cancel must remove only the
-- selected exit's changes, preserving both original absence and sibling work.
local function exerciseMissingNativeMaps(withSibling)
  local source = CurrentRun.CurrentRoom
  local savedOffered, savedExitRooms = source.OfferedRewards, source.ExitDoorRooms
  source.OfferedRewards = nil
  source.ExitDoorRooms = nil
  local exit = exitByObject(1)
  local receipt = M.dispatch("apply_world_exit", {
    doorToken = exit.doorToken, kind = "reward", target = "MaxHealthDrop",
    requestId = "missing-maps-" .. tostring(withSibling), includeCatalogs = true,
  })
  local applied = receipt.worldActions.exits[1].activeLease
  assert(applied ~= nil and type(source.OfferedRewards) == "table"
      and type(source.ExitDoorRooms) == "table",
    "native reward assignment failed with initially absent source maps")
  if withSibling then
    source.OfferedRewards[2] = { Type = "MaxManaDrop" }
    source.ExitDoorRooms[2] = "F_IndependentRoom"
  end
  M.dispatch("cancel_world_exit", {
    doorToken = exit.doorToken, leaseToken = applied.leaseToken,
    requestId = "cancel-missing-maps-" .. tostring(withSibling),
    includeCatalogs = true,
  })
  if withSibling then
    assert(source.OfferedRewards[1] == nil and source.OfferedRewards[2].Type == "MaxManaDrop"
        and source.ExitDoorRooms[1] == nil and source.ExitDoorRooms[2] == "F_IndependentRoom",
      "cancelling one native reward overwrote a sibling map update")
  else
    assert(source.OfferedRewards == nil and source.ExitDoorRooms == nil,
      "cancelling a native reward did not restore absent map fields")
  end
  source.OfferedRewards, source.ExitDoorRooms = savedOffered, savedExitRooms
  assert(exitByObject(1).activeLease == nil
      and door1.Room.ChosenRewardType == "RoomMoneyDrop",
    "missing-map reward cancellation left a stale lease or room value")
end
exerciseMissingNativeMaps(false)
exerciseMissingNativeMaps(true)

-- A generic category Apply is a reservation only: no candidate sampling,
-- CreateRoom, actual door target, ExitDoorRooms or OfferedRewards mutation.
local drawsBefore = nativeRandomCalls
local combatCreationsBefore = CurrentRun.RoomCreations.F_Combat01 or 0
local sourceRoom = CurrentRun.CurrentRoom
local sourceExitRoom1 = sourceRoom.ExitDoorRooms[1]
local sourceExitRoom2 = sourceRoom.ExitDoorRooms[2]
local offeredBefore1 = DeepCopyTable(sourceRoom.OfferedRewards[1])
local previewsBefore = previewCalls
local routeReply = M.dispatch("apply_world_exit", {
  doorToken = first.doorToken,
  kind = "roomCategory",
  target = "combat",
  requestId = "route-exit-1",
  includeCatalogs = true,
})
local routeLease = routeReply.worldActions.exits[1].activeLease
assert(type(routeLease) == "table" and routeLease.kind == "roomCategory"
    and routeLease.target == "combat")
assert(nativeRandomCalls == drawsBefore
    and (CurrentRun.RoomCreations.F_Combat01 or 0) == combatCreationsBefore,
  "category Apply sampled or created a destination")
assert(door1.Room == originalRoom1 and sourceRoom.ExitDoorRooms[1] == sourceExitRoom1
    and sourceRoom.ExitDoorRooms[2] == sourceExitRoom2,
  "category Apply changed the native exit graph")
assert(sourceRoom.OfferedRewards[1].Type == offeredBefore1.Type
    and sourceRoom.OfferedRewards[1].ForceLootName == offeredBefore1.ForceLootName)
assert(previewCalls > previewsBefore, "reservation did not refresh native exit presentation")
assert(door1.PreviewRoomName == originalRoom1.Name
    and door1.PreviewReward == ""
    and door1.PreviewOverride == "ExitPreview",
  "generic reservation preview claimed an uncommitted concrete room or reward")

M.dispatch("cancel_world_exit", {
  doorToken = first.doorToken,
  leaseToken = routeLease.leaseToken,
  requestId = "cancel-route-exit-1",
  includeCatalogs = true,
})
assert(nativeRandomCalls == drawsBefore
    and (CurrentRun.RoomCreations.F_Combat01 or 0) == combatCreationsBefore,
  "category Cancel left RNG or room-creation residue")
assert(door1.Room == originalRoom1 and sourceRoom.ExitDoorRooms[1] == sourceExitRoom1)
assert(door1.PreviewRoomName == originalRoom1.Name
    and door1.PreviewReward == originalRoom1.ChosenRewardType
    and door1.PreviewOverride == originalRoom1.RewardPreviewOverride,
  "cancel did not restore the original native door preview")
assert(exitByObject(1).activeLease == nil)

-- Two doors may hold independent plans. Native denial commits neither. The
-- selected authorized door materializes exactly once at LeaveRoom, then source
-- departure invalidates its sibling lease.
local firstNow, secondNow = exitByObject(1), exitByObject(2)
local a = M.dispatch("apply_world_exit", {
  doorToken = firstNow.doorToken, kind = "roomCategory", target = "combat",
  requestId = "route-a", includeCatalogs = true,
})
local b = M.dispatch("apply_world_exit", {
  doorToken = secondNow.doorToken, kind = "roomCategory", target = "combat",
  requestId = "route-b", includeCatalogs = true,
})
assert(a.worldActions.exits[1].activeLease ~= nil)
assert(exitByObject(2).activeLease ~= nil, "second exact exit overwrote the first plan")

door1.Blocked = true
local deniedDraws = nativeRandomCalls
local deniedCreations = CurrentRun.RoomCreations.F_Combat01 or 0
assert(AttemptUseDoor(door1) == false and nativeLeaveCalls == 0)
assert(nativeRandomCalls == deniedDraws
    and (CurrentRun.RoomCreations.F_Combat01 or 0) == deniedCreations,
  "denied native door use committed a reserved category")
door1.Blocked = nil

local entered = AttemptUseDoor(door1)
assert(type(entered) == "table" and entered.Name == "F_Combat01",
  "authorized exact exit did not enter the planned generic category")
assert(nativeLeaveCalls == 1 and nativeRandomCalls == deniedDraws + 1
    and (CurrentRun.RoomCreations.F_Combat01 or 0) == deniedCreations + 1,
  "authorized exact exit did not materialize exactly one destination")
assert(door1.Room == entered, "native door still points at the pre-plan destination")

-- Observe against the source room object because StartRoom has changed
-- CurrentRun.CurrentRoom. Both source-room leases are consumed/invalidated.
assert(sourceRoom.ExitDoorRooms[1] == entered.Name,
  "late commit failed to update the native source-room exit map")
assert(door2.Room == originalRoom2
    and door2.PreviewRoomName == originalRoom2.Name
    and exitByObject(2).activeLease == nil,
  "committing one route left a sibling route preview or lease behind")

-- Exact-exit route ownership has deterministic precedence over a pending
-- room-based named occurrence. The route commits one room; the incompatible
-- occurrence stays armed for a later native-eligible opportunity instead of
-- overwriting the selected door or generating a second room.
setRoomSet("F")
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
local precedenceDoor = MapState.OfferedExitDoors[1]
precedenceDoor.Room.ChosenRewardType = "RoomMoneyDrop"
AssignRoomToExitDoor(precedenceDoor, precedenceDoor.Room)
local precedenceExit = exitByObject(1)
setOccurrence("npc:Arachne", "occurrence-after-exits")
local precedenceCreations = CurrentRun.RoomCreations.F_Combat01 or 0
local precedenceReply = M.dispatch("apply_world_exit", {
  doorToken = precedenceExit.doorToken,
  kind = "roomCategory",
  target = "combat",
  requestId = "route-with-room-occurrence",
  includeCatalogs = true,
})
assert(precedenceReply.worldActions.exits[1].activeLease ~= nil)
local precedenceEntered = AttemptUseDoor(precedenceDoor)
assert(type(precedenceEntered) == "table" and precedenceEntered.Name == "F_Combat01")
assert((CurrentRun.RoomCreations.F_Combat01 or 0) == precedenceCreations + 1,
  "route/occurrence interaction generated more than one destination")
assert(M.nextOccurrenceTarget == "npc:Arachne"
    and M.nextOccurrenceToken == "occurrence-after-exits",
  "exact exit route silently consumed or replaced an incompatible room occurrence")
M.dispatch("cancel_world_occurrence", {
  leaseToken = M.nextOccurrenceToken,
  requestId = "cancel-precedence-occurrence",
  includeCatalogs = false,
})

-- Leaving through one exit restores an unused reward lease on its sibling.
-- Native random selection otherwise offers a forced story room in slot 2;
-- construct an ordinary native-generated combat exit for the reward lease.
setRoomSet("F")
MapState.OfferedExitDoors = {
  [1] = { ObjectId = 1, ChooseRoomArgs = {} },
  [2] = { ObjectId = 2, ChooseRoomArgs = {}, ForceRoomName = "F_Combat01" },
}
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
local cleanupDoor1, cleanupDoor2 = MapState.OfferedExitDoors[1], MapState.OfferedExitDoors[2]
local cleanupRoom2 = cleanupDoor2.Room
local cleanupExit2 = exitByObject(2)
assert(cleanupDoor2.Room.Name == "F_Combat01"
    and targetExists(cleanupExit2, "reward", "MaxHealthDrop"),
  "fixture must generate a genuinely native-eligible ordinary sibling")
local rewardLeaseReply = M.dispatch("apply_world_exit", {
  doorToken = cleanupExit2.doorToken,
  kind = "reward",
  target = "MaxHealthDrop",
  requestId = "sibling-reward-lease",
  includeCatalogs = true,
})
assert(cleanupDoor2.Room.ChosenRewardType == "MaxHealthDrop")
local routeExit1 = exitByObject(1)
M.dispatch("apply_world_exit", {
  doorToken = routeExit1.doorToken,
  kind = "roomCategory",
  target = "combat",
  requestId = "commit-other-exit",
  includeCatalogs = true,
})
local siblingCommitted = AttemptUseDoor(cleanupDoor1)
assert(type(siblingCommitted) == "table" and siblingCommitted.Name == "F_Combat01")
assert(cleanupDoor2.Room == cleanupRoom2
    and cleanupDoor2.Room.ChosenRewardType == "RoomMoneyDrop"
    and exitByObject(2).activeLease == nil,
  "committing another exit left an unused reward modification behind")

-- Re-enter a fresh source fixture to prove external native replacement changes
-- exact target identity and invalidates stale lease authority.
setRoomSet("F")
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
local rerollDoor = MapState.OfferedExitDoors[1]
rerollDoor.Room.ChosenRewardType = "RoomMoneyDrop"
AssignRoomToExitDoor(rerollDoor, rerollDoor.Room)
local beforeReroll = exitByObject(1)
local pending = M.dispatch("apply_world_exit", {
  doorToken = beforeReroll.doorToken, kind = "roomCategory", target = "combat",
  requestId = "route-before-reroll", includeCatalogs = true,
})
local staleLease = pending.worldActions.exits[1].activeLease.leaseToken
local replacement = CreateRoom(RoomData.F_Combat01, { SkipChooseReward = true, SkipChooseEncounter = true })
replacement.ChosenRewardType = "MaxManaDrop"
AssignRoomToExitDoor(rerollDoor, replacement)
CreateDoorRewardPreview(rerollDoor)
local afterReroll = exitByObject(1)
assert(afterReroll.doorToken ~= beforeReroll.doorToken and afterReroll.activeLease == nil,
  "native target replacement retained stale exact-exit authority")
local ok = pcall(function()
  M.dispatch("cancel_world_exit", {
    doorToken = beforeReroll.doorToken,
    leaseToken = staleLease,
    requestId = "stale-cancel",
    includeCatalogs = true,
  })
end)
assert(not ok, "stale lease cancelled a replacement native target")

-- An in-place native reroll keeps the physical Room table, but revokes its
-- formerly observed token. Returning to the same descriptor must not revive
-- the old token (ABA).
local beforeNativeInPlace = exitByObject(1).doorToken
local nativeType = rerollDoor.Room.ChosenRewardType
local nativeReward = rerollDoor.Room.Reward
rerollDoor.Room.ChosenRewardType = "RoomMoneyDrop"
rerollDoor.Room.Reward = { Name = "RoomMoneyDrop" }
local afterNativeInPlace = exitByObject(1).doorToken
assert(afterNativeInPlace ~= beforeNativeInPlace,
  "native in-place reward reroll retained an obsolete door token")
rerollDoor.Room.ChosenRewardType = nativeType
rerollDoor.Room.Reward = nativeReward
assert(exitByObject(1).doorToken ~= beforeNativeInPlace,
  "native reward ABA restored the obsolete exact-exit token")
local obsoleteApply = pcall(function()
  M.dispatch("apply_world_exit", {
    doorToken = beforeNativeInPlace, kind = "reward", target = "MaxHealthDrop",
    requestId = "obsolete-aba-apply", includeCatalogs = true,
  })
end)
assert(not obsoleteApply, "obsolete native reward token re-applied a world edit")

-- Linked/critical source routing remains native-owned and cannot be overridden
-- by a generic category reservation.
CurrentRun.CurrentRoom.LinkedRoom = "F_Combat01"
local linked = exitByObject(1)
assert(not targetExists(linked, "roomCategory", "combat"),
  "linked native source incorrectly advertises generic route replacement")
local linkedOk = pcall(function()
  M.dispatch("apply_world_exit", {
    doorToken = linked.doorToken, kind = "roomCategory", target = "combat",
    requestId = "linked-route", includeCatalogs = true,
  })
end)
assert(not linkedOk, "linked native source accepted a generic category override")

-- A native CreateRoom/Assign failure occurs after AttemptUseDoor has passed its
-- eligibility/cost boundary. World Actions must fall back to the already
-- generated original door, restore graph entries and leave via native once.
local originalCreateRoom, originalAssign = CreateRoom, AssignRoomToExitDoor
for _, injected in ipairs({ "create", "assign" }) do
  setRoomSet("F")
  DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
  local faultDoor = MapState.OfferedExitDoors[1]
  local originalDestination = faultDoor.Room
  local faultSource = CurrentRun.CurrentRoom
  local offeredBefore = DeepCopyTable(faultSource.OfferedRewards[1])
  local exitBefore = faultSource.ExitDoorRooms[1]
  local prevLeave = nativeLeaveCalls
  local previousCreated = CurrentRun.RoomCreations.F_Combat01 or 0
  local seen = exitByObject(1)
  M.dispatch("apply_world_exit", {
    doorToken = seen.doorToken, kind = "roomCategory", target = "combat",
    requestId = "fault-" .. injected, includeCatalogs = true,
  })
  if injected == "create" then
    CreateRoom = function(data, args)
      originalCreateRoom(data, args)
      error("injected post-create failure")
    end
  else
    AssignRoomToExitDoor = function(door, room)
      originalAssign(door, room)
      if door == faultDoor and room ~= originalDestination then
        error("injected post-assign failure")
      end
    end
  end
  local enteredOnFailure = AttemptUseDoor(faultDoor)
  CreateRoom, AssignRoomToExitDoor = originalCreateRoom, originalAssign
  assert(enteredOnFailure == originalDestination
      and CurrentRun.CurrentRoom == originalDestination
      and nativeLeaveCalls == prevLeave + 1,
    "failed late commit stranded the player instead of using native original destination")
  assert(faultDoor.Room == originalDestination
      and faultSource.ExitDoorRooms[1] == exitBefore
      and faultSource.OfferedRewards[1].Type == offeredBefore.Type
      and faultSource.OfferedRewards[1].ForceLootName == offeredBefore.ForceLootName,
    "failed late commit corrupted the native selected exit graph")
  assert((CurrentRun.RoomCreations.F_Combat01 or 0) == previousCreated + 1,
    "test incorrectly pretended a partially created native room could be rolled back")
  assert(M.featureErrors.worldActions == "hades2.error.worldActionUnavailable",
    "failed native route did not retain an observable error")
end

print("hades2_exact_exit_world_actions_ok")
"""

with tempfile.TemporaryDirectory(prefix="mgt-hades2-exact-exit-") as directory:
    script = Path(directory) / "exact_exit.lua"
    script.write_text(BASE + MODEL + scenario, encoding="utf-8")
    result = subprocess.run(
        [
            LUA, str(script),
            str(ROOT / "Backend/games/hades2/runtime/hades.lua"),
            str(RESIDENT_DISPATCH_CONTRACT),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "hades2_exact_exit_world_actions_ok" in result.stdout

print("hades2_exact_exit_world_actions_ok")
