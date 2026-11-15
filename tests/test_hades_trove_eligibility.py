"""Hades I trove eligibility and clean unsupportedRuntime transport handling."""
from pathlib import Path
import subprocess
import sys
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
sys.path.insert(0, str(ROOT / 'tests'))

from core.adapter import AdapterError
from games.hades.lldb_worker import lua_literal
from games.hades.world import runtime_definitions
from lua_runtime_support import require_lua52

lua = require_lua52('Hades trove eligibility regression')
harness = r'''
local handleSecretSpawnCalls = 0
local forceNilSpawn = false
local forceRaiseUnsupported = false
local function clone(value)
  if type(value) ~= "table" then return value end
  local result = {}
  for k, v in pairs(value) do result[k] = clone(v) end
  return result
end
DeepCopyTable = clone
SaveIgnores = {}
GameState = { Resources = {}, LifetimeResourcesGained = {}, Cosmetics = {} }
CurrentRun = {
  Hero = { ObjectId = 10, Health = 50, MaxHealth = 50, Traits = {} },
  Money = 0,
  BiomeDepthCache = 1,
  RoomCreations = {},
  CurrentRoom = {
    Name = "A_Combat01",
    RoomSetName = "Tartarus",
    ChallengeEncounterName = "TimeChallengeTartarus",
    ChallengeChanceSuccess = true,
  },
}
RoomSetData = { Tartarus = {} }
EncounterSets = {
  ChallengeOptions = { "MoneyChallengeSwitch" },
}
ObstacleData = {
  MoneyChallengeSwitch = {
    Name = "MoneyChallengeSwitch",
    UnlockedAnimationName = "TroveReady",
    ChallengeAvailableUseText = "UseTrove",
    Requirements = { RequiredCosmetics = { "ChallengeSwitches1" } },
  },
}
EncounterData = {
  TimeChallengeTartarus = { Name = "TimeChallengeTartarus" },
}
function IsGameStateEligible(run, source, requirements)
  local req = requirements or source
  if type(req) ~= "table" then return true end
  if req.RequiredCosmetics then
    for _, name in ipairs(req.RequiredCosmetics) do
      if not (GameState.Cosmetics and GameState.Cosmetics[name]) then return false end
    end
  end
  return true
end
function ChooseChallengeEncounter(room)
  assert(room.ChallengeEncounterName and EncounterData[room.ChallengeEncounterName])
  return clone(EncounterData[room.ChallengeEncounterName])
end
function IsChallengeSwitchEligible(run, numPedestals)
  local room = run.CurrentRoom
  if numPedestals ~= nil then
    local reserved = 0
    if room.ForceWellShop then reserved = reserved + 1 end
    if room.ForceSellTraitShop then reserved = reserved + 1 end
    if numPedestals <= reserved then return false end
  end
  return room.ChallengeChanceSuccess == true
end
function IsWellShopEligible() return false end
function IsSellTraitShopEligible() return false end
function IsSecretDoorEligible() return false end
function IsShrinePointDoorEligible() return false end
function IsFishingEligible() return false end
function HasHeroTraitValue() return false end
function UseHeroTraitsWithValue() end
function CheckRoomExitsReady() return true end
function RefreshUseButton() end
function SetAnimation() end
OfferedExitDoors = {}
function GetIdsByType(args)
  if args.Name == "ChallengeSwitchBase" then return CurrentRun.CurrentRoom._pedestals or { 801 } end
  return {}
end
function GetInactiveIdsByType() return {} end
function GetRandomValue(values) return values[1] end
function HandleSecretSpawns(run)
  handleSecretSpawnCalls = handleSecretSpawnCalls + 1
  local room = run.CurrentRoom
  local points = GetIdsByType({ Name = "ChallengeSwitchBase" })
  if #points > 0 and IsChallengeSwitchEligible(run, #points) then
    room.ForceChallengeSwitch = true
    if forceRaiseUnsupported then error("hades.error.unsupportedRuntime") end
    local options = {}
    for _, name in pairs(EncounterSets.ChallengeOptions) do
      local data = ObstacleData[name]
      if data.Requirements == nil or IsGameStateEligible(CurrentRun, data, data.Requirements) then
        options[#options + 1] = name
      end
    end
    if #options > 0 and not forceNilSpawn then
      local encounter = ChooseChallengeEncounter(room)
      room.ChallengeEncounter = encounter
      room.ChallengeSwitch = clone(ObstacleData[options[1]])
      room.ChallengeSwitch.ObjectId = points[1]
    end
  end
end

local runtime = assert(loadfile(RUNTIME))()
runtime.worldDefinitions = DEFINITIONS
local status = runtime.status()
local world = function() return runtime.status().world end
local function contains(list, target)
  for _, value in ipairs(list or {}) do if value == target then return true end end
  return false
end
local function fails(needle, fn)
  local ok, err = pcall(fn)
  assert(not ok, "expected failure containing " .. needle)
  assert(tostring(err):find(needle, 1, true), "unexpected error: " .. tostring(err))
end

-- 1. Fresh save without House Contractor ChallengeSwitches1: trove must not be
-- offered and direct generation must fail cleanly without entering HandleSecretSpawns.
assert(not contains(world().objects, "trove"), "trove offered before ChallengeSwitches1 unlocked")
local roomId = world().roomId
fails("hades.error.worldUnavailable", function()
  runtime.generate_chamber_object({ roomId = roomId, object = "trove" })
end)
assert(handleSecretSpawnCalls == 0, "locked trove entered HandleSecretSpawns")
assert(CurrentRun.CurrentRoom.ForceChallengeSwitch == nil, "locked trove mutated ForceChallengeSwitch")

-- 2. Even after ChallengeSwitches1 is unlocked, a room with no valid
-- ChallengeEncounterName must omit trove and fail upfront without HandleSecretSpawns.
GameState.Cosmetics.ChallengeSwitches1 = true
CurrentRun.CurrentRoom.ChallengeEncounterName = nil
assert(not contains(world().objects, "trove"), "trove offered without ChallengeEncounterName")
fails("hades.error.worldUnavailable", function()
  runtime.generate_chamber_object({ roomId = roomId, object = "trove" })
end)
assert(handleSecretSpawnCalls == 0, "room without ChallengeEncounterName entered HandleSecretSpawns")

-- 3. An unspawned ForceWellShop reserve consumes the sole pedestal, whereas an
-- already-spawned WellShop with one free pedestal still allows trove.
CurrentRun.CurrentRoom.ChallengeEncounterName = "TimeChallengeTartarus"
CurrentRun.CurrentRoom._pedestals = { 801 }
CurrentRun.CurrentRoom.ForceWellShop = true
assert(not contains(world().objects, "trove"), "trove offered on a pedestal reserved for unspawned WellShop")
fails("hades.error.worldUnavailable", function()
  runtime.generate_chamber_object({ roomId = roomId, object = "trove" })
end)
assert(handleSecretSpawnCalls == 0)
CurrentRun.CurrentRoom._pedestals = { 801, 802 }
CurrentRun.CurrentRoom.WellShop = { ObjectId = 801 }
assert(contains(world().objects, "trove"), "already-spawned WellShop blocked second free pedestal")

-- 4. An unexpected post-HandleSecretSpawns nil object must not claim unsupportedRuntime
-- ("No change was made") after HandleSecretSpawns already mutated room state.
forceNilSpawn = true
fails("hades.error.outcomeUnknown", function()
  runtime.generate_chamber_object({ roomId = roomId, object = "trove" })
end)
assert(handleSecretSpawnCalls == 1)

-- 5. Valid unlocked room offers and spawns trove cleanly.
forceNilSpawn = false
CurrentRun.CurrentRoom.ForceChallengeSwitch = nil
CurrentRun.CurrentRoom.ChallengeSwitch = nil
assert(contains(world().objects, "trove"))
runtime.generate_chamber_object({ roomId = roomId, object = "trove" })
assert(CurrentRun.CurrentRoom.ChallengeSwitch and CurrentRun.CurrentRoom.ChallengeSwitch.ObjectId == 802)

-- 6. Pre-mutation checks keep unsupportedRuntime while post-mutation failures raise outcomeUnknown.
local savedResources = GameState.Resources
GameState.Resources = nil
fails("hades.error.unsupportedRuntime", function()
  runtime.set_resource("MetaPoints", 10)
end)
GameState.Resources = savedResources

CurrentRun.CurrentRoom.ForceChallengeSwitch = nil
CurrentRun.CurrentRoom.ChallengeSwitch = nil
forceRaiseUnsupported = true
fails("hades.error.outcomeUnknown", function()
  runtime.generate_chamber_object({ roomId = roomId, object = "trove" })
end)
forceRaiseUnsupported = false

local savedInvulnerable = SetPlayerInvulnerable
SetPlayerInvulnerable = nil
fails("hades.error.outcomeUnknown", function()
  runtime.set_feature("invincibility", true)
end)
SetPlayerInvulnerable = savedInvulnerable
print("hades_trove_eligibility_lua_ok")
'''
harness = harness.replace('RUNTIME', lua_literal(str(ROOT / 'Backend/games/hades/runtime.lua')))
harness = harness.replace('DEFINITIONS', lua_literal(runtime_definitions()))
result = subprocess.run([lua, '-'], input=harness, text=True, capture_output=True)
assert result.returncode == 0, result.stdout + result.stderr
assert 'hades_trove_eligibility_lua_ok' in result.stdout

