-- Exact supported-build room reward stand owner (RoomLogic.lua:5037-5067).
-- This fixture is loaded after chamber_facility_room_model.lua, before resident.
RoomData.BaseRoom.MetaRewardStandSpawnChance = 0.1
RoomData.BaseRoom.MetaRewardStandRequirements = {allow=true}
ObstacleData.MetaRewardStand = {
  Name='MetaRewardStand',OnUsedFunctionName='AttemptUseChallengeSwitch',
  ChallengeSwitchUseFunctionName='UseMetaRewardStand',
  UseText='UseMetaRewardStand_Locked',
  AvailableUseText='UseMetaRewardStand_Unlocked',
  RequiredShrinePoints=12,
  RewardIconScale=1.0,
  ExitsUnlockedFunctionName='HarvestPointAvailablePresentation',
  ExitsUnlockedFunctionArgs={SkipVoiceLines=true},
}
ResourceData.CardUpgradePoints={
  Name='CardUpgradePoints',MetaRewardStandPickupSound='BountyClaim',
}
ResourceData.FamiliarPoints={
  Name='FamiliarPoints',MetaRewardStandPickupSound='BountyClaim',
}
MetaRewardStandData = {
 WeightedOptions={
  {Name='CardUpgradePoints',Animation='CardUpgradePointsDrop',Amount=1,Weight=1},
  {Name='FamiliarPoints',Animation='FamiliarPointsDrop',Amount=1,Weight=1},
 }
}
GameState.SpentShrinePointsCache=12
local nativeRewardSpawns, nativeRewardClaims, nativeRewardDisplays = 0, 0, 0
local nativeRewardPresentations=0
CallFunctionName=function(name,object,args)
 assert(name=='HarvestPointAvailablePresentation' and object.Name=='MetaRewardStand')
 assert(type(args)=='table' and args.SkipVoiceLines)
 nativeRewardPresentations=nativeRewardPresentations+1
end
local originalShopsHandle=HandleSecretSpawns
IsMetaRewardStandEligible=function(run,room)
 if room.ForceMetaRewardStand then return true end
 -- roomData is global and is assigned on the game's OnAnyLoad callback.
 local requirements=roomData.MetaRewardStandRequirements
   or RoomData.BaseRoom.MetaRewardStandRequirements
 return IsGameStateEligible(room,requirements) and room.MetaRewardStandSuccess==true
end
GetRandomEligibleValueFromWeightedList=function(options)
 for _,reward in ipairs(options) do
  if not reward.GameStateRequirements
      or IsGameStateEligible(reward,reward.GameStateRequirements) then return reward end
 end
end
SpawnObstacle=function(args)
 nativeRewardDisplays=nativeRewardDisplays+1
 local id=800+nativeRewardDisplays
 MapState.ActiveObstacles[id]={Name=args.Name,ObjectId=id}
 return id
end
SetScale=function() end
Attach=function() end
SetThingProperty=function() end
StopAnimation=function() end
IsAlive=function(args) return MapState.ActiveObstacles[args.Id]~=nil end
HandleSecretSpawns=function(run)
 originalShopsHandle(run)
 local currentRoom=run.CurrentRoom
 local bases=GetIdsByType({Name='ChallengeSwitchBase'})
 if not IsEmpty(bases) and IsMetaRewardStandEligible(run,currentRoom) then
  currentRoom.ForceMetaRewardStand=true
  local base=RemoveRandomValue(bases)
  local object=copy(ObstacleData.MetaRewardStand)
  object.ObjectId=base
  SetupObstacle(object)
  SetAnimation({DestinationId=base,Name='MetaRewardStandLocked'})
  currentRoom.MetaRewardStand=object
  local reward=GetRandomEligibleValueFromWeightedList(MetaRewardStandData.WeightedOptions)
  local visual=SpawnObstacle({Name='BlankObstacle',DestinationId=base,Group='Standing'})
  SetAnimation({DestinationId=visual,Name=reward.Animation})
  CreateAnimation({Name='MetaRewardStandItemShadow',DestinationId=visual})
  SetScale({Id=visual,Fraction=object.RewardIconScale})
  Attach({Id=visual,DestinationId=base,OffsetY=-30,OffsetZ=100})
  SetThingProperty({Property='SortMode',Value='FromParent',DestinationId=visual})
  UseableOn({Id=base})
  object.ResourceData=ResourceData[reward.Name]
  object.RewardAmount=reward.Amount
  object.DisplayItemId=visual
  if GameState.SpentShrinePointsCache<object.RequiredShrinePoints then
   object.UseText='UseMetaRewardStand_LockedByShrine'
   object.CannotUseText='MetaRewardStandBlockedByShrine'
  end
  run.LastMetaRewardStandDepth=run.RunDepthCache
  nativeRewardSpawns=nativeRewardSpawns+1
 end
end
UseMetaRewardStand=function(object)
 assert(object.ReadyToUse and IsUseable({Id=object.ObjectId}))
 assert(GameState.SpentShrinePointsCache>=object.RequiredShrinePoints)
 local key=object.ResourceData.Name
 GameState.Resources[key]=(GameState.Resources[key] or 0)+object.RewardAmount
 MapState.ActiveObstacles[object.DisplayItemId]=nil
 activeUsable[object.ObjectId]=false
 nativeRewardClaims=nativeRewardClaims+1
end
