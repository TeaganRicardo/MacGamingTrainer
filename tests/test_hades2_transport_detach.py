"""Detached targets must resume at the OS boundary, including partial failure."""
import signal
import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

fake_lldb = types.SimpleNamespace(eStateInvalid=0, eStateStopped=5,
                                 eStateRunning=6, eStateExited=10, eStateDetached=9)
with patch.dict(sys.modules, {"lldb": fake_lldb}), patch("subprocess.check_output", return_value=""):
    from games.hades2.transport import Hades2LuaTransport, TransportError


class Process:
    def __init__(self, *, state=fake_lldb.eStateRunning, release_failed=False):
        self.state = state
        self.release_failed = release_failed
        self.os_paused = False

    def GetState(self):
        return self.state

    def Detach(self):
        if not self.release_failed:
            self.state = fake_lldb.eStateDetached
        # Debugger release alone can leave the OS stop in effect.
        return types.SimpleNamespace(Fail=lambda: self.release_failed)


def make_transport(**options):
    transport = Hades2LuaTransport.__new__(Hades2LuaTransport)
    process = Process(**options)
    transport.process = process
    transport.pid = 4242
    transport.addresses = {"focus": 123}
    transport.focus_original = b"\x01"
    transport.tainted = True
    transport.drain = lambda: None
    transport.target = types.SimpleNamespace(DeleteAllBreakpoints=lambda: None)

    def stop(deadline):
        process.state = fake_lldb.eStateStopped
        process.os_paused = True

    def restore_focus():
        assert process.state == fake_lldb.eStateStopped
        transport.focus_original = None

    transport.stop = stop
    transport.restore_focus = restore_focus
    return transport, process


transport, process = make_transport()


def resume_released_target(pid, signo):
    assert pid == 4242 and signo == signal.SIGCONT
    assert process.state == fake_lldb.eStateDetached, "OS resume preceded debugger release"
    assert transport.focus_original is None, "released target kept an unrestored focus flag"
    process.os_paused = False


with patch("os.kill", side_effect=resume_released_target) as send_signal:
    transport.detach()
    assert not process.os_paused, "detached target stayed stopped"
    assert send_signal.call_count == 1, "release sent repeated OS resumes"
assert transport.process is None and transport.pid is None
assert transport.addresses == {} and not transport.tainted

for failure in (ProcessLookupError("target exited"), PermissionError("resume denied")):
    transport, process = make_transport()
    with patch("os.kill", side_effect=failure) as send_signal:
        if isinstance(failure, ProcessLookupError):
            transport.detach()
        else:
            try:
                transport.detach()
            except TransportError as error:
                assert error.code == "resume_failed" and error.diagnostic == "resume denied"
            else:
                raise AssertionError("OS resume failure was hidden")
        assert send_signal.call_count == 1, "failed OS resume was retried"
    assert process.state == fake_lldb.eStateDetached
    assert transport.process is None and transport.pid is None, "released attachment was retained"

transport, process = make_transport(release_failed=True)
with patch("os.kill") as send_signal:
    try:
        transport.detach()
    except TransportError as error:
        assert error.code == "detach_failed"
    else:
        raise AssertionError("debugger release failure was hidden")
    send_signal.assert_not_called()
assert transport.process is process and transport.pid == 4242, "failed release lost recovery ownership"

transport, process = make_transport(state=fake_lldb.eStateExited)
with patch("os.kill") as send_signal:
    transport.detach()
    send_signal.assert_not_called()
assert transport.process is None and transport.pid is None

print("hades2_transport_detach_ok")
