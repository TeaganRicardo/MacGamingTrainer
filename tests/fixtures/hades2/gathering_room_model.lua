
SessionState = {}; SessionMapState = {}
GameState = { Resources = {}, LifetimeResourcesGained = {}, RunHistory = {}, LootPickups = {} }
ResourceData = {}; ResourceDisplayOrderData = {}; TraitElementData = {}; TraitData = {}
LootData = {}; ConsumableData = {}; RewardStoreData = {}; ScreenData = {}
MapState = { RoomRequiredObjects = {}, ActiveObstacles = {} }; LootObjects = {}
CodexOrdering = { OlympianGods = {}, Order = {} }; ActiveScreens = {}; ScreenAnchors = {}; ScreenState = {}
UpdateTimers = function() end
CurrentRun = { Hero = { ObjectId = 1, Health = 100, MaxHealth = 100, Mana = 50, MaxMana = 50,
  Traits = {}, TraitDictionary = {}, Elements = {}, BoonData = {} }, CurrentRoom = { Name = 'Existing' },
  BiomeHarvestPointsSeen = {}, NumRerolls = 10, PickedTraits = {}, BannedTraits = {} }
local function copy(value)
  if type(value) ~= 'table' then return value end
  local result = {}; for key, item in pairs(value) do result[key] = copy(item) end; return result
end
DeepCopyTable = copy; ShallowCopyTable = copy
local draw, draws, familiar, bonus, fault = 0, 0, nil, 0, false
RandomChance = function(chance) draws = draws + 1; return draw <= chance end
HasFamiliarTool = function(tool) return familiar == tool end
GetTotalHeroTraitValue = function(key) return key == 'FamiliarResourceBonusChance' and bonus or 0 end
IsGameStateEligible = function(_, requirements) if fault then error('native room fault') end; return not requirements or requirements.allow ~= false end
HarvestData = { DefaultSpawnChances = { .2, .1 }, DefaultGameStateRequirements = {} }
ShovelPointData = { ToolName = 'ToolShovel', HarvestPointName = 'ShovelPoint', RoomChanceName = 'ShovelPointChance', SpawnChance = .2, SpawnLimitPerBiome = 1 }
PickaxePointData = { ToolName = 'ToolPickaxe', HarvestPointName = 'PickaxePoint', RoomChanceName = 'PickaxePointChance', SpawnChance = .2, SpawnLimitPerBiome = 1 }
ExorcismData = { ToolName = 'ToolExorcismBook', HarvestPointName = 'ExorcismPoint', RoomChanceName = 'ExorcismPointChance', SpawnChance = .2, SpawnLimitPerBiome = 1 }
FishingData = { ToolName = 'ToolFishingRod', HarvestPointName = 'FishingPoint', RoomChanceName = 'FishingPointChance', SpawnChance = .2, SpawnLimitPerBiome = 1 }
local tools = { ShovelPointData, PickaxePointData, ExorcismData, FishingData }
GetHarvestPointSpawnChance = function(data, room)
  local hasFamiliar = HasFamiliarTool(data.ToolName)
  local limit = data.SpawnLimitPerBiome + (hasFamiliar and 1 or 0)
  if not room.IgnoreHarvestBiomeSpawnLimit and (CurrentRun.BiomeHarvestPointsSeen[data.HarvestPointName] or 0) >= limit then return 0 end
  if room[data.RoomChanceName] == 0 then return 0 end
  return (room[data.RoomChanceName] or data.SpawnChance) + (hasFamiliar and bonus or 0)
end
local nativeChance = GetHarvestPointSpawnChance
CreateRoom = function(roomData, args)
  args = args or {}; args.RewardStoreName = args.RewardStoreName or roomData.ForcedRewardStore or 'RunProgress'
  local room = copy(roomData)
  for key, value in pairs(args and args.RoomOverrides or {}) do room[key] = value end
  room.HarvestPointsAllowed = 0
  if not CurrentRun.ActiveBounty and not CurrentRun.IsDreamRun then
    if room.HasHarvestPoint then
      if room.HarvestPointForceRequirements and IsGameStateEligible(room, room.HarvestPointForceRequirements) then room.HarvestPointsAllowed = 1
      elseif IsGameStateEligible(room, room.HarvestPointRequirements) then
        for _, chance in ipairs(room.HarvestPointChances or HarvestData.DefaultSpawnChances) do
          if RandomChance(chance + (HasFamiliarTool('ToolHarvest') and bonus or 0)) then room.HarvestPointsAllowed = room.HarvestPointsAllowed + 1 end
        end
      end
    end
    local successes = 0
    for _, data in ipairs(tools) do
      local prefix = data.HarvestPointName
      if room['Has' .. prefix] and IsGameStateEligible(room, room[prefix .. 'Requirements']) then
        local forced = room[prefix .. 'ForceRequirements'] and IsGameStateEligible(room, room[prefix .. 'ForceRequirements'])
        room[prefix .. 'Success'] = forced or RandomChance(GetHarvestPointSpawnChance(data, room))
        if room[prefix .. 'Success'] then successes = successes + 1 end
      end
    end
    if room.AllowOnlyOneToolHarvestableResource and successes > 1 then
      local kept = false
      for _, data in ipairs(tools) do local key = data.HarvestPointName .. 'Success'; if room[key] then if kept then room[key] = false else kept = true end end end
    end
  end
  return room
end
local nativeCreate = CreateRoom
dofile(assert(arg[1])); dofile(assert(arg[2]))
local M = __MacGamingTrainerV1
local function set(values) return M.dispatch('set_gathering_probabilities', { probabilities = values, includeCatalogs = false }) end
local families = {
 flora = { has = 'HasHarvestPoint', result = 'HarvestPointsAllowed', tool = 'ToolHarvest' },
 mining = { has = 'HasPickaxePoint', result = 'PickaxePointSuccess', data = PickaxePointData },
 digging = { has = 'HasShovelPoint', result = 'ShovelPointSuccess', data = ShovelPointData },
 shades = { has = 'HasExorcismPoint', result = 'ExorcismPointSuccess', data = ExorcismData },
 fishing = { has = 'HasFishingPoint', result = 'FishingPointSuccess', data = FishingData },
}
local function successful(room, family) local value = room[families[family].result]; return value == true or type(value) == 'number' and value > 0 end
