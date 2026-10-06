import subprocess
import tempfile
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
LUA = require_lua52("Force Enable Rerolls reward-door behavior")

SOURCE = (ROOT / "tests/test_hades2_force_enable_rerolls.py").read_text()
START = SOURCE.index("HARNESS = r'''") + len("HARNESS = r'''")
END = SOURCE.index("\n'''\n\nwith tempfile", START)
BASE_HARNESS = SOURCE[START:END]

DOOR_STUBS = r'''
-- Current 1.143476 reward-door reroll seams. Packaged trials can omit the
-- DoorRerollMetaUpgrade-derived AllowDoorReroll trait value entirely.
MapState.OfferedExitDoors = {}
MapState.ShipWheels = {}
RoomData = { TestCurrent = {} }
CurrentRun.CurrentRoom.Name = 'TestCurrent'
CurrentRun.CurrentRoom.ExitDoorRooms = {}
CurrentRun.CurrentRoom.OfferedRewards = {}

local nativeDoorReroll = false
local nativeDoorTrait = { Name = 'DoorRerollMetaUpgrade', AllowDoorReroll = true }
HasHeroTraitValue = function(propertyName)
  if propertyName == 'AllowDoorReroll' and nativeDoorReroll then
    return nativeDoorTrait
  end
  return nil
end

CheckSpecialDoorRequirement = function(door)
  return door.SpecialRequirement
end
CheckRoomExitsReady = function() return true end

local refreshes = {}
RefreshUseButton = function(id, target)
  refreshes[id] = (refreshes[id] or 0) + 1
end
AddControlBlock = function() end

AssignRoomToExitDoor = function(door, room)
  door.Room = room
  MapState.OfferedExitDoors[door.ObjectId] = door
  CurrentRun.CurrentRoom.ExitDoorRooms[door.ObjectId] = room.Name
  if room.ChosenRewardType ~= nil then
    CurrentRun.CurrentRoom.OfferedRewards[door.ObjectId] = {
      Type = room.ChosenRewardType,
      ForceLootName = room.ForceLootName,
    }
  end
  if room.ForceDoorAllowReroll then door.AllowReroll = true end
  if RoomData[CurrentRun.CurrentRoom.Name].ForceCurrentRoomDoorsAllowReroll then
    door.AllowReroll = true
  end
  if door.AllowReroll and not room.NoReroll
      and CheckSpecialDoorRequirement(door) == nil
      and room.ChosenRewardType ~= 'Shop'
      and HasHeroTraitValue('AllowDoorReroll') then
    door.CanBeRerolled = true
  end
  RefreshUseButton(door.ObjectId, door)
end

local doorRerolls = 0
local fieldsRerolls = 0
local wheelRerolls = 0
AttemptRerollDoor = function(run, door)
  doorRerolls = doorRerolls + 1
  door.Room.ChosenRewardType = 'PoseidonUpgrade'
end
AttemptRerollFieldsDoor = function(run, door)
  fieldsRerolls = fieldsRerolls + 1
  door.Room.CageRewards[1] = { RewardType = 'PoseidonUpgrade' }
end
AttemptRerollShipWheel = function(run, wheel)
  wheelRerolls = wheelRerolls + 1
  wheel.ChosenRewardType = 'PoseidonUpgrade'
end
AttemptReroll = function(run, target)
  if run.NumRerolls <= 0 or target == nil or not target.CanBeRerolled
      or target.RerollFunctionName == nil then
    return
  end
  run.NumRerolls = run.NumRerolls - 1
  if target.Room and target.Room.CageRewards ~= nil then
    target.RerollIndex = 1
    target.RerollFunctionName = 'AttemptRerollFieldsDoor'
  end
  CallFunctionName(target.RerollFunctionName, run, target)
end
'''

BASE_HARNESS = BASE_HARNESS.replace(
    "dofile(assert(arg[1])); dofile(assert(arg[2]))",
    DOOR_STUBS + "\ndofile(assert(arg[1])); dofile(assert(arg[2]))",
)