# Clean pre-mutation hades.error.unsupportedRuntime must raise runtime_not_ready
# without tainting the transport, whereas hades.error.outcomeUnknown must taint.
fake_lldb = types.SimpleNamespace(
    SBError=lambda: types.SimpleNamespace(Fail=lambda: False, Success=lambda: True),
    eStateStopped=5, eStateRunning=6, eStateExited=10,
    ePermissionsReadable=1, ePermissionsWritable=2,
)
with patch.dict(sys.modules, {'lldb': fake_lldb}), patch('subprocess.check_output', return_value=''):
    from games.hades import transport as module


class Options:
    def __getattr__(self, name):
        return lambda *args: None


def make_transport(error_text):
    transport = module.HadesLuaTransport.__new__(module.HadesLuaTransport)
    transport.pid = 42
    transport._tainted_pid = None
    transport._unsafe_vm_pid = None
    transport.focus_original = None
    transport._cleanup_pending = False
    transport._cleanup_failure = None
    transport.addresses = {
        name: idx + 100
        for idx, name in enumerate((
            '_ZN3sgg13ConfigOptions20RequireFocusToUpdateE',
            '_ZN3sgg3App6UpdateEf',
            'lua_gettop', 'luaL_loadbufferx', 'lua_pcallk', 'lua_tolstring', 'lua_settop',
        ))
    }
    transport.alive = lambda: True
    transport._stop = lambda deadline: None
    transport._resume = lambda deadline, **kwargs: None
    transport._restore_focus = lambda: None
    transport.target = types.SimpleNamespace(DeleteAllBreakpoints=lambda: None)
    frame = types.SimpleNamespace(
        EvaluateExpression=lambda *args: types.SimpleNamespace(
            GetError=lambda: types.SimpleNamespace(Fail=lambda: False),
            GetValueAsSigned=lambda: 2,
        )
    )
    transport._boundary = lambda: (types.SimpleNamespace(GetFrameAtIndex=lambda i: frame), 123)
    transport.process = types.SimpleNamespace(
        AllocateMemory=lambda *args: 1000,
        WriteMemory=lambda addr, payload, err: len(payload),
        ReadCStringFromMemory=lambda output, cap, err: error_text,
        DeallocateMemory=lambda addr: None,
    )
    return transport


