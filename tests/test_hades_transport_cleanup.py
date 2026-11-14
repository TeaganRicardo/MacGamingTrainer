"""A leased native breakpoint is removed only after an observed stop."""
from pathlib import Path
import re
import sys
import tempfile
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
from core.adapter import AdapterError


class Error:
    def Fail(self):
        return False

    def Success(self):
        return True


fake_lldb = types.SimpleNamespace(
    SBError=Error, eStateStopped=5, eStateRunning=6, eStateExited=10,
    ePermissionsReadable=1, ePermissionsWritable=2,
)
with patch.dict(sys.modules, {'lldb': fake_lldb}), patch('subprocess.check_output', return_value=''):
    from games.hades import transport as module


def fixture():
    events = []
    clock = [0]
    running = [False]
    exited = [False]
    breakpoint = types.SimpleNamespace(GetID=lambda: 1)

    def delete():
        assert not running[0], 'BreakpointDelete ran before the cleanup stop'
        events.append('delete')

    def stop(deadline):
        events.append('stop')
        running[0] = False

    def resume(deadline, **options):
        events.append('resume')
        running[0] = True
        clock[0] += 4

    def kill():
        events.append('kill')
        running[0], exited[0] = False, True
        return Error()

    transport = module.HadesLuaTransport.__new__(module.HadesLuaTransport)
    transport.pid = 42
    transport._tainted_pid = None
    transport._unsafe_vm_pid = None
    transport.focus_original = None
    transport.addresses = {name: index + 100 for index, name in enumerate((
        '_ZN3sgg13ConfigOptions20RequireFocusToUpdateE', '_ZN3sgg3App6UpdateEf',
        'lua_gettop', 'luaL_loadbufferx', 'lua_pcallk', 'lua_tolstring', 'lua_settop',
    ))}
    transport.target = types.SimpleNamespace(
        BreakpointCreateByAddress=lambda address: breakpoint, DeleteAllBreakpoints=delete,
    )
    transport.process = types.SimpleNamespace(
        ReadMemory=lambda *args: b'\x01', WriteMemory=lambda address, value, error: len(value),
        AllocateMemory=lambda *args: 1000,
        DeallocateMemory=lambda address: events.append('free'),
        Detach=lambda *args: events.append(('detach', args)) or Error(),
        Kill=kill,
        GetState=lambda: fake_lldb.eStateExited if exited[0] else (
            fake_lldb.eStateRunning if running[0] else fake_lldb.eStateStopped),
    )
    transport.alive = lambda: not exited[0]
    transport._drain = lambda: None
    transport._stop = stop
    transport._resume = resume
    transport._restore_focus = lambda: events.append('restore')
    return transport, breakpoint, events, clock, running


# An initial Stop failure precedes all native mutation. Cleanup must not
# reissue that stop or claim the Lua mutation had an unknown outcome.
for stop_code in ('stop_failed', 'stop_timeout'):
    transport, breakpoint, events, clock, running = fixture()
    def refuse_initial_stop(deadline):
        events.append('stop-rejected')
        raise AdapterError(stop_code, 'hades.error.stopTimeout', diagnostic='LLDB stop rejected')
    transport._stop = refuse_initial_stop
    try:
        transport.execute('return "{}"', mutating=True)
    except AdapterError as error:
        assert error.code == stop_code and error.diagnostic == 'LLDB stop rejected'
    else:
        raise AssertionError('failed pre-Lua stop was accepted')
    assert events == ['stop-rejected'], 'failed initial stop was reissued during cleanup'
    assert transport.tainted is False, 'no Lua mutation must not be labeled unknown'

transport, breakpoint, events, clock, running = fixture()
with patch.object(module.time, 'monotonic', side_effect=lambda: clock[0]):
    try:
        transport.execute('return "{}"', mutating=True)
    except AdapterError as error:
        assert error.code == 'runtime_not_ready'
    else:
        raise AssertionError('an expired boundary deadline executed Lua')
assert events == ['stop', 'restore', 'resume', 'stop', 'delete', 'restore', 'resume'], events

