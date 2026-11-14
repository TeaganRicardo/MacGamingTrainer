"""Native-shaped boon editing, yielding menu teardown and synthetic save reload.

The fixture preserves the supported game's RemoveWeaponTrait/RemoveTraitData,
AddTraitData and CloseScreen call order at the ownership seam. Native rendering
and disk persistence are represented here; actual game save/load acceptance is
separate. No captured or real user save paths are read by this test.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
sys.path.insert(0, str(ROOT / 'tests'))

from core.adapter import AdapterError
from core.sidecar import SidecarTerminalError
from games.hades.client import HadesRuntimeClient
from games.hades.lldb_worker import HadesLLDBWorker, error_payload, lua_literal
from games.hades.recovery import HadesRecoveryJournal
from games.hades.save_document import HadesSaveDocument, HadesSaveHeader, LuaTable
from lua_runtime_support import require_lua52

LUA = require_lua52('Hades boon edit lifecycle')
FIXTURE = r'''
local fixture = { removals = 0, additions = 0, closes = 0, ticks = 0 }
_threads, _workingThreads = {}, {}
_worldTime, _screenTime = 0, 0
SaveIgnores = {}
for _, name in ipairs({ '_G', 'coroutine', 'table', 'string', 'math', 'io', 'os',
    'debug', 'package', 'bit32', 'SaveIgnores', 'TraitData', 'PresetEventArgs',
    'ScreenAnchors', 'LootData', '_saveData', '_threads', '_workingThreads' }) do SaveIgnores[name] = true end
local function copy(value)
  if type(value) ~= 'table' then return value end
  local result = {}
  for key, item in pairs(value) do result[key] = copy(item) end
  return result
end
local function assertSerializable(value, seen)
  local kind = type(value)
  assert(kind ~= 'function' and kind ~= 'thread' and kind ~= 'userdata',
    'transient native or Trainer closure entered the save')
  if kind ~= 'table' then return end
  assert(not seen[value], 'cyclic runtime state entered the save')
  seen[value] = true
  for key, item in pairs(value) do assertSerializable(key, seen); assertSerializable(item, seen) end
  seen[value] = nil
end
-- Main.lua:1008-1035 selects eligible globals before luabins serializes them.
function Save()
  local selected = {}
  for key, value in pairs(_G) do
    local kind = type(value)
    if value ~= nil and not SaveIgnores[key] and kind ~= 'function'
        and kind ~= 'userdata' and kind ~= 'thread' then selected[key] = value end
  end
  assertSerializable(selected, {})
  _saveData = copy(selected)
end
GameState = { Resources = {}, RunHistory = {} }
CurrentRun = { Hero = { ObjectId = 42, Health = 50, MaxHealth = 50,
  Traits = {}, TraitDictionary = {}, IncomingDamageModifiers = {}, OutgoingDamageModifiers = {}, Weapons = {} },
  Money = 25, NumRerolls = 3, CurrentRoom = { Name = 'A_Shop01' } }
PresetEventArgs = { PatroclusBenefitChoices = {} }
TraitData = {
  TrapDamageTrait = { Name = 'TrapDamageTrait',
    RarityLevels = { Common = {}, Rare = {}, Epic = {}, Heroic = {} },
    AddIncomingDamageModifiers = { TrapDamageTakenMultiplier = 0.4 } },
  SiblingTrait = { Name = 'SiblingTrait', RarityLevels = { Common = {}, Heroic = {} } },
  AddedTrait = { Name = 'AddedTrait', RarityLevels = { Common = {}, Rare = {} } },
  ZeusWeaponTrait = { Name = 'ZeusWeaponTrait', Slot = 'Melee', RarityLevels = { Common = {} } },
  SwordDoubleDashAttackTrait = { Name = 'SwordDoubleDashAttackTrait', RequiredWeapon = 'SwordWeapon',
    AddOutgoingDamageModifiers = { ValidWeaponMultiplier = 1.2 } },
  TemporaryTrait = { Name = 'TemporaryTrait', RemainingUses = 3, RarityLevels = { Common = {} } },
  CooldownTrait = { Name = 'CooldownTrait', CurrentCooldown = 0, RoomCooldown = 3,
    RarityLevels = { Common = {} } },
  ChaosBlessingTrapDamageTrait = { Name = 'ChaosBlessingTrapDamageTrait', RarityLevels = { Common = {}, Epic = {} } },
  ChaosCurseTrapDamageTrait = { Name = 'ChaosCurseTrapDamageTrait', RarityLevels = { Common = {}, Epic = {} } },
}
LootData = { TrialUpgrade = { PermanentTraits = { 'ChaosBlessingTrapDamageTrait' },
  TemporaryTraits = { 'ChaosCurseTrapDamageTrait' } } }
ScreenAnchors = {}
function wait(duration) coroutine.yield({ wait = duration }) end
function waitScreenTime(duration) coroutine.yield({ wait = duration, screenTime = true }) end
local function resumeNative(co, destination)
  local ok, value = coroutine.resume(co)
  assert(ok, value)
  if coroutine.status(co) ~= 'dead' and value and value.wait then
    table.insert(destination, { thread = co, screenTime = value.screenTime,
      resumeTime = (value.screenTime and _screenTime or _worldTime) + value.wait })
  end
end
function thread(fn, ...)
  local args = table.pack(...)
  resumeNative(coroutine.create(function() fn(table.unpack(args, 1, args.n)) end), _threads)
end
local function replaceContext(kind)
  if kind == 'room' then CurrentRun.CurrentRoom = { Name = 'A_Combat21' }
  elseif kind == 'hero' then
    CurrentRun.Hero = copy(CurrentRun.Hero)
    CurrentRun.Hero.ObjectId = 43
  elseif kind == 'menu' then ScreenAnchors.TraitTrayScreen = { CanClose = true, replacement = true }
  else error('unknown fixture context') end
end
local function tick()
  fixture.ticks = fixture.ticks + 1
  if fixture.paused then return end
  local command = MacGamingTrainerHades and MacGamingTrainerHades.traitCommand
  if fixture.stopAfterStart and command and command.state == 'running' then return end
  if fixture.replaceBeforeStart and command and command.state == 'pending' then
    replaceContext(fixture.replaceBeforeStart)
    fixture.replaceBeforeStart = nil
  end
  _worldTime, _screenTime = _worldTime + 0.1, _screenTime + 0.1
  -- Main.lua update resumes _threads into _workingThreads before swapping them.
  for _, info in pairs(_threads) do
    local now = info.screenTime and _screenTime or _worldTime
    if coroutine.status(info.thread) ~= 'dead' and info.resumeTime < now then
      resumeNative(info.thread, _workingThreads)
    else table.insert(_workingThreads, info) end
  end
  _threads, _workingThreads = _workingThreads, {}
  if fixture.replaceAfterYield and command and command.state == 'running' then
    replaceContext(fixture.replaceAfterYield)
    fixture.replaceAfterYield = nil
  end
  if fixture.expireDuringClose and command and command.state == 'running' then
    fixture.expireDuringClose = nil
    fixture.nativeExpirations = 1
    RemoveTraitData(CurrentRun.Hero, CurrentRun.Hero.TraitDictionary.TrapDamageTrait[1])
  end
  if fixture.saveEachTick and command then
    Save()
    fixture.saveSnapshots = fixture.saveSnapshots or {}
    table.insert(fixture.saveSnapshots, { menuOpen = ScreenAnchors.TraitTrayScreen ~= nil,
      state = command.state, snapshot = copy(_saveData) })
  end
end
-- UIScripts.lua:2679-2688 yields synchronously, not through a new thread.
function CloseScreen(componentIds, delay)
  if delay ~= nil and delay > 0 then wait(delay) end
  waitScreenTime(0.2)
end
-- TraitTrayScripts.lua:442-505: the caller owns this yielding teardown.
function CloseAdvancedTooltipScreen()
  if not ScreenAnchors.TraitTrayScreen or not ScreenAnchors.TraitTrayScreen.CanClose then return end
  ScreenAnchors.TraitTrayScreen.CanClose = false
  fixture.closes = fixture.closes + 1
  CloseScreen({}, 0.05)
  ScreenAnchors.TraitTrayScreen = nil
end
function AreTraitsIdentical(left, right) return left.Name == right.Name end
function UpdateHeroTraitDictionary()
  local cache = {}
  for _, trait in pairs(CurrentRun.Hero.Traits) do
    cache[trait.Name] = cache[trait.Name] or {}
    table.insert(cache[trait.Name], trait)
  end
  CurrentRun.Hero.TraitDictionary = cache
end
function GetTraitNameCount(unit, name)
  local group = unit.TraitDictionary[name]
  return group and #group or 0
end
function HeroHasTrait(name) return CurrentRun.Hero.TraitDictionary[name] ~= nil end
function GetProcessedTraitData(args)
  local trait = copy(TraitData[args.TraitName])
  trait.Rarity = args.Rarity
  if trait.AddIncomingDamageModifiers then
    trait.AddIncomingDamageModifiers.TrapDamageTakenMultiplier = args.Rarity == 'Heroic' and 0.049 or 0.4
  end
  return trait
end
-- TraitScripts.lua:1180-1221 removes the physical record, rebuilds its index,
-- then tears down the name-owned incoming damage modifier.
function RemoveTraitData(unit, selected, args)
  for index, trait in pairs(unit.Traits) do
    if trait == selected then unit.Traits[index] = nil; break end
  end
  if not (args and args.SkipUIUpdate) then UpdateHeroTraitDictionary() end
  if selected.AddIncomingDamageModifiers then
    for index, data in pairs(unit.IncomingDamageModifiers) do
      if data.Name == selected.Name then table.remove(unit.IncomingDamageModifiers, index); break end
    end
  end
  if selected.AddOutgoingDamageModifiers then
    for index, data in pairs(unit.OutgoingDamageModifiers) do
      if data.Name == selected.Name then table.remove(unit.OutgoingDamageModifiers, index); break end
    end
  end
  -- Native OnExpire.TraitData transforms through AddTraitData, without replaying
  -- the curse's full acquisition path.
  if selected.OnExpire and selected.OnExpire.TraitData then
    local nextTrait = selected.OnExpire.TraitData
    nextTrait.TraitTitle, nextTrait.Id = selected.TraitTitle, selected.Id
    AddTraitData(unit, nextTrait)
  end
end
function RemoveWeaponTrait(name)
  assert(not fixture.inExpression, 'native trait removal ran inside a debugger expression')
  fixture.removals = fixture.removals + 1
  while HeroHasTrait(name) do RemoveTraitData(CurrentRun.Hero, CurrentRun.Hero.TraitDictionary[name][1]) end
  -- TraitScripts.lua:1051-1155 rebuilds a removed attack's weapon and re-adds
  -- its dependent Hammers through AddTraitToHero before the final index update.
  if TraitData[name].Slot == 'Melee' then
    local dependents = {}
    for _, trait in pairs(CurrentRun.Hero.Traits) do
      if trait.RequiredWeapon == 'SwordWeapon' then table.insert(dependents, trait) end
    end
    for _, trait in ipairs(dependents) do RemoveTraitData(CurrentRun.Hero, trait, { SkipUIUpdate = true }) end
    for _, trait in ipairs(dependents) do AddTraitToHero({ TraitData = trait, SkipPriorityTray = true }) end
    UpdateHeroTraitDictionary()
  end
end
-- TraitScripts.lua:832-914 closes an open trait menu before adding effects.
function AddTraitData(unit, data)
  assert(not fixture.inExpression, 'native trait acquisition ran inside a debugger expression')
  if fixture.failAdd then error('fixture native add failed after removal') end
  local trait = copy(data)
  local nextIndex = 1
  while unit.Traits[nextIndex] do nextIndex = nextIndex + 1 end
  unit.Traits[nextIndex] = trait
  if ScreenAnchors.TraitTrayScreen then CloseAdvancedTooltipScreen() end
  UpdateHeroTraitDictionary()
  if trait.AddIncomingDamageModifiers then
    local modifier = copy(trait.AddIncomingDamageModifiers)
    modifier.Name = trait.Name
    table.insert(unit.IncomingDamageModifiers, modifier)
  end
  if trait.AddOutgoingDamageModifiers then
    local modifier = copy(trait.AddOutgoingDamageModifiers)
    modifier.Name = trait.Name
    table.insert(unit.OutgoingDamageModifiers, modifier)
  end
  fixture.additions = fixture.additions + 1
end
function AddTraitToHero(args)
  AddTraitData(CurrentRun.Hero, args.TraitData or GetProcessedTraitData({
    Unit = CurrentRun.Hero, TraitName = args.TraitName, Rarity = args.Rarity }))
end
function TraitUIUpdateText(trait)
  assert(not fixture.inExpression, 'native trait UI update ran inside a debugger expression')
  fixture.uiUpdates = (fixture.uiUpdates or 0) + 1
end
function IncrementTraitCooldown(trait, increment)
  assert(not fixture.inExpression, 'native cooldown refresh ran inside a debugger expression')
  trait.CurrentCooldown = math.min(trait.CurrentCooldown + increment, trait.RoomCooldown or trait.TimeCooldown)
end
function UpdateMoneyUI() end
AddTraitToHero({ TraitName = 'TrapDamageTrait', Rarity = 'Common' })
AddTraitToHero({ TraitName = 'SiblingTrait', Rarity = 'Common' })
fixture.additions = 0
function FixtureInspect()
  return MacGamingTrainerHades.json({ fixture = fixture, saved = _saveData,
    run = CurrentRun, menuOpen = ScreenAnchors.TraitTrayScreen ~= nil,
    menuReplacement = ScreenAnchors.TraitTrayScreen and ScreenAnchors.TraitTrayScreen.replacement,
    propertyDepth = MacGamingTrainerHades.propertyDepth,
    queued = #_threads,
    receipt = MacGamingTrainerHades.traitCommand and MacGamingTrainerHades.trait_command_result(
      MacGamingTrainerHades.traitCommand.id) })
end
function FixtureFailAdd() fixture.failAdd = true end
function FixtureControl(name, value) fixture[name] = value end
while true do
  local line = io.read('*l')
  if not line then break end
  local source = assert(load('return ' .. line))()
  fixture.inExpression = true
  local ok, value = pcall(assert(load(source, 'fixture-expression')))
  fixture.inExpression = false
  if ok then io.write('OK\t', value, '\n')
  else io.write('ERROR\t', tostring(value):gsub('[\r\n]', ' '), '\n') end
  io.flush()
  if ok then tick() end
end
'''


class LuaTransport:
    pid = 42

    def __init__(self):
        self.process = subprocess.Popen([LUA, '-e', FIXTURE], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.calls = 0
        self.sources = []

    def alive(self):
        return self.process.poll() is None

    def attach(self, pid, executable):
        assert pid == self.pid and executable == '/fixture/Game.macOS'

    def exchange(self, source):
        self.process.stdin.write(lua_literal(source) + '\n')
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        assert line, self.process.stderr.read()
        status, text = line.rstrip('\n').split('\t', 1)
        if status == 'ERROR':
            raise AdapterError('outcome_unknown', 'hades.error.outcomeUnknown', diagnostic=text)
        return json.loads(text)

    def execute(self, source, *, mutating):
        self.calls += 1
        self.sources.append((source, mutating))
        return self.exchange(source)

    def inspect(self, source=''):
        return self.exchange(source + '; return FixtureInspect()')

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=5)
        assert self.process.returncode == 0, self.process.stderr.read()
        self.process.stdout.close()
        self.process.stderr.close()


def lua_table(value):
    if not isinstance(value, dict):
        return value
    entries = [(int(key) if key.isdecimal() else key, lua_table(item)) for key, item in value.items()]
    return LuaTable(0, len(entries), entries)


def boon(state, name):
    return next(row for row in state['traits'] if row['name'] == name)


class WorkerSidecar:
    started = True
    terminal = False
    lose_reply = False

    def __init__(self, worker):
        self.worker = worker
        self.calls = []

    def request(self, method, params, **options):
        self.calls.append(method)
        try:
            result = self.worker.dispatch(method, params)
        except AdapterError as error:
            return {'error': error_payload(error)}
        if self.lose_reply:
            self.terminal = True
            raise SidecarTerminalError('fixture lost completed action reply', outcome_unknown=True)
        return {'result': result}

    def close(self):
        self.started = False


def reload_snapshot(saved):
    assert 'MacGamingTrainerHades' not in saved, 'resident coroutine/receipt owner leaked into native saves'
    doc = HadesSaveDocument(HadesSaveHeader(map_name='A_Shop01'), [lua_table(saved)])
    with tempfile.TemporaryDirectory(prefix='mgt-hades-boon-save-') as folder:
        target = Path(folder) / 'Profile1_Temp.sav'
        target.write_bytes(doc.to_bytes())
        loaded = HadesSaveDocument.load(target)
    return loaded.lua_state


def verify_snapshot(saved, rarity):
    hero = reload_snapshot(saved)['CurrentRun']['Hero']
    traits = list(hero['Traits'].values())
    selected = [row for row in traits if row['Name'] == 'TrapDamageTrait']
    assert len(selected) == 1 and selected[0]['Rarity'] == rarity, 'saved selected boon does not match expected ' + rarity
    assert len([row for row in traits if row['Name'] == 'SiblingTrait']) == 1
    modifiers = list(hero['IncomingDamageModifiers'].values())
    assert len(modifiers) == 1 and modifiers[0]['Name'] == 'TrapDamageTrait'
    assert modifiers[0]['TrapDamageTakenMultiplier'] == (0.049 if rarity == 'Heroic' else 0.4)
    dictionary = hero['TraitDictionary']['TrapDamageTrait']
    assert len(dictionary) == 1 and dictionary[1]['Rarity'] == rarity


def verify_saved_snapshot(transport):
    observation = transport.inspect('Save()')
    verify_snapshot(observation['saved'], 'Heroic')
    assert observation['fixture']['removals'] == 1 and observation['fixture']['additions'] == 1


for menu_open in (False, True):
    transport = LuaTransport()
    try:
        worker = HadesLLDBWorker(transport)
        before = worker.dispatch('status', {})
        if menu_open:
            transport.inspect('ScreenAnchors.TraitTrayScreen = { CanClose = true }; FixtureControl("saveEachTick",true)')
        try:
            result = worker.dispatch('update_trait', {
                'instanceId': boon(before, 'TrapDamageTrait')['instanceId'],
                'rarity': 'Heroic', 'level': 1, 'target': before['target'],
            })
        except AdapterError as error:
            raise AssertionError('valid boon edit failed across native menu teardown: ' + str(error.diagnostic)) from error
        assert boon(result, 'TrapDamageTrait')['rarity'] == 'Heroic'
        assert boon(result, 'SiblingTrait')['rarity'] == 'Common'
        verify_saved_snapshot(transport)
        snapshot = transport.inspect()
        assert not snapshot['menuOpen'] and snapshot['propertyDepth'] == 0
        if menu_open:
            during_close = [row for row in snapshot['fixture']['saveSnapshots'].values() if row['menuOpen']]
            assert len(during_close) >= 2, 'native saves did not observe both menu-close yields'
            for row in during_close:
                verify_snapshot(row['snapshot'], 'Common')
            for row in snapshot['fixture']['saveSnapshots'].values():
                if row['state'] == 'complete':
                    verify_snapshot(row['snapshot'], 'Heroic')
        command_id = snapshot['receipt']['id']
        duplicate = transport.execute('return MacGamingTrainerHades.json(MacGamingTrainerHades.submit_trait_command('
                                      + lua_literal(command_id) + ',"update_trait",{}))', mutating=True)
        assert duplicate['state'] == 'complete'
        assert transport.inspect()['fixture']['removals'] == 1
        polls = [(source, mutating) for source, mutating in transport.sources
                 if source.startswith('return MacGamingTrainerHades.json(MacGamingTrainerHades.trait_command_result(')]
        assert polls and all(not mutating for _, mutating in polls), 'receipt observation installed or replayed a command'
    finally:
        transport.close()

print('hades_boon_edit_native_menu_and_synthetic_save_reload_ok')

# Both a partially executed edit and a completed edit with a lost receipt retain
# the original recovery journal. The client must never send the one-shot again.
for partial_failure in (False, True):
    transport = LuaTransport()
    try:
        worker = HadesLLDBWorker(transport)
        sidecar = WorkerSidecar(worker)
        with tempfile.TemporaryDirectory(prefix='mgt-hades-boon-recovery-') as folder:
            journal = HadesRecoveryJournal(Path(folder) / 'request.json')
            client = HadesRuntimeClient(sidecar, recovery=journal, identity=lambda pid: 'fixture-birth')
            before = client.connect(42, '/fixture/Game.macOS')
            params = {'instanceId': boon(before, 'TrapDamageTrait')['instanceId'],
                      'rarity': 'Heroic', 'level': 1, 'target': before['target']}
            if partial_failure:
                transport.inspect('FixtureFailAdd()')
            else:
                sidecar.lose_reply = True
            try:
                client.command('update_trait', params)
            except AdapterError as error:
                assert error.code == 'outcome_unknown', error.code
            else:
                raise AssertionError('an uncertain native edit was reported as confirmed')
            assert json.loads(journal.path.read_text())['method'] == 'update_trait'
            calls = len(sidecar.calls)
            try:
                client.command('update_trait', params)
            except AdapterError as error:
                assert error.code == 'restart_required', error.code
            else:
                raise AssertionError('an unknown native boon edit was replayed')
            assert len(sidecar.calls) == calls
            state = transport.inspect()
            assert state['fixture']['removals'] == 1
            assert state['fixture']['additions'] == (0 if partial_failure else 1)
            assert state['propertyDepth'] == 0
            if not partial_failure:
                verify_saved_snapshot(transport)
    finally:
        transport.close()

print('hades_boon_edit_unknown_outcome_nonreplay_ok')


def update_params(before, **changes):
    return {'instanceId': boon(before, 'TrapDamageTrait')['instanceId'],
            'rarity': 'Heroic', 'level': 1, 'target': before['target'], **changes}


# An unstarted native command can be cancelled while the native scheduler is
# paused. A cancelled queue entry must remain a no-op after the game resumes.
transport = LuaTransport()
try:
    worker = HadesLLDBWorker(transport)
    before = worker.dispatch('status', {})
    transport.inspect('FixtureControl("paused",true)')
    clock = [0.0]
    with patch('games.hades.lldb_worker.time.monotonic', side_effect=lambda: clock[0]), \
            patch('games.hades.lldb_worker.time.sleep', side_effect=lambda seconds: clock.__setitem__(0, clock[0] + 1)):
        try:
            worker.dispatch('update_trait', update_params(before))
        except AdapterError as error:
            assert error.code == 'runtime_not_ready', error.code
        else:
            raise AssertionError('a paused, unstarted trait command was reported as completed')
    state = transport.inspect()
    assert state['receipt']['state'] == 'cancelled' and state['queued'] == 1
    command_id = state['receipt']['id']
    duplicate = transport.execute('return MacGamingTrainerHades.json(MacGamingTrainerHades.submit_trait_command('
                                  + lua_literal(command_id) + ',"update_trait",{}))', mutating=True)
    assert duplicate['state'] == 'cancelled' and transport.inspect()['queued'] == 1
    transport.inspect('FixtureControl("paused",false)')
    state = transport.inspect()
    assert state['fixture']['removals'] == 0 and state['fixture']['additions'] == 0
    assert state['queued'] == 0 and not getattr(transport, 'tainted', False)
finally:
    transport.close()

# Admission errors are still known failures: the selected group remains intact.
for changes, presentation in (({'rarity': 'Legendary'}, 'invalidValue'),
                              ({'instanceId': 'trait:departed:1'}, 'staleTrait')):
    transport = LuaTransport()
    try:
        worker = HadesLLDBWorker(transport)
        before = worker.dispatch('status', {})
        transport.inspect('ScreenAnchors.TraitTrayScreen={CanClose=true}')
        try:
            worker.dispatch('update_trait', update_params(before, **changes))
        except AdapterError as error:
            assert error.code == 'runtime_not_ready' and error.presentation == 'hades.error.' + presentation
        else:
            raise AssertionError('invalid native trait admission succeeded')
        state = transport.inspect()
        assert state['fixture']['removals'] == 0 and state['fixture']['additions'] == 0
        assert state['fixture']['closes'] == 0 and state['menuOpen'], 'invalid edit closed the native menu'
        assert state['propertyDepth'] == 0 and not getattr(transport, 'tainted', False)
        assert boon(worker.dispatch('status', {}), 'TrapDamageTrait')['rarity'] == 'Common'
    finally:
        transport.close()

# A native duration expiry can run while menu teardown yields. The original
# physical selection is rechecked before removing or re-adding any boon.
for method in ('update_trait', 'remove_trait'):
    transport = LuaTransport()
    try:
        worker = HadesLLDBWorker(transport)
        before = worker.dispatch('status', {})
        transport.inspect('ScreenAnchors.TraitTrayScreen={CanClose=true}; FixtureControl("expireDuringClose",true)')
        try:
            worker.dispatch(method, update_params(before))
        except AdapterError as error:
            assert error.code == 'runtime_not_ready' and error.presentation == 'hades.error.staleTrait'
        else:
            raise AssertionError('menu teardown reused a natively expired physical boon')
        state = transport.inspect()
        assert state['fixture']['nativeExpirations'] == 1
        assert state['fixture']['removals'] == 0 and state['fixture']['additions'] == 0
        assert state['propertyDepth'] == 0 and not getattr(transport, 'tainted', False)
        assert all(row['name'] != 'TrapDamageTrait' for row in worker.dispatch('status', {})['traits'])
    finally:
        transport.close()

# Native menu teardown yields with a hook depth held. A replacement run owner
# must not receive the suspended operation's post-yield UI/modifier writes.
for timing in ('replaceBeforeStart', 'replaceAfterYield'):
    for owner in ('room', 'hero', 'menu'):
        transport = LuaTransport()
        try:
            worker = HadesLLDBWorker(transport)
            before = worker.dispatch('status', {})
            transport.inspect('ScreenAnchors.TraitTrayScreen={CanClose=true}; FixtureControl('
                              + lua_literal(timing) + ',' + lua_literal(owner) + ')')
            try:
                worker.dispatch('update_trait', update_params(before))
            except AdapterError as error:
                expected = 'runtime_not_ready' if timing == 'replaceBeforeStart' else 'outcome_unknown'
                assert error.code == expected, (timing, owner, error.code)
            else:
                raise AssertionError('a trait edit crossed its captured native owner')
            state = transport.inspect()
            assert state['propertyDepth'] == 0
            assert state['fixture']['additions'] == 0
            assert state['fixture']['removals'] == 0
            if owner == 'menu':
                assert state['menuOpen'] and state['menuReplacement'], 'an old continuation closed its replacement menu'
        finally:
            transport.close()

# After native work starts, expiry retains an unknown outcome and abandons its
# continuation. Releasing the scheduler does not finish or resubmit that action.
transport = LuaTransport()
try:
    worker = HadesLLDBWorker(transport)
    before = worker.dispatch('status', {})
    transport.inspect('ScreenAnchors.TraitTrayScreen={CanClose=true}; FixtureControl("stopAfterStart",true)')
    clock = [0.0]
    with patch('games.hades.lldb_worker.time.monotonic', side_effect=lambda: clock[0]), \
            patch('games.hades.lldb_worker.time.sleep', side_effect=lambda seconds: clock.__setitem__(0, clock[0] + 1)):
        try:
            worker.dispatch('update_trait', update_params(before))
        except AdapterError as error:
            assert error.code == 'outcome_unknown', error.code
        else:
            raise AssertionError('an incomplete started native edit was reported as known')
    state = transport.inspect()
    assert state['receipt']['state'] == 'unknown' and state['propertyDepth'] == 0
    assert state['fixture']['removals'] == 0 and state['fixture']['additions'] == 0
    transport.inspect('FixtureControl("stopAfterStart",false)')
    assert transport.inspect()['fixture']['additions'] == 0
    try:
        transport.exchange('return MacGamingTrainerHades.json(MacGamingTrainerHades.submit_trait_command('
                           '"another-command","update_trait",{}))')
    except AdapterError as error:
        assert 'hades.error.restartRequired' in error.diagnostic
    else:
        raise AssertionError('resident accepted another command after abandoning partial native work')
finally:
    transport.close()

print('hades_boon_edit_deferred_cancellation_and_continuation_ownership_ok')

# Exercise the other admitted trait families through the same real worker and
# native scheduler. Detailed category/equipment semantics remain in the broader
# runtime suite; these cases protect dispatch, native owners and saved fields.
transport = LuaTransport()
try:
    worker = HadesLLDBWorker(transport)
    state = worker.dispatch('status', {})
    transport.inspect('ScreenAnchors.TraitTrayScreen={CanClose=true}')
    state = worker.dispatch('add_trait', {'trait': 'AddedTrait', 'rarity': 'Rare', 'level': 1,
                                         'target': state['target']})
    assert boon(state, 'AddedTrait')['rarity'] == 'Rare'
    saved = reload_snapshot(transport.inspect('Save()')['saved'])['CurrentRun']['Hero']
    assert saved['TraitDictionary']['AddedTrait'][1]['Rarity'] == 'Rare'
    transport.inspect('ScreenAnchors.TraitTrayScreen={CanClose=true}')
    closes = transport.inspect()['fixture']['closes']
    state = worker.dispatch('remove_trait', {'instanceId': boon(state, 'AddedTrait')['instanceId'],
                                            'target': state['target']})
    assert all(row['name'] != 'AddedTrait' for row in state['traits'])
    observation = transport.inspect('Save()')
    assert not observation['menuOpen'] and observation['fixture']['closes'] == closes + 1
    saved = reload_snapshot(observation['saved'])['CurrentRun']['Hero']
    assert 'AddedTrait' not in saved['TraitDictionary']
    assert {row['Name'] for row in saved['Traits'].values()} == {'TrapDamageTrait', 'SiblingTrait'}

    state = worker.dispatch('add_trait', {'trait': 'TemporaryTrait', 'rarity': 'Common', 'level': 1,
                                         'target': state['target']})
    transport.inspect('ScreenAnchors.TraitTrayScreen={CanClose=true}')
    closes = transport.inspect()['fixture']['closes']
    state = worker.dispatch('set_trait_uses', {'instanceId': boon(state, 'TemporaryTrait')['instanceId'],
                                              'uses': 4, 'target': state['target']})
    assert boon(state, 'TemporaryTrait')['remainingUses'] == 4
    observation = transport.inspect('Save()')
    assert observation['menuOpen'] and observation['fixture']['closes'] == closes
    saved = reload_snapshot(observation['saved'])['CurrentRun']['Hero']
    assert saved['TraitDictionary']['TemporaryTrait'][1]['RemainingUses'] == 4
    state = worker.dispatch('set_trait_uses', {'instanceId': boon(state, 'TemporaryTrait')['instanceId'],
                                              'uses': 0, 'target': state['target']})
    assert all(row['name'] != 'TemporaryTrait' for row in state['traits'])
    saved = reload_snapshot(transport.inspect('Save()')['saved'])['CurrentRun']['Hero']
    assert 'TemporaryTrait' not in saved['TraitDictionary']

    state = worker.dispatch('add_trait', {'trait': 'CooldownTrait', 'rarity': 'Common', 'level': 1,
                                         'target': state['target']})
    transport.inspect('ScreenAnchors.TraitTrayScreen={CanClose=true}')
    closes = transport.inspect()['fixture']['closes']
    state = worker.dispatch('refresh_trait', {'instanceId': boon(state, 'CooldownTrait')['instanceId'],
                                             'target': state['target']})
    assert boon(state, 'CooldownTrait')['cooldown'] == 3
    observation = transport.inspect('Save()')
    assert observation['menuOpen'] and observation['fixture']['closes'] == closes
    saved = reload_snapshot(observation['saved'])['CurrentRun']['Hero']
    assert saved['TraitDictionary']['CooldownTrait'][1]['CurrentCooldown'] == 3

    blessing, curse = 'ChaosBlessingTrapDamageTrait', 'ChaosCurseTrapDamageTrait'
    state = worker.dispatch('add_chaos_pair', {'blessing': blessing, 'curse': curse, 'rarity': 'Epic',
                                              'encounters': 2, 'target': state['target']})
    assert boon(state, curse)['remainingUses'] == 2 and boon(state, curse)['blessing'] == blessing
    saved = reload_snapshot(transport.inspect('Save()')['saved'])['CurrentRun']['Hero']
    assert saved['TraitDictionary'][curse][1]['OnExpire']['TraitData']['Name'] == blessing
    transport.inspect('ScreenAnchors.TraitTrayScreen={CanClose=true}')
    state = worker.dispatch('expire_trait', {'instanceId': boon(state, curse)['instanceId'],
                                            'target': state['target']})
    assert all(row['name'] != curse for row in state['traits'])
    assert boon(state, blessing)['rarity'] == 'Epic'
    observation = transport.inspect('Save()')
    assert not observation['menuOpen'] and observation['propertyDepth'] == 0
    saved = reload_snapshot(observation['saved'])['CurrentRun']['Hero']
    assert curse not in saved['TraitDictionary']
    assert saved['TraitDictionary'][blessing][1]['Rarity'] == 'Epic'
    assert saved['TraitDictionary'][blessing][1]['LastCurseName'] == curse
    verify_snapshot(observation['saved'], 'Common')
finally:
    transport.close()

print('hades_boon_add_remove_uses_expire_cooldown_and_chaos_saved_fields_ok')

# Native weapon removal can reacquire an unrelated Hammer. Menu-close yields
# must precede both selected removal and that dependent trait rebuild.
transport = LuaTransport()
try:
    worker = HadesLLDBWorker(transport)
    state = worker.dispatch('status', {})
    transport.inspect('CurrentRun.Hero.Weapons.SwordWeapon=true')
    for name in ('ZeusWeaponTrait', 'SwordDoubleDashAttackTrait'):
        state = worker.dispatch('add_trait', {'trait': name, 'rarity': 'Common', 'level': 1,
                                             'target': state['target']})
    transport.inspect('ScreenAnchors.TraitTrayScreen={CanClose=true}; FixtureControl("saveEachTick",true)')
    state = worker.dispatch('remove_trait', {'instanceId': boon(state, 'ZeusWeaponTrait')['instanceId'],
                                            'target': state['target']})
    observation = transport.inspect()
    snapshots = list(observation['fixture']['saveSnapshots'].values())
    assert any(row['menuOpen'] and row['state'] == 'running' for row in snapshots)
    for row in snapshots:
        hero = reload_snapshot(row['snapshot'])['CurrentRun']['Hero']
        names = {trait['Name'] for trait in hero['Traits'].values()}
        assert names == set(hero['TraitDictionary']), 'weapon rebuild saved a physical trait without its index'
        expected = {'TrapDamageTrait', 'SiblingTrait', 'SwordDoubleDashAttackTrait'}
        if row['menuOpen']:
            expected.add('ZeusWeaponTrait')
        assert names == expected, 'selected weapon removal started before native menu teardown completed'
        assert hero['TraitDictionary']['SwordDoubleDashAttackTrait'][1]['RequiredWeapon'] == 'SwordWeapon'
        modifiers = list(hero['OutgoingDamageModifiers'].values())
        assert len(modifiers) == 1 and modifiers[0]['Name'] == 'SwordDoubleDashAttackTrait'
        assert modifiers[0]['ValidWeaponMultiplier'] == 1.2, 'weapon rebuild saved the Hammer before restoring its effect'
    assert all(row['name'] != 'ZeusWeaponTrait' for row in state['traits'])
    assert boon(state, 'SwordDoubleDashAttackTrait')['rarity'] == 'Common'
    assert not observation['menuOpen'] and observation['receipt']['state'] == 'complete'
    verify_snapshot(transport.inspect('Save()')['saved'], 'Common')
finally:
    transport.close()

print('hades_boon_weapon_removal_rebuild_save_consistency_ok')