with patch.object(module.lldb, 'SBExpressionOptions', Options, create=True), \
        patch.object(module.lldb, 'eLanguageTypeC_plus_plus', 4, create=True):
    clean_transport = make_transport('runtime.lua:232: hades.error.unsupportedRuntime')
    try:
        clean_transport.execute('return "{}"', mutating=True)
    except AdapterError as error:
        assert error.code == 'runtime_not_ready', f'expected runtime_not_ready, got {error.code}'
        assert error.presentation == 'hades.error.unsupportedRuntime', error.presentation
    else:
        raise AssertionError('unsupportedRuntime unexpectedly succeeded')
    assert clean_transport.tainted is False, 'clean unsupportedRuntime tainted the target'

    for wrapped_error in (
        'runtime.lua:2299: hades.error.outcomeUnknown',
        'runtime.lua:2323: hades.error.outcomeUnknown: runtime.lua:101: hades.error.unsupportedRuntime',
    ):
        uncertain_transport = make_transport(wrapped_error)
        try:
            uncertain_transport.execute('return "{}"', mutating=True)
        except AdapterError as error:
            assert error.code == 'outcome_unknown', f'expected outcome_unknown, got {error.code}'
            assert error.presentation == 'hades.error.outcomeUnknown', error.presentation
        else:
            raise AssertionError('outcomeUnknown unexpectedly succeeded')
        assert uncertain_transport.tainted is True

print('hades_trove_eligibility_and_unsupported_runtime_ok')
