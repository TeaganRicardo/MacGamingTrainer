"""#832: Modify Exit allows every target the code can build and warns instead.

The fixture is modeled on the owner's 2026-11-23 Summit run: Q combat rooms
inherit NoReward, so every reward was disabled (`room_no_reward`), and a
deterministic forced room disabled every route (`native_forced_room_present`).
"""
import subprocess
import tempfile
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
LUA = require_lua52("Hades II Modify Exit allow-and-warn")
BASE = (
    ROOT / "tests/fixtures/hades2/gathering_room_model.lua"
).read_text(encoding="utf-8").split("local nativeCreate = CreateRoom")[0]
MODEL = (
    ROOT / "tests/fixtures/hades2/occurrence_routing_model.lua"
).read_text(encoding="utf-8")

scenario = r"""
-- Summit-shaped region: a DebugOnly template, NoReward combat rooms, one
-- deterministic forced combat room and natively ineligible minibosses.
RoomData.Q_CombatData = { Name = "Q_CombatData", RoomSetName = "Q", DebugOnly = true, NoReward = true }
RoomData.Q_Combat03 = { Name = "Q_Combat03", RoomSetName = "Q", NoReward = true }
RoomData.Q_Combat11 = { Name = "Q_Combat11", RoomSetName = "Q", NoReward = true }
RoomData.Q_Combat12 = { Name = "Q_Combat12", RoomSetName = "Q", NoReward = true }
RoomData.Q_MiniBoss02 = { Name = "Q_MiniBoss02", RoomSetName = "Q" }
RoomData.Q_MiniBoss05 = { Name = "Q_MiniBoss05", RoomSetName = "Q" }
RoomSets.Q = { "Q_CombatData", "Q_Combat03", "Q_Combat11", "Q_Combat12", "Q_MiniBoss02", "Q_MiniBoss05" }
roomEligible.Q_MiniBoss02 = false
roomEligible.Q_MiniBoss05 = false
nativeRoomForced.Q_Combat03 = true

LootData.ZeusUpgrade = { Name = "ZeusUpgrade", GodLoot = true }
LootData.ApolloUpgrade = { Name = "ApolloUpgrade", GodLoot = true }
GetEligibleLootNames = function() return { "ZeusUpgrade", "ApolloUpgrade" } end
ReachedMaxGods = function() return false end
local runProgress = CurrentRun.RewardStores.RunProgress
runProgress[#runProgress + 1] = { Name = "Boon", AllowDuplicates = true }
RewardStoreData.RunProgress = runProgress
RewardStoreData.MetaProgress = { { Name = "MetaCardPointsCommonDrop", AllowDuplicates = true } }

-- Native ChooseRoomReward returns nothing for a NoReward room.
local fixtureChooseRoomReward = ChooseRoomReward
ChooseRoomReward = function(run, room, storeName, previously, args)
  if room.NoReward then return nil end
  return fixtureChooseRoomReward(run, room, storeName, previously, args)
end

setRoomSet("Q")
MapState.OfferedExitDoors = {
  [1] = { ObjectId = 1, ChooseRoomArgs = {}, ForceRoomName = "Q_Combat11" },
}
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
local door = MapState.OfferedExitDoors[1]
door.ForceRoomName = nil -- only used to build the owner's room; not a fixed route
assert(door.Room.Name == "Q_Combat11" and door.Room.NoReward == true
    and door.Room.ChosenRewardType == nil,
  "fixture must model the owner's no-reward Summit combat exit")

local function exitRow()
  local status = M.dispatch("status", { includeCatalogs = true })
  local row = status.worldActions.exits[1]
  assert(row ~= nil and row.objectId == 1, "Summit exit was not observed")
  return row
end

local function target(row, kind, id)
  for _, candidate in ipairs(row.targets or {}) do
    if candidate.kind == kind and candidate.id == id then return candidate end
  end
  return nil
end

-- 1. Catalog: the game's own rules warn, they never disable.
local row = exitRow()
for _, id in ipairs({ "ZeusUpgrade", "ApolloUpgrade", "MaxHealthDrop", "RoomMoneyDrop" }) do
  local reward = target(row, "reward", id)
  assert(reward ~= nil and reward.enabled == true,
    "reward " .. id .. " was refused on a NoReward room: "
      .. tostring(reward and reward.reason))
end
assert(row.roomKind == "combat" and row.reward == "",
  "exit row must report the door's current room type and (absent) reward")
assert(row.rewardWarning == "room_no_reward",
  "in-place reward edits on a NoReward room must carry a room-level warning")
local meta = target(row, "reward", "MetaCardPointsCommonDrop")
assert(meta ~= nil and meta.enabled == true and meta.warning == "reward_not_in_current_store",
  "another reward pool must be offered with a warning")
local combat = target(row, "roomCategory", "combat")
assert(combat ~= nil and combat.enabled == true and combat.acceptsReward == true
    and combat.warning == nil,
  "the forced room's own category must stay available without a warning")
local miniboss = target(row, "roomCategory", "miniboss")
assert(miniboss ~= nil and miniboss.enabled == true and miniboss.acceptsReward == true
    and miniboss.warning == "native_ineligible",
  "a natively ineligible miniboss must warn, not disable: "
    .. tostring(miniboss and (miniboss.reason or miniboss.warning)))
local named = target(row, "roomCategory", "Q_MiniBoss02")
assert(named ~= nil and named.enabled == true and named.acceptsReward == true,
  "a named miniboss must stay selectable")
assert(target(row, "roomCategory", "Q_CombatData") == nil,
  "a DebugOnly template is not a buildable room")
assert(row.targetDiagnostics.reason == "available",
  "an exit with buildable targets reported no_legal_target")

-- 2. Apply Combat > Zeus on a combat door edits the reward in place.
local originalRoom = door.Room
local applied = M.dispatch("apply_world_exit", {
  doorToken = row.doorToken, room = "combat", reward = "ZeusUpgrade",
  requestId = "combat-zeus", includeCatalogs = true,
})
local lease = applied.worldActions.exits[1].activeLease
assert(lease ~= nil and lease.room == "combat" and lease.reward == "ZeusUpgrade"
    and type(lease.leaseToken) == "string",
  "Apply must report the game's lease with both room type and reward")
assert(door.Room == originalRoom and door.Room.ChosenRewardType == "Boon"
    and door.Room.ForceLootName == "ZeusUpgrade",
  "Combat > Zeus did not force Zeus on the existing combat room")
local observed = applied.worldActions.exits[1]
assert(observed.roomKind == "combat" and observed.reward == "ZeusUpgrade",
  "the exit row must report what the door now holds")
assert(door.PreviewReward == "ZeusUpgrade", "door preview did not show the new reward")

M.dispatch("cancel_world_exit", {
  doorToken = observed.doorToken, leaseToken = lease.leaseToken,
  requestId = "cancel-combat-zeus", includeCatalogs = true,
})
assert(door.Room == originalRoom and door.Room.ChosenRewardType == nil
    and door.Room.ForceLootName == nil,
  "Cancel did not restore the original no-reward room")

-- 3. Apply Miniboss > Max Health builds a natively ineligible miniboss with
-- that exact reward when the player walks through the door.
row = exitRow()
local routed = M.dispatch("apply_world_exit", {
  doorToken = row.doorToken, room = "miniboss", reward = "MaxHealthDrop",
  requestId = "miniboss-health", includeCatalogs = true,
})
local routeLease = routed.worldActions.exits[1].activeLease
assert(routeLease ~= nil and routeLease.room == "miniboss"
    and routeLease.reward == "MaxHealthDrop",
  "route lease must carry the chosen reward")
assert(door.Room == originalRoom, "a room-type change must not rebuild the room before departure")
assert(door.PreviewReward == "MaxHealthDrop",
  "a room-type reservation with a reward must preview that reward")
local entered = AttemptUseDoor(door)
assert(type(entered) == "table" and (entered.Name == "Q_MiniBoss02" or entered.Name == "Q_MiniBoss05"),
  "the door did not lead to a miniboss room")
assert(entered.ChosenRewardType == "MaxHealthDrop",
  "the built miniboss room lost the chosen reward")

-- 4. Story, Shop and Fountain are leaves without a reward submenu.
RoomData.F_Reprieve01 = { Name = "F_Reprieve01", RoomSetName = "F" }
RoomSets.F[#RoomSets.F + 1] = "F_Reprieve01"
setRoomSet("F")
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
row = exitRow()
for _, id in ipairs({ "story", "shop", "reprieve" }) do
  local leaf = target(row, "roomCategory", id)
  assert(leaf ~= nil and leaf.enabled == true and leaf.acceptsReward == false,
    id .. " must be a selectable leaf without rewards")
end
local storyReply = M.dispatch("apply_world_exit", {
  doorToken = row.doorToken, room = "story",
  requestId = "story-leaf", includeCatalogs = true,
})
assert(storyReply.worldActions.exits[1].activeLease.room == "story"
    and storyReply.worldActions.exits[1].activeLease.reward == nil)

-- 5. A door whose room type the region does not build (an intro, a region
-- transition) keeps an in-place reward edit under "current".
RoomData.Q_Intro = { Name = "Q_Intro", RoomSetName = "Q" }
setRoomSet("N")
CurrentRun.CurrentRoom.NextRoomSet = { "Q" }
MapState.OfferedExitDoors = { [1] = { ObjectId = 1, ChooseRoomArgs = {}, ForceRoomName = "Q_Intro" } }
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
MapState.OfferedExitDoors[1].ForceRoomName = nil
row = exitRow()
local current = target(row, "roomCategory", "current")
assert(row.roomKind == "" and current ~= nil and current.enabled == true
    and current.acceptsReward == true,
  "an intro door lost its in-place reward edit")
local transition = target(row, "roomCategory", "combat")
assert(transition ~= nil and transition.enabled == true
    and transition.warning == "source_next_room_set"
    and row.targetDiagnostics.routes.roomSetName == "Q",
  "a region transition must offer the next region's room types with a warning")
local introReply = M.dispatch("apply_world_exit", {
  doorToken = row.doorToken, room = "current", reward = "ZeusUpgrade",
  requestId = "intro-zeus", includeCatalogs = true,
})
assert(introReply.worldActions.exits[1].reward == "ZeusUpgrade"
    and MapState.OfferedExitDoors[1].Room.Name == "Q_Intro",
  "an in-place edit on an intro door changed its room")

-- A door the game swapped to an anomaly room keeps its source region's types.
RoomData.B_Combat01 = { Name = "B_Combat01", RoomSetName = "Anomaly" }
RoomSets.Anomaly = { "B_Combat01" }
setRoomSet("F")
CurrentRun.CurrentRoom.DoAnomalies = true
MapState.OfferedExitDoors = { [1] = { ObjectId = 1, ChooseRoomArgs = {}, ForceRoomName = "B_Combat01" } }
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
MapState.OfferedExitDoors[1].ForceRoomName = nil
row = exitRow()
assert(row.targetDiagnostics.routes.roomSetName == "F"
    and target(row, "roomCategory", "story") ~= nil
    and target(row, "roomCategory", "shop") ~= nil,
  "an anomaly-swapped door lost its region's room types")

-- 6. Only what cannot be built is refused: a native probe that throws.
setRoomSet("F")
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
local nativeRewardEligible = IsRoomRewardEligible
IsRoomRewardEligible = function(run, room, reward, previously, args)
  if reward.Name == "MaxManaDrop" then error("native reward probe fault") end
  return nativeRewardEligible(run, room, reward, previously, args)
end
row = exitRow()
local faulted = target(row, "reward", "MaxManaDrop")
assert(faulted ~= nil and faulted.enabled == false
    and faulted.reason == "reward_eligibility_probe_error",
  "a reward whose native probe threw must be refused")
assert(target(row, "reward", "MaxHealthDrop").enabled == true,
  "one reward probe fault refused an unrelated reward")
assert(not pcall(function()
  M.dispatch("apply_world_exit", {
    doorToken = row.doorToken, room = "combat", reward = "MaxManaDrop",
    requestId = "faulted-reward", includeCatalogs = true,
  })
end), "a refused reward was applied")
IsRoomRewardEligible = nativeRewardEligible

local nativeEligible = IsRoomEligible
IsRoomEligible = function() error("native room probe fault") end
row = exitRow()
local broken = target(row, "roomCategory", "combat")
assert(broken ~= nil and broken.enabled == false
    and broken.reason == "room_eligibility_probe_error",
  "a room type whose every probe threw must be refused")
local stillCurrent = target(row, "roomCategory", "current")
assert(stillCurrent ~= nil and stillCurrent.enabled == true and stillCurrent.acceptsReward == true,
  "a refused own room type removed the in-place reward edit")
assert(not pcall(function()
  M.dispatch("apply_world_exit", {
    doorToken = row.doorToken, room = "combat",
    requestId = "faulted-route", includeCatalogs = true,
  })
end), "a refused room type was applied")
IsRoomEligible = nativeEligible

assert(not pcall(function()
  M.dispatch("apply_world_exit", {
    doorToken = "exit:stale", room = "combat", reward = "MaxHealthDrop",
    requestId = "missing-door", includeCatalogs = true,
  })
end), "a missing door was applied")

-- 7. Unknown outcome: a native failure after the edit began is never
-- replayed, and the same request cannot run again.
row = exitRow()
local nativeAssign = AssignRoomToExitDoor
local assignCalls = 0
AssignRoomToExitDoor = function(...)
  assignCalls = assignCalls + 1
  error("native assign lost its reply")
end
local firstOk, firstError = pcall(function()
  M.dispatch("apply_world_exit", {
    doorToken = row.doorToken, room = "current", reward = "MaxHealthDrop",
    requestId = "unknown-outcome", includeCatalogs = true,
  })
end)
assert(not firstOk and tostring(firstError):find("MGT_OUTCOME_UNKNOWN", 1, true),
  "a failed in-flight edit was not reported as an unknown outcome")
local againOk, againError = pcall(function()
  M.dispatch("apply_world_exit", {
    doorToken = row.doorToken, room = "current", reward = "MaxHealthDrop",
    requestId = "unknown-outcome", includeCatalogs = true,
  })
end)
assert(not againOk and tostring(againError):find("do not retry", 1, true)
    and assignCalls == 1,
  "an unknown outcome was replayed")
AssignRoomToExitDoor = nativeAssign

print("hades2_modify_exit_allow_and_warn_ok")
"""

with tempfile.TemporaryDirectory(prefix="mgt-hades2-modify-exit-") as directory:
    script = Path(directory) / "modify_exit.lua"
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
    assert "hades2_modify_exit_allow_and_warn_ok" in result.stdout

print("hades2_modify_exit_allow_and_warn_ok")
