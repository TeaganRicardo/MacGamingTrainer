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

# Already-expired deadline while running must not issue a new Stop request.
process = Process()
expect_error(transport_for(process), time.monotonic() - 1, "stop_timeout")
assert process.stop_calls == 0

# Stop().Fail() still succeeds if draining reveals an already-stopped process.
class FailedStopAlreadyStoppedProcess(Process):
    def Stop(self):
        self.stop_calls += 1
        self.state = lldb.eStateStopped
        return StopResult(False)


already_stopped_on_fail = FailedStopAlreadyStoppedProcess()
transport_for(already_stopped_on_fail)._stop(time.monotonic() + 1)
assert already_stopped_on_fail.stop_calls == 1

# Public transport.stop(deadline) releases a late physical stop rather than leaving Hades paused.
late_process = Process(complete_after=None)
late_transport = transport_for(late_process)
late_transport._tainted_pid = None
late_transport.pid = 42
late_transport.tainted = False
late_events = []
def raise_timeout_after_late_stop(_deadline):
    late_process.state = lldb.eStateStopped
    raise AdapterError("stop_timeout", "hades.error.stopTimeout")
late_transport._stop = raise_timeout_after_late_stop
late_transport._resume = lambda _deadline: late_events.append("resume") or setattr(late_process, "state", lldb.eStateRunning)
try:
    late_transport.stop(time.monotonic() + 0.5)
except AdapterError as error:
    assert error.code == "stop_timeout"
else:
    raise AssertionError("late stop release masked primary stop timeout")
assert late_events == ["resume"] and late_process.state == lldb.eStateRunning and not late_transport.tainted

# Failing to release that late physical stop taints the attachment and surfaces outcome_unknown.
stuck_process = Process(complete_after=None)
stuck_transport = transport_for(stuck_process)
stuck_transport._tainted_pid = None
stuck_transport.pid = 42
stuck_transport.tainted = False
def raise_stuck_timeout(_deadline):
    stuck_process.state = lldb.eStateStopped
    raise AdapterError("stop_timeout", "hades.error.stopTimeout", diagnostic="timed out")
stuck_transport._stop = raise_stuck_timeout
def fail_resume(_deadline):
    raise AdapterError("resume_failed", "hades.error.resumeFailed", diagnostic="continue rejected")
stuck_transport._resume = fail_resume
try:
    stuck_transport.stop(time.monotonic() + 0.5)
except AdapterError as error:
    assert error.code == "outcome_unknown" and stuck_transport.tainted
    assert "timed out" in error.diagnostic and "continue rejected" in error.diagnostic
else:
    raise AssertionError("failed late stop release did not raise outcome_unknown")

print("hades_lldb_acknowledged_stop_contract_ok")
