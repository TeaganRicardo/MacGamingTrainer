"""Hades II named occurrence one-shot commits at native room admission."""
import subprocess
import tempfile
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
LUA = require_lua52("Hades II named occurrence native room commit")
BASE = (
    ROOT / "tests/fixtures/hades2/gathering_room_model.lua"
).read_text(encoding="utf-8").split("local nativeCreate = CreateRoom")[0]
MODEL = (
    ROOT / "tests/fixtures/hades2/occurrence_routing_model.lua"
).read_text(encoding="utf-8")

scenario = r"""
setRoomSet("F")
setOccurrence("npc:Arachne", "offered-unselected")
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
local chosen, other
for _, door in pairs(MapState.OfferedExitDoors) do
  if door.ReadyToUse and door.Room.Name == "F_Story01" then chosen = door
  elseif door.ReadyToUse then other = door end
end
assert(chosen and other, "native offered exits did not include both destinations")
assert(M.nextOccurrenceTarget == "npc:Arachne"
    and M.nextOccurrenceToken == "offered-unselected"
    and M.lastConsumedNextOccurrenceToken == nil,
  "mere offer consumed the run-scoped one-shot before player selection")
assert(CurrentRun.CurrentRoom.Name == "F_Start", "offering changed active room")

-- The player takes the other legal exit: this must not count as fulfilling
-- the named occurrence even though it was genuinely offered and previewed.
assert(AttemptUseDoor(other).Name == other.Room.Name)
assert(M.nextOccurrenceTarget == "npc:Arachne"
    and M.lastConsumedNextOccurrenceToken == nil,
  "unselected target consumed on a competing exit's StartRoom")

-- Re-enter an eligible owner fixture with a fresh room creation window;
-- same resident/run and pending one-shot survives the former room.
setRoomSet("F")
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
local matching
for _, door in pairs(MapState.OfferedExitDoors) do
  if door.ReadyToUse and door.Room.Name == "F_Story01" then matching = door end
end
assert(matching, "matching room was not native-eligible at the new opportunity")
assert(M.lastConsumedNextOccurrenceToken == nil, "offering was treated as commitment")
assert(AttemptUseDoor(matching).Name == "F_Story01")
assert(M.nextOccurrenceTarget == nil and M.nextOccurrenceToken == nil
    and M.lastConsumedNextOccurrenceToken == "offered-unselected",
  "genuine native StartRoom did not consume the exact matching request")

-- Explicit cancellation preserves native exits; a later entry cannot
-- accidentally consume a cancelled request or synthesize a receipt.
setRoomSet("F")
setOccurrence("shop:Charon", "cancel-before-entry")
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
local shop
for _, door in pairs(MapState.OfferedExitDoors) do
  if door.ReadyToUse and door.Room.Name == "F_Shop01" then shop = door end
end
assert(shop)
M.dispatch("set_next_occurrence", { target = nil, includeCatalogs = false })
local receipt = M.lastConsumedNextOccurrenceToken
assert(AttemptUseDoor(shop).Name == "F_Shop01")
assert(M.nextOccurrenceTarget == nil and M.lastConsumedNextOccurrenceToken == receipt,
  "cancelled next occurrence request was rearmed or consumed on entry")

-- The legacy reward and occurrence requests both use StartRoom. They must
-- compose under one native hook, irrespective of which feature was armed first.
setRoomSet("F")
setOccurrence("npc:Arachne", "occurrence-first")
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
local combat
for _, door in pairs(MapState.OfferedExitDoors) do
  if door.ReadyToUse and door.Room.Name == "F_Combat01" then combat = door end
end
assert(combat)
combat.Room.ChosenRewardType = "RoomMoneyDrop"
M.dispatch("set_next_room_reward", {
  reward = "MaxHealthDrop", token = "reward-after-occurrence", includeCatalogs = false,
})
assert(M.nextRoomRewardRoutedRooms[combat.Room] == "reward-after-occurrence")
assert(AttemptUseDoor(combat).Name == "F_Combat01")
assert(M.lastConsumedNextRoomRewardToken == "reward-after-occurrence"
    and M.nextRoomReward == nil
    and M.nextOccurrenceTarget == "npc:Arachne"
    and StartRoom ~= nativeStartRoom,
  "reward consumption detached a pending named encounter's native StartRoom hook")
setRoomSet("F")
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
local pendingStory
for _, door in pairs(MapState.OfferedExitDoors) do
  if door.ReadyToUse and door.Room.Name == "F_Story01" then pendingStory = door end
end
assert(pendingStory)
AttemptUseDoor(pendingStory)
assert(M.lastConsumedNextOccurrenceToken == "occurrence-first"
    and StartRoom == nativeStartRoom,
  "named room commit failed to release the last shared native hook")

setRoomSet("F")
M.dispatch("set_next_room_reward", {
  reward = "MaxHealthDrop", token = "reward-first", includeCatalogs = false,
})
setOccurrence("npc:Arachne", "occurrence-after-reward")
M.dispatch("set_next_room_reward", { reward = nil, includeCatalogs = false })
assert(M.nextRoomReward == nil and M.nextOccurrenceTarget == "npc:Arachne"
    and StartRoom ~= nativeStartRoom,
  "reward cancellation wrongly detached the remaining occurrence owner")
DoUnlockRoomExits(CurrentRun, CurrentRun.CurrentRoom)
local laterStory
for _, door in pairs(MapState.OfferedExitDoors) do
  if door.ReadyToUse and door.Room.Name == "F_Story01" then laterStory = door end
end
assert(laterStory)
AttemptUseDoor(laterStory)
assert(M.lastConsumedNextOccurrenceToken == "occurrence-after-reward"
    and StartRoom == nativeStartRoom,
  "later occurrence did not use and retire the shared room owner")
print("hades2_occurrence_commit_ok")
"""

with tempfile.TemporaryDirectory(prefix="mgt-occurrence-commit-") as directory:
    script = Path(directory) / "occurrence_commit.lua"
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
    assert "hades2_occurrence_commit_ok" in result.stdout

print("hades2_occurrence_commit_ok")
