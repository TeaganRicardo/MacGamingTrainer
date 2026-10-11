-- Minimal target-build-shaped room/encounter routing model for #459.
-- Loaded after the shared gathering fixture prefix has established the generic
-- resident globals, but before the production resident source.

CurrentRun.CurrentRoom = {
  Name = "F_Start",
  RoomSetName = "F",
  RoomCreations = {},
  ChosenRewardType = "RoomMoneyDrop",
  LegalEncounters = { "CombatNormal" },
}
CurrentRun.RoomCreations = {}
CurrentRun.RoomCountCache = {}
CurrentRun.BiomeRoomCountCache = {}
CurrentRun.EncountersOccurredCache = {}
CurrentRun.EncountersOccurredBiomeCache = {}
CurrentRun.EncountersDepthCache = {}
CurrentRun.BlockedEncounters = {}
CurrentRun.RunDepthCache = 1
CurrentRun.BiomeDepthCache = 1

RoomData = {
  F_Combat01 = { Name = "F_Combat01", RoomSetName = "F" },
  F_Forced01 = { Name = "F_Forced01", RoomSetName = "F" },
  F_Story01 = { Name = "F_Story01", RoomSetName = "F", MaxCreationsThisRun = 1 },
  F_Shop01 = { Name = "F_Shop01", RoomSetName = "F", MaxCreationsThisRun = 1 },
  G_Combat01 = { Name = "G_Combat01", RoomSetName = "G" },
  G_Story01 = { Name = "G_Story01", RoomSetName = "G", MaxCreationsThisRun = 1 },
  G_Shop01 = { Name = "G_Shop01", RoomSetName = "G", MaxCreationsThisRun = 1 },
  H_Bridge01 = { Name = "H_Bridge01", RoomSetName = "H" },
  I_Story01 = { Name = "I_Story01", RoomSetName = "I", MaxCreationsThisRun = 1 },
  N_Story01 = { Name = "N_Story01", RoomSetName = "N", MaxCreationsThisRun = 1 },
  N_Shop01 = { Name = "N_Shop01", RoomSetName = "N", MaxCreationsThisRun = 1 },
  O_Story01 = { Name = "O_Story01", RoomSetName = "O", MaxCreationsThisRun = 1 },
  O_Shop01 = { Name = "O_Shop01", RoomSetName = "O", MaxCreationsThisRun = 1 },
  P_Story01 = { Name = "P_Story01", RoomSetName = "P", MaxCreationsThisRun = 1 },
  P_Shop01 = { Name = "P_Shop01", RoomSetName = "P", MaxCreationsThisRun = 1 },
}
RoomSets = {
  F = { "F_Combat01", "F_Forced01", "F_Story01", "F_Shop01" },
  G = { "G_Combat01", "G_Story01", "G_Shop01" },
  H = { "H_Bridge01" },
  I = { "I_Story01" },
  N = { "N_Story01", "N_Shop01" },
  O = { "O_Story01", "O_Shop01" },
  P = { "P_Story01", "P_Shop01" },
}

EncounterData = {
  CombatNormal = { Name = "CombatNormal" },
  ArtemisCombatF = { Name = "ArtemisCombatF" },
  ArtemisCombatF2 = { Name = "ArtemisCombatF2" },
  ArtemisCombatIntro = { Name = "ArtemisCombatIntro" },
  AthenaCombatP = { Name = "AthenaCombatP" },
  AthenaCombatP02 = { Name = "AthenaCombatP02" },
  AthenaCombatIntro = { Name = "AthenaCombatIntro" },
  IcarusCombatO = { Name = "IcarusCombatO" },
  IcarusCombatO2 = { Name = "IcarusCombatO2" },
  IcarusCombatIntro = { Name = "IcarusCombatIntro" },
  IcarusCombatP = { Name = "IcarusCombatP" },
  IcarusCombatP2 = { Name = "IcarusCombatP2" },
  NemesisCombatF = { Name = "NemesisCombatF" },
  NemesisCombatG = { Name = "NemesisCombatG" },
  NemesisCombatH = { Name = "NemesisCombatH" },
  NemesisCombatI = { Name = "NemesisCombatI" },
  NemesisCombatIntro = { Name = "NemesisCombatIntro" },
  NemesisRandomEvent = { Name = "NemesisRandomEvent" },
  BridgeNemesisRandomEvent = { Name = "BridgeNemesisRandomEvent" },
  HeraclesCombatN = { Name = "HeraclesCombatN" },
  HeraclesCombatN2 = { Name = "HeraclesCombatN2" },
  HeraclesCombatIntro = { Name = "HeraclesCombatIntro" },
  HeraclesCombatO = { Name = "HeraclesCombatO" },
  HeraclesCombatO2 = { Name = "HeraclesCombatO2" },
  HeraclesCombatP = { Name = "HeraclesCombatP" },
  HeraclesCombatP2 = { Name = "HeraclesCombatP2" },
  Story_Echo_01 = { Name = "Story_Echo_01" },
  BridgeShop = { Name = "BridgeShop" },
}
EnemyData = {}

