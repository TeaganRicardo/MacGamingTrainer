"""Portable LLDB stop-ownership checks for Hades I's exact-build transport.

The native Apple Silicon/Rosetta comparison was performed on the supported
Game.macOS image: SBProcess.Stop survived repeated boundaries, whereas the
old SendAsyncInterrupt path lost its stop event and stranded the inferior.
"""
import sys
import time
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

lldb = types.SimpleNamespace(
    eStateInvalid=0, eStateStopped=5, eStateRunning=6,
    eStateExited=10, eStateDetached=9,
)
with patch.dict(sys.modules, {"lldb": lldb}), patch("subprocess.check_output", return_value=""):
    from games.hades.transport import HadesLuaTransport
    from core.adapter import AdapterError


class StopResult:
    def __init__(self, ok=True):
        self.ok = ok

    def Fail(self):
        return not self.ok

    def __str__(self):
        return "simulated LLDB stop failure"


class Process:
    def __init__(self, state=lldb.eStateRunning, *, complete_after=1, stop_ok=True):
        self.state = state
        self.stop_ok = stop_ok
        self.complete_after = complete_after
        self.stop_calls = 0
        self.observations = 0

    def GetState(self):
        self.observations += 1
        if self.stop_calls and self.complete_after is not None:
            if self.observations >= self.complete_after:
                self.state = lldb.eStateStopped
        return self.state

    def Stop(self):
        self.stop_calls += 1
        return StopResult(self.stop_ok)

    def SendAsyncInterrupt(self):
        raise AssertionError("Hades I must use the acknowledged LLDB Stop API")


def transport_for(process, *, live=True):
    transport = HadesLuaTransport.__new__(HadesLuaTransport)
    transport.process = process
    transport.alive = lambda: live
    transport._drain = lambda: None
    return transport


def expect_error(transport, deadline, code):
    try:
        transport._stop(deadline)
    except AdapterError as error:
        assert error.code == code, (error.code, code)
        return error
    raise AssertionError("unexpected success")


# A successful Stop request still needs a confirmed stopped-state observation.
process = Process(complete_after=5)
transport = transport_for(process)
transport._stop(time.monotonic() + 0.5)
assert process.stop_calls == 1
assert process.observations >= 5
assert process.state == lldb.eStateStopped

# Already-stopped and missing-process paths must not send a stop request.
process = Process(state=lldb.eStateStopped)
transport_for(process)._stop(time.monotonic() - 1)
assert process.stop_calls == 0
process = Process()
expect_error(transport_for(process, live=False), time.monotonic() + 1, "not_connected")
assert process.stop_calls == 0

# An LLDB API error must not be interpreted as a successful stop.
process = Process(complete_after=None, stop_ok=False)
expect_error(transport_for(process), time.monotonic() + 1, "stop_failed")
assert process.stop_calls == 1

# A successful Stop return without an observed stop event is still a failure.
process = Process(complete_after=None)
expect_error(transport_for(process), time.monotonic() + 0.02, "stop_timeout")
assert process.stop_calls == 1, "never blindly resend an uncertain stop"
assert process.state == lldb.eStateRunning

print("hades_lldb_acknowledged_stop_contract_ok")
