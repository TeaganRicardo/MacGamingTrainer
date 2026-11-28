"""Native-shaped Hades resources, fishing, reward and exit ownership journeys."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
sys.path.insert(0, str(ROOT / 'tests'))
from games.hades.lldb_worker import lua_literal
from games.hades.world import runtime_definitions
from lua_runtime_support import require_lua52

lua = require_lua52('Hades world action ownership journeys')
harness = r'''
local function clone(value)
  if type(value) ~= "table" then return value end
  local result = {}; for k, v in pairs(value) do result[k] = clone(v) end
  return result
end
DeepCopyTable = clone
SaveIgnores = {}
GameState = { Resources = { MetaPoints = 10 }, LifetimeResourcesGained = { MetaPoints = 20 } }
CurrentRun = { Hero = { ObjectId = 10, Health = 50, MaxHealth = 50, Traits = {} }, Money = 5,
  BiomeDepthCache = 8, RoomCreations = {}, CurrentRoom = { Name = "A_Combat01", RoomSetName = "Tartarus" } }
local originalRoom = CurrentRun.CurrentRoom
RoomSetData = { Tartarus = {
  A_Combat02 = { Name = "A_Combat02", ChosenRewardType = "RoomRewardMoneyDrop" },
  A_Story01 = { Name = "A_Story01", ForcedReward = "Story", LegalEncounters = { "Story_Sisyphus_01" }, eligible = true },
  A_Shop01 = { Name = "A_Shop01", ForcedReward = "Shop", eligible = false },
}, Alternate = {
  B_Combat01 = { Name = "B_Combat01", ChosenRewardType = "RoomRewardMoneyDrop" },
  B_Shop01 = { Name = "B_Shop01", ForcedReward = "Shop", eligible = false },
}, Asphodel = {
  B_Combat01 = { Name = "B_Combat01", ChosenRewardType = "RoomRewardMoneyDrop" },
  B_Story01 = { Name = "B_Story01", ForcedReward = "Story", LegalEncounters = { "Story_Eurydice_01" }, eligible = true },
}, Elysium = {
  C_Combat01 = { Name = "C_Combat01", ChosenRewardType = "RoomRewardMoneyDrop" },
  C_Story01 = { Name = "C_Story01", ForcedReward = "Story", LegalEncounters = { "Story_Patroclus_01" }, eligible = true },
}, Secrets = { { Name = "RoomSecret01" } } }
EncounterSets = { ThanatosEncounters = { "ThanatosTartarus" } }
EncounterData = {
  NativeDefault = { Name = "NativeDefault" },
  ThanatosTartarus = { Name = "ThanatosTartarus" },
  Story_Sisyphus_01 = { Name = "Story_Sisyphus_01" },
  Story_Eurydice_01 = { Name = "Story_Eurydice_01" },
  Story_Patroclus_01 = { Name = "Story_Patroclus_01" },
}
local encounterCalls, recordedEncounter = 0, nil
function SetupEncounter(data, room) return clone(data) end
function IsEncounterEligible(run, room, data)
  if data.Name:find("Story_", 1, true) == 1 then
    if data.blocked then return false end
    for _, legal in ipairs(room.LegalEncounters or {}) do
      if legal == data.Name then return true end
    end
    return false
  end
  return data.Name == "NativeDefault" or room.blockThanatos ~= true
end
function IsEncounterForced(run, room, data) return data.forced == true end
function ChooseEncounter(run, room)
  encounterCalls = encounterCalls + 1
  local eligible, forced = {}, {}
  for _, data in pairs(EncounterData) do
    if IsEncounterEligible(run, room, data) then
      eligible[#eligible + 1] = data
      if IsEncounterForced(run, room, data) then forced[#forced + 1] = data end
    end
  end
  table.sort(eligible, function(a, b) return a.Name < b.Name end)
  table.sort(forced, function(a, b) return a.Name < b.Name end)
  return SetupEncounter(GetRandomValue(#forced > 0 and forced or eligible), room)
end
function RecordEncounter(run, encounter)
  assert(run == CurrentRun)
  recordedEncounter = encounter.Name
end
local eligibilityUsesRandom = false
function IsRoomEligible(run, room, data, args)
  assert(type(args) == "table")
  if eligibilityUsesRandom then GetRandomValue({ true, false }) end
  return data.eligible ~= false and data.Name ~= room.Name
    and (not data.ForceAtBiomeDepthMin or run.BiomeDepthCache >= data.ForceAtBiomeDepthMin)
end
local randomDraws, forceError, forcedUsesRandom = 0, false, false
function RandomChance(chance) randomDraws = randomDraws + 1; return false end
local nativeRandomChance = RandomChance
function IsRoomForced(run, room, data, args)
  assert(run == CurrentRun and room == run.CurrentRoom and type(args) == "table")
  if forceError then RandomChance(0.5); error("injected native force failure") end
  if forcedUsesRandom and data.RandomForced then return GetRandomValue({ false, true }) end
  if data.AlwaysForce then return true end
  local depth = run.BiomeDepthCache + (args.RoomsSkipped or 0)
  if data.ForceAtBiomeDepthMin and depth >= data.ForceAtBiomeDepthMin then
    if depth >= data.ForceAtBiomeDepthMax then return true end
    return RandomChance(1 / (data.ForceAtBiomeDepthMax - depth))
  end
  return false
end
local roomGenerationCalls, randomValueCalls = 0, 0
local lastCreateArgs
function CreateRoom(data, args)
  lastCreateArgs = clone(args)
  roomGenerationCalls = roomGenerationCalls + 1
  CurrentRun.RoomCreations[data.Name] = (CurrentRun.RoomCreations[data.Name] or 0) + 1
  local result = clone(data); result.RoomSetName = CurrentRun.CurrentRoom.RoomSetName or "Tartarus"
  if args and args.ChooseEncounterForTest then
    result.Encounter = ChooseEncounter(CurrentRun, result)
  end
  return result
end
function SetupRoomReward(run, room) if room.ChosenRewardType == "Boon" then assert(room.ForceLootName) end end
function IsRoomRewardEligible(run, room, reward) return reward.Name ~= room.blockReward and not reward.locked end
function IsGameStateEligible(run, source) return source ~= nil and not source.locked end
LootData = { ZeusUpgrade = {}, AthenaUpgrade = {}, WeaponUpgrade = {}, StackUpgrade = {}, HermesUpgrade = { locked = true } }
RewardStoreData = { RunProgress = { { Name = "Boon" }, { Name = "StackUpgrade", locked = true } } }
local firstRoom = { Name = "A_Combat02", ChosenRewardType = "RoomRewardMoneyDrop" }
local firstDoor = {
  Name = "ExitDoor", ObjectId = 100, ReadyToUse = true, CanBeRerolled = true, Room = firstRoom,
}
local secondRoom = { Name = "B_Combat02", ChosenRewardType = "RoomRewardMoneyDrop" }
local secondDoor = {
  Name = "ExitDoor", ObjectId = 101, ReadyToUse = true, Room = secondRoom,
  ChooseRoomArgs = { RoomSetName = "Alternate" },
}
OfferedExitDoors = { [100] = firstDoor, [101] = secondDoor }
local assigned, previews, destroyed = 0, 0, 0
function AssignRoomToExitDoor(door, room)
  assigned = assigned + 1; door.Room = room; OfferedExitDoors[door.ObjectId] = door
  CurrentRun.CurrentRoom.OfferedRewards = CurrentRun.CurrentRoom.OfferedRewards or {}
  CurrentRun.CurrentRoom.OfferedRewards[door.ObjectId] = { Type = room.ChosenRewardType, ForceLootName = room.ForceLootName }
end
function CreateDoorRewardPreview(door)
  previews = previews + 1
  door.PreviewReward = door.Room and (door.Room.ForceLootName or door.Room.ChosenRewardType or "") or ""
  door.PreviewRoomName = door.Room and door.Room.Name or ""
  door.PreviewAnimation = door.Room and (
    door.Room.NextRoomSet and "ExitPreview"
    or door.Room.ChosenRewardType == nil and "StoryPreview"
    or (door.Room.ChosenRewardType .. "Preview")
  ) or ""
  door.PreviewIcon = door.Room and door.Room.RewardPreviewIcon or nil
  door.PreviewFx = door.Room and door.Room.RewardPreviewFx or nil
end
local leaveCalls = 0
function LeaveRoom(run, door)
  assert(run == CurrentRun and (door == firstDoor or door == secondDoor) and door.Room)
  leaveCalls = leaveCalls + 1
  run.CurrentRoom = door.Room
  return door.Room
end
function AttemptUseDoor(door)
  if not door.ReadyToUse or door.Room == nil or OfferedExitDoors[door.ObjectId] ~= door then return false end
  return LeaveRoom(CurrentRun, door)
end
function Destroy(args) destroyed = destroyed + #args.Ids end
local inactivePoints = { 501 }
local pedestalIds = { 801, 802, 803 }
local secretPoints = { 601 }
local positions = { [601] = { X = 100, Y = 50 }, [602] = { X = 400, Y = 50 }, [850] = { X = 100, Y = 50 } }
local closestError = false
function GetClosest(args)
  if closestError then error("injected native footprint failure") end
  local nearest, distance
  local origin = assert(positions[args.Id])
  for _, id in ipairs(args.DestinationIds) do
    local point = positions[id]
    local value = (point.X - origin.X)^2 + (point.Y - origin.Y)^2
    if not distance or value < distance then nearest, distance = id, value end
  end
  return nearest
end
function IsWellShopEligible(run, room) return room.WellShopChanceSuccess and not room.blockWell end
function IsSellTraitShopEligible(run, room) return room.SellTraitShopChanceSuccess end
function IsChallengeSwitchEligible(run, count) return run.CurrentRoom.ChallengeChanceSuccess end
function IsShrinePointDoorEligible() return true end
function RefreshUseButton() end
function SetAnimation() end
local injectedSpawnError = false
function HandleSecretSpawns(run)
  assert(not IsSecretDoorEligible(run, run.CurrentRoom), "unrelated Chaos generation escaped scope")
  assert(not IsFishingEligible(run, run.CurrentRoom), "unrelated fishing escaped scope")
  assert(not IsShrinePointDoorEligible(run, run.CurrentRoom), "unrelated Erebus generation escaped scope")
  if injectedSpawnError then error("injected native spawn failure") end
  local points = GetIdsByType({ Name = "ChallengeSwitchBase" })
  if IsWellShopEligible(run, run.CurrentRoom) then
    run.CurrentRoom.WellShop = { ObjectId = points[1], AvailableUseText = "UseWell" }
  elseif IsSellTraitShopEligible(run, run.CurrentRoom) then
    run.CurrentRoom.SellTraitShop = { ObjectId = points[1], AvailableUseText = "UsePurge" }
  elseif IsChallengeSwitchEligible(run, #points) then
    run.CurrentRoom.ChallengeSwitch = { ObjectId = points[1], ChallengeAvailableUseText = "UseTrove", UnlockedAnimationName = "TroveReady" }
  end
end
function GetInactiveIdsByType(args) assert(args.Name == "FishingPoint"); return inactivePoints end
function GetIdsByType(args)
  if args.Name == "ChallengeSwitchBase" then return pedestalIds end
  assert(args.Name == "SecretPoint"); return secretPoints
end
function GetRandomValue(values)
  randomValueCalls = randomValueCalls + 1
  return values[1]
end
function GetRunDepth(run) return 8 end
local activated = 0
function Activate(args) activated = args.Id; inactivePoints = {} end
local traitUses = 0
function UseHeroTraitsWithValue() traitUses = traitUses + 1 end
function CheckRoomExitsReady(room) return true end
function thread(fn, ...) return fn(...) end
function FishingPointAvailablePresentation(room) assert(room.FishingPointId == 501) end
function IsFishingEligible(run, room)
  if room.PersistentFishing and room.oldCompleted then return false end
  return room.FishingPointChanceSuccess and room.rodUnlocked ~= false
end
function IsSecretDoorEligible(run, room) return room.SecretChanceSuccess and room.chaosUnlocked ~= false end
function ChooseNextRoomData(run, args)
  if args.RoomDataSet == RoomSetData.Secrets then return args.RoomDataSet[1] end
  local eligible, forced = {}, {}
  for _, data in pairs(RoomSetData[run.CurrentRoom.RoomSetName or "Tartarus"] or {}) do
    if IsRoomEligible(run, run.CurrentRoom, data, args) then
      eligible[#eligible + 1] = data
      if IsRoomForced(run, run.CurrentRoom, data, args) then forced[#forced + 1] = data end
    end
  end
  table.sort(eligible, function(a, b) return a.Name < b.Name end)
  return GetRandomValue(#forced > 0 and forced or eligible)
end
ObstacleData = { SecretDoor = { Name = "SecretDoor" } }
function GetSecretDoorCost() return 12 end
local spawned = 0
function SpawnObstacle(args)
  spawned = spawned + 1
  if positions[args.DestinationId] then positions[700 + spawned] = clone(positions[args.DestinationId]) end
  return 700 + spawned
end
function SetupObstacle(door) assert(door.Name == "SecretDoor") end
function ExitDoorUnlockedPresentation(door) assert(door.HealthCost == 12) end
function AddResource(name, amount, source)
  assert(source == "MacGamingTrainer.Hades")
  GameState.Resources[name] = (GameState.Resources[name] or 0) + amount
  GameState.LifetimeResourcesGained[name] = (GameState.LifetimeResourcesGained[name] or 0) + amount
end
function AddMoney(amount, source) CurrentRun.Money = CurrentRun.Money + amount end
local loot, consumable = {}, nil
function GiveLoot(args) loot[#loot + 1] = args end
function CreateWeaponLoot(args) loot[#loot + 1] = { ForceLootName = "WeaponUpgrade", SpawnPoint = args.SpawnPoint } end
function CreateStackLoot(args) loot[#loot + 1] = { ForceLootName = "StackUpgrade", SpawnPoint = args.SpawnPoint } end
ConsumableData = { GemDrop = {} }
ActivatedObjects = {}
function CreateConsumableItem(id, name, cost) consumable = { ObjectId = id, Name = name, Cost = cost }; return consumable end
function ApplyConsumableItemResourceMultiplier(room, reward) reward.multiplied = true end
function ExtractValues(hero, reward) reward.extracted = hero.ObjectId end
local runtime = assert(loadfile(RUNTIME))()
runtime.worldDefinitions = DEFINITIONS
local function world() return runtime.status().world end
local function params(extra)
  local result = { roomId = world().roomId }
  for k, v in pairs(extra or {}) do result[k] = v end
  return result
end
local function fails(key, fn)
  local ok, err = pcall(fn); assert(not ok and tostring(err):find(key, 1, true), tostring(err))
end
local initialWorld = world()
local originalRoomId = initialWorld.roomId
-- Native reward requirements can update the frame's bookkeeping counter or
-- sample chance. Catalog observation must preserve the frame and RNG, while
-- stochastic native eligibility cannot be advertised as a sure target.
local previousSession, originalRewardEligible = SessionMapState, IsRoomRewardEligible
SessionMapState = { RequirementChecksThisFrame = 29 }
local observationSession = SessionMapState
local rewardRequiresRandom = false
IsRoomRewardEligible = function(run, room, reward)
  SessionMapState.RequirementChecksThisFrame =
    SessionMapState.RequirementChecksThisFrame + 1
  if rewardRequiresRandom and reward.Name == "Boon" then
    return GetRandomValue({ true, false })
  end
  return originalRewardEligible(run, room, reward)
end
local function findTarget(door, kind, id)
  for _, target in ipairs(door.targets or {}) do
    if target.kind == kind and target.id == id then return target end
  end
  return nil
end
local function hasTarget(door, kind, id)
  local target = findTarget(door, kind, id)
  return target ~= nil and target.enabled ~= false
end
local beforeRewardDraw = randomValueCalls
assert(hasTarget(initialWorld.doors[1], "reward", "AthenaUpgrade"))
assert(initialWorld.doors[1].roomKind == "combat", "missing roomKind on combat door")
assert(SessionMapState == observationSession
    and SessionMapState.RequirementChecksThisFrame == 29
    and randomValueCalls == beforeRewardDraw,
  "native reward catalog changed the game's bookkeeping or RNG")
rewardRequiresRandom = true
local rngAthena = findTarget(world().doors[1], "reward", "AthenaUpgrade")
assert(rngAthena and rngAthena.enabled == true and rngAthena.warning == "reward_eligibility_requires_rng",
  "random-dependent reward target did not retain availability with rng warning")
assert(SessionMapState == observationSession
    and SessionMapState.RequirementChecksThisFrame == 29
    and randomValueCalls == beforeRewardDraw,
  "native chance probe advanced reward RNG or frame bookkeeping")
IsRoomRewardEligible = originalRewardEligible
SessionMapState = previousSession
assert(initialWorld.canFish and initialWorld.canChaos and #initialWorld.doors == 2)
-- Native-generated doors can be assigned before they own any Room reference.
local unassigned = { Name = "ExitDoor", ObjectId = 120, ReadyToUse = true }
AssignRoomToExitDoor(unassigned, clone(firstRoom))
assert(unassigned.Room.Name == "A_Combat02",
  "native first assignment failed for a door without a previous room")
OfferedExitDoors[120] = nil
originalRoom.OfferedRewards[120] = nil

-- A native in-place reroll has no Trainer lease. Its observed reward history
-- must still revoke the original token permanently, including a return to
-- the exact original reward fields.
local idleDoorToken = world().doors[1].doorToken
local idleReward = firstRoom.ChosenRewardType
firstRoom.ChosenRewardType = "Boon"; firstRoom.ForceLootName = "AthenaUpgrade"
local changedIdleToken = world().doors[1].doorToken
assert(changedIdleToken ~= idleDoorToken,
  "native unleased reroll retained an earlier exact exit token")
firstRoom.ChosenRewardType = idleReward; firstRoom.ForceLootName = nil
assert(world().doors[1].doorToken ~= idleDoorToken,
  "native unleased reward ABA revived the old exact exit token")
fails("staleDoor", function()
  runtime.apply_world_exit({ roomId = originalRoomId, doorToken = idleDoorToken,
    room = "combat", reward = "AthenaUpgrade", requestId = "idle-native-aba" })
end)

assert(hasTarget(initialWorld.doors[1], "roomCategory", "story"))
assert(findTarget(initialWorld.doors[1], "roomCategory", "combat").acceptsReward == true)
assert(findTarget(initialWorld.doors[1], "roomCategory", "story").acceptsReward == false)
assert(hasTarget(initialWorld.doors[2], "roomCategory", "combat"))
assert(not hasTarget(initialWorld.doors[2], "roomCategory", "story"),
  "door-specific RoomSetName leaked the other door's route catalog")

-- Native eligibility/force probes are read-only. If either native query tries
-- to sample RNG, the targets remain buildable with an rng warning and zero draws.
eligibilityUsesRandom = true
local beforeEligibilityRandom = randomValueCalls
local rngWorld = world()
local rngCombat = findTarget(rngWorld.doors[1], "roomCategory", "combat")
local rngStory = findTarget(rngWorld.doors[1], "roomCategory", "story")
assert(rngCombat and rngCombat.enabled == true and rngCombat.warning == "room_eligibility_requires_rng")
assert(rngStory and rngStory.enabled == true and rngStory.warning == "room_eligibility_requires_rng")
assert(randomValueCalls == beforeEligibilityRandom,
  "route eligibility inspection consumed native RNG")
eligibilityUsesRandom = false
assert(#world().doors[1].targets > 0)
RoomSetData.Tartarus.A_ForcedRandom = {
  Name = "A_ForcedRandom", RandomForced = true,
}
forcedUsesRandom = true
local beforeForcedRandomProbe = randomValueCalls
assert(hasTarget(world().doors[1], "roomCategory", "combat"),
  "a random-dependent native force query unexpectedly hid combat route")
assert(randomValueCalls == beforeForcedRandomProbe,
  "native force inspection consumed GetRandomValue")
forcedUsesRandom = false
RoomSetData.Tartarus.A_ForcedRandom = nil
assert(#world().doors[1].targets > 0)

-- Two generated exits own independent leases. Native denial must not commit
-- either route; cancelling one exit must leave the other reservation intact.
local firstPlanDoor, secondPlanDoor = world().doors[1], world().doors[2]
runtime.apply_world_exit({
  roomId = originalRoomId, doorToken = firstPlanDoor.doorToken,
  room = "combat", requestId = "parallel-exit-a",
})
runtime.apply_world_exit({
  roomId = originalRoomId, doorToken = secondPlanDoor.doorToken,
  room = "combat", requestId = "parallel-exit-b",
})
local firstPlanLease = world().doors[1].activeLease
local secondPlanLease = world().doors[2].activeLease
assert(firstPlanLease and secondPlanLease
    and firstPlanLease.leaseToken ~= secondPlanLease.leaseToken)
local deniedDraws, deniedCreations, deniedLeaves =
  randomValueCalls, roomGenerationCalls, leaveCalls
firstDoor.ReadyToUse = false
assert(AttemptUseDoor(firstDoor) == false)
assert(randomValueCalls == deniedDraws and roomGenerationCalls == deniedCreations
    and leaveCalls == deniedLeaves,
  "native door denial committed a reserved route")
firstDoor.ReadyToUse = true
runtime.cancel_world_exit({
  roomId = originalRoomId, doorToken = world().doors[2].doorToken,
  leaseToken = secondPlanLease.leaseToken, requestId = "parallel-exit-b-cancel",
})
assert(world().doors[1].activeLease.leaseToken == firstPlanLease.leaseToken
    and world().doors[2].activeLease == nil,
  "cancelling one exit disturbed the competing exit lease")
runtime.cancel_world_exit({
  roomId = originalRoomId, doorToken = world().doors[1].doorToken,
  leaseToken = firstPlanLease.leaseToken, requestId = "parallel-exit-a-cancel",
})
assert(world().doors[1].activeLease == nil and world().doors[2].activeLease == nil)
assert(originalRoom.FishingPointChanceSuccess == nil and originalRoom.SecretChanceSuccess == nil)
runtime.gain_resource({ resource = "MetaPoints", amount = 7 })
assert(GameState.Resources.MetaPoints == 17 and GameState.LifetimeResourcesGained.MetaPoints == 27)
runtime.gain_resource({ resource = "Money", amount = 9 }); assert(CurrentRun.Money == 14)
fails("invalidValue", function() runtime.gain_resource({ resource = "Arbitrary", amount = 5 }) end)
runtime.spawn_reward(params({ reward = "ZeusUpgrade" }))
runtime.spawn_reward(params({ reward = "WeaponUpgrade" }))
runtime.spawn_reward(params({ reward = "StackUpgrade" }))
assert(#loot == 3 and loot[1].ForceLootName == "ZeusUpgrade" and loot[1].SpawnPoint == 10)
fails("worldUnavailable", function() runtime.spawn_reward(params({ reward = "HermesUpgrade" })) end)
assert(#loot == 3, "native source gating was bypassed")
runtime.spawn_reward(params({ reward = "GemDrop" }))
assert(consumable.Cost == 0 and consumable.multiplied and consumable.extracted == 10)
assert(ActivatedObjects[consumable.ObjectId] == consumable)
local rewardDoor = world().doors[1]
runtime.apply_world_exit({
  roomId = originalRoomId, doorToken = rewardDoor.doorToken,
  room = "combat", reward = "AthenaUpgrade", requestId = "athena-reward-1",
})
assert(firstDoor.Room == firstRoom and firstDoor.Room.ChosenRewardType == "Boon"
    and firstDoor.Room.ForceLootName == "AthenaUpgrade",
  "reward Apply replaced the physical target room instead of editing in place")
assert(firstDoor.CanBeRerolled == true,
  "reward Apply disabled the game's native reroll path")
local rewardObserved = world().doors[1]
assert(originalRoom.OfferedRewards[100].ForceLootName == "AthenaUpgrade"
    and rewardObserved.doorToken == rewardDoor.doorToken
    and rewardObserved.activeLease
    and rewardObserved.activeLease.room == "combat"
    and rewardObserved.activeLease.reward == "AthenaUpgrade"
    and rewardObserved.activeLease.leaseToken == "exit:athena-reward-1",
  "reward Apply changed stable exact-exit identity or lease feedback")
fails("staleDoor", function()
  runtime.apply_world_exit({
    roomId = originalRoomId, doorToken = rewardObserved.doorToken,
    room = "combat", reward = "AthenaUpgrade", requestId = "athena-reward-duplicate",
  })
end)
runtime.cancel_world_exit({
  roomId = originalRoomId, doorToken = rewardObserved.doorToken,
  leaseToken = rewardObserved.activeLease.leaseToken, requestId = "athena-reward-cancel",
})
assert(firstDoor.Room == firstRoom and world().doors[1].activeLease == nil)
assert(firstDoor.CanBeRerolled == true,
  "reward Cancel did not restore native rerollability")
local nativeGatedDoor = world().doors[1]
local stackTarget = findTarget(nativeGatedDoor, "reward", "StackUpgrade")
assert(stackTarget and stackTarget.warning == "reward_not_eligible",
  "store-gated StackUpgrade should still be selectable with a warning")
runtime.apply_world_exit({
  roomId = originalRoomId, doorToken = nativeGatedDoor.doorToken,
  room = "combat", reward = "StackUpgrade", requestId = "gated-reward",
})
assert(firstDoor.Room.ChosenRewardType == "StackUpgrade" and world().doors[1].activeLease.reward == "StackUpgrade",
  "store-gated reward did not apply with warning")
runtime.cancel_world_exit({
  roomId = originalRoomId, doorToken = world().doors[1].doorToken,
  leaseToken = world().doors[1].activeLease.leaseToken, requestId = "gated-reward-cancel",
})
assert(firstDoor.Room == firstRoom)
local rerollDoor = world().doors[1]
runtime.apply_world_exit({
  roomId = originalRoomId, doorToken = rerollDoor.doorToken,
  room = "combat", reward = "AthenaUpgrade", requestId = "athena-reroll",
})
local beforeNativeReroll = world().doors[1]
firstDoor.Room.ChosenRewardType = "RoomRewardMoneyDrop"; firstDoor.Room.ForceLootName = nil
assert(world().doors[1].activeLease == nil, "a native in-place reroll retained stale lease authority")
assert(world().doors[1].doorToken ~= beforeNativeReroll.doorToken,
  "native in-place reroll did not invalidate the prior exact-exit token")
fails("staleDoor", function()
  runtime.cancel_world_exit({
    roomId = originalRoomId, doorToken = beforeNativeReroll.doorToken,
    leaseToken = beforeNativeReroll.activeLease.leaseToken, requestId = "stale-reroll-cancel",
  })
end)
fails("staleDoor", function()
  runtime.apply_world_exit({
    roomId = originalRoomId, doorToken = beforeNativeReroll.doorToken,
    room = "combat", reward = "AthenaUpgrade", requestId = "stale-reroll-reapply",
  })
end)
firstDoor.Room = firstRoom
local storyCreationsBefore = CurrentRun.RoomCreations.A_Story01 or 0
local storyGenerationBefore = roomGenerationCalls
local storyDoor = world().doors[1]
runtime.apply_world_exit({
  roomId = originalRoomId,
  doorToken = storyDoor.doorToken,
  room = "story",
  requestId = "story-route-apply",
})
assert(firstDoor.Room == firstRoom,
  "route Apply replaced the native exit before the player used it")
assert((CurrentRun.RoomCreations.A_Story01 or 0) == storyCreationsBefore
    and roomGenerationCalls == storyGenerationBefore,
  "route Apply created a room or advanced room-generation state")
assert(firstDoor.PreviewRoomName == firstRoom.Name
    and firstDoor.PreviewReward == ""
    and firstDoor.PreviewAnimation == "StoryPreview"
    and firstDoor.PreviewIcon == nil and firstDoor.PreviewFx == nil,
  "story reservation preview promised an uncommitted native story room or reward")
local storyObserved = world().doors[1]
assert(storyObserved.activeLease
    and storyObserved.activeLease.room == "story"
    and storyObserved.activeLease.reward == nil
    and storyObserved.activeLease.leaseToken == "exit:story-route-apply",
  "route reservation was not projected as the authoritative active lease")
runtime.cancel_world_exit({
  roomId = originalRoomId,
  doorToken = storyObserved.doorToken,
  leaseToken = storyObserved.activeLease.leaseToken,
  requestId = "story-route-cancel",
})
assert(firstDoor.Room == firstRoom
    and (CurrentRun.RoomCreations.A_Story01 or 0) == storyCreationsBefore
    and roomGenerationCalls == storyGenerationBefore,
  "route cancellation left irreversible room-generation residue")
assert(firstDoor.PreviewRoomName == "A_Combat02"
    and firstDoor.PreviewReward == "RoomRewardMoneyDrop",
  "route cancellation did not restore the native exit preview")
assert(world().doors[1].activeLease == nil, "cancelled route lease remained active")

-- A generic combat reservation uses the supported neutral exit icon.
-- It never previews a specific room while real candidate RNG is deferred.
local combatPreviewDoor = world().doors[1]
runtime.apply_world_exit({
  roomId = originalRoomId, doorToken = combatPreviewDoor.doorToken,
  room = "combat", requestId = "neutral-combat-preview",
})
assert(firstDoor.Room == firstRoom and firstDoor.PreviewRoomName == firstRoom.Name
    and firstDoor.PreviewReward == "" and firstDoor.PreviewAnimation == "ExitPreview",
  "combat reservation claimed an uncommitted native combat room or reward")
runtime.cancel_world_exit({
  roomId = originalRoomId, doorToken = world().doors[1].doorToken,
  leaseToken = world().doors[1].activeLease.leaseToken,
  requestId = "neutral-combat-preview-cancel",
})
assert(firstDoor.PreviewRoomName == firstRoom.Name
    and firstDoor.PreviewReward == firstRoom.ChosenRewardType
    and world().doors[1].activeLease == nil,
  "generic combat preview failed to restore the native reward")

runtime.apply_world_occurrence({
  roomId = originalRoomId,
  targetID = "npc:Sisyphus",
  requestId = "precedence-sisyphus",
})
local precedenceOccurrenceToken = world().occurrence.leaseToken
local combatDoor = world().doors[1]
runtime.apply_world_exit({
  roomId = originalRoomId,
  doorToken = combatDoor.doorToken,
  room = "combat",
  requestId = "combat-route-apply",
})
local combatCreationsBefore = CurrentRun.RoomCreations.A_Combat02 or 0
local commitGenerationBefore = roomGenerationCalls
local entered = AttemptUseDoor(firstDoor)
assert(type(entered) == "table" and entered.Name == "A_Combat02",
  "native door use did not late-commit the reserved route")
assert(leaveCalls == 1
    and (CurrentRun.RoomCreations.A_Combat02 or 0) == combatCreationsBefore + 1
    and roomGenerationCalls == commitGenerationBefore + 1,
  "native door use did not materialize exactly one destination")
assert(world().occurrence and world().occurrence.target == "npc:Sisyphus"
    and world().occurrence.leaseToken == precedenceOccurrenceToken,
  "exact-exit combat route consumed or overwrote an incompatible named occurrence")
CurrentRun.CurrentRoom = originalRoom
firstDoor.Room = firstRoom
OfferedExitDoors[100] = firstDoor
runtime.cancel_world_occurrence({
  roomId = originalRoomId,
  leaseToken = precedenceOccurrenceToken,
  requestId = "precedence-sisyphus-cancel",
})
assert(world().occurrence == nil,
  "precedence regression left its independent named occurrence armed")

-- Departing through one exit must retire an independent unused reward edit
-- before native LeaveRoom records the room. The exact old offered entry,
-- including its absence, is restored.
local siblingRewardDoor = world().doors[2]
local originalSiblingOffer = originalRoom.OfferedRewards and originalRoom.OfferedRewards[101]
runtime.apply_world_exit({
  roomId = originalRoomId, doorToken = siblingRewardDoor.doorToken,
  room = "combat", reward = "AthenaUpgrade", requestId = "unused-sibling-reward",
})
assert(secondDoor.Room.ForceLootName == "AthenaUpgrade" and world().doors[2].activeLease)
local siblingDeparture = AttemptUseDoor(firstDoor)
assert(siblingDeparture == firstRoom and secondDoor.Room == secondRoom
    and (originalRoom.OfferedRewards and originalRoom.OfferedRewards[101]) == originalSiblingOffer,
  "unused sibling reward leaked into the native departure state")
CurrentRun.CurrentRoom = originalRoom
OfferedExitDoors[100] = firstDoor
assert(world().doors[2].activeLease == nil, "departed sibling lease retained authority")

local occurrenceSnapshot = world()
assert(#occurrenceSnapshot.occurrenceTargets == 5 and occurrenceSnapshot.occurrence == nil,
  "Hades I named occurrence catalog was not projected")
runtime.apply_world_occurrence({
  roomId = originalRoomId,
  targetID = "npc:Sisyphus",
  requestId = "sisyphus-once",
})
assert(world().occurrence.target == "npc:Sisyphus"
    and world().occurrence.leaseToken == "occurrence:sisyphus-once",
  "named room occurrence did not arm an authoritative run-scoped lease")
local selectedStory = ChooseNextRoomData(CurrentRun, {})
assert(selectedStory == RoomSetData.Tartarus.A_Story01,
  "named room occurrence was not selected from the native eligible pool")
assert(world().occurrence ~= nil, "merely offering the named room consumed the request")
local nextDoorBeforeCreation = ChooseNextRoomData(CurrentRun, {})
assert(nextDoorBeforeCreation ~= selectedStory,
  "one run-scoped named occurrence replaced multiple exits before native room creation")
local storyRoom = CreateRoom(selectedStory, { SkipChooseEncounter = true })
local nextDoorAfterCreation = ChooseNextRoomData(CurrentRun, {})
assert(nextDoorAfterCreation ~= selectedStory,
  "one run-scoped named occurrence replaced multiple generated exits")
storyRoom.RoomSetName = "Tartarus"
AssignRoomToExitDoor(firstDoor, storyRoom)
local storyEntered = AttemptUseDoor(firstDoor)
assert(storyEntered == storyRoom and world().occurrence == nil,
  "named room occurrence did not consume at native LeaveRoom commitment")
CurrentRun.CurrentRoom = originalRoom
firstDoor.Room = firstRoom
OfferedExitDoors[100] = firstDoor

-- A legal room cannot impersonate an exhausted or unsupported named NPC.
EncounterData.Story_Sisyphus_01.blocked = true
runtime.apply_world_occurrence({ roomId = originalRoomId,
  targetID = "npc:Sisyphus", requestId = "sisyphus-unavailable" })
assert(ChooseNextRoomData(CurrentRun, {}) ~= RoomSetData.Tartarus.A_Story01
    and world().occurrence.target == "npc:Sisyphus",
  "named story request bypassed native IsEncounterEligible")
runtime.cancel_world_occurrence({ roomId = originalRoomId,
  leaseToken = world().occurrence.leaseToken, requestId = "sisyphus-ineligible-cancel" })
EncounterData.Story_Sisyphus_01.blocked = nil
local legalSisyphus = RoomSetData.Tartarus.A_Story01.LegalEncounters
RoomSetData.Tartarus.A_Story01.LegalEncounters = { "OtherStory" }
runtime.apply_world_occurrence({ roomId = originalRoomId,
  targetID = "npc:Sisyphus", requestId = "sisyphus-illegal-room" })
assert(ChooseNextRoomData(CurrentRun, {}) ~= RoomSetData.Tartarus.A_Story01,
  "named story request ignored native LegalEncounters")
runtime.cancel_world_occurrence({ roomId = originalRoomId,
  leaseToken = world().occurrence.leaseToken, requestId = "sisyphus-illegal-cancel" })
RoomSetData.Tartarus.A_Story01.LegalEncounters = legalSisyphus

-- Each named story request uses its native biome and selected Room owner.
local function testNativeStory(targetID, biome, sourceName, storyName)
  CurrentRun.CurrentRoom = { Name = sourceName, RoomSetName = biome }
  OfferedExitDoors = { [100] = firstDoor }
  runtime.apply_world_occurrence({ roomId = world().roomId,
    targetID = targetID, requestId = "story-native-" .. biome })
  local choice = ChooseNextRoomData(CurrentRun, {})
  assert(choice.Name == storyName, "native named story selected an incorrect biome")
  local generated = CreateRoom(choice, { SkipChooseEncounter = true })
  assert(world().occurrence ~= nil, "named story was consumed when only generated")
  AssignRoomToExitDoor(firstDoor, generated)
  assert(AttemptUseDoor(firstDoor) == generated and world().occurrence == nil,
    "named story was not consumed on exact native admission")
  CurrentRun.CurrentRoom = originalRoom
  firstDoor.Room = firstRoom
  OfferedExitDoors = { [100] = firstDoor, [101] = secondDoor }
end
testNativeStory("npc:Eurydice", "Asphodel", "B_Combat00", "B_Story01")
testNativeStory("npc:Patroclus", "Elysium", "C_Combat00", "C_Story01")

RoomSetData.Tartarus.A_Shop01.eligible = true
runtime.apply_world_occurrence({
  roomId = originalRoomId,
  targetID = "shop:Charon",
  requestId = "charon-enter",
})
local charonData = ChooseNextRoomData(CurrentRun, {})
assert(charonData == RoomSetData.Tartarus.A_Shop01 and world().occurrence ~= nil,
  "Charon native shop room was not selected or consumed before admission")
local charonRoom = CreateRoom(charonData, { SkipChooseEncounter = true })
AssignRoomToExitDoor(firstDoor, charonRoom)
assert(AttemptUseDoor(firstDoor) == charonRoom and world().occurrence == nil,
  "Charon shop occurrence did not consume on exact native room admission")
CurrentRun.CurrentRoom = originalRoom
firstDoor.Room = firstRoom
OfferedExitDoors = { [100] = firstDoor, [101] = secondDoor }

runtime.apply_world_occurrence({
  roomId = originalRoomId,
  targetID = "shop:Charon",
  requestId = "charon-cancel",
})
local charonLease = world().occurrence.leaseToken
runtime.cancel_world_occurrence({
  roomId = originalRoomId,
  leaseToken = charonLease,
  requestId = "charon-cancel-request",
})
assert(world().occurrence == nil, "explicit named occurrence cancellation left a lease")
-- Restore the native availability fixture after the Charon-only eligibility case;
-- subsequent generic shop targets must remain genuinely unavailable.
RoomSetData.Tartarus.A_Shop01.eligible = false

runtime.apply_world_occurrence({
  roomId = originalRoomId,
  targetID = "npc:Thanatos",
  requestId = "thanatos-once",
})
local namedThanatos = ChooseEncounter(CurrentRun, firstDoor.Room)
assert(namedThanatos.Name == "ThanatosTartarus" and world().occurrence ~= nil,
  "named encounter was not selected or was consumed before native bookkeeping")
RecordEncounter(CurrentRun, namedThanatos)
assert(recordedEncounter == "ThanatosTartarus" and world().occurrence == nil,
  "named encounter did not consume at RecordEncounter commitment")

EncounterData.NativeDefault.forced = true
runtime.apply_world_occurrence({
  roomId = originalRoomId,
  targetID = "npc:Thanatos",
  requestId = "thanatos-native-force",
})
local forcedEncounter = ChooseEncounter(CurrentRun, firstDoor.Room)
assert(forcedEncounter.Name == "NativeDefault" and world().occurrence ~= nil,
  "named occurrence overrode a natively forced encounter")
runtime.cancel_world_occurrence({
  roomId = originalRoomId,
  leaseToken = world().occurrence.leaseToken,
  requestId = "thanatos-force-cancel",
})
EncounterData.NativeDefault.forced = nil
local forcedRoom = { Name = "A_PreBoss01", ForceAtBiomeDepthMin = 11, ForceAtBiomeDepthMax = 11,
  ForcedFirstReward = "Shop", ChosenRewardType = "Shop" }
RoomSetData.Tartarus.A_PreBoss01 = forcedRoom
CurrentRun.BiomeDepthCache = 11
assert(ChooseNextRoomData(CurrentRun, {}) == forcedRoom, "native depth-11 selection did not force its pre-boss")
firstDoor.Room = clone(forcedRoom)
local forcedDoorObs = world().doors[1]
assert(forcedDoorObs.roomKind == "" and forcedDoorObs.rewardWarning == "room_has_forced_reward",
  "forced pre-boss door lacked roomKind/rewardWarning")
local forcedCurrentTarget = findTarget(forcedDoorObs, "roomCategory", "current")
assert(forcedCurrentTarget and forcedCurrentTarget.enabled == true and forcedCurrentTarget.acceptsReward == true,
  "forced pre-boss door lacked fallback current target")
local forcedCombatTarget = findTarget(forcedDoorObs, "roomCategory", "combat")
assert(forcedCombatTarget and forcedCombatTarget.warning == "native_forced_room_present",
  "forced progression did not attach native_forced_room_present warning")
local beforeForcedApply = roomGenerationCalls
runtime.apply_world_exit({
  roomId = originalRoomId, doorToken = forcedDoorObs.doorToken,
  room = "current", reward = "AthenaUpgrade", requestId = "forced-in-place",
})
assert(firstDoor.Room.ForceLootName == "AthenaUpgrade" and roomGenerationCalls == beforeForcedApply)
runtime.cancel_world_exit({
  roomId = originalRoomId, doorToken = world().doors[1].doorToken,
  leaseToken = world().doors[1].activeLease.leaseToken, requestId = "forced-in-place-cancel",
})
assert(firstDoor.Room.ForcedFirstReward == "Shop" and firstDoor.Room.ChosenRewardType == "Shop",
  "cancelling forced in-place edit did not restore ForcedFirstReward")
firstDoor.Room = firstRoom
CurrentRun.BiomeDepthCache = 8
RoomSetData.Tartarus.A_PreBoss01 = nil
assert(#world().doors[1].targets > 0)
RoomSetData.Tartarus.A_PreBossChance = { Name = "A_PreBossChance", ForceAtBiomeDepthMin = 8, ForceAtBiomeDepthMax = 12 }
local beforeForceDraws = randomDraws
assert(ChooseNextRoomData(CurrentRun, {}) ~= RoomSetData.Tartarus.A_PreBossChance)
assert(randomDraws == beforeForceDraws + 1, "the native selector lost its original chance draw")
local beforeInspection = randomDraws
assert(hasTarget(world().doors[1], "roomCategory", "combat"))
runtime.disable_all()
assert(randomDraws == beforeInspection and RandomChance == nativeRandomChance,
  "status or disabled inspection consumed native force RNG")
ChooseNextRoomData(CurrentRun, {})
assert(randomDraws == beforeInspection + 1, "disabled native room selection changed its draw count")
local beforeForceError = randomDraws
forceError = true
local probeErrWorld = world()
local probeErrCombat = findTarget(probeErrWorld.doors[1], "roomCategory", "combat")
assert(probeErrCombat and probeErrCombat.enabled == false and probeErrCombat.reason == "room_eligibility_probe_error",
  "IsRoomForced probe failure did not disable room category with room_eligibility_probe_error")
assert(RandomChance == nativeRandomChance and randomDraws == beforeForceError,
  "native force-query failure leaked its callback or consumed RNG")
forceError = false
RoomSetData.Tartarus.A_PreBossChance = nil
local cancelRouteDoor = world().doors[1]
runtime.apply_world_exit({
  roomId = originalRoomId, doorToken = cancelRouteDoor.doorToken,
  room = "combat", requestId = "cancel-combat-route",
})
local cancelRouteLease = world().doors[1].activeLease
runtime.cancel_world_exit({
  roomId = originalRoomId, doorToken = world().doors[1].doorToken,
  leaseToken = cancelRouteLease.leaseToken, requestId = "cancel-combat-route-request",
})
assert(firstDoor.Room == firstRoom and world().doors[1].activeLease == nil)
local beforeAssignments = assigned
local shopDoor = world().doors[1]
local shopTarget = findTarget(shopDoor, "roomCategory", "shop")
assert(shopTarget and shopTarget.enabled == true and shopTarget.warning == "native_ineligible",
  "ineligible shop room did not retain availability with warning")
fails("worldUnavailable", function()
  runtime.apply_world_exit({
    roomId = originalRoomId, doorToken = shopDoor.doorToken,
    room = "reprieve", requestId = "unavailable-reprieve",
  })
end)
assert(assigned == beforeAssignments)

runtime.apply_world_occurrence({
  roomId = originalRoomId, targetID = "npc:Thanatos", requestId = "thanatos-with-reward",
})
local composedDoor = world().doors[1]
runtime.apply_world_exit({
  roomId = originalRoomId, doorToken = composedDoor.doorToken,
  room = "combat", reward = "AthenaUpgrade", requestId = "reward-with-thanatos",
})
assert(world().occurrence and world().doors[1].activeLease
    and firstDoor.Room.ForceLootName == "AthenaUpgrade",
  "exit reward edit displaced the independent named occurrence lease")
local composedEncounter = ChooseEncounter(CurrentRun, firstDoor.Room)
assert(composedEncounter.Name == "ThanatosTartarus" and world().occurrence ~= nil)
RecordEncounter(CurrentRun, composedEncounter)
assert(world().occurrence == nil, "named occurrence did not commit independently of reward lease")
local composedLease = world().doors[1].activeLease
runtime.cancel_world_exit({
  roomId = originalRoomId, doorToken = world().doors[1].doorToken,
  leaseToken = composedLease.leaseToken, requestId = "cancel-composed-reward",
})

runtime.apply_world_occurrence({
  roomId = originalRoomId, targetID = "npc:Thanatos", requestId = "thanatos-disable-all",
})
runtime.disable_all()
assert(world().occurrence == nil)
assert(ChooseEncounter(CurrentRun, firstDoor.Room).Name == "NativeDefault")

-- Disable All releases both route-preview and reward leases without leaving
-- a synthetic preview or a modified native reward behind.
runtime.apply_world_exit({
  roomId = originalRoomId, doorToken = world().doors[1].doorToken,
  room = "story", requestId = "disable-all-route",
})
assert(firstDoor.PreviewRoomName == firstRoom.Name
    and firstDoor.PreviewReward == ""
    and firstDoor.PreviewAnimation == "StoryPreview"
    and world().doors[1].activeLease)
runtime.disable_all()
assert(firstDoor.Room == firstRoom and firstDoor.PreviewRoomName == "A_Combat02"
    and world().doors[1].activeLease == nil,
  "Disable All left a synthetic route preview or route lease")
runtime.apply_world_exit({
  roomId = originalRoomId, doorToken = world().doors[1].doorToken,
  room = "combat", reward = "AthenaUpgrade", requestId = "disable-all-reward",
})
assert(firstDoor.Room.ForceLootName == "AthenaUpgrade" and world().doors[1].activeLease)
runtime.disable_all()
assert(firstDoor.Room == firstRoom and world().doors[1].activeLease == nil
    and firstDoor.CanBeRerolled == true,
  "Disable All left a modified reward or stale lease")

-- Native AttemptUseDoor has already spent applicable costs before LeaveRoom.
-- If CreateRoom or AssignRoomToExitDoor fails, the original room must still be
-- entered once with the original native door identity and lease released.
local realCreateRoom, realAssignRoom = CreateRoom, AssignRoomToExitDoor
for _, injected in ipairs({ "create", "assign" }) do
  firstDoor.Room = firstRoom
  CurrentRun.CurrentRoom = originalRoom
  OfferedExitDoors[100] = firstDoor
  local originalDestination = firstDoor.Room
  local originalOffered = originalRoom.OfferedRewards and originalRoom.OfferedRewards[100]
  local previousGenerations, previousLeaves = roomGenerationCalls, leaveCalls
  runtime.apply_world_exit({
    roomId = originalRoomId, doorToken = world().doors[1].doorToken,
    room = "combat", requestId = "failing-route-" .. injected,
  })
  if injected == "create" then
    CreateRoom = function(data, args)
      realCreateRoom(data, args)
      error("injected native room setup error")
    end
  else
    AssignRoomToExitDoor = function(door, room, ...)
      local result = realAssignRoom(door, room, ...)
      if door == firstDoor and room ~= originalDestination then
        error("injected native assignment error")
      end
      return result
    end
  end
  local enteredOnFailure = AttemptUseDoor(firstDoor)
  CreateRoom, AssignRoomToExitDoor = realCreateRoom, realAssignRoom
  assert(enteredOnFailure == originalDestination
      and CurrentRun.CurrentRoom == originalDestination
      and leaveCalls == previousLeaves + 1,
    "failed Hades I late commit stranded native door transition")
  assert(firstDoor.Room == originalDestination
      and (originalRoom.OfferedRewards and originalRoom.OfferedRewards[100]) == originalOffered,
    "failed Hades I late commit changed native original destination")
  assert(roomGenerationCalls == previousGenerations + 1,
    "test incorrectly rewound an irreversible native room-creation attempt")
  CurrentRun.CurrentRoom = originalRoom
  assert(world().doors[1].activeLease == nil
      and type(runtime.worldRouteFailure) == "string",
    "failed Hades I route retained a stale lease or hid native error")
end
firstDoor.Room = firstRoom
CurrentRun.CurrentRoom = originalRoom

-- A sibling preview can fail even if the selected route commits correctly.
-- Its failure must not prevent the accepted native transition from finishing.
runtime.apply_world_exit({
  roomId = originalRoomId, doorToken = world().doors[1].doorToken,
  room = "combat", requestId = "cleanup-primary",
})
runtime.apply_world_exit({
  roomId = originalRoomId, doorToken = world().doors[2].doorToken,
  room = "combat", requestId = "cleanup-sibling",
})
local originalPreview = CreateDoorRewardPreview
CreateDoorRewardPreview = function(door)
  if door == secondDoor then error("injected sibling preview failure") end
  return originalPreview(door)
end
local beforeCleanupLeave = leaveCalls
local siblingFailureResult = AttemptUseDoor(firstDoor)
CreateDoorRewardPreview = originalPreview
assert(type(siblingFailureResult) == "table"
    and siblingFailureResult.Name == "A_Combat02"
    and leaveCalls == beforeCleanupLeave + 1,
  "Hades I sibling preview cleanup failure aborted native door transition")
CurrentRun.CurrentRoom = originalRoom
firstDoor.Room = firstRoom
secondDoor.Room = secondRoom
assert(world().doors[2].activeLease == nil and type(runtime.worldRouteFailure) == "string",
  "Hades I failed sibling cleanup did not release the lease or report error")

runtime.generate_fishing(params())
assert(activated == 501 and originalRoom.FishingPointId == 501 and CurrentRun.LastFishingPointDepth == 8)
assert(not world().canFish)
fails("worldUnavailable", function() runtime.generate_fishing(params()) end)
local erebus = { Name = "ShrinePointDoor", ObjectId = 850, ShrinePointReq = 5, Room = { Name = "RoomChallenge01" } }
OfferedExitDoors[850] = erebus
local beforeGateSpawns, beforeGateTraits = spawned, traitUses
assert(not world().canChaos, "an Erebus-occupied secret point was available")
fails("worldUnavailable", function() runtime.generate_chaos_gate(params()) end)
assert(spawned == beforeGateSpawns and traitUses == beforeGateTraits
  and not originalRoom.ForceSecretDoor and not CurrentRun.LastSecretDepth)
secretPoints = { 601, 602 }
assert(world().canChaos, "an unoccupied shared secret point was hidden")
local gateParams = params()
closestError = true
fails("injected native footprint failure", function() runtime.generate_chaos_gate(gateParams) end)
closestError = false
assert(spawned == beforeGateSpawns and traitUses == beforeGateTraits and originalRoom.SecretChanceSuccess == nil)
runtime.generate_chaos_gate(gateParams)
local chaosDoor
for _, door in pairs(OfferedExitDoors) do if door.Name == "SecretDoor" then chaosDoor = door end end
assert(chaosDoor and chaosDoor.HealthCost == 12 and chaosDoor.ReadyToUse and chaosDoor.Room.Name == "RoomSecret01")
assert(positions[chaosDoor.ObjectId].X == positions[602].X and OfferedExitDoors[850] == erebus and erebus.ShrinePointReq == 5,
  "Chaos generation overlapped or changed the native Erebus gate")
assert(CurrentRun.LastSecretDepth == 8 and not world().canChaos)
fails("worldUnavailable", function() runtime.generate_chaos_gate(params()) end)
injectedSpawnError = true
fails("injected native spawn failure", function() runtime.generate_chamber_object(params({ object = "well" })) end)
assert(originalRoom.WellShopChanceSuccess == nil and IsShrinePointDoorEligible(CurrentRun, originalRoom))
assert(not originalRoom.WellShop)
injectedSpawnError = false
runtime.generate_chamber_object(params({ object = "well" }))
assert(originalRoom.WellShop.ObjectId == 801 and originalRoom.WellShop.ReadyToUse)
assert(originalRoom.WellShopChanceSuccess == nil)
runtime.generate_chamber_object(params({ object = "purge" }))
assert(originalRoom.SellTraitShop.ObjectId == 802 and originalRoom.SellTraitShop.ReadyToUse)
runtime.generate_chamber_object(params({ object = "trove" }))
assert(originalRoom.ChallengeSwitch.ObjectId == 803 and originalRoom.ChallengeSwitch.ReadyToUse)
assert(#world().objects == 0 and IsShrinePointDoorEligible(CurrentRun, originalRoom))
fails("worldUnavailable", function() runtime.generate_chamber_object(params({ object = "well" })) end)
runtime.apply_world_occurrence({
  roomId = originalRoomId, targetID = "npc:Thanatos", requestId = "abandoned-thanatos",
})
local abandoned = firstDoor.Room
local old = params({ reward = "ZeusUpgrade" })
local oldGate = params()
CurrentRun.CurrentRoom = { Name = "A_Combat02", RoomSetName = "Tartarus", rodUnlocked = false, chaosUnlocked = false }
OfferedExitDoors = {}
local count, beforeStaleGateSpawns = #loot, spawned
fails("staleRoom", function() runtime.spawn_reward(old) end)
fails("staleRoom", function() runtime.generate_chaos_gate(oldGate) end)
assert(spawned == beforeStaleGateSpawns, "old-room gate generation reached native creation")
assert(#loot == count and not world().canFish and not world().canChaos)
local pendingAcrossRooms = world().occurrence
assert(pendingAcrossRooms and pendingAcrossRooms.leaseToken == "occurrence:abandoned-thanatos")
assert(ChooseEncounter(CurrentRun, abandoned).Name == "NativeDefault",
  "stale source-room object selected a run-scoped encounter")
assert(ChooseEncounter({ Hero = CurrentRun.Hero }, CurrentRun.CurrentRoom).Name == "NativeDefault",
  "foreign run selected a local encounter")
assert(world().occurrence and world().occurrence.leaseToken == pendingAcrossRooms.leaseToken,
  "a stale/foreign encounter attempt consumed the pending run-scoped request")
local nextGeneratedRoom = CreateRoom(RoomSetData.Tartarus.A_Combat02, {
  ChooseEncounterForTest = true,
})
assert(nextGeneratedRoom.Encounter.Name == "ThanatosTartarus" and world().occurrence,
  "native room generation did not preserve the valid cross-room occurrence request")
RecordEncounter(CurrentRun, nextGeneratedRoom.Encounter)
assert(world().occurrence == nil, "next native commitment did not consume one-shot occurrence")
runtime.apply_world_occurrence({
  roomId = world().roomId, targetID = "npc:Thanatos", requestId = "hero-replaced",
})
CurrentRun.Hero = clone(CurrentRun.Hero)
assert(world().occurrence == nil and ChooseEncounter(CurrentRun, CurrentRun.CurrentRoom).Name == "NativeDefault",
  "hero identity replacement retained the previous run-scoped occurrence")
assert(assigned > 0 and previews > 0)

-- Conditional Fishing & Chaos Gate probabilities (0-100%, nil restore) and dynamic reasons.
for _, bad in ipairs({ -1, 100.5, 0/0, 1/0, true, "50" }) do
  fails("invalidValue", function() runtime.set_fishing_chance(bad) end)
  fails("invalidValue", function() runtime.set_chaos_gate_chance(bad) end)
end
local prevBonusFn = GetTotalHeroTraitValue
GetTotalHeroTraitValue = function(key) return key == "FishingPointChanceBonus" and 0.2 or 0 end
GameState.ActiveMutators = {
  { SecretSpawnChanceMultiplier = 2, FishingPointChanceMultiplier = 0.5 },
}
local st = runtime.set_fishing_chance(50)
assert(st.fishingChance == 50)
st = runtime.set_chaos_gate_chance(80)
assert(st.chaosGateChance == 80)
local rolledRoom = CreateRoom({
  Name = "A_Combat03", RoomSetName = "Tartarus",
  SecretSpawnChance = 0.08, FishingPointChance = 0.1,
}, { ExistingArg = true })
assert(math.abs(lastCreateArgs.RoomOverrides.SecretSpawnChance - 0.4) < 1e-6,
  "SecretSpawnChance did not account for mutator multiplier")
assert(math.abs(lastCreateArgs.RoomOverrides.FishingPointChance - 0.6) < 1e-6,
  "FishingPointChance did not account for hero bonus and mutator multiplier")
assert(math.abs(rolledRoom.SecretSpawnChance - 0.08) < 1e-6
    and math.abs(rolledRoom.FishingPointChance - 0.1) < 1e-6,
  "CreateRoom mutated base SecretSpawnChance / FishingPointChance on created room")

-- Secrets / SecretSpawnChance == 0 rooms must keep native 0% Chaos gate suppression.
lastCreateArgs = nil
local zeroSecretRoom = CreateRoom({
  Name = "A_PostBoss01", RoomSetName = "Tartarus", SecretSpawnChance = 0,
}, {})
assert(lastCreateArgs.RoomOverrides.SecretSpawnChance == nil,
  "100/80% chaos override leaked into SecretSpawnChance=0 room")
lastCreateArgs = nil
CreateRoom({ Name = "RoomSecret01", RoomSetName = "Secrets", SecretSpawnChance = 0.1 }, {})
assert(lastCreateArgs.RoomOverrides.SecretSpawnChance == nil,
  "chaos override leaked into Secrets biome")

-- 0% suppresses passive spawning via IsSecretDoorEligible and RoomChanceSuccess flags,
-- while preserving explicit ForceSecretDoor and explicit one-shot Generate.
runtime.set_fishing_chance(0)
runtime.set_chaos_gate_chance(0)
local suppressedRoom = CreateRoom({
  Name = "A_Combat04", RoomSetName = "Tartarus", SecretSpawnChance = 0.08, FishingPointChance = 0.1,
}, {})
assert(suppressedRoom.FishingPointChanceSuccess == false and suppressedRoom.SecretChanceSuccess == false,
  "0% did not clear FishingPointChanceSuccess / SecretChanceSuccess")
suppressedRoom.SecretChanceSuccess = true
CurrentRun.CurrentRoom = suppressedRoom
assert(IsSecretDoorEligible(CurrentRun, suppressedRoom) == false,
  "0% did not suppress uncommitted IsSecretDoorEligible check")
suppressedRoom.ForceSecretDoor = true
assert(IsSecretDoorEligible(CurrentRun, suppressedRoom) == true,
  "0% blocked an explicit ForceSecretDoor room")

-- Explicit Generate still works when probability override is 0%.
inactivePoints = { 501 }
secretPoints = { 601 }
OfferedExitDoors = {}
CurrentRun.LastFishingPointDepth = nil
CurrentRun.LastSecretDepth = nil
suppressedRoom.ForceSecretDoor = nil
assert(world().canFish == true and world().canChaos == true,
  "0% auto-spawn override blocked explicit one-shot Generate availability")
runtime.generate_fishing(params())
runtime.generate_chaos_gate(params())
assert(activated == 501 and suppressedRoom.FishingPointId == 501 and CurrentRun.LastSecretDepth == 8)

-- Dynamic fishingReason and chaosReason diagnostics.
local prevCosmetics = GameState.Cosmetics
assert(world().fishingReason == "existing" and world().chaosReason == "existing",
  "expected existing reasons, got " .. tostring(world().fishingReason) .. " / " .. tostring(world().chaosReason))
suppressedRoom.FishingPointId = nil
suppressedRoom.CompletedFishing = nil
suppressedRoom.ForceFishing = nil
suppressedRoom.ForceSecretDoor = nil
OfferedExitDoors = {}
inactivePoints = {}
assert(world().fishingReason == "placement", "expected placement, got " .. tostring(world().fishingReason))
inactivePoints = { 501 }
suppressedRoom.rodUnlocked = false
suppressedRoom.FishingPointRequirements = { RequiredCosmetics = { "FishingUnlockItem" } }
GameState.Cosmetics = {}
assert(world().fishingReason == "rod", "expected rod, got " .. tostring(world().fishingReason))
GameState.Cosmetics = { FishingUnlockItem = true }
assert(world().fishingReason == "progression", "expected fishing progression, got " .. tostring(world().fishingReason))
suppressedRoom.FishingPointRequirements = { RequiredMinRoomsSinceFishingPoint = 10 }
CurrentRun.RunDepthCache = 12
CurrentRun.LastFishingPointDepth = 8
assert(world().fishingReason == "spacing", "expected fishing spacing, got " .. tostring(world().fishingReason))
suppressedRoom.rodUnlocked = true

secretPoints = {}
assert(world().chaosReason == "placement", "expected chaos placement, got " .. tostring(world().chaosReason))
secretPoints = { 601 }
OfferedExitDoors[850] = { Name = "ShrinePointDoor", ObjectId = 850, Room = { Name = "RoomChallenge01" } }
positions[601] = clone(positions[850])
assert(world().chaosReason == "occupied", "expected occupied, got " .. tostring(world().chaosReason))
OfferedExitDoors = {}
CurrentRun.CurrentRoom.UsePreviousRoomSet = true
assert(world().chaosReason == "route", "expected route, got " .. tostring(world().chaosReason))
CurrentRun.CurrentRoom.UsePreviousRoomSet = nil
suppressedRoom.SecretSpawnChance = 0
assert(world().chaosReason == "room", "expected room, got " .. tostring(world().chaosReason))
suppressedRoom.SecretSpawnChance = 0.08
suppressedRoom.chaosUnlocked = false
assert(world().chaosReason == "progression", "expected chaos progression, got " .. tostring(world().chaosReason))
suppressedRoom.SecretDoorRequirements = { RequiredMinRoomsSinceSecretDoor = 10 }
CurrentRun.RunDepthCache = 12
CurrentRun.LastSecretDepth = 8
assert(world().chaosReason == "spacing", "expected chaos spacing, got " .. tostring(world().chaosReason))
suppressedRoom.chaosUnlocked = true

runtime.set_fishing_chance(nil)
runtime.set_chaos_gate_chance(nil)
assert(runtime.fishingChance == nil and runtime.chaosGateChance == nil)
GameState.Cosmetics = prevCosmetics
GameState.ActiveMutators = nil
GetTotalHeroTraitValue = prevBonusFn
CurrentRun.RunDepthCache = nil
CurrentRun.CurrentRoom = originalRoom
inactivePoints = { 501 }
secretPoints = { 601 }
OfferedExitDoors = { [100] = firstDoor, [101] = secondDoor }
CurrentRun.LastFishingPointDepth = nil
CurrentRun.LastSecretDepth = nil
positions[601] = { X = 100, Y = 50 }
originalRoom.FishingPointId = nil
originalRoom.WellShop = nil
originalRoom.SellTraitShop = nil
originalRoom.ChallengeSwitch = nil

-- All 9 gods appear on modifiable combat doors (with warning = "god_not_eligible"
-- when unlock/depth rules fail), House Contractor *RunProgress drops resolve and
-- apply cleanly, and observation runs without redundant canModify calls.
local allGodsLoot = {
  ZeusUpgrade = { locked = true },
  PoseidonUpgrade = { locked = true },
  AthenaUpgrade = {},
  AphroditeUpgrade = { locked = true },
  AresUpgrade = {},
  ArtemisUpgrade = {},
  DionysusUpgrade = {},
  DemeterUpgrade = { locked = true },
  HermesUpgrade = { locked = true },
  WeaponUpgrade = {},
  StackUpgrade = {},
}
local previousLoot, previousStore, previousCosmetics, previousConsumables =
  LootData, RewardStoreData, GameState.Cosmetics, ConsumableData
local previousForcedFn = IsRoomForced
LootData = allGodsLoot
ConsumableData = {
  RoomRewardMoneyDrop = {}, RoomRewardMaxHealthDrop = {},
  RoomRewardMetaPointDropRunProgress = {}, GemDropRunProgress = {},
  LockKeyDropRunProgress = {}, GiftDropRunProgress = {},
}
GameState.Cosmetics = {
  RoomRewardMetaPointDropRunProgress = true,
  GemDropRunProgress = true,
  LockKeyDropRunProgress = true,
  GiftDropRunProgress = true,
}
RewardStoreData = {
  InvalidOverrides = { "Secrets" },
  MetaProgress = {
    { Name = "RoomRewardMetaPointDropRunProgress" },
    { Name = "GemDropRunProgress" },
    { Name = "LockKeyDropRunProgress" },
    { Name = "GiftDropRunProgress" },
  },
  RunProgress = {
    { Name = "Boon" },
    { Name = "HermesUpgrade", locked = true },
    { Name = "WeaponUpgrade" },
    { Name = "StackUpgrade" },
    { Name = "RoomRewardMaxHealthDrop" },
    { Name = "RoomRewardMoneyDrop" },
  },
}
CurrentRun.CurrentRoom = originalRoom
firstDoor.Room = firstRoom
OfferedExitDoors = { [100] = firstDoor }
local forceChecks = 0
IsRoomForced = function(...) forceChecks = forceChecks + 1; return previousForcedFn(...) end
local godsWorld = world()
IsRoomForced = previousForcedFn
-- Route enumeration checks candidates once per room plus once for canModify(door),
-- never 21x inside the reward loop.
assert(forceChecks <= 8, "redundant canModify checks in world observation: " .. tostring(forceChecks))
local byId = {}
for _, target in ipairs(godsWorld.doors[1].targets or {}) do
  if target.kind == "reward" then byId[target.id] = target end
end
for _, god in ipairs({
  "ZeusUpgrade", "PoseidonUpgrade", "AthenaUpgrade", "AphroditeUpgrade",
  "AresUpgrade", "ArtemisUpgrade", "DionysusUpgrade", "DemeterUpgrade", "HermesUpgrade",
}) do
  assert(byId[god], "missing god target on modifiable exit: " .. god)
end
assert(byId.ZeusUpgrade.warning == "god_not_eligible")
assert(byId.PoseidonUpgrade.warning == "god_not_eligible")
assert(byId.DemeterUpgrade.warning == "god_not_eligible")
assert(byId.HermesUpgrade.warning == "god_not_eligible")
assert(byId.AthenaUpgrade.warning == nil)
assert(byId.RoomRewardMetaPointDrop and byId.GemDrop and byId.LockKeyDrop and byId.GiftDrop,
  "House Contractor *RunProgress drops missing from exit targets")

local hermesApply = runtime.apply_world_exit({
  roomId = godsWorld.roomId, doorToken = godsWorld.doors[1].doorToken,
  room = "combat", reward = "HermesUpgrade", requestId = "warned-hermes",
})
assert(firstDoor.Room.ChosenRewardType == "HermesUpgrade" and hermesApply.world.doors[1].activeLease.reward == "HermesUpgrade")
runtime.cancel_world_exit({
  roomId = hermesApply.world.roomId, doorToken = hermesApply.world.doors[1].doorToken,
  leaseToken = hermesApply.world.doors[1].activeLease.leaseToken, requestId = "warned-hermes-cancel",
})
local darknessApply = runtime.apply_world_exit({
  roomId = godsWorld.roomId, doorToken = world().doors[1].doorToken,
  room = "combat", reward = "RoomRewardMetaPointDrop", requestId = "contractor-darkness",
})
assert(firstDoor.Room.ChosenRewardType == "RoomRewardMetaPointDropRunProgress")
runtime.cancel_world_exit({
  roomId = darknessApply.world.roomId, doorToken = darknessApply.world.doors[1].doorToken,
  leaseToken = darknessApply.world.doors[1].activeLease.leaseToken, requestId = "contractor-darkness-cancel",
})

-- Combined room-type + reward reservation: when a door currently leads to a story room,
-- picking combat + AthenaUpgrade previews AthenaUpgrade without CreateRoom, cancels cleanly,
-- and late-commits combat + AthenaUpgrade on LeaveRoom.
firstDoor.Room = { Name = "A_Story01", ChosenRewardType = "Story" }
CurrentRun.CurrentRoom = originalRoom
local storyDoorObs = world().doors[1]
assert(storyDoorObs.roomKind == "story")
local storyRoomTarget = findTarget(storyDoorObs, "roomCategory", "story")
local combatRoomTarget = findTarget(storyDoorObs, "roomCategory", "combat")
local currentFallbackTarget = findTarget(storyDoorObs, "roomCategory", "current")
assert(storyRoomTarget and storyRoomTarget.acceptsReward == false)
assert(combatRoomTarget and combatRoomTarget.acceptsReward == true)
assert(currentFallbackTarget and currentFallbackTarget.acceptsReward == true)
local combinedCreations = roomGenerationCalls
local combinedApply = runtime.apply_world_exit({
  roomId = storyDoorObs.roomId or godsWorld.roomId,
  doorToken = storyDoorObs.doorToken,
  room = "combat", reward = "AthenaUpgrade", requestId = "combined-combat-athena",
})
assert(roomGenerationCalls == combinedCreations, "combined route+reward Apply called CreateRoom early")
assert(firstDoor.PreviewReward == "AthenaUpgrade", "combined route+reward Apply did not preview chosen reward")
assert(combinedApply.world.doors[1].activeLease.room == "combat"
    and combinedApply.world.doors[1].activeLease.reward == "AthenaUpgrade")
runtime.cancel_world_exit({
  roomId = combinedApply.world.roomId,
  doorToken = combinedApply.world.doors[1].doorToken,
  leaseToken = combinedApply.world.doors[1].activeLease.leaseToken,
  requestId = "combined-combat-athena-cancel",
})
assert(firstDoor.PreviewReward == "Story", "cancelling combined route+reward did not restore Story preview")
runtime.apply_world_exit({
  roomId = godsWorld.roomId,
  doorToken = world().doors[1].doorToken,
  room = "combat", reward = "AthenaUpgrade", requestId = "combined-combat-athena-commit",
})
local combinedEntered = AttemptUseDoor(firstDoor)
assert(combinedEntered.Name == "A_Combat02"
    and combinedEntered.ChosenRewardType == "Boon"
    and combinedEntered.ForceLootName == "AthenaUpgrade",
  "combined route+reward did not materialize both room type and reward on LeaveRoom")
CurrentRun.CurrentRoom = originalRoom
firstDoor.Room = firstRoom
OfferedExitDoors[100] = firstDoor

-- Fine-grained probe error, god limit, sibling god exclusion, current-store warning, and room reasons.
local originalEligibleFn = IsRoomRewardEligible
IsRoomRewardEligible = function(run, room, reward)
  if reward.Name == "StackUpgrade" then error("injected reward probe error") end
  return originalEligibleFn(run, room, reward)
end
local errRewardTarget = findTarget(world().doors[1], "reward", "StackUpgrade")
assert(errRewardTarget and errRewardTarget.enabled == false
    and errRewardTarget.reason == "reward_eligibility_probe_error",
  "throwing reward probe did not disable reward with reward_eligibility_probe_error")
fails("worldUnavailable", function()
  runtime.apply_world_exit({
    roomId = godsWorld.roomId, doorToken = world().doors[1].doorToken,
    room = "combat", reward = "StackUpgrade", requestId = "disabled-reward-probe",
  })
end)
IsRoomRewardEligible = originalEligibleFn

GetEligibleLootNames = function(excluded) return { "AthenaUpgrade" } end
ReachedMaxGods = function(excluded) return true end
CurrentRun.RewardStores = { RunProgress = { { Name = "Boon" } } }
firstRoom.RewardStoreName = "RunProgress"
originalRoom.OfferedRewards = { [100] = { Type = "Boon", ForceLootName = "AthenaUpgrade" }, [101] = { Type = "Boon", ForceLootName = "AresUpgrade" } }
local fineWorld = world()
local aresTarget = findTarget(fineWorld.doors[1], "reward", "AresUpgrade")
local zeusLimitTarget = findTarget(fineWorld.doors[1], "reward", "ZeusUpgrade")
local gemOtherStoreTarget = findTarget(fineWorld.doors[1], "reward", "GemDrop")
assert(aresTarget and aresTarget.warning == "reward_not_available", "sibling god did not emit reward_not_available")
assert(zeusLimitTarget and zeusLimitTarget.warning == "god_limit", "maxed god pool did not emit god_limit")
assert(gemOtherStoreTarget and gemOtherStoreTarget.warning == "reward_not_in_current_store",
  "off-store reward did not emit reward_not_in_current_store")
GetEligibleLootNames = nil
ReachedMaxGods = nil
CurrentRun.RewardStores = nil
firstRoom.RewardStoreName = nil
originalRoom.OfferedRewards = {}

RoomSetData.Tartarus.A_Story01.eligible = false
RoomSetData.Tartarus.A_Story01.ForceAtBiomeDepthMin = 10
assert(findTarget(world().doors[1], "roomCategory", "story").warning == "biome_depth_too_low")
RoomSetData.Tartarus.A_Story01.ForceAtBiomeDepthMin = nil
RoomSetData.Tartarus.A_Story01.eligible = true
originalRoom.NextRoomSet = { "Asphodel" }
assert(findTarget(world().doors[1], "roomCategory", "combat").warning == "source_next_room_set")
originalRoom.NextRoomSet = nil

-- Deferred world command machinery on Main.lua:_threads runs cleanly and
-- cancels pending commands when paused without tainting the runtime.
_threads = {}
local cancelledWorld = runtime.submit_world_command("wcmd-cancel", "gain_resource",
  { [1] = { resource = "Money", amount = 50 }, n = 1 })
assert(cancelledWorld.state == "pending")
cancelledWorld = runtime.cancel_world_command("wcmd-cancel")
assert(cancelledWorld.state == "cancelled")

_threads = {}
local submittedWorld = runtime.submit_world_command("wcmd-run", "apply_world_exit",
  { [1] = {
    roomId = godsWorld.roomId, doorToken = world().doors[1].doorToken,
    room = "combat", reward = "PoseidonUpgrade", requestId = "deferred-poseidon",
  }, n = 1 })
assert(submittedWorld.state == "pending" and #_threads == 1)
assert(coroutine.resume(_threads[1].thread))
local finishedWorld = runtime.world_command_result("wcmd-run")
assert(finishedWorld.state == "complete" and firstDoor.Room.ForceLootName == "PoseidonUpgrade")
runtime.cancel_world_exit({
  roomId = finishedWorld.result.world.roomId,
  doorToken = finishedWorld.result.world.doors[1].doorToken,
  leaseToken = finishedWorld.result.world.doors[1].activeLease.leaseToken,
  requestId = "deferred-poseidon-cancel",
})

LootData, RewardStoreData, GameState.Cosmetics, ConsumableData =
  previousLoot, previousStore, previousCosmetics, previousConsumables
print("hades_world_native_shaped_journeys_ok")
'''
harness = harness.replace('RUNTIME', lua_literal(str(ROOT / 'Backend/games/hades/runtime.lua')))
harness = harness.replace('DEFINITIONS', lua_literal(runtime_definitions()))
result = subprocess.run([lua, '-'], input=harness, text=True, capture_output=True)
assert result.returncode == 0, result.stdout + result.stderr
assert 'hades_world_native_shaped_journeys_ok' in result.stdout
print('hades_world_workflows_ok')