# A failed boundary never transfers a local breakpoint to its caller. The
# private target retains it, and failed suspension must not resume past it.
transport, breakpoint, events, clock, running = fixture()
observed_stop = transport._stop

def boundary_cleanup_stop(deadline):
    if running[0]:
        raise AdapterError('stop_timeout', 'hades.error.stopTimeout')
    observed_stop(deadline)

transport._stop = boundary_cleanup_stop
with patch.object(module.time, 'monotonic', side_effect=lambda: clock[0]):
    try:
        transport.execute('return "{}"', mutating=True)
    except AdapterError as error:
        assert error.code == 'outcome_unknown'
    else:
        raise AssertionError('failed boundary cleanup was hidden')
assert transport.tainted and events == ['stop', 'restore', 'resume'], events
transport._stop = observed_stop
transport.detach()
assert events[-4:] == ['stop', 'restore', 'delete', ('detach', ())], events


class Options:
    def __getattr__(self, name):
        return lambda *args: None


transport, breakpoint, events, clock, running = fixture()
running[0] = True
transport._boundary = lambda: (types.SimpleNamespace(GetFrameAtIndex=lambda index: frame), 123)
frame = types.SimpleNamespace(EvaluateExpression=lambda *args: types.SimpleNamespace(
    GetError=lambda: NativeError(),
))


class NativeError:
    def Fail(self):
        return True

    def __str__(self):
        return 'fixture expression interrupted'


with patch.object(module.lldb, 'SBExpressionOptions', Options, create=True), \
        patch.object(module.lldb, 'eLanguageTypeC_plus_plus', 4, create=True):
    try:
        transport.execute('return "{}"', mutating=True)
    except AdapterError as error:
        assert error.code == 'outcome_unknown'
        assert error.presentation == 'hades.error.luaInterrupted'
    else:
        raise AssertionError('an expression failure lost its unknown-outcome result')
assert transport.tainted
assert transport._unsafe_vm_pid == 42
assert events == ['kill'] and not transport.alive(), events
transport.detach()
assert events == ['kill'], events
assert transport.process is None and transport.pid is None
assert transport._unsafe_vm_pid is None, 'released VM diagnosis can kill a later reused PID'

# LLDB can also reject compilation before entering Lua, or lose a result after
# protected return/stack cleanup. Neither observation authorizes Force Quit.
for observed_phase in (b'\x00', b'\x02'):
    transport, breakpoint, events, clock, running = fixture()
    transport._boundary = lambda: (types.SimpleNamespace(GetFrameAtIndex=lambda index: frame), 123)
    transport.process.ReadMemory = lambda *args: observed_phase
    with patch.object(module.lldb, 'SBExpressionOptions', Options, create=True), \
            patch.object(module.lldb, 'eLanguageTypeC_plus_plus', 4, create=True):
        try:
            transport.execute('return "{}"', mutating=True)
        except AdapterError as error:
            assert error.code == 'outcome_unknown' and error.presentation == 'hades.error.outcomeUnknown'
        else:
            raise AssertionError('an expression engine failure was hidden')
    assert not transport.vm_interrupted and transport.alive()
    assert events == ['stop', 'delete', 'restore', 'free', 'resume'], events

# An unreadable execution phase cannot establish that Lua cleanup completed.
transport, breakpoint, events, clock, running = fixture()
transport._boundary = lambda: (types.SimpleNamespace(GetFrameAtIndex=lambda index: frame), 123)
def fail_phase_read(address, count, error):
    error.Fail = lambda: True
    return b'\x00'
transport.process.ReadMemory = fail_phase_read
with patch.object(module.lldb, 'SBExpressionOptions', Options, create=True), \
        patch.object(module.lldb, 'eLanguageTypeC_plus_plus', 4, create=True):
    try:
        transport.execute('return "{}"', mutating=True)
    except AdapterError as error:
        assert error.presentation == 'hades.error.luaInterrupted'
    else:
        raise AssertionError('an unreadable execution phase was accepted')
assert events == ['kill'] and not transport.alive()

