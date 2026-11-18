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

local function targetRow(row, kind, target)
  for _, candidate in ipairs(row.targets or {}) do
    if candidate.kind == kind and candidate.id == target then return candidate end
  end
  return nil
end

local function targetExists(row, kind, target)
  local candidate = targetRow(row, kind, target)
  return candidate ~= nil and candidate.enabled ~= false
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
assert(type(first.targetDiagnostics) == "table"
    and first.targetDiagnostics.targetCount > 0,
  "target observation omitted bounded availability diagnostics")
assert(first.targetDiagnostics.reward.storeName == "RunProgress"
    and first.targetDiagnostics.reward.candidateCount > 0,
  "reward diagnostics did not report the native store and candidate count")
assert(first.targetDiagnostics.routes.roomSetName == "F"
    and first.targetDiagnostics.routes.candidateCountByCategory.combat > 0,
  "route diagnostics did not report the native room set and category counts")

-- Sparse status/action replies omit expensive global catalogs. The exact-exit
-- target catalog must remain available for the same physical door/token.
local sparseRNG = nativeRandomCalls
local sparseStatus = M.dispatch("status", { includeCatalogs = false })
local sparseFirst = sparseStatus.worldActions.exits[1]
assert(sparseFirst.doorToken == first.doorToken
    and targetExists(sparseFirst, "reward", "MaxHealthDrop")
    and targetExists(sparseFirst, "roomCategory", "combat"),
  "sparse status erased the cached exact-exit target catalog")
assert(type(sparseFirst.targetDiagnostics) == "table"
    and sparseFirst.targetDiagnostics.targetCount == #sparseFirst.targets,
  "sparse status erased target diagnostics")
assert(nativeRandomCalls == sparseRNG,
  "sparse status re-probed a stable target catalog or consumed RNG")
assert(targetExists(first, "roomCategory", "combat"),
  "selected exit lacks a native-eligible generic room-category target")

-- Native DoUnlockRoomExits removes positional UnavailableDoorIds from
-- the collapsed exit array before choosing or previewing exits. A retained
-- stale map entry must not become editable.
local originalUnavailableDoorIds = CurrentRun.CurrentRoom.UnavailableDoorIds
CurrentRun.CurrentRoom.UnavailableDoorIds = { 2 }
local unavailableWorld = world()
assert(#unavailableWorld.exits == 1 and unavailableWorld.exits[1].objectId == 1,
  "native positional unavailable door slot was exposed as an editable exit")
CurrentRun.CurrentRoom.UnavailableDoorIds = originalUnavailableDoorIds
first, second = exitByObject(1), exitByObject(2)

-- Native IsRoomEligible / IsRoomForced pass a mutable args table through
-- IsGameStateEligible. Catalog observation must isolate those diagnostic
-- writes just as it isolates SessionMapState and room descriptor Tags.
local nativeProbeEligible = IsRoomEligible
local nativeProbeForced = IsRoomForced
IsRoomEligible = function(run, source, room, args)
  args.FirstFailedRequirement = "fixture eligibility probe"
  return nativeProbeEligible(run, source, room, args)
end
IsRoomForced = function(run, source, room, args, otherDoors)
  args.ForceProbeMutation = true
  return nativeProbeForced(run, source, room, args, otherDoors)
end
local readOnlyArgs = door1.ChooseRoomArgs
local readOnlyExit = exitByObject(1)
assert(readOnlyArgs.FirstFailedRequirement == nil
    and readOnlyArgs.ForceProbeMutation == nil,
  "native room eligibility observation mutated the actual door ChooseRoomArgs")
IsRoomEligible = nativeProbeEligible
IsRoomForced = nativeProbeForced
first, second = exitByObject(1), exitByObject(2)

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
local randomReward = targetRow(exitByObject(1), "reward", "MaxHealthDrop")
assert(randomReward ~= nil and randomReward.enabled == false
    and randomReward.reason == "reward_eligibility_requires_rng",
  "random-dependent native reward must remain visible but disabled")
