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
RoomSetData = {
  Tartarus = {
    A_Combat02 = { Name = "A_Combat02", ChosenRewardType = "RoomRewardMoneyDrop" },
    A_Story01 = { Name = "A_Story01", ForcedReward = "Story", LegalEncounters = { "Story_Sisyphus_01" }, eligible = true },
    A_Shop01 = { Name = "A_Shop01", ForcedReward = "Shop", LegalEncounters = { "Shop" }, eligible = false },
  },
  Asphodel = {
    B_Story01 = { Name = "B_Story01", ForcedReward = "Story", LegalEncounters = { "Story_Eurydice_01" }, eligible = true },
    B_Shop01 = { Name = "B_Shop01", ForcedReward = "Shop", LegalEncounters = { "Shop" }, eligible = true },
  },
  Elysium = {
    C_Story01 = { Name = "C_Story01", ForcedReward = "Story", LegalEncounters = { "Story_Patroclus_01" }, eligible = true },
    C_Shop01 = { Name = "C_Shop01", ForcedReward = "Shop", LegalEncounters = { "Shop" }, eligible = true },
  },
  Secrets = { { Name = "RoomSecret01" } },
}
RoomData = {
  A_Story01 = RoomSetData.Tartarus.A_Story01,
  A_Shop01 = RoomSetData.Tartarus.A_Shop01,
  B_Story01 = RoomSetData.Asphodel.B_Story01,
  B_Shop01 = RoomSetData.Asphodel.B_Shop01,
  C_Story01 = RoomSetData.Elysium.C_Story01,
  C_Shop01 = RoomSetData.Elysium.C_Shop01,
}
EncounterSets = { ThanatosEncounters = { "ThanatosTartarus" } }
EncounterData = {
  ThanatosTartarus = { Name = "ThanatosTartarus" },
  Story_Sisyphus_01 = { Name = "Story_Sisyphus_01" },
  Story_Eurydice_01 = { Name = "Story_Eurydice_01" },
  Story_Patroclus_01 = { Name = "Story_Patroclus_01" },
}
local encounterCalls = 0
function ChooseEncounter(run, room)
  encounterCalls = encounterCalls + 1
  if type(room.LegalEncounters) == "table" and room.LegalEncounters[1] then
    return { Name = room.LegalEncounters[1] }
  end
  return { Name = "NativeDefault" }
end
function SetupEncounter(data, room) return clone(data) end
function IsEncounterEligible(run, room, data)
  if type(room.LegalEncounters) == "table" then
    local legal = false
    for _, name in ipairs(room.LegalEncounters) do if name == data.Name then legal = true end end
    if not legal then return false end
  end
  return room.blockThanatos ~= true
end
function IsRoomEligible(run, room, data, args)
  assert(type(args) == "table")
  return data.eligible ~= false and data.Name ~= room.Name
    and (not data.ForceAtBiomeDepthMin or run.BiomeDepthCache >= data.ForceAtBiomeDepthMin)
end
local randomDraws, forceError = 0, false
function RandomChance(chance) randomDraws = randomDraws + 1; return false end
local nativeRandomChance = RandomChance
function IsRoomForced(run, room, data, args)
  assert(run == CurrentRun and room == run.CurrentRoom and type(args) == "table")
  if forceError then RandomChance(0.5); error("injected native force failure") end
  if data.AlwaysForce then return true end
  local depth = run.BiomeDepthCache + (args.RoomsSkipped or 0)
  if data.ForceAtBiomeDepthMin and depth >= data.ForceAtBiomeDepthMin then
    if depth >= data.ForceAtBiomeDepthMax then return true end
    return RandomChance(1 / (data.ForceAtBiomeDepthMax - depth))
  end
  return false
end
function CreateRoom(data, args)
  CurrentRun.RoomCreations[data.Name] = (CurrentRun.RoomCreations[data.Name] or 0) + 1
  local result = clone(data); result.RoomSetName = CurrentRun.CurrentRoom.RoomSetName or "Tartarus"; return result