# Detaching and destroying the worker must not turn an interrupted Lua VM
# back into a running game that can overwrite its save.
transport, breakpoint, events, clock, running = fixture()
transport._unsafe_vm_pid = transport.pid
try:
    module.HadesLuaTransport._resume(transport, 1)
except AdapterError as error:
    assert error.code == 'restart_required' and error.presentation == 'hades.error.luaTerminationFailed'
else:
    raise AssertionError('an interrupted VM was resumed')
assert not events

# An expected game-native slow-effect admission refusal from Lua is definite,
# so it remains retryable once that effect has retired.
transport, breakpoint, events, clock, running = fixture()
running[0] = True
native_error = types.SimpleNamespace(Fail=lambda: False)
validation_frame = types.SimpleNamespace(EvaluateExpression=lambda *args: types.SimpleNamespace(
    GetError=lambda: native_error, GetValueAsSigned=lambda: 1,
))
transport._boundary = lambda: (types.SimpleNamespace(GetFrameAtIndex=lambda index: validation_frame), 123)
transport.process.ReadCStringFromMemory = lambda *args: 'hades.error.runtimeNotReady'
with patch.object(module.lldb, 'SBExpressionOptions', Options, create=True), \
        patch.object(module.lldb, 'eLanguageTypeC_plus_plus', 4, create=True):
    try:
        transport.execute('return "{}"', mutating=True)
    except AdapterError as error:
        assert error.code == 'runtime_not_ready' and error.presentation == 'hades.error.runtimeNotReady'
    else:
        raise AssertionError('definitive Lua rejection was accepted')
assert not transport.tainted, 'a known Lua admission failure must allow retry'
assert events == ['stop', 'delete', 'restore', 'free', 'resume'], events

# Termination takes priority over focus/scratch/breakpoint cleanup, even if a
# cleanup Stop would fail. None of those failures may resume an unsafe VM.
transport, breakpoint, events, clock, running = fixture()
transport._boundary = lambda: (types.SimpleNamespace(GetFrameAtIndex=lambda index: frame), 123)
running[0] = True

def failed_stop(deadline):
    raise AdapterError('stop_timeout', 'hades.error.stopTimeout')

transport._stop = failed_stop
with patch.object(module.lldb, 'SBExpressionOptions', Options, create=True), \
        patch.object(module.lldb, 'eLanguageTypeC_plus_plus', 4, create=True):
    try:
        transport.execute('return "{}"', mutating=True)
    except AdapterError as error:
        assert error.code == 'outcome_unknown'
        assert error.presentation == 'hades.error.luaInterrupted'
        assert error.diagnostic == 'fixture expression interrupted'
    else:
        raise AssertionError('failed suspension was hidden')
assert transport.tainted and events == ['kill'] and not transport.alive(), events


class KillError(NativeError):
    def __str__(self):
        return 'fixture kill failed'


# A failed native Kill retains the debugger handle and the recovery interlock.
transport, breakpoint, events, clock, running = fixture()
transport._boundary = lambda: (types.SimpleNamespace(GetFrameAtIndex=lambda index: frame), 123)
kill_successfully = transport.process.Kill
transport.process.Kill = lambda: events.append('kill-failed') or KillError()
transport.debugger = object()
with patch.object(module.lldb, 'SBExpressionOptions', Options, create=True), \
        patch.object(module.lldb, 'eLanguageTypeC_plus_plus', 4, create=True):
    try:
        transport.execute('return "{}"', mutating=True)
    except AdapterError as error:
        assert error.code == 'outcome_unknown' and error.presentation == 'hades.error.luaTerminationFailed'
        assert 'fixture expression interrupted' in error.diagnostic and 'fixture kill failed' in error.diagnostic
    else:
        raise AssertionError('failed termination was hidden')
assert transport.tainted and transport.cleanup_pending and transport.alive()
destroyed = []
with patch.object(module.lldb, 'SBDebugger', types.SimpleNamespace(Destroy=destroyed.append), create=True):
    try:
        transport.close()
    except AdapterError as error:
        assert error.presentation == 'hades.error.luaTerminationFailed'
    else:
        raise AssertionError('close abandoned an unsafe live process')