local randomRewardApply = pcall(function()
  M.dispatch("apply_world_exit", {
    doorToken = exitByObject(1).doorToken,
    kind = "reward", target = "MaxHealthDrop",
    requestId = "blocked-random-reward", includeCatalogs = true,
  })
end)
assert(not randomRewardApply,
  "a disabled reward must be rejected at the resident mutation seam")
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
local eligibilityBlocked = exitByObject(1)
assert(not targetExists(eligibilityBlocked, "roomCategory", "combat"))
assert(targetRow(eligibilityBlocked, "roomCategory", "combat") ~= nil
    and targetRow(eligibilityBlocked, "roomCategory", "combat").enabled == false,
  "random-dependent room eligibility must retain a disabled category")
assert(eligibilityBlocked.targetDiagnostics.routes.randomEligibilityRoom ~= nil,
  "random-dependent room eligibility was not diagnosed")
assert(nativeRandomCalls == beforeEligibilityProbe,
  "IsRoomEligible inspection consumed native RNG")
probeEligibilityUsesRandom = false
assert(targetExists(exitByObject(1), "roomCategory", "combat"))
RoomData.F_Forced01.RandomForced = true
probeForceUsesRandom = true
local beforeForceProbe = nativeRandomCalls
local forceBlocked = exitByObject(1)
assert(targetExists(forceBlocked, "roomCategory", "combat"),
  "probabilistic native force must not suppress otherwise legal room choices")
assert(forceBlocked.targetDiagnostics.routes.randomForceRoom == "F_Forced01",
  "random-dependent native force did not report the affected room")
assert(nativeRandomCalls == beforeForceProbe,
  "IsRoomForced inspection consumed native RNG")
probeForceUsesRandom = false
RoomData.F_Forced01.RandomForced = nil
assert(targetExists(exitByObject(1), "roomCategory", "combat"))

-- A deterministic native forced room is a hard progression constraint.
-- Show alternatives disabled rather than removing them from the picker.
nativeRoomForced.F_Forced01 = true
local hardForced = exitByObject(1)
local disabledCombat = targetRow(hardForced, "roomCategory", "combat")
assert(disabledCombat ~= nil and disabledCombat.enabled == false
    and disabledCombat.reason == "native_forced_room_present",
  "hard forced progression must keep alternatives visible and blocked")
local forcedRouteApply = pcall(function()
  M.dispatch("apply_world_exit", {
    doorToken = hardForced.doorToken,
    kind = "roomCategory", target = "combat",
    requestId = "blocked-forced-route", includeCatalogs = true,
  })
end)
assert(not forcedRouteApply,
  "a disabled native forced route must be rejected by the resident")
nativeRoomForced.F_Forced01 = nil

-- Native DoUnlockRoomExits evaluates doors in order. The current door
-- and later doors have no assigned Room when IsRoomForced runs for this door.
local originalForcedDoor1Room, originalForcedDoor2Room = door1.Room, door2.Room
local originalOnceFlag = RoomData.F_Story01.AlwaysForceOncePerRoom
RoomData.F_Story01.AlwaysForceOncePerRoom = true
door2.Room = DeepCopyTable(RoomData.F_Story01)
local forcedForFirst = exitByObject(1)
local forcedForFirstTarget = targetRow(forcedForFirst, "roomCategory", "combat")
assert(forcedForFirstTarget and forcedForFirstTarget.enabled == false
    and forcedForFirstTarget.reason == "native_forced_room_present",
  "a later door's already-generated room incorrectly suppressed native force on an earlier door")

door1.Room = DeepCopyTable(RoomData.F_Story01)
local laterDoor = exitByObject(2)
local laterStory = targetRow(laterDoor, "roomCategory", "story")
assert(laterStory and laterStory.enabled == true,
  "an earlier door's forced-once room incorrectly blocked the later door's other-room choices")

door1.Room = originalForcedDoor1Room
door2.Room = originalForcedDoor2Room
RoomData.F_Story01.AlwaysForceOncePerRoom = originalOnceFlag
-- Restoring the physical room descriptors intentionally advances the
-- ABA-safe door epochs. Refresh both tokens before later apply/cancel checks.
first, second = exitByObject(1), exitByObject(2)

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
local sparseAfterReroll = M.dispatch("status", { includeCatalogs = false }).worldActions.exits[1]
assert(sparseAfterReroll.doorToken ~= beforeReroll.doorToken
    and targetExists(sparseAfterReroll, "roomCategory", "combat"),
  "sparse status reused a stale target catalog after native door replacement")
assert(sparseAfterReroll.targetDiagnostics.roomName == "F_Combat01",
  "replacement door diagnostics still describe the previous native room")
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

