-- Native challenge branch: typed encounter options, original switch and callbacks.
RoomData.BaseRoom.ChallengeSpawnChance = 0.2
RoomData.BaseRoom.ChallengeSpawnRequirements = {allow=true}
RoomData.BaseRoom.TimeChallengeSwitchRequirements = {allow=true}
RoomData.BaseRoom.PerfectClearSwitchRequirements = {allow=true}
RoomData.BaseRoom.EliteSwitchRequirements = {allow=true}
ObstacleData.ChallengeSwitch = {OnUsedFunctionName='AttemptUseChallengeSwitch'}
ObstacleData.TimeChallengeSwitch_Money = {
  Name='TimeChallengeSwitch_Money', OnUsedFunctionName='AttemptUseChallengeSwitch',
  EncounterOptionsName='TimeChallengeEncounterOptions', RewardType='Money',
  ChallengeSwitchUseFunctionName='UseChallengeSwitch',
  ChallengeAvailableUseText='UseChallengeSwitch_Unlocked', UnlockedAnimationName='TimeChallengeUnlocked',
}
ObstacleData.PerfectClearChallengeSwitch_Pom = {
  Name='PerfectClearChallengeSwitch_Pom', OnUsedFunctionName='AttemptUseChallengeSwitch',
  EncounterOptionsName='PerfectClearEncounterOptions', RewardType='StackUpgrade',
  ChallengeSwitchUseFunctionName='UseChallengeSwitch',
  ChallengeAvailableUseText='UseChallengeSwitch_Unlocked', UnlockedAnimationName='PerfectClearUnlocked',
}
ObstacleData.EliteChallengeSwitch_Talent = {
  Name='EliteChallengeSwitch_Talent', OnUsedFunctionName='AttemptUseChallengeSwitch',
  EncounterOptionsName='EliteChallengeEncounterOptions', RewardType='TalentDrop',
  ChallengeSwitchUseFunctionName='UseChallengeSwitch',
  ChallengeAvailableUseText='UseChallengeSwitch_Unlocked', UnlockedAnimationName='EliteChallengeUnlocked',
}
EncounterSets = {
  TimeChallengeOptions={'TimeChallengeSwitch_Money'},
  PerfectClearOptions={'PerfectClearChallengeSwitch_Pom'},
  EliteChallengeOptions={'EliteChallengeSwitch_Talent'},
}
EncounterData={
 TimeChallengeF={Name='TimeChallengeF',StartingValue=100,Generated=true},
 PerfectClearChallengeF={Name='PerfectClearChallengeF',StartingValue=1,Generated=false},
 EliteChallengeF={Name='EliteChallengeF',StartingValue=1,Generated=true},
}
local nativeChallengeGen, nativeChallengeUses, nativeRewards = 0, 0, 0
local forcedUses = {}
-- A native force may have been granted for a *later* room. A direct
-- one-shot challenge must not consume it while borrowing the spawn owner.
local forcedTraits = {
  ForceChallengeSwitch = true,
  ForcePerfectClearSwitch = true,
  ForceEliteSwitch = true,
}
local baseHandleSecretSpawns = HandleSecretSpawns
IsTimeChallengeForced = function(room) return room.ForceChallengeSwitch or false end
IsPerfectClearChallengeForced = function(room) return room.ForcePerfectClearSwitch or false end
IsEliteChallengeForced = function(room) return room.ForceEliteSwitch or false end
UseHeroTraitsWithValue = function(name, consume)
 forcedUses[name] = (forcedUses[name] or 0) + 1
 if consume then forcedTraits[name] = false end
end
GetRandomValue = function(list) assert(type(list)=='table'); return list[1] end
GenerateEncounter = function(run,room,encounter) nativeChallengeGen=nativeChallengeGen+1 end
IsHorizontallyFlipped = function() return false end
Attach = function() end
CreateTextBox = function() end
ModifyTextBox = function() end
GetRunDepth = function(run) return run.RunDepthCache end
round = function(number) return math.floor(number+.5) end
RandomInt = function(a,b) return a end
SetThingProperty = function() end
local originalSpawn = SpawnObstacle
SpawnObstacle = function(args)
  nativeChallengeGen = nativeChallengeGen + 1
  return 500 + nativeChallengeGen
end
local originalShopHSS = HandleSecretSpawns
HandleSecretSpawns = function(run)
  local room=run.CurrentRoom
  -- In this fixture the shop/secret portion executes first, but all three
  -- shop eligibility callbacks are masked by the native one-shot owner.
  originalShopHSS(run)
  local baseIds=GetIdsByType({Name='ChallengeSwitchBase'})
  if IsEmpty(baseIds) or not IsGameStateEligible(room,
      room.ChallengeSpawnRequirements or RoomData.BaseRoom.ChallengeSpawnRequirements) then return end
  local candidates={}
  local candidatesByFamily = {
   {'TimeChallengeOptions','TimeChallengeSwitchRequirements','IsTimeChallengeForced','ForceChallengeSwitch'},
   {'PerfectClearOptions','PerfectClearSwitchRequirements','IsPerfectClearChallengeForced','ForcePerfectClearSwitch'},
   {'EliteChallengeOptions','EliteSwitchRequirements','IsEliteChallengeForced','ForceEliteSwitch'},
  }
  for _,family in ipairs(candidatesByFamily) do
    local pool,req,force,forcedTrait=table.unpack(family)
    if IsGameStateEligible(room,room[req] or RoomData.BaseRoom[req]) then
      if room.ChallengeChanceSuccess or _G[force](room) then
        UseHeroTraitsWithValue(forcedTrait,true)
        for _,name in pairs(EncounterSets[pool]) do
          local def=ObstacleData[name]
          if def and (def.Requirements==nil or IsGameStateEligible(def,def.Requirements)) then
            candidates[#candidates+1]=name
          end
        end
      end
    end
  end
  if IsEmpty(candidates) then return end
  local selected=GetRandomValue(candidates)
  local object=copy(ObstacleData[selected])
  object.ObjectId=RemoveRandomValue(baseIds)
  room.ChallengeSwitch=object
  local encounterName=GetRandomValue(room[object.EncounterOptionsName])
  local encounter=copy(EncounterData[encounterName])
  if encounter.Generated then GenerateEncounter(run,room,encounter) end
  room.ChallengeEncounter=encounter
  encounter.Switch=object
  encounter.SpawnNearId=object.ObjectId
  SetupObstacle(object)
  SetAnimation({DestinationId=object.ObjectId,Name='LockedChallenge'})
  UseableOn({Id=object.ObjectId})
  run.LastChallengeDepth=run.RunDepthCache
end
UseChallengeSwitch = function(object)
  assert(object.ReadyToUse and object.ChallengeSwitchUseFunctionName=='UseChallengeSwitch')
  return true
end
AttemptUseChallengeSwitch = function(object)
 local room=CurrentRun.CurrentRoom
 assert(room.ChallengeSwitch==object and IsUseable({Id=object.ObjectId}))
 room.ChallengeEncounter.InProgress=true
 nativeChallengeUses=nativeChallengeUses+1
end
CompleteChallenge = function()
 local room=CurrentRun.CurrentRoom
 assert(room.ChallengeEncounter.InProgress)
 room.ChallengeEncounter.InProgress=false
 room.ChallengeEncounter.Completed=true
 nativeRewards=nativeRewards+1
end
