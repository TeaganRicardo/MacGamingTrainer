import subprocess
import tempfile
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
LUA = require_lua52('gathering generation native owner')
PREFIX = (ROOT / 'tests/fixtures/hades2/gathering_room_model.lua').read_text()
HARNESS = PREFIX + r'''
GameState.WeaponsUnlocked = { ToolPickaxe = true, ToolShovel = true, ToolExorcismBook = true, ToolFishingRod = true }
ResourceData = { PlantFMoly = {}, OreFSilver = {}, SeedMystery = {}, MemPointsCommon = {}, FishFCommon = {} }
local definitions = {
 flora = { point = 'HarvestPoint', num = 'NumHarvestPoints', cache = 'HarvestPointChoicesIds', allowed = 'HarvestPointsAllowed', usable = 'UseableHarvestPoint', callback = 'UseHarvestPoint', resource = 'PlantFMoly' },
 mining = { point = 'PickaxePoint', num = 'NumPickaxePoints', cache = 'PickaxePointChoices', flag = 'PickaxePointSuccess', allowed = 'PickaxePointsAllowed', usable = 'UseablePickaxePoint', tool = 'ToolPickaxe', callback = 'UsePickaxePoint', data = 'PickaxePointData', resource = 'OreFSilver' },
 digging = { point = 'ShovelPoint', num = 'NumShovelPoints', cache = 'ShovelPointChoices', flag = 'ShovelPointSuccess', allowed = 'ShovelPointsAllowed', usable = 'UseableShovelPoint', tool = 'ToolShovel', callback = 'UseShovelPoint', resource = 'SeedMystery' },
 shades = { point = 'ExorcismPoint', num = 'NumExorcismPoints', cache = 'ExorcismPointChoices', flag = 'ExorcismPointSuccess', allowed = 'ExorcismPointsAllowed', usable = 'UseableExorcismPoint', tool = 'ToolExorcismBook', callback = 'UseExorcismPoint', data = 'ExorcismData', used = 'ExorcismPointUsed', resource = 'MemPointsCommon' },
 fishing = { point = 'FishingPoint', num = 'NumFishingPoints', cache = 'FishingPointChoices', flag = 'FishingPointSuccess', allowed = 'FishingPointsAllowed', usable = 'UseableFishingPoint', tool = 'ToolFishingRod', callback = 'UseFishingPoint', used = 'FishingPointUsed', resource = 'FishFCommon' },
}
HarvestData.WeightedOptions = { { Weight = 1, AddResources = { PlantFMoly = 1 } }, { Weight = 1, ConsumableName = 'Mixer6CommonDrop' } }
PickaxePointData.WeightedOptions = { { Weight = 1, MaxHealth = 3, ResourceName = 'OreFSilver' } }
ShovelPointData.WeightedOptions = { { Weight = 1, AddResources = { SeedMystery = 1 } } }
ExorcismData.WeightedOptions = { { Weight = 1, Animation = 'Shade', AddResources = { MemPointsCommon = 1 } } }
FishingData.BiomeFish = { Defaults = { { Name = 'FishFCommon' } } }; FishingData.FishValues = { FishFCommon = {} }
ObstacleData = {}; RoomData = {}
local inactive, activated, faultAfterActivation, setupCalls = {}, {}, false, 0
local complexAllowed = true
local function reset()
  CurrentRun.CurrentRoom = { Name = 'AuthoredRoom', RoomSetName = 'F' }; CurrentRun.BiomeHarvestPointsSeen = {}
  MapState = { ActiveObstacles = {}, RoomRequiredObjects = {} }; inactive = {}; activated = {}
  local nextId = 100
  for family, definition in pairs(definitions) do
    nextId = nextId + 1; local id = nextId; inactive[definition.point] = { id }
    CurrentRun.CurrentRoom[definition.num] = 0
    ObstacleData[definition.point] = { Name = definition.point, OnUsedFunctionName = definition.callback }
    _G[definition.callback] = function(object)
      assert(MapState.ActiveObstacles[object.ObjectId] == object and not object.Used)
      object.Used = true; if definition.used then CurrentRun.CurrentRoom[definition.used] = true end
      -- Native collection calls the existing resource owner, including its multiplier.
      AddResource(definition.resource, 1, definition.point)
    end
  end
end
AddResource = function(name, amount) GameState.Resources[name] = (GameState.Resources[name] or 0) + amount end
SpendResource = function(name, amount) GameState.Resources[name] = (GameState.Resources[name] or 0) - amount end
HasAccessToTool = function(tool) return GameState.WeaponsUnlocked[tool] or HasFamiliarTool(tool) end
IsComplexHarvestAllowed = function() return complexAllowed end
IsUseable = function(args) local object = MapState.ActiveObstacles[args.Id]; return object and not object.Used and not object.Unusable end
GetInactiveIdsByType = function(args) return copy(inactive[args.Name] or {}) end
GetRandomValueFromWeightedList = function(weights) return next(weights) end
GetRandomEligibleValueFromWeightedList = function(options, args)
  for _, option in ipairs(options) do if IsGameStateEligible(option, option.GameStateRequirements, args) then return option end end
end
Activate = function(args) activated[args.Id] = true end
SetupObstacle = function(object)
  MapState.ActiveObstacles[object.ObjectId] = object; object.Health = object.MaxHealth
  if faultAfterActivation then error('native failure after activation') end
end
OverwriteTableKeys = function(target, values) for key, value in pairs(values) do target[key] = value end end
ChangeDrawGroup = function() end; SetGeometry = function() end; SetAnimation = function() end
RestoreMapStateObject = function() end; CreateAnimation = function() end
ExorcismGenerateMoveSequence = function(object) object.MoveSequence = { 1 } end
ExorcismPointChosenPresentation = function() end
GetCurrentFishingBiomeName = function() return CurrentRun.CurrentRoom.RoomSetName end
SetupHarvestPoints = function(room)
  setupCalls = setupCalls + 1
  assert(room == CurrentRun.CurrentRoom, 'generation replaced authoritative room')
  for family, definition in pairs(definitions) do
    local selected = definition.flag and room[definition.flag] or not definition.flag and (room.HarvestPointsAllowed or 0) > 0
    if selected and not (definition.used and room[definition.used]) then
      local id = room[definition.cache] and room[definition.cache][1]
      if id and not MapState.ActiveObstacles[id] then
        local object = copy(ObstacleData[definition.point]); object.ObjectId = id
        if family == 'flora' then OverwriteTableKeys(object, HarvestData.WeightedOptions[room.HarvestPointChoicesOptions[1]])
        elseif definition.data then
          local chosenKey = family == 'mining' and 'ChosenPickaxePointData' or 'ChosenExorcismPointData'
          room[chosenKey] = room[chosenKey] or GetRandomEligibleValueFromWeightedList(_G[definition.data].WeightedOptions, { RoomSetName = room.RoomSetName })
          OverwriteTableKeys(object, room[chosenKey])
        end
        Activate({ Id = id }); SetupObstacle(object)
        room[definition.num] = room[definition.num] + 1; room[definition.usable] = true
        if family ~= 'flora' then CurrentRun.BiomeHarvestPointsSeen[definition.point] = 1 end
        if family == 'shades' then ExorcismGenerateMoveSequence(object) end
      end
    end
  end
end
GetConfigOptionValue = function() return false end
IsEmpty = function(values) return next(values) == nil end
RemoveRandomValue = function(values) return table.remove(values, 1) end
reset()
local state = M.dispatch('status', { includeCatalogs = false })
assert(state.gatheringTargets and state.gatheringTargets.flora.available, 'no observed flora Generate target')
local token = state.gatheringTargets.flora.scopeToken
local reply = M.dispatch('generate_gathering', { requestId = 'flora-one', family = 'flora', scopeToken = token, includeCatalogs = false })
assert(reply.actionOutcome == 'completed' and CurrentRun.CurrentRoom.NumHarvestPoints == 1)
local object = MapState.ActiveObstacles[CurrentRun.CurrentRoom.HarvestPointChoicesIds[1]]
assert(object.OnUsedFunctionName == 'UseHarvestPoint' and IsUseable({ Id = object.ObjectId }) and object.AddResources.PlantFMoly == 1)
_G[object.OnUsedFunctionName](object)
assert(GameState.Resources.PlantFMoly == 1, 'native collection did not grant resources')
local duplicate = M.dispatch('generate_gathering', { requestId = 'flora-one', family = 'flora', scopeToken = token, includeCatalogs = false })
assert(duplicate.duplicate and duplicate.actionOutcome == 'completed' and setupCalls == 1, 'duplicate resurrected collected point')
print('gathering_generation_ok')
'''


