"""A leased native breakpoint is removed only after an observed stop."""
from pathlib import Path
import sys
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

    def delete(identity):
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
        BreakpointCreateByAddress=lambda address: breakpoint, BreakpointDelete=delete,
    )
    transport.process = types.SimpleNamespace(
        ReadMemory=lambda *args: b'\x01', WriteMemory=lambda address, value, error: len(value),
        AllocateMemory=lambda *args: 1000,
        DeallocateMemory=lambda address: events.append('free'),
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
assert events == ['stop', 'restore', 'resume', 'stop', 'delete', 'stop', 'restore', 'resume'], events


class Options:
    def __getattr__(self, name):
        return lambda *args: None


transport, breakpoint, events, clock, running = fixture()
running[0] = True
transport._boundary = lambda: (types.SimpleNamespace(GetFrameAtIndex=lambda index: frame), 123, breakpoint)
frame = types.SimpleNamespace(EvaluateExpression=lambda *args: types.SimpleNamespace(
    GetError=lambda: types.SimpleNamespace(Fail=lambda: True),
))
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
transport._boundary = lambda: (types.SimpleNamespace(GetFrameAtIndex=lambda index: frame), 123, breakpoint)
running[0] = True

def failed_stop(deadline):
    raise AdapterError('stop_timeout', 'hades.error.stopTimeout')

transport._stop = failed_stop
with patch.object(module.lldb, 'SBExpressionOptions', Options, create=True), \
        patch.object(module.lldb, 'eLanguageTypeC_plus_plus', 4, create=True):
    try:
        transport.execute('return "{}"', mutating=True)
    except AdapterError as error:
        assert error.code == 'stop_timeout'
    else:
        raise AssertionError('failed suspension was hidden')
assert transport.tainted and events == [], events
print('hades_transport_cleanup_stopped_breakpoint_ownership_ok')