assert events == ['kill-failed', 'kill-failed'] and destroyed == [], events
transport.process.Kill = kill_successfully
with patch.object(module.lldb, 'SBDebugger', types.SimpleNamespace(Destroy=destroyed.append), create=True):
    transport.close()
assert events == ['kill-failed', 'kill-failed', 'kill'] and transport.process is None, events
assert destroyed == [transport.debugger]

# An accepted Kill without an observed exit is still a failure.
transport, breakpoint, events, clock, running = fixture()
transport._unsafe_vm_pid = transport.pid
transport.process.Kill = lambda: events.append('kill') or Error()
with patch.object(module.time, 'monotonic', side_effect=range(10)), patch.object(module.time, 'sleep'):
    try:
        transport.detach()
    except AdapterError as error:
        assert error.presentation == 'hades.error.luaTerminationFailed'
    else:
        raise AssertionError('an unobserved target exit was accepted')
assert events == ['kill'] and transport.cleanup_pending and transport.process is not None

from games.hades.client import HadesRuntimeClient
from games.hades.lldb_worker import error_payload
from games.hades.lldb_worker import HadesLLDBWorker
from games.hades.schema import DEFAULT_FEATURES
from games.hades.catalog import data as catalog_data
from games.hades.world import reward_catalog
from games.hades.recovery import HadesRecoveryJournal


class PayloadCapture:
    pid = 42

    def __init__(self):
        self.sizes = []

    def attach(self, pid, executable):
        pass

    def alive(self):
        return True

    def execute(self, source, *, mutating):
        self.sizes.append(len(source.encode('utf-8')))
        assert self.sizes[-1] <= module.LUA_SOURCE_LIMIT_BYTES, 'assembled resident request exceeds transport capacity'
        result = {'heroId': 'a' * 32 + ':1:2:40000', 'heroReady': True}
        submitted = re.search(r'return runtime\.json\(runtime\.submit_trait_command\("([0-9a-f]{32})",', source)
        if submitted:
            return {'id': submitted.group(1), 'state': 'complete', 'mutationStarted': True, 'result': result}
        return result


# Exercise the actual request builder, including its resident, world registry,
# two feature documents, UTF-8 escaping and captured native owner arguments.
capture = PayloadCapture()
HadesLLDBWorker(capture).dispatch('connect', {'pid': 42, 'executable': '/tmp/Hades/Game.macOS'})
worker = HadesLLDBWorker(capture)
features = {key: (False if type(value) is bool else 20 if key == 'dashBonus' else 0.10000000000000002)
            for key, value in DEFAULT_FEATURES.items()}
worker.dispatch('connect', {'pid': 42, 'executable': '/tmp/Hades/Game.macOS', 'features': features})
worker.dispatch('configure', {'features': features})
worker.dispatch('set_boon_rarity', {'target': 'Epic'})
target = {'heroId': 'a' * 32 + ':1:2:40000'}
longest = max((row for row in catalog_data()['entries'] if row.get('acquirable', True)), key=lambda row: len(row['id']))
worker.dispatch('add_trait', {'target': target, 'trait': longest['id'],
                            'rarity': max(longest['rarities'], key=len),
                            'level': 100 if longest.get('supportsLevel', True) else 1})
