-- Exact source-shape fixture: physical current-room shops via native entry owners.
-- Loaded after gathering_room_model and chaos_gate_room_model prefixes, before
-- the resident script, so the command can use real native-shaped callbacks.

RoomData.BaseRoom.WellShopSpawnChance = 0.15
RoomData.BaseRoom.SurfaceShopSpawnChance = 0
RoomData.BaseRoom.WellShopRequirements = { allow = true }
RoomData.BaseRoom.SurfaceShopRequirements = { allow = true }
ObstacleData.WellShop = {
  Name = 'WellShop', OnUsedFunctionName = 'AttemptUseChallengeSwitch',
  AvailableUseText = 'UseWell_Unlocked',
  ChallengeSwitchUseFunctionName = 'UseWellShop',
}
ObstacleData.SurfaceShop = {
  Name = 'SurfaceShop', OnUsedFunctionName = 'AttemptUseChallengeSwitch',
  AvailableUseText = 'UseWell_Unlocked',
  ChallengeSwitchUseFunctionName = 'ShowSurfaceShopScreen',
}
ObstacleData.SellTraitShop = {
  Name = 'SellTraitShop', OnUsedFunctionName = 'AttemptUseChallengeSwitch',
  AvailableUseText = 'UseTraitShop_Unlocked',
  ChallengeSwitchUseFunctionName = 'OpenSellTraitMenu',
}

StoreData = { RoomShop = {}, SurfaceShop = {} }
local facilityPoints = { 211 }
local nativeIds = GetIdsByType
GetIdsByType = function(args)
  if args.Name == 'ChallengeSwitchBase' then return copy(facilityPoints) end
  return nativeIds(args)
end
MapState.ActiveObstacles[211] = { Name = 'ChallengeSwitchBase', ObjectId = 211 }
MapState.RoomRequiredObjects = {}
SessionMapState.SpawnPointsUsed = {}
local originalSetupHarvestPoints = SetupHarvestPoints
local setupHarvestCalls = 0
SetupHarvestPoints = function(room) setupHarvestCalls = setupHarvestCalls + 1 end

local localForce, nativeSpawns, nativeShopStock, nativeSellMenus = 0, 0, 0, 0
local nativePurchases, unrelatedChallenges = 0, 0
local activeUsable = {}
IsUseable = function(args) return activeUsable[args.Id] == true end
UseableOn = function(args) activeUsable[args.Id] = true end
SetupObstacle = function(obj)
  nativeSpawns = nativeSpawns + 1
  MapState.ActiveObstacles[obj.ObjectId] = obj
end
SetAnimation = function() end
RefreshUseButton = function() end
PlaySound = function() end
CreateAnimation = function() end
CheckRoomExitsReady = function(room) return room.ExitsUnlocked and not room.BlockExits end
AttemptUseChallengeSwitch = function(object)
  return object.ReadyToUse == true and CheckRoomExitsReady(CurrentRun.CurrentRoom)
end
FillInShopOptions = function(args)
  nativeShopStock = nativeShopStock + 1
  local name = args.StoreData == StoreData.RoomShop and 'charon' or 'hermes'
  return { StoreOptions = { { Name = name..'Potion', Cost = 30 },
    { Name = name..'Boon', Cost = 45 } }, StoreName = name }
end
IsWellShopEligible = function(run,room)
  return room.ForceWellShop or room.WellShopChanceSuccess
    and IsGameStateEligible(room,room.WellShopRequirements or RoomData.BaseRoom.WellShopRequirements)
end
IsSurfaceShopEligible = function(run,room)
  return room.ForceSurfaceShop or room.SurfaceShopChanceSuccess
    and IsGameStateEligible(room,room.SurfaceShopRequirements or RoomData.BaseRoom.SurfaceShopRequirements)
end
IsSellTraitShopEligible = function(room)
  return room.ForceSellShop or room.SellShopChanceSuccess
    and IsGameStateEligible(room,room.SellShopRequirements)
end
IsGodTrait = function(name,args) return name == 'ZeusBoon' and args.ForShop end
GenerateSellTraitValues = function(room)
  room.SellValues = {}
  for _, trait in ipairs(CurrentRun.Hero.Traits) do
    if trait.Rarity and IsGodTrait(trait.Name,{ForShop=true}) then
      room.SellValues[trait.Name] = { Name = trait.Name, Value = 45, Rarity = trait.Rarity }
    end
  end
end
GenerateSellTraitShop = function(room)
  GenerateSellTraitValues(room)
  room.SellOptions = {}
  for _, option in pairs(room.SellValues) do room.SellOptions[#room.SellOptions+1] = option end
end
RunShopGeneration = function(room)
  if IsWellShopEligible(CurrentRun,room) then
    room.Store = FillInShopOptions({StoreData=StoreData.RoomShop,RoomName=room.Name})
  end
  if IsSurfaceShopEligible(CurrentRun,room) then
    room.Store = FillInShopOptions({StoreData=StoreData.SurfaceShop,RoomName=room.Name})
  end
end
HandleSecretSpawns = function(run)
  local room = run.CurrentRoom
  local bases = GetIdsByType({Name='ChallengeSwitchBase'})
  local function setupShop(kind)
    local base = RemoveRandomValue(bases)
    local obj = copy(ObstacleData[kind])
    obj.ObjectId = base
    room[kind] = obj
    SetupObstacle(obj)
    SetAnimation({DestinationId=base,Name=kind..'Locked'})
    UseableOn({Id=base})
    return obj
  end
  if not IsEmpty(bases) and IsWellShopEligible(run,room) then
    room.ForceWellShop = true
    setupShop('WellShop')
    run.LastWellShopDepth = run.RunDepthCache
  end
  if not IsEmpty(bases) and IsSellTraitShopEligible(room) then
    room.ForceSellShop = true
    setupShop('SellTraitShop')
    GenerateSellTraitShop(room)
  end
  if not IsEmpty(bases) and IsSurfaceShopEligible(run,room) then
    room.ForceSurfaceShop = true
    setupShop('SurfaceShop')
  end
  if not IsEmpty(bases) then unrelatedChallenges = unrelatedChallenges + 1 end
  SetupHarvestPoints(room)
  if room.AnomalyDoorChanceSuccess then room.DoAnomalies = true end
end
UseWellShop = function(item)
  assert(CurrentRun.CurrentRoom.Store.StoreOptions[1].Cost == 30)
  CurrentRun.Hero.Money = CurrentRun.Hero.Money - item.Cost
  nativePurchases = nativePurchases + 1
end
ShowSurfaceShopScreen = UseWellShop
OpenSellTraitMenu = function()
  local room=CurrentRun.CurrentRoom
  assert(room.SellOptions and #room.SellOptions > 0)
  nativeSellMenus = nativeSellMenus + 1
end
local nativeCreateFacility = CreateRoom
CreateRoom = function(data,args)
  local room = nativeCreateFacility(data,args)
  room.WellShopChanceSuccess = RandomChance(room.WellShopSpawnChance or RoomData.BaseRoom.WellShopSpawnChance)
  room.SurfaceShopChanceSuccess = RandomChance(room.SurfaceShopSpawnChance or RoomData.BaseRoom.SurfaceShopSpawnChance)
  room.SellShopChanceSuccess = RandomChance(room.SellShopSpawnChance or 0)
  room.ExitsUnlocked = true
  room.ActiveEncounters = {}
  return room
end