-- The selected exit may commit successfully while a sibling preview is
-- broken. That cleanup failure must not abort LeaveRoom after door costs.
setRoomSet("F")
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
local cleanupFirst, cleanupSecond = MapState.OfferedExitDoors[1], MapState.OfferedExitDoors[2]
M.dispatch("apply_world_exit", {
  doorToken = exitByObject(1).doorToken, kind = "roomCategory", target = "combat",
  requestId = "cleanup-first", includeCatalogs = true,
})
M.dispatch("apply_world_exit", {
  doorToken = exitByObject(2).doorToken, kind = "roomCategory", target = "combat",
  requestId = "cleanup-second", includeCatalogs = true,
})
local nativePreview = CreateDoorRewardPreview
CreateDoorRewardPreview = function(door, ...)
  if door == cleanupSecond then error("injected sibling native preview failure") end
  return nativePreview(door, ...)
end
local previousLeaves = nativeLeaveCalls
local safelyEntered = AttemptUseDoor(cleanupFirst)
CreateDoorRewardPreview = nativePreview
assert(type(safelyEntered) == "table" and safelyEntered.Name == "F_Combat01"
    and nativeLeaveCalls == previousLeaves + 1
    and M.featureErrors.worldActions == "hades2.error.worldActionUnavailable",
  "sibling preview cleanup failure aborted accepted native door use")
assert(M.dispatch("status", { includeCatalogs = false }).worldActions.occurrence == nil)

-- Real-shaped god loot sources are stable targets independent of the
-- temporarily depleted RunProgress deck. Locked gods stay visible.
LootData.ApolloUpgrade = { Name = "ApolloUpgrade", GodLoot = true,
  DoorIcon = "BoonDropApolloPreview" }
LootData.ZeusUpgrade = { Name = "ZeusUpgrade", GodLoot = true,
  DoorIcon = "BoonDropZeusPreview" }
