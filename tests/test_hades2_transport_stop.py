"""Portable stop-boundary failures; real debugger lifecycles run on macOS."""
import signal
import json
import sys
import time
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

fake_lldb = types.SimpleNamespace(
    eStateInvalid=0, eStateStopped=5, eStateRunning=6,
    eStateExited=10, eStateDetached=9,
)
with patch.dict(sys.modules, {"lldb": fake_lldb}), patch(
    "subprocess.check_output", return_value="",
):
    from games.hades2.transport import Hades2LuaTransport, TransportError


class Process:
    def __init__(self, state):
        self.state = state

    def GetState(self):
        return self.state


def make_transport(state):
    transport = Hades2LuaTransport.__new__(Hades2LuaTransport)
    transport.process = Process(state)
    transport.pid = 4242
    transport.drain = lambda: None
    return transport


def expect_error(transport, deadline, code):
    try:
        transport.stop(deadline)
    except TransportError as error:
        assert error.code == code, (error.code, code)
        return error
    else:
        raise AssertionError("stop unexpectedly succeeded")


# A completed stop must be observed by LLDB, not inferred from signal delivery.
transport = make_transport(fake_lldb.eStateRunning)
observations = iter((fake_lldb.eStateRunning, fake_lldb.eStateRunning, fake_lldb.eStateStopped))
transport.process.GetState = lambda: next(observations)
with patch("os.kill") as send_signal:
    transport.stop(time.monotonic() + 1)
    send_signal.assert_called_once_with(transport.pid, signal.SIGSTOP)

# An already stopped process and a spent budget must have no new OS side effect.
transport = make_transport(fake_lldb.eStateStopped)
with patch("os.kill") as send_signal:
    transport.stop(time.monotonic() - 1)
    send_signal.assert_not_called()

transport = make_transport(fake_lldb.eStateRunning)
with patch("os.kill") as send_signal:
    expect_error(transport, time.monotonic() - 1, "stop_failed")
    send_signal.assert_not_called()

for state in (fake_lldb.eStateInvalid, fake_lldb.eStateExited, fake_lldb.eStateDetached):
    transport = make_transport(state)
    with patch("os.kill") as send_signal:
        expect_error(transport, time.monotonic() + 1, "disconnected")
        send_signal.assert_not_called()

# Process disappearance and denied delivery remain known pre-call failures.
for failure, code in ((ProcessLookupError(), "disconnected"), (PermissionError(), "stop_failed")):
    transport = make_transport(fake_lldb.eStateRunning)
    with patch("os.kill", side_effect=failure) as send_signal:
        expect_error(transport, time.monotonic() + 1, code)
        assert send_signal.call_count == 1, "failed stop was retried"
    assert not getattr(transport, "tainted", False), "pre-call stop failure invented an unknown mutation"

# Successful delivery alone cannot open a boundary while LLDB still sees running.
transport = make_transport(fake_lldb.eStateRunning)
with patch("os.kill") as send_signal:
    error = expect_error(transport, time.monotonic() + .015, "process_timeout")
    assert send_signal.call_count == 1, "unobserved stop was blindly resent"
assert json.loads(error.diagnostic) == {'phase': 'transport.stop', 'expectedStates': [5], 'lastObservedState': 6}

# An expired wait does not fabricate an observation or perform another GetState.
transport = make_transport(fake_lldb.eStateRunning)
with patch.object(transport.process, 'GetState') as observe, patch('time.monotonic', return_value=1):
    try:
        transport.wait_state((fake_lldb.eStateStopped,), 0)
    except TransportError as error:
        assert error.code == 'process_timeout'
        assert json.loads(error.diagnostic)['lastObservedState'] is None
    else:
        raise AssertionError('Expired wait was accepted')
    observe.assert_not_called()

# Initial boundary and detach stops keep their existing signal and error rules,
# while the diagnostic identifies which owning phase exhausted its budget.
for phase, invoke in (
    ('boundary.initial_stop', lambda t: t.boundary()),
    ('detach.stop', lambda t: t.detach()),
):
    transport = make_transport(fake_lldb.eStateRunning)
    transport.tainted = False
    transport.alive = lambda: True
    with patch('time.monotonic', side_effect=[0, 1, 2, 4]), patch('time.sleep'), patch('os.kill') as send_signal, patch.object(transport.process, 'GetState', wraps=transport.process.GetState) as observe:
        try:
            invoke(transport)
        except TransportError as error:
            assert error.code == 'process_timeout'
            assert error.presentation == TransportError('process_timeout', '游戏进程状态切换超时。').presentation
            assert json.loads(error.diagnostic) == {'phase': phase, 'expectedStates': [5], 'lastObservedState': 6}
        else:
            raise AssertionError('Unobserved owning stop was accepted')
        assert observe.call_count == 2 and send_signal.call_count == 1
    assert not transport.tainted

# Cleanup's timeout still replaces the primary error and taints trust. It now
# retains the primary code as observation rather than changing that priority.
transport = make_transport(fake_lldb.eStateRunning)
transport.tainted = False
transport.alive = lambda: True
def fail_boundary():
    raise TransportError('lua_error', 'primary fixture failure')
transport.boundary = fail_boundary
with patch('time.monotonic', side_effect=[0, 1, 2, 3, 5, 6]), patch('time.sleep'), patch('os.kill') as send_signal:
    try:
        transport.execute('return 1')
    except TransportError as error:
        assert error.code == 'process_timeout'
        assert json.loads(error.diagnostic) == {'phase': 'execute.cleanup_stop', 'expectedStates': [5], 'lastObservedState': 6, 'primary_error_code': 'lua_error'}
    else:
        raise AssertionError('Cleanup timeout was hidden')
    assert send_signal.call_count == 1
assert transport.tainted

print("hades2_transport_stop_ok")