end
function SetupRoomReward(run, room) if room.ChosenRewardType == "Boon" then assert(room.ForceLootName) end end
function IsRoomRewardEligible(run, room, reward) return reward.Name ~= room.blockReward and not reward.locked end
function IsGameStateEligible(run, source) return source ~= nil and not source.locked end
LootData = { ZeusUpgrade = {}, AthenaUpgrade = {}, WeaponUpgrade = {}, StackUpgrade = {}, HermesUpgrade = { locked = true } }
RewardStoreData = { RunProgress = { { Name = "Boon" }, { Name = "StackUpgrade", locked = true } } }
local firstRoom = { Name = "A_Combat02", ChosenRewardType = "RoomRewardMoneyDrop" }
local firstDoor = { Name = "ExitDoor", ObjectId = 100, ReadyToUse = true, Room = firstRoom }
OfferedExitDoors = { [100] = firstDoor }
local assigned, previews, destroyed = 0, 0, 0
function AssignRoomToExitDoor(door, room)
  assigned = assigned + 1; door.Room = room; OfferedExitDoors[door.ObjectId] = door
  CurrentRun.CurrentRoom.OfferedRewards = CurrentRun.CurrentRoom.OfferedRewards or {}
  CurrentRun.CurrentRoom.OfferedRewards[door.ObjectId] = { Type = room.ChosenRewardType, ForceLootName = room.ForceLootName }
end
function CreateDoorRewardPreview(door) previews = previews + 1 end
function Destroy(args) destroyed = destroyed + #args.Ids end
local recordCalls, leaveCalls = 0, 0
function RecordEncounter(run, encounter)
  assert(run == CurrentRun and type(encounter) == "table")
  recordCalls = recordCalls + 1
  run.LastRecordedEncounter = encounter.Name
  return encounter
end
function LeaveRoom(run, door)
  assert(run == CurrentRun and type(door) == "table" and type(door.Room) == "table")
  leaveCalls = leaveCalls + 1
  local target = door.Room
  if target.Encounter == nil then target.Encounter = ChooseEncounter(run, target) end
  RecordEncounter(run, target.Encounter)
  run.CurrentRoom = target
  return target
end
function AttemptUseDoor(door)
  if not door.ReadyToUse or door.Blocked or OfferedExitDoors[door.ObjectId] ~= door then return false end
  return LeaveRoom(CurrentRun, door)
end
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
local selectionDraws = 0
function GetRandomValue(values)
  selectionDraws = selectionDraws + 1
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
  args = args or {}
  if args.RoomDataSet == RoomSetData.Secrets then return args.RoomDataSet[1] end
  if ForceNextRoom ~= nil and RoomData[ForceNextRoom] ~= nil then return RoomData[ForceNextRoom] end
  local setName = args.ForceNextRoomSet or run.CurrentRoom.RoomSetName or "Tartarus"
  local eligible, forced = {}, {}
  for _, data in pairs(RoomSetData[setName] or {}) do
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
local function doorParams(extra)
  local result = params({ doorToken = world().doors[1].doorToken })
  for k, v in pairs(extra or {}) do result[k] = v end
  return result
end
local function hasTarget(row, kind, id)
  for _, target in ipairs(row.targets or {}) do
    if target.kind == kind and target.id == id then return true end
  end
  return false
end
local function cancelDoor()
  local row = world().doors[1]
  assert(row.activeLease and row.activeLease.leaseToken)
  return runtime.cancel_world_exit(params({
    doorToken = row.doorToken,
    leaseToken = row.activeLease.leaseToken,
  }))
end
local function fails(key, fn)
  local ok, err = pcall(fn); assert(not ok and tostring(err):find(key, 1, true), tostring(err))