local currentRunStore = CurrentRun.RewardStores.RunProgress
currentRunStore[#currentRunStore + 1] = { Name = "Boon", AllowDuplicates = true }
RewardStoreData.RunProgress = {
  { Name = "Boon", AllowDuplicates = true },
  { Name = "HermesUpgrade", GameStateRequirements = {} },
}
RewardStoreData.MetaProgress = { { Name = "MetaCurrencyDrop", AllowDuplicates = true } }
CurrentRun.RewardStores.MetaProgress = { { Name = "MetaCurrencyDrop", AllowDuplicates = true } }
local lastExcludedGods = {}
GetEligibleLootNames = function(excluded)
  lastExcludedGods = excluded or {}
  local names = { "ApolloUpgrade", "ZeusUpgrade" }
  for _, name in ipairs(excluded or {}) do
    for index = #names, 1, -1 do
      if names[index] == name then table.remove(names, index) end
    end
  end
  return names
end
ReachedMaxGods = function(excluded)
  lastExcludedGods = excluded or {}
  return false
end
setRoomSet("F")
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
local godExit = exitByObject(1)
assert(targetExists(godExit, "reward", "ApolloUpgrade")
    and targetExists(godExit, "reward", "ZeusUpgrade"),
  "native Boon template did not enumerate distinct Olympian targets")
assert(not targetRow(godExit, "reward", "MetaCurrencyDrop"),
  "MetaProgress reward leaked into a RunProgress exit")
local offDeckHermes = targetRow(godExit, "reward", "HermesUpgrade")
assert(offDeckHermes and offDeckHermes.enabled == false
    and offDeckHermes.reason == "reward_not_in_current_store",
  "reference-store-only reward must stay visible but disabled while native deck has choices")
local originalGodDoor = MapState.OfferedExitDoors[1]
local originalGodRoom = originalGodDoor.Room
local appliedGod = M.dispatch("apply_world_exit", {
  doorToken = godExit.doorToken, kind = "reward",
  target = "ApolloUpgrade", requestId = "specific-god",
  includeCatalogs = true,
})
assert(originalGodDoor.Room == originalGodRoom
    and originalGodRoom.ChosenRewardType == "Boon"
    and originalGodRoom.ForceLootName == "ApolloUpgrade",
  "exact exit reward did not force the selected god natively")
local godLease = appliedGod.worldActions.exits[1].activeLease
assert(godLease ~= nil)
M.dispatch("cancel_world_exit", {
  doorToken = godExit.doorToken, leaseToken = godLease.leaseToken,
  requestId = "cancel-specific-god", includeCatalogs = true,
})
assert(originalGodDoor.Room == originalGodRoom
    and originalGodRoom.ForceLootName ~= "ApolloUpgrade",
  "cancelling a god reward did not restore the actual native door")
CurrentRun.CurrentRoom.OfferedRewards[2] = {
  Type = "Boon", ForceLootName = "ApolloUpgrade",
}
local duplicateGod = targetRow(exitByObject(1), "reward", "ApolloUpgrade")
assert(duplicateGod and duplicateGod.enabled == false
    and duplicateGod.reason == "reward_not_available",
  "a sibling god reward must remain visible but unavailable")
local excludedApollo = false
for _, name in ipairs(lastExcludedGods) do
  if name == "ApolloUpgrade" then excludedApollo = true end
end
assert(excludedApollo,
  "native GetEligibleLootNames/ReachedMaxGods did not receive sibling-door exclusions")
local duplicateGodApply = pcall(function()
  M.dispatch("apply_world_exit", {
    doorToken = exitByObject(1).doorToken,
    kind = "reward", target = "ApolloUpgrade",
    requestId = "blocked-duplicate-god", includeCatalogs = true,
  })
end)
assert(not duplicateGodApply, "duplicate god target was accepted despite being greyed")
CurrentRun.CurrentRoom.OfferedRewards[2] = nil
GetEligibleLootNames = function() return { "ApolloUpgrade" } end
local unavailableGod = targetRow(exitByObject(1), "reward", "ZeusUpgrade")
assert(unavailableGod and unavailableGod.enabled == false
    and unavailableGod.reason == "god_not_eligible",
  "unavailable god must remain in the catalog with a native reason")
CurrentRun.LootTypeHistory = { ApolloUpgrade = true }
GetEligibleLootNames = function(excluded) return { "ApolloUpgrade" } end
ReachedMaxGods = function(excluded) return true end
local maxGod = targetRow(exitByObject(1), "reward", "ZeusUpgrade")
assert(maxGod and maxGod.enabled == false and maxGod.reason == "god_limit",
  "the native max-gods-per-run limit was not exposed as a disabled target")
CurrentRun.LootTypeHistory = {}
ReachedMaxGods = function(excluded) return false end

-- When the selected native deck has no eligible entries, ChooseRoomReward
-- refills from GetRewardStoreData for that same store. The catalog may enable
-- those refill candidates, but must never borrow a different store.
CurrentRun.RewardStores.RunProgress = {}
local refilled = exitByObject(1)
assert(targetExists(refilled, "reward", "HermesUpgrade"),
  "empty native RunProgress deck did not expose its own refill candidates")
local metaRoom = originalGodDoor.Room
local priorStoreName = metaRoom.RewardStoreName
metaRoom.RewardStoreName = "MetaProgress"
local metaOnly = exitByObject(1)
assert(targetExists(metaOnly, "reward", "MetaCurrencyDrop"),
  "MetaProgress reward was unavailable on an exit using the native MetaProgress store")
metaRoom.RewardStoreName = priorStoreName
CurrentRun.RewardStores.RunProgress = currentRunStore


-- P-region named minibosses and story rooms are presented even while
-- hard biome/run eligibility gates make them unavailable.
RoomData.P_MiniBoss01 = {
  Name = "P_MiniBoss01", RoomSetName = "P",
  ForceAtBiomeDepthMin = 4, ForceAtBiomeDepthMax = 7,
  MaxCreationsThisRun = 1,
}
RoomData.P_MiniBoss02 = {
  Name = "P_MiniBoss02", RoomSetName = "P",
  ForceAtBiomeDepthMin = 4, ForceAtBiomeDepthMax = 7,
  MaxCreationsThisRun = 1,
}
table.insert(RoomSets.P, "P_MiniBoss01")
table.insert(RoomSets.P, "P_MiniBoss02")
local priorEligible = IsRoomEligible
IsRoomEligible = function(run, source, room, args)
  if room.ForceAtBiomeDepthMin ~= nil
      and run.BiomeDepthCache < room.ForceAtBiomeDepthMin then return false end
  return priorEligible(run, source, room, args)
end
setRoomSet("P")
CurrentRun.BiomeDepthCache = 3
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
local early = exitByObject(1)
for _, name in ipairs({ "P_MiniBoss01", "P_MiniBoss02" }) do
  local choice = targetRow(early, "roomCategory", name)
  assert(choice and choice.enabled == false
      and choice.reason == "biome_depth_too_low",
    "early P miniboss must be listed as disabled")
end
CurrentRun.BiomeDepthCache = 5
local mature = exitByObject(1)
assert(targetExists(mature, "roomCategory", "P_MiniBoss01")
    and targetExists(mature, "roomCategory", "P_MiniBoss02"),
  "P minibosses were not enabled at native depth five")
CurrentRun.RoomCreations.P_MiniBoss01 = 1
local spent = targetRow(exitByObject(1), "roomCategory", "P_MiniBoss01")
assert(spent and spent.enabled == false
    and spent.reason == "max_creations_this_run",
  "used-once P miniboss must remain visible and disabled")
assert(targetExists(exitByObject(1), "roomCategory", "P_MiniBoss02"),
  "spent miniboss incorrectly blocked a different miniboss option")
CurrentRun.RoomCreations.P_Story01 = 1
local spentStory = targetRow(exitByObject(1), "roomCategory", "story")
assert(spentStory and spentStory.enabled == false,
  "one-per-run story destination must remain visible and disabled")

RoomData.P_MiniBoss02.MaxCreationsPerRoom = 1
CurrentRun.CurrentRoom.RoomCreations.P_MiniBoss02 = 1
local perRoomLimit = targetRow(exitByObject(1), "roomCategory", "P_MiniBoss02")
assert(perRoomLimit and perRoomLimit.enabled == false
    and perRoomLimit.reason == "room_max_creations_per_room",
  "per-room creation limit did not explain the disabled miniboss")
RoomData.P_MiniBoss02.MaxCreationsPerRoom = nil
CurrentRun.CurrentRoom.RoomCreations.P_MiniBoss02 = nil

RoomData.P_MiniBoss02.RequiresLinked = true
local linkedOnly = targetRow(exitByObject(1), "roomCategory", "P_MiniBoss02")
assert(linkedOnly and linkedOnly.enabled == false
    and linkedOnly.reason == "room_linked_route_required",
  "linked-room requirement did not explain the disabled target")
RoomData.P_MiniBoss02.RequiresLinked = nil

RoomData.P_MiniBoss02.DebugOnly = true
local debugOnly = targetRow(exitByObject(1), "roomCategory", "P_MiniBoss02")
assert(debugOnly and debugOnly.enabled == false
    and debugOnly.reason == "room_debug_only",
  "developer-only room was not retained with a disabled reason")
RoomData.P_MiniBoss02.DebugOnly = nil

local originalChooseArgs = door1.ChooseRoomArgs
RoomData.P_MiniBoss02.Tags = { "Outdoor" }
door1.ChooseRoomArgs = { RequireTags = { "Indoor" } }
local requiredTags = targetRow(exitByObject(1), "roomCategory", "P_MiniBoss02")
assert(requiredTags and requiredTags.enabled == false
    and requiredTags.reason == "room_required_tags_missing",
  "required native room tags did not explain the disabled target")
door1.ChooseRoomArgs = { OutdoorRequiresIndoorTag = true }
CurrentRun.CurrentRoom.Tags = { "Outdoor" }
local indoorOnly = targetRow(exitByObject(1), "roomCategory", "P_MiniBoss02")
assert(indoorOnly and indoorOnly.enabled == false
    and indoorOnly.reason == "room_requires_indoor",
  "outdoor-to-indoor route restriction did not explain the disabled target")
door1.ChooseRoomArgs = originalChooseArgs
CurrentRun.CurrentRoom.Tags = nil
RoomData.P_MiniBoss02.Tags = nil

RoomData.P_Story01.MaxAppearancesThisRun = 1
CurrentRun.RoomCountCache.P_Story01 = 1
local seenStory = targetRow(exitByObject(1), "roomCategory", "story")
assert(seenStory and seenStory.enabled == false
    and seenStory.reason == "room_max_appearances_this_run",
  "run-wide room appearance limit did not explain the disabled story room")
RoomData.P_Story01.MaxAppearancesThisRun = nil
CurrentRun.RoomCountCache.P_Story01 = nil

IsRoomEligible = priorEligible

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
