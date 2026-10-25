"""A leased native breakpoint is removed only after an observed stop."""
from pathlib import Path
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
    SBError=Error, eStateStopped=5, eStateRunning=6,
    ePermissionsReadable=1, ePermissionsWritable=2,
)
with patch.dict(sys.modules, {'lldb': fake_lldb}), patch('subprocess.check_output', return_value=''):
    from games.hades import transport as module


def fixture():
    events = []
    clock = [0]
    running = [False]
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

    transport = module.HadesLuaTransport.__new__(module.HadesLuaTransport)
    transport.pid = 42
    transport._tainted_pid = None
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
        Detach=lambda: Error(),
    )
    transport.alive = lambda: True
    transport._stop = stop
    transport._resume = resume
    transport._restore_focus = lambda: events.append('restore')
    return transport, breakpoint, events, clock, running


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
assert events[-3:] == ['stop', 'restore', 'delete'], events


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
    else:
        raise AssertionError('an expression failure lost its unknown-outcome result')
assert transport.tainted
assert events == ['stop', 'delete', 'restore', 'free', 'resume'], events

# If suspension itself fails, retain the breakpoint for the existing detach
# recovery path instead of attempting native cleanup against a running target.
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
        assert 'fixture expression interrupted; cleanup: hades.error.stopTimeout' == error.diagnostic
    else:
        raise AssertionError('failed suspension was hidden')
assert transport.tainted and events == [], events

from games.hades.client import HadesRuntimeClient
from games.hades.lldb_worker import error_payload
from games.hades.recovery import HadesRecoveryJournal


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
        client.command('heal', {})
    except AdapterError as error:
        assert error.code == 'outcome_unknown'
    else:
        raise AssertionError('the client accepted uncertain cleanup')
    assert not client.connected and journal.path.is_file()
    try:
        client.command('heal', {})
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