reward = max((row for row in reward_catalog() if row['doorAllowed']), key=lambda row: len(row['id']))['id']
worker.dispatch('apply_world_exit', {
    'target': target, 'roomId': 'a' * 32 + ':1:room:3',
    'doorToken': '4:5:' + reward + ':nil:6',
    'kind': 'reward', 'targetID': reward, 'requestId': 'cleanup-reward-apply',
})
worker.dispatch('cancel_world_exit', {
    'target': target, 'roomId': 'a' * 32 + ':1:room:3',
    'doorToken': '4:5:' + reward + ':nil:6',
    'leaseToken': 'lease-cleanup-reward', 'requestId': 'cleanup-reward-cancel',
})
worker.dispatch('apply_world_exit', {
    'target': target, 'roomId': 'a' * 32 + ':1:room:3',
    'doorToken': '4:5:' + reward + ':nil:6',
    'kind': 'roomCategory', 'targetID': 'reprieve', 'requestId': 'cleanup-route-apply',
})
worker.dispatch('cancel_world_exit', {
    'target': target, 'roomId': 'a' * 32 + ':1:room:3',
    'doorToken': '4:5:' + reward + ':nil:6',
    'leaseToken': 'lease-cleanup-route', 'requestId': 'cleanup-route-cancel',
})
leveled = max((row for row in catalog_data()['entries'] if row['kind'] == 'boon' and row['supportsLevel']),
              key=lambda row: len(row['id']))
group_id = 'trait:' + leveled['id'] + ':' + ','.join(map(str, range(1_000_000, 1_000_100)))
worker.dispatch('update_trait', {'target': target, 'instanceId': group_id, 'rarity': 'Legendary', 'level': 100})
assert max(capture.sizes) > 64 * 1024, 'fixture missed the combined resident/group request regression'
oversized_transport, _, oversized_events, _, _ = fixture()
at_limit = '中' * (module.LUA_SOURCE_LIMIT_BYTES // 3) + 'ab'
assert len(at_limit.encode('utf-8')) == module.LUA_SOURCE_LIMIT_BYTES
try:
    oversized_transport.execute(at_limit + 'c', mutating=True)
except ValueError:
    pass
else:
    raise AssertionError('over-budget UTF-8 request crossed the transport boundary')
assert oversized_events == [] and not oversized_transport.tainted, 'rejected source touched or tainted the game'


class BoundaryReached(Exception):
    pass


def observe_boundary():
    raise BoundaryReached()


at_limit_transport, _, _, _, _ = fixture()
at_limit_transport._boundary = observe_boundary
try:
    at_limit_transport.execute(at_limit, mutating=True)
except BoundaryReached:
    pass
else:
    raise AssertionError('an exact-limit UTF-8 request did not reach the native boundary')


class Sidecar:
    calls = 0

    def request(self, *args, **options):
        self.calls += 1
        try:
            transport.execute('return "{}"', mutating=True)
        except AdapterError as error:
            return {'error': error_payload(error)}
        raise AssertionError('failed cleanup unexpectedly succeeded')


# Cross the actual worker/client error boundary: failed cleanup cannot turn an
# unknown native result into a retryable response or erase its durable record.
with tempfile.TemporaryDirectory(prefix='hades-cleanup-') as directory, \
        patch.object(module.lldb, 'SBExpressionOptions', Options, create=True), \
        patch.object(module.lldb, 'eLanguageTypeC_plus_plus', 4, create=True):
    transport._tainted_pid = None
    journal = HadesRecoveryJournal(Path(directory) / 'request.json')
    sidecar = Sidecar()
    client = HadesRuntimeClient(sidecar, recovery=journal)
    client.pid, client.process_identity, client.connected = 42, 'fixture-lifetime', True
    try:
        client.command('set_value', {'field': 'money', 'value': 1, 'target': {'heroId': 'fixture'}})
    except AdapterError as error:
        assert error.code == 'outcome_unknown'
        assert error.presentation == 'hades.error.luaTerminationFailed'
    else:
        raise AssertionError('the client accepted uncertain cleanup')
    assert not client.connected and journal.path.is_file()
    try:
        client.command('set_value', {'field': 'money', 'value': 1, 'target': {'heroId': 'fixture'}})
    except AdapterError as error:
        assert error.code == 'restart_required'
    else:
        raise AssertionError('the uncertain command was replayed')
    assert sidecar.calls == 1
    try:
        HadesRecoveryJournal(journal.path).guard(42, 'fixture-lifetime')
    except AdapterError as error:
        assert error.code == 'restart_required'
    else:
        raise AssertionError('backend replacement discarded uncertain cleanup')
print('hades_transport_cleanup_stopped_breakpoint_ownership_ok')