roomEligible = {}
encounterEligible = {}
nativeRoomForced = {}
nativeEncounterForced = {}
ForceNextRoom = nil
ForceNextEncounter = nil

IsRoomEligible = function(run, currentRoom, nextRoomData, args)
  if type(nextRoomData) ~= "table" then return false end
  if roomEligible[nextRoomData.Name] == false then return false end
  if nextRoomData.MaxCreationsThisRun ~= nil
      and (run.RoomCreations[nextRoomData.Name] or 0) >= nextRoomData.MaxCreationsThisRun then
    return false
  end
  return true
end

IsRoomForced = function(run, currentRoom, nextRoomData, args, otherDoors)
  return nativeRoomForced[nextRoomData.Name] == true
end
local nativeIsRoomForced = IsRoomForced

ChooseNextRoomData = function(run, args, otherDoors)
  args = args or {}
  if ForceNextRoom ~= nil and RoomData[ForceNextRoom] ~= nil then return RoomData[ForceNextRoom] end
  if args.ForceNextRoom ~= nil and RoomData[args.ForceNextRoom] ~= nil then return RoomData[args.ForceNextRoom] end
  local current = run.CurrentRoom
  local roomSet = RoomSets[args.RoomSetName or current.RoomSetName] or {}
  local eligible, forced = {}, {}
  for _, name in ipairs(roomSet) do
    local data = RoomData[name]
    if IsRoomEligible(run, current, data, args) then
      eligible[#eligible + 1] = data
      if IsRoomForced(run, current, data, args, otherDoors) then forced[#forced + 1] = data end
    end
  end
  return forced[1] or eligible[1]
end
local nativeChooseNextRoomData = ChooseNextRoomData

CreateRoom = function(roomData, args)
  assert(type(roomData) == "table", "fixture CreateRoom requires room data")
  local room = DeepCopyTable(roomData)
  CurrentRun.RoomCreations[room.Name] = (CurrentRun.RoomCreations[room.Name] or 0) + 1
  CurrentRun.CurrentRoom.RoomCreations = CurrentRun.CurrentRoom.RoomCreations or {}
  CurrentRun.CurrentRoom.RoomCreations[room.Name] =
    (CurrentRun.CurrentRoom.RoomCreations[room.Name] or 0) + 1
  return room
end

DoUnlockRoomExits = function(run, room)
  MapState.OfferedExitDoors = {}
  local ordered = {}
  for index = 1, 2 do
    local door = { ObjectId = index, ChooseRoomArgs = {} }
    local data = ChooseNextRoomData(run, door.ChooseRoomArgs, ordered)
    door.Room = CreateRoom(data, { SkipChooseReward = true, SkipChooseEncounter = true })
    ordered[#ordered + 1] = door
    MapState.OfferedExitDoors[door.ObjectId] = door
  end
end
local nativeDoUnlockRoomExits = DoUnlockRoomExits

IsEncounterEligible = function(run, room, data, args)
  if type(data) ~= "table" then return false end
  if encounterEligible[data.Name] == false then return false end
  local legal = args and args.LegalEncounters or room.LegalEncounters
  if type(legal) == "table" then
    local found = false
    for _, name in pairs(legal) do if name == data.Name then found = true; break end end
    if not found then return false end
  end
  return true
end

IsEncounterForced = function(run, room, data)
  return nativeEncounterForced[data.Name] == true
end
local nativeIsEncounterForced = IsEncounterForced

SetupEncounter = function(data, room)
  return DeepCopyTable(data)
end

ChooseEncounter = function(run, room, args)
  args = args or {}
  local data = nil
  if ForceNextEncounter ~= nil then
    data = EncounterData[ForceNextEncounter]
    ForceNextEncounter = nil
  elseif run.ForceNextEncounterData ~= nil then
    data = run.ForceNextEncounterData
  end
  if data == nil then
    local eligible, forced = {}, {}
    local legal = args.LegalEncounters or room.LegalEncounters or {}
    for _, name in pairs(legal) do
      local candidate = EncounterData[name]
      if IsEncounterEligible(run, room, candidate, args) then
        eligible[#eligible + 1] = candidate
        if IsEncounterForced(run, room, candidate) then forced[#forced + 1] = candidate end
      end
    end
    data = forced[1] or eligible[1]
  end
  assert(type(data) == "table", "fixture ChooseEncounter found no encounter")
  return SetupEncounter(data, room)
end
local nativeChooseEncounter = ChooseEncounter

local function setRoomSet(name)
  CurrentRun.CurrentRoom = {
    Name = name .. "_Start",
    RoomSetName = name,
    RoomCreations = {},
    ChosenRewardType = "RoomMoneyDrop",
    LegalEncounters = { "CombatNormal" },
  }
  CurrentRun.RoomCreations = {}
  MapState.OfferedExitDoors = {}
end

dofile(assert(arg[1]))
dofile(assert(arg[2]))
local M = assert(__MacGamingTrainerV1)

local function setOccurrence(target, token)
  return M.dispatch("set_next_occurrence", {
    target = target,
    token = token,
    includeCatalogs = false,
  })
end
