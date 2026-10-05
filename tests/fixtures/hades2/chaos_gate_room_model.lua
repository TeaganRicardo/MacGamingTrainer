-- Minimal native interfaces: room roll, eligibility, destination, entry/return.
local gatheringCreate = CreateRoom
local nativeRequirements = IsGameStateEligible
RoomData = { BaseRoom = { SecretSpawnChance = .2 },
 Chaos_01 = { Name = 'Chaos_01', RoomSetName = 'Chaos', UsePreviousRoomSet = true, PauseBiomeState = true },
 F_Next = { Name = 'F_Next', RoomSetName = 'F' } }
RoomSets = { Chaos = { 'Chaos_01' }, F = { 'F_Next' } }
CurrentRun.RoomHistory = {}; CurrentRun.RoomCountCache = {}; CurrentRun.RoomCreations = {}
CurrentRun.BiomeRoomCountCache = {}; CurrentRun.RunDepthCache = 8
local heroForce, forceUses, spawns, charges = false, 0, 0, 0
local points = { 101 }; local exitsReady = true
GetSecretDoorCost = function() return math.ceil(10 + CurrentRun.RunDepthCache * .5) end
GetIdsByType = function(args) return args.Name == 'SecretPoint' and copy(points) or {} end
HasHeroTraitValue = function(key) return key == 'ForceSecretDoor' and heroForce end
IsRoomEligible = function(_, room, data)
 return data ~= nil and not data.DebugOnly and data.Name ~= room.Name
  and nativeRequirements(data, data.GameStateRequirements)
end
CreateRoom = function(data, args)
 local room = gatheringCreate(data, args)
 room.SecretChanceSuccess = RandomChance(room.SecretSpawnChance or .2)
 room.ExitDoorRooms = {}; room.RoomCreations = {}
 return room
end
local nativeCreate = CreateRoom
IsSecretDoorEligible = function(run, room)
 if room.ForceSecretDoor then return true end
 if heroForce and room.Name ~= 'F_Boss01' then return true end
 if not room.SecretChanceSuccess or room.Name == 'F_Boss01' or not GameState.ChaosUnlocked then return false end
 for _, previous in ipairs(run.RoomHistory) do if previous.ForceSecretDoor then return false end end
 return nativeRequirements(room, room.SecretDoorRequirements)
end
local nativeEligible = IsSecretDoorEligible
HandleSecretSpawns = function(run)
 local room = run.CurrentRoom
 if #points == 0 or not IsSecretDoorEligible(run, room) then return end
 room.ForceSecretDoor = true
 local forced = heroForce; heroForce = false; forceUses = forceUses + 1
 local destination
 if ForceNextRoom and RoomData[ForceNextRoom] then destination = RoomData[ForceNextRoom]
 else for _, name in ipairs(RoomSets.Chaos or {}) do
  if IsRoomEligible(run, room, RoomData[name], { ForceNextRoomSet = 'Chaos' }) then destination = RoomData[name]; break end
 end end
 if not destination then return end
 spawns = spawns + 1
 local door = { Name = 'SecretDoor', OnUsedFunctionName = 'AttemptUseDoor', ObjectId = 1000 + spawns, ReadyToUse = true,
  Room = CreateRoom(destination), HealthCost = forced and 0 or room.SecretDoorHealthCost or math.ceil(10 + run.RunDepthCache * .5) }
 MapState.ActiveObstacles[door.ObjectId] = door
 MapState.OfferedExitDoors = MapState.OfferedExitDoors or {}; MapState.OfferedExitDoors[door.ObjectId] = door
 room.ExitDoorRooms[door.ObjectId] = destination.Name; room.SecretDoorHealthCost = door.HealthCost
end
AttemptUseDoor = function(door)
 if door.InUse or not door.ReadyToUse or not exitsReady or CurrentRun.Hero.Health <= door.HealthCost then return end
 door.InUse = true; charges = charges + 1; CurrentRun.Hero.Health = CurrentRun.Hero.Health - door.HealthCost
 table.insert(CurrentRun.RoomHistory, CurrentRun.CurrentRoom); CurrentRun.CurrentRoom = door.Room
end
ChooseNextRoomData = function(run)
 local set = run.CurrentRoom.RoomSetName
 if run.CurrentRoom.UsePreviousRoomSet then set = run.RoomHistory[#run.RoomHistory].RoomSetName end
 return RoomData[RoomSets[set][1]]
end
dofile(assert(arg[1])); dofile(assert(arg[2]))
local M = __MacGamingTrainerV1
local function setChaos(value) return M.dispatch('set_chaos_gate_probability', { probability = value, includeCatalogs = false }) end
local function setGathering(values) return M.dispatch('set_gathering_probabilities', { probabilities = values, includeCatalogs = false }) end
local function newRoom(value, roll, data, args)
 setChaos(value); draw = roll
 CurrentRun.CurrentRoom = CreateRoom(data or { Name = 'F_Combat01', RoomSetName = 'F' }, args)
 return CurrentRun.CurrentRoom
end
local function gate() for _, object in pairs(MapState.ActiveObstacles) do if object.Name == 'SecretDoor' then return object end end end
GameState.ChaosUnlocked = true
