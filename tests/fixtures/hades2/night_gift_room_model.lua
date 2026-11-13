-- Actual-data-shaped I/Q Gift of Night owner, joined to the existing native
-- challenge fixture before resident initialization.
RoomData.BaseRoom.MetaRewardStandSpawnChance = 0.10
RoomData.BaseRoom.MetaRewardStandRequirements = {allow = true}
RoomData.I_Gift = { Name="I_Gift", RoomSetName="I", MetaRewardStandSpawnChance=.3,
 WellShopSpawnChance=0,
 MetaRewardStandRequirements={allow=true} }
RoomData.Q_Gift = { Name="Q_Gift", RoomSetName="Q", MetaRewardStandSpawnChance=.5,
 WellShopSpawnChance=0,
 MetaRewardStandRequirements={allow=true} }
ObstacleData.MetaRewardStand = {
 Name='MetaRewardStand', OnUsedFunctionName='AttemptUseChallengeSwitch',
 ChallengeSwitchUseFunctionName='UseMetaRewardStand',
 UseText='UseMetaRewardStand_Locked',
 AvailableUseText='UseMetaRewardStand_Unlocked',
 RequiredShrinePoints=12, RewardIconScale=1,
 ExitsUnlockedFunctionName='HarvestPointAvailablePresentation',
}
ResourceData = ResourceData or {}
ResourceData.NightCard = {Name='NightCard',MetaRewardStandPickupSound='/SFX/NightCard'}
ResourceData.NightWeapon = {Name='NightWeapon',MetaRewardStandPickupSound='/SFX/NightWeapon'}
MetaRewardStandData = {WeightedOptions={
  {Name='NightCard',Animation='NightCardDrop',Amount=1,Weight=1},
  {Name='NightWeapon',Animation='NightWeaponDrop',Amount=1,Weight=1},
}}
GameState.SpentShrinePointsCache = 12
local nativeGiftClaims,nativeGiftDisplays,nativeGiftUnlocks = 0,0,0
local nativeMetaChoice = 0
IsMetaRewardStandEligible = function(run,room)
 if room.ForceMetaRewardStand then return true end
 return room.MetaRewardStandSuccess
   and IsGameStateEligible(room, roomData.MetaRewardStandRequirements or RoomData.BaseRoom.MetaRewardStandRequirements)
end
GetRandomEligibleValueFromWeightedList = function(options)
 nativeMetaChoice=nativeMetaChoice+1
 for _, entry in ipairs(options) do
   if entry.Weight > 0 and (not entry.GameStateRequirements
       or IsGameStateEligible(entry,entry.GameStateRequirements)) then return entry end
 end
end
local priorSpawn=SpawnObstacle
SpawnObstacle=function(args)
 if args.Name=='BlankObstacle' then nativeGiftDisplays=nativeGiftDisplays+1; return 600+nativeGiftDisplays end
 return priorSpawn(args)
end
SetScale=function() end
StopAnimation=function() end
CallFunctionName=function(name,obj,args)
 nativeGiftUnlocks=nativeGiftUnlocks+1
end
UseableOff=function(args) activeUsable[args.Id]=false end
UseMetaRewardStand=function(object)
 assert(object.ReadyToUse and object.ResourceData.Name and object.DisplayItemId)
 assert(IsUseable({Id=object.ObjectId}))
 nativeGiftClaims=nativeGiftClaims+1
 GameState.NightCardsClaimed=(GameState.NightCardsClaimed or 0)+object.RewardAmount
 UseableOff({Id=object.ObjectId})
end
local previousHandleSecretSpawns=HandleSecretSpawns
HandleSecretSpawns=function(run)
 previousHandleSecretSpawns(run)
 local room=run.CurrentRoom
 local baseIds=GetIdsByType({Name='ChallengeSwitchBase'})
 if IsEmpty(baseIds) or not IsMetaRewardStandEligible(run,room) then return end
 room.ForceMetaRewardStand=true
 local stand=copy(ObstacleData.MetaRewardStand)
 stand.ObjectId=RemoveRandomValue(baseIds)
 SetupObstacle(stand)
 SetAnimation({DestinationId=stand.ObjectId,Name='MetaRewardStandLocked'})
 room.MetaRewardStand=stand
 local reward=GetRandomEligibleValueFromWeightedList(MetaRewardStandData.WeightedOptions)
 local displayId=SpawnObstacle({Name='BlankObstacle',DestinationId=stand.ObjectId})
 SetAnimation({DestinationId=displayId,Name=reward.Animation})
 CreateAnimation({Name='MetaRewardStandItemShadow',DestinationId=displayId})
 SetScale({Id=displayId,Fraction=stand.RewardIconScale})
 Attach({Id=displayId,DestinationId=stand.ObjectId,OffsetY=-30,OffsetZ=100})
 SetThingProperty({Property='SortMode',Value='FromParent',DestinationId=displayId})
 UseableOn({Id=stand.ObjectId})
 stand.ResourceData=ResourceData[reward.Name]
 stand.RewardAmount=reward.Amount
 stand.DisplayItemId=displayId
 if GameState.SpentShrinePointsCache < stand.RequiredShrinePoints then
  stand.UseText='UseMetaRewardStand_LockedByShrine'
  stand.CannotUseText='MetaRewardStandBlockedByShrine'
  stand.ExitsUnlockedFunctionName=nil
 end
 run.LastMetaRewardStandDepth=run.RunDepthCache
end
local priorGiftCreate=CreateRoom
CreateRoom=function(data,args)
 local room=priorGiftCreate(data,args)
 room.MetaRewardStandSuccess=RandomChance(room.MetaRewardStandSpawnChance or
   RoomData.BaseRoom.MetaRewardStandSpawnChance)
 return room
end
