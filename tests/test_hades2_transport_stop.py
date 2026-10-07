"""Portable stop-boundary failures; real debugger lifecycles run on macOS."""
import signal
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
    expect_error(transport, time.monotonic() + .015, "process_timeout")
    assert send_signal.call_count == 1, "unobserved stop was blindly resent"

print("hades2_transport_stop_ok")