DOOR_CASES = r'''
-- Start from ordinary native rules with no DoorRerollMetaUpgrade, matching a
-- packaged trial that globally removes reroll Arcana.
M.dispatch('set_feature', { feature = 'forceEnableRerolls', value = false, includeCatalogs = false })
nativeDoorReroll = false
CurrentRun.NumRerolls = 6
MapState.OfferedExitDoors = {}
MapState.ShipWheels = {}

local rewardRoom = {
  Name = 'RewardRoom',
  ChosenRewardType = 'ZeusUpgrade',
}
local rewardDoor = {
  ObjectId = 801,
  AllowReroll = true,
  ReadyToUse = true,
  RerollFunctionName = 'AttemptRerollDoor',
}
AssignRoomToExitDoor(rewardDoor, rewardRoom)
assert(not rewardDoor.CanBeRerolled,
  'trial-disabled reward door unexpectedly had native reroll capability')

local traitsBefore = #CurrentRun.Hero.Traits
local refreshBefore = refreshes[rewardDoor.ObjectId] or 0
M.dispatch('set_feature', { feature = 'forceEnableRerolls', value = true, includeCatalogs = false })
assert(rewardDoor.CanBeRerolled,
  'enabling Force Enable Rerolls did not activate an already-offered reward door')
assert(HasHeroTraitValue('AllowDoorReroll'),
  'Force Enable Rerolls did not expose the native door-reroll capability query')
assert(#CurrentRun.Hero.Traits == traitsBefore,
  'Force Enable Rerolls mutated permanent/current Hero trait ownership')
assert((refreshes[rewardDoor.ObjectId] or 0) > refreshBefore,
  'enabling feature did not refresh the existing door prompt')

local beforeSpend = CurrentRun.NumRerolls
AttemptReroll(CurrentRun, rewardDoor)
assert(CurrentRun.NumRerolls == beforeSpend - 1 and doorRerolls == 1,
  'reward door did not reroll through native AttemptReroll/AttemptRerollDoor')
assert(rewardRoom.ChosenRewardType == 'PoseidonUpgrade',
  'native reward-door owner did not receive the rerolled reward')

-- "Force" applies to a genuine reward owner even if that door instance says
-- AllowReroll=false; the Trainer does not persistently rewrite that authored flag.
local authoredBlockedRoom = { Name = 'BlockedReward', ChosenRewardType = 'ZeusUpgrade' }
local authoredBlockedDoor = {
  ObjectId = 802,
  AllowReroll = false,
  ReadyToUse = true,
  RerollFunctionName = 'AttemptRerollDoor',
}
AssignRoomToExitDoor(authoredBlockedDoor, authoredBlockedRoom)
assert(authoredBlockedDoor.CanBeRerolled,
  'valid reward door remained blocked solely by authored AllowReroll=false')
assert(authoredBlockedDoor.AllowReroll == false,
  'feature rewrote the authored AllowReroll flag instead of overriding availability')

-- Game-owned hard-invalid owners remain invalid. These are not "global reroll
-- disabled" cases; they lack a legal reward-door reroll transaction.
local storyRoom = {
  Name = 'StoryRoom', ChosenRewardType = 'Story', NoReroll = true,
}
local storyDoor = {
  ObjectId = 803, AllowReroll = true, ReadyToUse = true,
  RerollFunctionName = 'AttemptRerollDoor',
}
AssignRoomToExitDoor(storyDoor, storyRoom)
assert(not storyDoor.CanBeRerolled and storyRoom.NoReroll == true,
  'NoReroll story/boss owner was incorrectly force-enabled')

local shopRoom = { Name = 'ShopRoom', ChosenRewardType = 'Shop' }
local shopDoor = {
  ObjectId = 804, AllowReroll = true, ReadyToUse = true,
  RerollFunctionName = 'AttemptRerollDoor',
}
AssignRoomToExitDoor(shopDoor, shopRoom)
assert(not shopDoor.CanBeRerolled,
  'Shop exit was incorrectly treated as a reward reroll owner')

local lockedRoom = { Name = 'LockedReward', ChosenRewardType = 'ZeusUpgrade' }
local lockedDoor = {
  ObjectId = 805, AllowReroll = true, ReadyToUse = true,
  RerollFunctionName = 'AttemptRerollDoor', SpecialRequirement = 'Locked',
}
AssignRoomToExitDoor(lockedDoor, lockedRoom)
assert(not lockedDoor.CanBeRerolled,
  'special-requirement exit was force-enabled before the game made it legal')

local emptyRoom = { Name = 'NoReward', NoReward = true }
local emptyDoor = {
  ObjectId = 806, AllowReroll = true, ReadyToUse = true,
  RerollFunctionName = 'AttemptRerollDoor',
}
AssignRoomToExitDoor(emptyDoor, emptyRoom)
assert(not emptyDoor.CanBeRerolled,
  'no-reward exit was incorrectly exposed as a reroll owner')

-- Fields keeps its native cage/door generator and native one-reroll spend.
local fieldsRoom = {
  Name = 'FieldsReward',
  ChosenRewardType = 'ZeusUpgrade',
  CageRewards = { { RewardType = 'ZeusUpgrade' } },
}
local fieldsDoor = {
  ObjectId = 807,
  AllowReroll = true,
  ReadyToUse = true,
  RerollFunctionName = 'AttemptRerollFieldsDoor',
}
AssignRoomToExitDoor(fieldsDoor, fieldsRoom)
assert(fieldsDoor.CanBeRerolled,
  'Fields reward door was not force-enabled')
beforeSpend = CurrentRun.NumRerolls
AttemptReroll(CurrentRun, fieldsDoor)
assert(CurrentRun.NumRerolls == beforeSpend - 1 and fieldsRerolls == 1,
  'Fields reroll did not remain owned by native AttemptRerollFieldsDoor')

-- Ship wheels use the same native AllowDoorReroll capability even though they
-- are not in OfferedExitDoors. Mid-encounter enable must update an existing wheel.
M.dispatch('set_feature', { feature = 'forceEnableRerolls', value = false, includeCatalogs = false })
nativeDoorReroll = false
local wheel = {
  ObjectId = 901,
  ReadyToUse = true,
  ChosenRewardType = 'ZeusUpgrade',
  RerollFunctionName = 'AttemptRerollShipWheel',
  Room = CurrentRun.CurrentRoom,
}
MapState.ShipWheels = { [wheel.ObjectId] = wheel }
assert(not wheel.CanBeRerolled,
  'trial-disabled ship wheel unexpectedly had native reroll capability')
M.dispatch('set_feature', { feature = 'forceEnableRerolls', value = true, includeCatalogs = false })
assert(wheel.CanBeRerolled,
  'enabling feature did not activate an already-created ship-wheel reward owner')
beforeSpend = CurrentRun.NumRerolls
AttemptReroll(CurrentRun, wheel)
assert(CurrentRun.NumRerolls == beforeSpend - 1 and wheelRerolls == 1,
  'ship-wheel reroll did not remain owned by native AttemptRerollShipWheel')

-- Disable restores current native capability instead of leaving forced booleans.
M.dispatch('set_feature', { feature = 'forceEnableRerolls', value = false, includeCatalogs = false })
assert(not HasHeroTraitValue('AllowDoorReroll'),
  'disabling feature left synthetic door-reroll capability active')
assert(not rewardDoor.CanBeRerolled and not authoredBlockedDoor.CanBeRerolled
  and not fieldsDoor.CanBeRerolled and not wheel.CanBeRerolled,
  'disabling feature left trial-disabled reward owners force-enabled')

-- If the native DoorRerollMetaUpgrade is actually present, disable must restore
-- ordinary native availability instead of suppressing it.
nativeDoorReroll = true
local nativeRoom = { Name = 'NativeReward', ChosenRewardType = 'ZeusUpgrade' }
local nativeDoor = {
  ObjectId = 902,
  AllowReroll = true,
  ReadyToUse = true,
  RerollFunctionName = 'AttemptRerollDoor',
}
AssignRoomToExitDoor(nativeDoor, nativeRoom)
assert(nativeDoor.CanBeRerolled, 'native DoorReroll capability baseline is broken')
M.dispatch('set_feature', { feature = 'forceEnableRerolls', value = true, includeCatalogs = false })
M.dispatch('set_feature', { feature = 'forceEnableRerolls', value = false, includeCatalogs = false })
assert(nativeDoor.CanBeRerolled,
  'disable suppressed a reward door that remains natively rerollable')
assert(HasHeroTraitValue('AllowDoorReroll') == nativeDoorTrait,
  'disable did not release the synthetic AllowDoorReroll capability hook')
'''

HARNESS = BASE_HARNESS.replace(
    "print('hades2_force_enable_rerolls_ok')",
    DOOR_CASES + "\nprint('hades2_force_enable_rerolls_ok')",
)

with tempfile.TemporaryDirectory(prefix="mgt-force-enable-rerolls-doors-") as temporary:
    harness = Path(temporary) / "force-enable-rerolls-doors.lua"
    harness.write_text(HARNESS)
    result = subprocess.run(
        [LUA, str(harness), str(ROOT / "Backend/games/hades2/runtime/hades.lua"),
         str(RESIDENT_DISPATCH_CONTRACT)],
        cwd=ROOT, text=True, capture_output=True, timeout=30,
    )
    if result.returncode:
        print(result.stdout)
        print(result.stderr)
        raise SystemExit(result.returncode)
    assert "hades2_force_enable_rerolls_ok" in result.stdout

print("hades2_force_enable_rerolls_doors_runtime_ok")