def run(code):
    with tempfile.TemporaryDirectory(prefix='mgt-gathering-generation-') as temporary:
        harness = Path(temporary) / 'generation.lua'; harness.write_text(code)
        result = subprocess.run([LUA, str(harness), str(ROOT / 'Backend/games/hades2/runtime/hades.lua'),
                                 str(RESIDENT_DISPATCH_CONTRACT)], text=True, capture_output=True, timeout=30)
        if result.returncode:
            print(result.stdout, result.stderr)
            raise SystemExit(result.returncode)
        assert 'gathering_generation_ok' in result.stdout


BASE = HARNESS.split("local state = M.dispatch")[0]
CASES = [HARNESS]
CASES.append(BASE + r'''
for family, definition in pairs(definitions) do
  reset()
  local state = M.dispatch('status', { includeCatalogs = false })
  local target = state.gatheringTargets[family]
  assert(target.available, family .. ' unavailable')
  local reply = M.dispatch('generate_gathering', { requestId = 'all-' .. family, family = family, scopeToken = target.scopeToken, includeCatalogs = false })
  assert(reply.actionOutcome == 'completed' and CurrentRun.CurrentRoom[definition.num] == 1)
  local object = MapState.ActiveObstacles[CurrentRun.CurrentRoom[definition.cache][1]]
  assert(object.Name == definition.point and IsUseable({ Id = object.ObjectId }))
  _G[object.OnUsedFunctionName](object)
  assert(GameState.Resources[definition.resource] == 1, family .. ' did not use native collection')
  assert(not M.dispatch('status', { includeCatalogs = false }).gatheringTargets[family].available)
  local before = setupCalls
  assert(not pcall(M.dispatch, 'generate_gathering', { requestId = 'again-' .. family, family = family, scopeToken = target.scopeToken }))
  assert(setupCalls == before)
end
print('gathering_generation_ok')
''')
CASES.append(BASE + r'''
for family, definition in pairs(definitions) do
  reset(); familiar = definition.tool or 'ToolHarvest'
  assert(not M.dispatch('status', { includeCatalogs = false }).gatheringTargets[family].available, family .. ' linked Familiar missing was accepted')
  MapState.FamiliarUnit = {}
  assert(not M.dispatch('status', { includeCatalogs = false }).gatheringTargets[family].available, 'incomplete Familiar native unit accepted')
  MapState.FamiliarUnit = { ObjectId = 50 }
  assert(M.dispatch('status', { includeCatalogs = false }).gatheringTargets[family].available)
end
familiar = nil; reset(); complexAllowed = false
for _, family in ipairs({ 'flora', 'mining', 'digging' }) do assert(M.dispatch('status', { includeCatalogs = false }).gatheringTargets[family].available, 'universal combat lock added') end
for _, family in ipairs({ 'shades', 'fishing' }) do assert(not M.dispatch('status', { includeCatalogs = false }).gatheringTargets[family].available) end
complexAllowed = true; ScreenAnchors.LavaVignetteId = 7
assert(not M.dispatch('status', { includeCatalogs = false }).gatheringTargets.fishing.available)
ScreenAnchors.LavaVignetteId = nil
for family, definition in pairs(definitions) do
 reset(); local target = M.dispatch('status', { includeCatalogs = false }).gatheringTargets[family]
 MapState = { ActiveObstacles = {} }
 assert(not pcall(M.dispatch, 'generate_gathering', { requestId = 'stale-' .. family, family = family, scopeToken = target.scopeToken }))
 assert(setupCalls == 0 and M.requests['stale-' .. family] == nil)
end
print('gathering_generation_ok')
''')
CASES.append(BASE + r'''
reset()
local room = CurrentRun.CurrentRoom
room.HarvestPointsAllowed = 4; room.ShovelPointSuccess = true; room.ExorcismPointSuccess = nil; room.FishingPointSuccess = false
local target = M.dispatch('status', { includeCatalogs = false }).gatheringTargets.mining
faultAfterActivation = true
local activateOwner = Activate
local ok, errorText = pcall(M.dispatch, 'generate_gathering', { requestId = 'partial', family = 'mining', scopeToken = target.scopeToken, includeCatalogs = false })
assert(not ok and tostring(errorText):find('MGT_OUTCOME_UNKNOWN'))
assert(M.terminalActionUnknown and M.lastActionReceipt.outcome == 'outcome_unknown')
assert(room.HarvestPointsAllowed == 4 and room.ShovelPointSuccess == true and room.ExorcismPointSuccess == nil and room.FishingPointSuccess == false, 'unrelated mask leaked')
assert(Activate == activateOwner and MapState.ActiveObstacles[room.PickaxePointChoices[1]], 'partial native result removed')
assert(not pcall(M.dispatch, 'set_gathering_probabilities', { probabilities = { flora = 100 } }), 'new request passed unknown boundary')
assert(not pcall(M.dispatch, 'generate_gathering', { requestId = 'different', family = 'flora', scopeToken = 'new' }))
print('gathering_generation_ok')
''')
CASES.append(BASE + r'''
reset(); local room = CurrentRun.CurrentRoom
local target = M.dispatch('status', { includeCatalogs = false }).gatheringTargets.flora
local nativeSetup = SetupHarvestPoints
SetupHarvestPoints = function() error('before activation') end
local reply = M.dispatch('generate_gathering', { requestId = 'known', family = 'flora', scopeToken = target.scopeToken, includeCatalogs = false })
assert(reply.actionOutcome == 'failed' and not M.terminalActionUnknown and room.HarvestPointsAllowed == nil and room.HarvestPointChoicesIds == nil and room.HarvestPointChoicesOptions == nil)
SetupHarvestPoints = nativeSetup
assert(M.dispatch('status', { includeCatalogs = false }).gatheringTargets.flora.available)
print('gathering_generation_ok')
''')
CASES.append(BASE + r'''
for _, mutate in ipairs({
 function() CurrentRun.CurrentRoom = copy(CurrentRun.CurrentRoom) end,
 function() CurrentRun.Hero = copy(CurrentRun.Hero) end,
 function() SessionState = {} end,
 function() HarvestData.WeightedOptions[1].AddResources.PlantFMoly = 2 end,
 function() inactive.HarvestPoint = {} end,
 function() MapState.HostilePolymorph = true end,
}) do
 reset(); MapState.HostilePolymorph = nil; HarvestData.WeightedOptions[1].AddResources.PlantFMoly = 1
 local target = M.dispatch('status', { includeCatalogs = false }).gatheringTargets.flora
 local before = setupCalls
 mutate()
 assert(not pcall(M.dispatch, 'generate_gathering', { requestId = 'stale-' .. tostring(mutate), family = 'flora', scopeToken = target.scopeToken }))
 assert(setupCalls == before, 'stale owner activated native placement')
end
print('gathering_generation_ok')
''')
CASES.append(BASE + r'''
for family, definition in pairs(definitions) do
 reset()
 local saved = _G[definition.callback]; _G[definition.callback] = nil
 assert(not M.dispatch('status', { includeCatalogs = false }).gatheringTargets[family].available, 'missing native callback accepted')
 _G[definition.callback] = saved
 if definition.tool then GameState.WeaponsUnlocked[definition.tool] = nil; assert(not M.dispatch('status', { includeCatalogs = false }).gatheringTargets[family].available); GameState.WeaponsUnlocked[definition.tool] = true end
 for _, blocked in ipairs({ function() CurrentRun.CurrentRoom[definition.num] = 1 end,
   function() CurrentRun.CurrentRoom[definition.cache] = { 999 } end,
   function() MapState.ActiveObstacles[999] = { Name = definition.point, Used = true } end }) do
   reset(); blocked(); assert(not M.dispatch('status', { includeCatalogs = false }).gatheringTargets[family].available)
 end
end
reset(); HarvestData.WeightedOptions = { { Weight = 1, ConsumableName = 'Mixer6CommonDrop' } }
assert(not M.dispatch('status', { includeCatalogs = false }).gatheringTargets.flora.available, 'Darkness consumable masqueraded as Flora')
reset(); FishingData.BiomeFish.Defaults[1].GameStateRequirements = { allow = false }
assert(not M.dispatch('status', { includeCatalogs = false }).gatheringTargets.fishing.available, 'fishing ignored native fish pool requirements')
print('gathering_generation_ok')
''')
CASES.append(BASE + r'''
reset(); ResourceDisplayOrderData = { 'PlantFMoly', 'OreFSilver', 'SeedMystery', 'MemPointsCommon', 'FishFCommon' }
M.dispatch('set_feature', { feature = 'resourceMultiplier', value = 3 })
M.dispatch('set_feature', { feature = 'resourceMultiplierEnabled', value = true })
for family, definition in pairs(definitions) do
 reset()
 local target = M.dispatch('status', { includeCatalogs = false }).gatheringTargets[family]
 M.dispatch('generate_gathering', { requestId = 'multiply-' .. family, family = family, scopeToken = target.scopeToken, includeCatalogs = false })
 local object = MapState.ActiveObstacles[CurrentRun.CurrentRoom[definition.cache][1]]
 _G[object.OnUsedFunctionName](object)
 assert(GameState.Resources[definition.resource] == 3, family .. ' bypassed existing native resource multiplier owner')
end
print('gathering_generation_ok')
''')
CASES.append(BASE + r'''
reset()
local room = CurrentRun.CurrentRoom
for family, definition in pairs(definitions) do
 local target = M.dispatch('status', { includeCatalogs = false }).gatheringTargets[family]
 assert(target.available)
 local reply = M.dispatch('generate_gathering', { requestId = 'same-room-' .. family, family = family, scopeToken = target.scopeToken, includeCatalogs = false })
 assert(reply.actionOutcome == 'completed' and CurrentRun.CurrentRoom == room)
end
local count = 0; for _, object in pairs(MapState.ActiveObstacles) do count = count + 1; assert(IsUseable({ Id = object.ObjectId })) end
assert(count == 5 and setupCalls == 5, 'five families did not retain independent native objects')
print('gathering_generation_ok')
''')
CASES.append(BASE + r'''
reset()
local target = M.dispatch('status', { includeCatalogs = false }).gatheringTargets.flora
IsUseable = function() return false end
local ok, errorText = pcall(M.dispatch, 'generate_gathering', { requestId = 'unusable-native-object', family = 'flora', scopeToken = target.scopeToken, includeCatalogs = false })
assert(not ok and tostring(errorText):find('MGT_OUTCOME_UNKNOWN') and M.lastActionReceipt.outcome == 'outcome_unknown', 'visual-only prop falsely completed')
assert(next(MapState.ActiveObstacles) ~= nil and M.terminalActionUnknown, 'partial unusable native result erased')
print('gathering_generation_ok')
''')
CASES.append(BASE + r'''
reset()
WaitForFishingInput = function() error('auto minigame bypass lost') end
ExorcismSequence = function() return false end
M.dispatch('set_feature', { feature = 'autoMiniGames', value = true })
local nativeFishCollection, nativeShadeCollection = UseFishingPoint, UseExorcismPoint
UseFishingPoint = function(object)
 CurrentRun.Hero.FishingState = 'Success'; CurrentRun.Hero.FishingInput = nil
 WaitForFishingInput({})
 assert(CurrentRun.Hero.FishingInput, 'native fishing success window not respected')
 return nativeFishCollection(object)
end
UseExorcismPoint = function(object)
 assert(ExorcismSequence(object, ExorcismData, {}, CurrentRun.Hero), 'native exorcism sequence not delegated')
 return nativeShadeCollection(object)
end
for _, family in ipairs({ 'fishing', 'shades' }) do
 local definition = definitions[family]
 local target = M.dispatch('status', { includeCatalogs = false }).gatheringTargets[family]
 M.dispatch('generate_gathering', { requestId = 'auto-' .. family, family = family, scopeToken = target.scopeToken, includeCatalogs = false })
 local object = MapState.ActiveObstacles[CurrentRun.CurrentRoom[definition.cache][1]]
 _G[object.OnUsedFunctionName](object)
 assert(GameState.Resources[definition.resource] == 1, 'native minigame collection reward not retained')
end
print('gathering_generation_ok')
''')
CASES.append(BASE + r'''
reset(); MapState.HostilePolymorph = true
for family in pairs(definitions) do
 local target = M.dispatch('status', { includeCatalogs = false }).gatheringTargets[family]
 assert(not target.available and target.reason == 'hades2.gathering.unavailable.polymorph', 'native polymorph owner bypassed')
end
assert(setupCalls == 0)
reset(); local target = M.dispatch('status', { includeCatalogs = false }).gatheringTargets.flora
local nativeSetup = SetupHarvestPoints
SetupHarvestPoints = function(room) nativeSetup(room); MapState.HostilePolymorph = true end
local ok, errorText = pcall(M.dispatch, 'generate_gathering', { requestId = 'polymorph-after-activation', family = 'flora', scopeToken = target.scopeToken, includeCatalogs = false })
assert(not ok and tostring(errorText):find('MGT_OUTCOME_UNKNOWN') and M.terminalActionUnknown and next(MapState.ActiveObstacles) ~= nil, 'postactivation polymorph falsely completed or removed native result')
print('gathering_generation_ok')
''')
for code in CASES:
    run(code)
print('hades2_gathering_generation_ok')
