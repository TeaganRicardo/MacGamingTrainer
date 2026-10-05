import subprocess
import tempfile
from pathlib import Path

from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]
LUA = require_lua52('gathering probability room owner')

HARNESS = (ROOT / 'tests/fixtures/hades2/gathering_room_model.lua').read_text() + r'''set({ mining = 0 })
local result = CreateRoom({ Name = 'Zero', HasPickaxePoint = true }, {})
assert(not result.PickaxePointSuccess, 'controlled zero leaked through native inclusive draw==0')
print('gathering_probability_ok')
'''


def run(code):
    with tempfile.TemporaryDirectory(prefix='mgt-gathering-probability-') as temporary:
        harness = Path(temporary) / 'room.lua'
        harness.write_text(code)
        result = subprocess.run([LUA, str(harness), str(ROOT / 'Backend/games/hades2/runtime/hades.lua'),
                                 str(RESIDENT_DISPATCH_CONTRACT)], text=True, capture_output=True, timeout=30)
        if result.returncode:
            print(result.stdout, result.stderr)
            raise SystemExit(result.returncode)
        assert 'gathering_probability_ok' in result.stdout


CASES = {'controlled_zero': HARNESS}
PREFIX = HARNESS.split('set({ mining = 0 })')[0]
CASES['all_boundaries_familiar_and_native_quota'] = PREFIX + r'''
for family, definition in pairs(families) do
  for _, case in ipairs({ { 0, 0, false }, { 0, 100, true }, { 1, 100, true }, { .25, 25, true }, { .250001, 25, false } }) do
    draw, familiar, bonus = case[1], definition.tool or definition.data.ToolName, .2
    set({ [family] = case[2] })
    local room = { Name = family, [definition.has] = true }
    local before = draws
    assert(successful(CreateRoom(room, {}), family) == case[3], family .. ' conditional probability mismatch')
    assert(draws - before == (family == 'flora' and 2 or 1), 'native RNG trial count changed')
  end
  if definition.data then
    draw, familiar, bonus = 0, nil, 0
    set({ [family] = 100 })
    CurrentRun.BiomeHarvestPointsSeen[definition.data.HarvestPointName] = 1
    local room = { Name = family, [definition.has] = true }
    assert(not successful(CreateRoom(room, {}), family), 'quota refusal passed zero draw')
    familiar = definition.data.ToolName
    assert(successful(CreateRoom(room, {}), family), 'native familiar +1 quota lost')
    CurrentRun.BiomeHarvestPointsSeen[definition.data.HarvestPointName] = 2
    assert(not successful(CreateRoom(room, {}), family))
    room.IgnoreHarvestBiomeSpawnLimit = true
    assert(successful(CreateRoom(room, {}), family))
    room[definition.data.RoomChanceName] = 0
    assert(not successful(CreateRoom(room, {}), family), 'structural room exclusion overwritten')
    CurrentRun.BiomeHarvestPointsSeen = {}
  end
end
print('gathering_probability_ok')
'''
CASES['default_forces_exclusions_arbitration_and_private_inputs'] = PREFIX + r'''
set({})
assert(CreateRoom == nativeCreate and GetHarvestPointSpawnChance == nativeChance, 'Native defaults installed a needless hook')
local default = { Name = 'Default', HasHarvestPoint = true, HasPickaxePoint = true, PickaxePointChance = 0 }
assert(CreateRoom(default, {}).PickaxePointSuccess == true, 'default changed native inclusive-zero behavior')
set({ flora = 0, mining = 0, digging = 0 })
local forced = { Name = 'Forced', HasHarvestPoint = true, HasPickaxePoint = true, HasShovelPoint = true,
 HarvestPointForceRequirements = {}, PickaxePointForceRequirements = {}, ShovelPointForceRequirements = {} }
local result = CreateRoom(forced, {})
assert(result.HarvestPointsAllowed == 1 and result.PickaxePointSuccess and result.ShovelPointSuccess, 'native force lost')
set({ flora = 100, mining = 100, digging = 100, shades = 100, fishing = 100 })
for family, definition in pairs(families) do
  local input = { Name = family, [definition.has] = true }
  CurrentRun.ActiveBounty = 'Bounty'; assert(not successful(CreateRoom(input, {}), family)); CurrentRun.ActiveBounty = nil
  CurrentRun.IsDreamRun = true; assert(not successful(CreateRoom(input, {}), family)); CurrentRun.IsDreamRun = nil
  local key = family == 'flora' and 'HarvestPointRequirements' or definition.data.HarvestPointName .. 'Requirements'
  input[key] = { allow = false }; assert(not successful(CreateRoom(input, {}), family))
end
local all = { Name = 'Arbitration', HasShovelPoint = true, HasPickaxePoint = true, HasExorcismPoint = true, HasFishingPoint = true, AllowOnlyOneToolHarvestableResource = true }
local result = CreateRoom(all, {}); local count = 0
for _, data in ipairs(tools) do if result[data.HarvestPointName .. 'Success'] then count = count + 1 end end
assert(count == 1, 'controlled probabilities bypassed native cross-family arbitration')
familiar, bonus = 'ToolHarvest', .2
local input = { Name = 'Overrides', HasHarvestPoint = true, HarvestPointChances = { .3, .1 } }
local overrides = { HarvestPointChances = { .4, .2, .1 } }; local args = { RoomOverrides = overrides }
assert(CreateRoom(input, args).HarvestPointsAllowed == 3)
assert(input.HarvestPointChances[1] == .3 and overrides.HarvestPointChances[1] == .4 and args.RoomOverrides == overrides)
assert(CurrentRun.CurrentRoom.Name == 'Existing', 'room-generation owner changed authoritative current room')
for key in pairs(result) do assert(not tostring(key):find('Trainer') and key ~= 'probabilities') end
fault = true; assert(not pcall(CreateRoom, input, args)); fault = false
assert(GetHarvestPointSpawnChance(PickaxePointData, { Name = 'OutsideFrame' }) == .2, 'exception leaked private probability frame')
local foreign = function() return 'foreign' end; CreateRoom = foreign
M.dispatch('cleanup', {})
assert(CreateRoom == foreign and GetHarvestPointSpawnChance == nativeChance, 'cleanup overwrote a foreign room hook')
print('gathering_probability_ok')
'''
CASES['early_native_owner_and_args_output'] = PREFIX + r'''
set({ flora = 50 })
familiar = 'ToolHarvest'
local getterCalls = 0
GetTotalHeroTraitValue = function()
  getterCalls = getterCalls + 1
  assert(type(CurrentRun.Hero.Traits) == 'table', 'extra early familiar getter without native Hero traits')
  return .2
end
CurrentRun.Hero.Traits = nil
for _, input in ipairs({ { Name = 'NoHarvest' },
 { Name = 'Forced', HasHarvestPoint = true, HarvestPointForceRequirements = {} },
 { Name = 'Ineligible', HasHarvestPoint = true, HarvestPointRequirements = { allow = false } } }) do
  assert(pcall(CreateRoom, input, {}), 'controlled flora broke a native early-return owner')
end
CurrentRun.ActiveBounty = 'Bounty'; assert(pcall(CreateRoom, { Name = 'Bounty', HasHarvestPoint = true }, {})); CurrentRun.ActiveBounty = nil
CurrentRun.IsDreamRun = true; assert(pcall(CreateRoom, { Name = 'Dream', HasHarvestPoint = true }, {})); CurrentRun.IsDreamRun = nil
assert(getterCalls == 0)
CurrentRun.Hero.Traits = {}; familiar = nil
local args = { RoomOverrides = { HarvestPointChances = { .1 } } }
CreateRoom({ Name = 'Output', ForcedRewardStore = 'NativeStore', HasHarvestPoint = true }, args)
assert(args.RewardStoreName == 'NativeStore' and args.RoomOverrides.HarvestPointChances[1] == .1,
  'private args lost the native RewardStoreName output or rewrote overrides')
print('gathering_probability_ok')
'''
CASES['session_new_run_and_terminal_native_pass'] = PREFIX + r'''
set({ mining = 0 })
local oldRun = CurrentRun
CurrentRun = { Hero = { Traits = {} }, BiomeHarvestPointsSeen = {} }
assert(not CreateRoom({ Name = 'FirstNewRun', HasPickaxePoint = true }, {}).PickaxePointSuccess, 'first room lost accepted durable probability')
assert(M.run == oldRun, 'room hook adopted a run without synchronization')
local ownedSession = SessionState
SessionState = {}
assert(CreateRoom({ Name = 'ForeignSession', HasPickaxePoint = true }, {}).PickaxePointSuccess, 'foreign session was controlled')
SessionState = ownedSession
M.terminalActionUnknown = true
assert(CreateRoom({ Name = 'Unknown', HasPickaxePoint = true }, {}).PickaxePointSuccess, 'unknown action still controlled new room')
assert(M.run == oldRun, 'unknown action adopted another run')
print('gathering_probability_ok')
'''
CASES['native_random_eligibility_decides_once'] = PREFIX + r'''
local eligibilityChecks = 0
IsGameStateEligible = function(_, requirements)
 eligibilityChecks = eligibilityChecks + 1
 if requirements and requirements.ChanceToPlay then return RandomChance(requirements.ChanceToPlay) end
 return not requirements or requirements.allow ~= false
end
set({ flora = 50 }); familiar, bonus, draw = 'ToolHarvest', .2, .4
local before = draws
local room = CreateRoom({ Name = 'NativeRandomRequirements', HasHarvestPoint = true, HarvestPointRequirements = { ChanceToPlay = .5 } }, {})
assert(room.HarvestPointsAllowed == 2 and eligibilityChecks == 1, 'Flora evaluated native random eligibility twice')
assert(draws - before == 3, 'probability override added a native eligibility RNG draw')
print('gathering_probability_ok')
'''
for code in CASES.values():
    run(code)
print('hades2_gathering_probability_ok')