end
local initialWorld = world()
assert(initialWorld.canFish and initialWorld.canChaos and #initialWorld.doors == 1)
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
-- Reward Apply edits only this exact target and is directly reversible.
local originalReward = firstDoor.Room.ChosenRewardType
local originalForceLoot = firstDoor.Room.ForceLootName
local rewardDoorToken = world().doors[1].doorToken
assert(hasTarget(world().doors[1], "reward", "AthenaUpgrade"))
runtime.apply_world_exit(doorParams({
  kind = "reward", actionTarget = "AthenaUpgrade",
}))
local rewardLease = assert(world().doors[1].activeLease)
assert(rewardLease.kind == "reward" and rewardLease.target == "AthenaUpgrade")
assert(world().doors[1].doorToken == rewardDoorToken,
  "reward mutation changed physical exact-door identity")
assert(firstDoor.Room == firstRoom
  and firstDoor.Room.ChosenRewardType == "Boon"
  and firstDoor.Room.ForceLootName == "AthenaUpgrade")
assert(originalRoom.OfferedRewards[100].ForceLootName == "AthenaUpgrade")
cancelDoor()
assert(firstDoor.Room == firstRoom
  and firstDoor.Room.ChosenRewardType == originalReward
  and firstDoor.Room.ForceLootName == originalForceLoot
  and world().doors[1].activeLease == nil)

-- Native reward-store eligibility remains authoritative.
fails("worldUnavailable", function()
  runtime.apply_world_exit(doorParams({
    kind = "reward", actionTarget = "StackUpgrade",
  }))
end)
assert(firstDoor.Room == firstRoom, "native reward-store gating was bypassed")

-- A native in-place reward reroll invalidates the lease instead of granting
-- restore authority over a target the game has since changed.
runtime.apply_world_exit(doorParams({
  kind = "reward", actionTarget = "AthenaUpgrade",
}))
local staleRewardLease = world().doors[1].activeLease.leaseToken
firstDoor.Room.ChosenRewardType = "RoomRewardMoneyDrop"
firstDoor.Room.ForceLootName = nil
firstDoor.Room.Reward = nil
firstDoor.Room.RewardOverrides = nil
assert(world().doors[1].activeLease == nil,
  "a native in-place reroll retained stale lease authority")
fails("staleDoor", function()
  runtime.cancel_world_exit(params({
    doorToken = world().doors[1].doorToken,
    leaseToken = staleRewardLease,
  }))
end)
AssignRoomToExitDoor(firstDoor, firstRoom)

-- Room-category Apply/Cancel is a reservation only: no RNG, CreateRoom or
-- native exit-map assignment happens until the player actually uses that door.
assert(hasTarget(world().doors[1], "roomCategory", "story"))
local beforeRouteDraws = selectionDraws
local beforeStoryCreations = CurrentRun.RoomCreations.A_Story01 or 0
local beforeRouteAssignments = assigned
runtime.apply_world_exit(doorParams({
  kind = "roomCategory", actionTarget = "story",
}))
local routeLease = assert(world().doors[1].activeLease)
assert(routeLease.kind == "roomCategory" and routeLease.target == "story")
assert(firstDoor.Room == firstRoom
  and selectionDraws == beforeRouteDraws
  and (CurrentRun.RoomCreations.A_Story01 or 0) == beforeStoryCreations
  and assigned == beforeRouteAssignments,
  "route Apply performed native route-selection side effects")
cancelDoor()
assert(firstDoor.Room == firstRoom
  and selectionDraws == beforeRouteDraws
  and (CurrentRun.RoomCreations.A_Story01 or 0) == beforeStoryCreations
  and assigned == beforeRouteAssignments,
  "route Cancel left native route-selection side effects")

-- Forced native ownership removes generic route targets and reward editing.
local forcedRoom = { Name = "A_PreBoss01", ForceAtBiomeDepthMin = 11, ForceAtBiomeDepthMax = 11,
  ForcedFirstReward = "Shop", ChosenRewardType = "Shop" }
RoomSetData.Tartarus.A_PreBoss01 = forcedRoom
CurrentRun.BiomeDepthCache = 11
assert(ChooseNextRoomData(CurrentRun, {}) == forcedRoom, "native depth-11 selection did not force its pre-boss")
firstDoor.Room = clone(forcedRoom)
AssignRoomToExitDoor(firstDoor, firstDoor.Room)
local forcedTarget, beforeForcedAssignments = firstDoor.Room, assigned
local forcedRow = world().doors[1]
assert(#forcedRow.targets == 0)
fails("worldUnavailable", function()
  runtime.apply_world_exit(doorParams({ kind = "roomCategory", actionTarget = "combat" }))
end)
fails("worldUnavailable", function()
  runtime.apply_world_exit(doorParams({ kind = "reward", actionTarget = "AthenaUpgrade" }))
end)
assert(firstDoor.Room == forcedTarget and assigned == beforeForcedAssignments)

-- A potentially forced candidate also hides the generic route catalog without
-- consuming the native RandomChance draw.
firstDoor.Room = firstRoom
AssignRoomToExitDoor(firstDoor, firstRoom)
CurrentRun.BiomeDepthCache = 8
RoomSetData.Tartarus.A_PreBoss01 = nil
RoomSetData.Tartarus.A_PreBossChance = {
  Name = "A_PreBossChance", ForceAtBiomeDepthMin = 8, ForceAtBiomeDepthMax = 12,
}
local beforeForceDraws = randomDraws
assert(ChooseNextRoomData(CurrentRun, {}) ~= RoomSetData.Tartarus.A_PreBossChance)
assert(randomDraws == beforeForceDraws + 1, "the native selector lost its original chance draw")
local beforeInspection = randomDraws
local inspected = world().doors[1]
assert(not hasTarget(inspected, "roomCategory", "combat"),
  "potentially forced route was exposed as an override")
runtime.disable_all()
assert(randomDraws == beforeInspection and RandomChance == nativeRandomChance,
  "status or disabled inspection consumed native force RNG")
ChooseNextRoomData(CurrentRun, {})
assert(randomDraws == beforeInspection + 1, "disabled native room selection changed its draw count")
local beforeForceError = randomDraws
forceError = true
fails("injected native force failure", world)
assert(RandomChance == nativeRandomChance and randomDraws == beforeForceError,
  "native force-query failure leaked its callback or consumed RNG")
forceError = false
RoomSetData.Tartarus.A_PreBossChance = nil

-- Native denial before LeaveRoom commits nothing. Authorized use materializes
-- exactly one eligible route and hands the result to native LeaveRoom.
local routeDraws = selectionDraws
local routeCreates = CurrentRun.RoomCreations.A_Story01 or 0
local routeAssignments = assigned
runtime.apply_world_exit(doorParams({
  kind = "roomCategory", actionTarget = "story",
}))
firstDoor.Blocked = true
assert(AttemptUseDoor(firstDoor) == false and leaveCalls == 0)
assert(selectionDraws == routeDraws
  and (CurrentRun.RoomCreations.A_Story01 or 0) == routeCreates
  and assigned == routeAssignments,
  "denied native door use committed a reserved route")
firstDoor.Blocked = nil
local entered = AttemptUseDoor(firstDoor)
assert(entered.Name == "A_Story01" and CurrentRun.CurrentRoom == entered)
assert(leaveCalls == 1
  and selectionDraws == routeDraws + 1
  and (CurrentRun.RoomCreations.A_Story01 or 0) == routeCreates + 1
  and assigned == routeAssignments + 1,
  "authorized route did not materialize exactly once at LeaveRoom")

-- Re-enter the original source fixture for named-occurrence behavior.
CurrentRun.CurrentRoom = originalRoom
firstDoor.Room = firstRoom
firstDoor.ReadyToUse, firstDoor.Blocked = true, nil
OfferedExitDoors = { [100] = firstDoor }
AssignRoomToExitDoor(firstDoor, firstRoom)

-- Thanatos is run-scoped, independent of a particular exit. ChooseEncounter
-- does not consume the lease; native RecordEncounter owns the irreversible ack.
runtime.apply_world_occurrence({ actionTarget = "thanatos" })
local occurrenceLease = assert(world().occurrence)
assert(occurrenceLease.target == "thanatos")
local chosen = ChooseEncounter(CurrentRun, firstDoor.Room)
assert(chosen.Name == "ThanatosTartarus" and encounterCalls == 1)
assert(world().occurrence and world().occurrence.leaseToken == occurrenceLease.leaseToken,
  "ChooseEncounter consumed the run-scoped occurrence before native record")
runtime.cancel_world_occurrence({ leaseToken = occurrenceLease.leaseToken })
RecordEncounter(CurrentRun, chosen)
assert(world().occurrence == nil,
  "recording after explicit cancellation synthesized a new occurrence lease")

runtime.apply_world_occurrence({ actionTarget = "thanatos" })
local committedLease = assert(world().occurrence).leaseToken
local beforeRecordCalls = recordCalls
local occurrenceRoom = AttemptUseDoor(firstDoor)
assert(occurrenceRoom == firstRoom and recordCalls == beforeRecordCalls + 1)
assert(CurrentRun.LastRecordedEncounter == "ThanatosTartarus")
assert(world().occurrence == nil,
  "matching native RecordEncounter did not consume the occurrence lease")

-- Native story-room and shop occurrences use the ordinary room selector.
-- They are selected only in the matching biome, remain armed while merely
-- offered, and are consumed only when the selected native exit is entered.
assert(#world().occurrenceTargets == 5)
local function routeOccurrence(target, biome, sourceName, expectedRoom, expectedEncounter, doorId)
  CurrentRun.CurrentRoom = { Name = sourceName, RoomSetName = biome }
  OfferedExitDoors = {}
  runtime.apply_world_occurrence({ actionTarget = target })
  local lease = assert(world().occurrence)
  local selectedData = ChooseNextRoomData(CurrentRun, {})
  assert(selectedData.Name == expectedRoom,
    target .. " did not route to its native-eligible room")
  local selectedRoom = CreateRoom(selectedData, { SkipChooseEncounter = true })
  local door = {
    Name = "ExitDoor", ObjectId = doorId, ReadyToUse = true, Room = selectedRoom,
  }
  AssignRoomToExitDoor(door, selectedRoom)
  assert(world().occurrence and world().occurrence.leaseToken == lease.leaseToken,
    target .. " was consumed when the room was only offered")
  local entered = AttemptUseDoor(door)
  assert(entered.Name == expectedRoom and world().occurrence == nil,
    target .. " did not consume at native room admission")
  assert(CurrentRun.LastRecordedEncounter == expectedEncounter,
    target .. " did not preserve the room's native encounter")
end

routeOccurrence("sisyphus", "Tartarus", "A_Combat01", "A_Story01", "Story_Sisyphus_01", 201)
routeOccurrence("eurydice", "Asphodel", "B_Combat01", "B_Story01", "Story_Eurydice_01", 202)
routeOccurrence("patroclus", "Elysium", "C_Combat01", "C_Story01", "Story_Patroclus_01", 203)
routeOccurrence("charon", "Asphodel", "B_Combat01", "B_Shop01", "Shop", 204)

-- A named occurrence remains pending when the current biome has no matching
-- native room, and native forced rooms keep priority over the request.
CurrentRun.CurrentRoom = { Name = "A_Combat01", RoomSetName = "Tartarus" }
OfferedExitDoors = {}
runtime.apply_world_occurrence({ actionTarget = "eurydice" })
local eurydiceLease = assert(world().occurrence).leaseToken
RoomSetData.Asphodel.B_Forced01 = { Name = "B_Forced01", AlwaysForce = true, eligible = true }
local tartarusChoice = ChooseNextRoomData(CurrentRun, {})
assert(tartarusChoice.Name ~= "B_Story01" and world().occurrence.leaseToken == eurydiceLease)
CurrentRun.CurrentRoom = { Name = "B_Combat01", RoomSetName = "Asphodel" }
OfferedExitDoors = {}
local forcedChoice = ChooseNextRoomData(CurrentRun, {})
assert(forcedChoice.Name == "B_Forced01" and world().occurrence.leaseToken == eurydiceLease,
  "a named room occurrence displaced a native forced destination")
RoomSetData.Asphodel.B_Forced01 = nil
local eurydiceData = ChooseNextRoomData(CurrentRun, {})
assert(eurydiceData.Name == "B_Story01" and world().occurrence.leaseToken == eurydiceLease)
local eurydiceRoom = CreateRoom(eurydiceData, { SkipChooseEncounter = true })
local eurydiceDoor = { Name = "ExitDoor", ObjectId = 205, ReadyToUse = true, Room = eurydiceRoom }
AssignRoomToExitDoor(eurydiceDoor, eurydiceRoom)
assert(AttemptUseDoor(eurydiceDoor).Name == "B_Story01" and world().occurrence == nil)

-- Row 1's exact-exit route has precedence over a pending named room occurrence.
-- It creates one destination and leaves the incompatible Row 2 request armed.
CurrentRun.CurrentRoom = { Name = "A_Combat01", RoomSetName = "Tartarus" }
OfferedExitDoors = {}
runtime.apply_world_occurrence({ actionTarget = "sisyphus" })
local sisyphusLease = assert(world().occurrence).leaseToken
local sisyphusData = ChooseNextRoomData(CurrentRun, {})
local sisyphusRoom = CreateRoom(sisyphusData, { SkipChooseEncounter = true })
local precedenceDoor = { Name = "ExitDoor", ObjectId = 206, ReadyToUse = true, Room = sisyphusRoom }
AssignRoomToExitDoor(precedenceDoor, sisyphusRoom)
local beforePrecedenceCreation = CurrentRun.RoomCreations.A_Combat02 or 0
local precedenceRow = world().doors[1]
runtime.apply_world_exit({
  roomId = world().roomId, doorToken = precedenceRow.doorToken,
  kind = "roomCategory", actionTarget = "combat",
})
local precedenceEntered = AttemptUseDoor(precedenceDoor)
assert(precedenceEntered.Name == "A_Combat02"
  and (CurrentRun.RoomCreations.A_Combat02 or 0) == beforePrecedenceCreation + 1
  and world().occurrence and world().occurrence.leaseToken == sisyphusLease,
  "exact-exit route and named occurrence competed or double-generated a room")
runtime.cancel_world_occurrence({ leaseToken = sisyphusLease })

-- Run-scoped occurrence survives source-room change and is consumed at the next
-- eligible recorded encounter; Disable All explicitly cancels it.
CurrentRun.CurrentRoom = originalRoom
OfferedExitDoors = { [100] = firstDoor }
firstDoor.Room = firstRoom
runtime.apply_world_occurrence({ actionTarget = "thanatos" })
local crossRoomLease = assert(world().occurrence).leaseToken
CurrentRun.CurrentRoom = { Name = "A_Combat02", RoomSetName = "Tartarus",
  rodUnlocked = false, chaosUnlocked = false }
OfferedExitDoors = {}
assert(world().occurrence and world().occurrence.leaseToken == crossRoomLease,
  "run-scoped occurrence was incorrectly source-room scoped")
local crossRoomEncounter = ChooseEncounter(CurrentRun, firstRoom)
assert(crossRoomEncounter.Name == "ThanatosTartarus")
RecordEncounter(CurrentRun, crossRoomEncounter)
assert(world().occurrence == nil)

runtime.apply_world_occurrence({ actionTarget = "thanatos" })
runtime.disable_all()
assert(world().occurrence == nil)
assert(ChooseEncounter(CurrentRun, firstRoom).Name == "NativeDefault")

-- Restore the main source room for the remaining generation journeys.
CurrentRun.CurrentRoom = originalRoom
OfferedExitDoors = { [100] = firstDoor }
firstDoor.Room = firstRoom
AssignRoomToExitDoor(firstDoor, firstRoom)
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
assert(ChooseEncounter(CurrentRun, abandoned).Name == "NativeDefault",
  "no World Actions occurrence should survive Disable All")
assert(assigned > 0 and previews > 0)
print("hades_world_native_shaped_journeys_ok")
'''
harness = harness.replace('RUNTIME', lua_literal(str(ROOT / 'Backend/games/hades/runtime.lua')))
harness = harness.replace('DEFINITIONS', lua_literal(runtime_definitions()))
result = subprocess.run([lua, '-'], input=harness, text=True, capture_output=True)
assert result.returncode == 0, result.stdout + result.stderr
assert 'hades_world_native_shaped_journeys_ok' in result.stdout
print('hades_world_workflows_ok')
