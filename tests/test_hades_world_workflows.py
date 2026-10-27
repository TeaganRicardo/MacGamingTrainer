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
  A_Story01 = { Name = "A_Story01", ForcedReward = "Story", eligible = true },
  A_Shop01 = { Name = "A_Shop01", ForcedReward = "Shop", eligible = false },
}, Secrets = { { Name = "RoomSecret01" } } }
EncounterSets = { ThanatosEncounters = { "ThanatosTartarus" } }
EncounterData = { ThanatosTartarus = { Name = "ThanatosTartarus" } }
local encounterCalls = 0
function ChooseEncounter(run, room) encounterCalls = encounterCalls + 1; return { Name = "NativeDefault" } end
function SetupEncounter(data, room) return clone(data) end
function IsEncounterEligible(run, room, data) return room.blockThanatos ~= true end
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
  local result = clone(data); result.RoomSetName = "Tartarus"; return result
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
function GetRandomValue(values) return values[1] end
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
  for _, data in pairs(RoomSetData.Tartarus) do
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
  local result = params({ doorId = world().doors[1].id })
  for k, v in pairs(extra or {}) do result[k] = v end
  return result
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
local oldDoor = doorParams({ reward = "AthenaUpgrade" })
runtime.set_door_reward(oldDoor)
assert(firstDoor.Room.ChosenRewardType == "Boon" and firstDoor.Room.ForceLootName == "AthenaUpgrade")
assert(originalRoom.OfferedRewards[100].ForceLootName == "AthenaUpgrade" and world().doors[1].canRestore)
fails("staleDoor", function() runtime.set_door_reward(oldDoor) end)
runtime.restore_door(doorParams()); assert(firstDoor.Room == firstRoom and not world().doors[1].canRestore)
fails("worldUnavailable", function() runtime.set_door_reward(doorParams({ reward = "StackUpgrade" })) end)
assert(firstDoor.Room == firstRoom, "native reward-store gating was bypassed")
runtime.set_door_reward(doorParams({ reward = "AthenaUpgrade" }))
local beforeNativeReroll = doorParams()
firstDoor.Room.ChosenRewardType = "RoomRewardMoneyDrop"; firstDoor.Room.ForceLootName = nil
assert(not world().doors[1].canRestore, "a native in-place reroll retained stale restore authority")
fails("staleDoor", function() runtime.restore_door(beforeNativeReroll) end)
firstDoor.Room = firstRoom
runtime.set_door_route(doorParams({ route = "story" }))
assert(firstDoor.Room.Name == "A_Story01" and CurrentRun.RoomCreations.A_Story01 == 1)
runtime.restore_door(doorParams()); assert(firstDoor.Room == firstRoom)
local forcedRoom = { Name = "A_PreBoss01", ForceAtBiomeDepthMin = 11, ForceAtBiomeDepthMax = 11,
  ForcedFirstReward = "Shop", ChosenRewardType = "Shop" }
RoomSetData.Tartarus.A_PreBoss01 = forcedRoom
CurrentRun.BiomeDepthCache = 11
assert(ChooseNextRoomData(CurrentRun, {}) == forcedRoom, "native depth-11 selection did not force its pre-boss")
firstDoor.Room = clone(forcedRoom)
local forcedTarget, beforeForcedAssignments = firstDoor.Room, assigned
assert(not world().doors[1].canReward and #world().doors[1].routes == 0)
fails("worldUnavailable", function() runtime.set_door_route(doorParams({ route = "combat" })) end)
fails("worldUnavailable", function() runtime.set_door_reward(doorParams({ reward = "AthenaUpgrade" })) end)
assert(firstDoor.Room == forcedTarget and assigned == beforeForcedAssignments)
firstDoor.Room = firstRoom
assert(#world().doors[1].routes == 0, "a forced room outside route categories was ignored")
fails("worldUnavailable", function() runtime.set_door_route(doorParams({ route = "thanatos" })) end)
CurrentRun.BiomeDepthCache = 8
RoomSetData.Tartarus.A_PreBoss01 = nil
assert(#world().doors[1].routes > 0)
RoomSetData.Tartarus.A_PreBossChance = { Name = "A_PreBossChance", ForceAtBiomeDepthMin = 8, ForceAtBiomeDepthMax = 12 }
local beforeForceDraws = randomDraws
assert(ChooseNextRoomData(CurrentRun, {}) ~= RoomSetData.Tartarus.A_PreBossChance)
assert(randomDraws == beforeForceDraws + 1, "the native selector lost its original chance draw")
local beforeInspection = randomDraws
assert(#world().doors[1].routes == 0, "potentially forced route was exposed as an override")
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
runtime.set_door_route(doorParams({ route = "combat" }))
runtime.restore_door(doorParams()); assert(firstDoor.Room == firstRoom)
local beforeAssignments = assigned
fails("worldUnavailable", function() runtime.set_door_route(doorParams({ route = "shop" })) end)
assert(assigned == beforeAssignments)
runtime.set_door_route(doorParams({ route = "thanatos" }))
assert(world().doors[1].pendingEncounter)
runtime.set_door_reward(doorParams({ reward = "AthenaUpgrade" }))
assert(world().doors[1].pendingEncounter and firstDoor.Room.ForceLootName == "AthenaUpgrade")
local scheduled = firstDoor.Room
local encounter = ChooseEncounter(CurrentRun, scheduled)
assert(encounter.Name == "ThanatosTartarus" and encounterCalls == 0)
assert(ChooseEncounter(CurrentRun, scheduled).Name == "NativeDefault" and encounterCalls == 1)
runtime.restore_door(doorParams())
runtime.set_door_route(doorParams({ route = "thanatos" })); runtime.disable_all()
assert(not world().doors[1].pendingEncounter)
assert(ChooseEncounter(CurrentRun, firstDoor.Room).Name == "NativeDefault")
runtime.restore_door(doorParams())
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
runtime.set_door_route(doorParams({ route = "thanatos" }))
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
assert(ChooseEncounter(CurrentRun, abandoned).Name == "NativeDefault", "old source-room intent survived")
assert(assigned > 0 and previews > 0)
print("hades_world_native_shaped_journeys_ok")
'''
harness = harness.replace('RUNTIME', lua_literal(str(ROOT / 'Backend/games/hades/runtime.lua')))
harness = harness.replace('DEFINITIONS', lua_literal(runtime_definitions()))
result = subprocess.run([lua, '-'], input=harness, text=True, capture_output=True)
assert result.returncode == 0, result.stdout + result.stderr
assert 'hades_world_native_shaped_journeys_ok' in result.stdout
print('hades_world_workflows_ok')
