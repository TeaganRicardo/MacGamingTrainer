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
    from games.hades2 import transport as hades2_transport
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

    def stop(deadline, **observations):
        assert observations == {'phase': 'detach.stop'}
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

# Failed attach rollback must preserve primary incompatible error, keep quarantined
# ownership when cleanup stops/fails, reject mutations, and finish cleanup on retry.
def make_attach_transport(*, triple="arm64-apple-macosx", uuid="expected-uuid", release_failed=False):
    attaching = Hades2LuaTransport.__new__(Hades2LuaTransport)
    proc = Process(state=fake_lldb.eStateStopped, release_failed=release_failed)
    image = types.SimpleNamespace(GetUUIDString=lambda: uuid)
    target = types.SimpleNamespace(
        AttachToProcessWithID=lambda listener, pid, error: proc,
        GetModuleAtIndex=lambda index: image,
        GetTriple=lambda: triple,
        DeleteAllBreakpoints=lambda: None,
    )
    attaching.debugger = types.SimpleNamespace(
        CreateTarget=lambda path: target,
        _destroyed=False,
    )
    attaching._target_ref = target
    attaching.listener = None
    attaching.target = None
    attaching.process = None
    attaching.pid = None
    attaching.addresses = {}
    attaching.tainted = False
    attaching._mailbox = None
    attaching.mailbox_mode = "lldb"
    attaching.native_runtime_installer = None
    attaching.native_mailbox_library = None
    attaching.runtime_uuid = None
    attaching.known_uuid = "expected-uuid"
    attaching.symbols = {}
    attaching.last_attach_profile = {}
    attaching.focus_original = None
    attaching.stop = lambda deadline, **obs: setattr(proc, "state", fake_lldb.eStateStopped)
    attaching.restore_focus = lambda: None
    attaching.drain = lambda: None
    return attaching, proc

fake_lldb.SBError = lambda: types.SimpleNamespace(Fail=lambda: False)
fake_lldb.SBDebugger = types.SimpleNamespace(Destroy=lambda dbg: setattr(dbg, "_destroyed", True))

# 1) LLDB Detach fails during attach rollback: keep live process ownership & deny mutations.
bad_attach, bad_proc = make_attach_transport(triple="x86_64-apple-macosx", release_failed=True)
with patch("os.kill") as send_signal:
    try:
        bad_attach.attach(7777)
    except TransportError as error:
        assert error.code == "incompatible", f"expected incompatible, got {error.code}"
        assert "rollback lldb_detach failed (pid=7777 still attached):" in (error.diagnostic or "")
    else:
        raise AssertionError("attach rollback masked primary incompatible error")
    send_signal.assert_not_called()

assert bad_attach.alive() is True
assert bad_attach.cleanup_pending is True
assert bad_attach.cleanup_failure[0] == "lldb_detach"
assert bad_attach.process is bad_proc and bad_attach.pid == 7777
assert bad_proc.state == fake_lldb.eStateStopped

for mode in ("lldb", "mailbox"):
    bad_attach.mailbox_mode = mode
    try:
        bad_attach.execute("return {}")
    except TransportError as error:
        assert error.code == "detach_failed"
        assert "pid=7777 still attached" in (error.diagnostic or "")
    else:
        raise AssertionError(f"quarantined {mode} execute succeeded")

try:
    bad_attach.boundary()
except TransportError as error:
    assert error.code == "detach_failed"
else:
    raise AssertionError("quarantined boundary succeeded")

with patch.dict(sys.modules, {"lldb": fake_lldb}):
    from debugger.lldb_time_warp import LLDBProcessTimeWarpDriver, ProcessTimeWarpError
    try:
        with LLDBProcessTimeWarpDriver(bad_attach, fake_lldb).session():
            raise AssertionError("quarantined transport entered TimeWarp session")
    except ProcessTimeWarpError as error:
        assert error.code == "detach_failed"
        assert error.presentation == "host.timeWarp.error.restartRequired"

with patch("os.kill") as send_signal:
    try:
        bad_attach.attach(7777)
    except TransportError as error:
        assert error.code == "detach_failed"
    else:
        raise AssertionError("attach reused quarantined attachment")
    send_signal.assert_not_called()
assert bad_attach.process is bad_proc and bad_attach.pid == 7777

bad_proc.release_failed = False
with patch("os.kill") as send_signal:
    bad_attach.detach()
    send_signal.assert_called_once_with(7777, signal.SIGCONT)
assert bad_proc.state == fake_lldb.eStateDetached
assert bad_attach.process is None and bad_attach.pid is None
assert not bad_attach.alive() and not bad_attach.cleanup_pending

# 2) Post-Detach os.kill(SIGCONT) fails during rollback: debugger released, OS resume still pending.
attach_os_fail, proc_os_fail = make_attach_transport(triple="x86_64-apple-macosx", release_failed=False)
with patch("os.kill", side_effect=PermissionError("os resume blocked")):
    try:
        attach_os_fail.attach(7779)
    except TransportError as error:
        assert error.code == "incompatible"
        assert "post-detach OS resume failed (pid=7779): os resume blocked" in (error.diagnostic or "")
    else:
        raise AssertionError("attach rollback masked incompatible after OS resume failure")
assert proc_os_fail.state == fake_lldb.eStateDetached
assert attach_os_fail.process is None and attach_os_fail.pid is None
assert not attach_os_fail.alive()
assert attach_os_fail.cleanup_pending is True
assert attach_os_fail.pending_resume_pid == 7779
assert attach_os_fail.cleanup_failure == ("os_resume", "os resume blocked")
try:
    attach_os_fail.execute("return {}")
except TransportError as error:
    assert error.code == "resume_failed"
    assert error.presentation == "hades2.error.resumeFailed"
else:
    raise AssertionError("execute allowed while OS resume remained pending")
with patch("os.kill") as send_signal:
    attach_os_fail.detach()
    send_signal.assert_called_once_with(7779, signal.SIGCONT)
assert not attach_os_fail.cleanup_pending and attach_os_fail.pending_resume_pid is None

# 3) Failed mailbox.close() preserves _mailbox & process ownership and retries cleanly.
class FlakyMailbox:
    def __init__(self):
        self.fail_close = True
        self.closed = False

    def close(self):
        if self.fail_close:
            raise OSError("mailbox busy")
        self.closed = True


mailbox_fail, mailbox_proc = make_attach_transport(triple="x86_64-apple-macosx", release_failed=False)
fake_mailbox = FlakyMailbox()
mailbox_fail._mailbox = fake_mailbox
with patch("os.kill") as send_signal:
    try:
        mailbox_fail.attach(7780)
    except TransportError as error:
        assert error.code == "incompatible"
        assert "rollback mailbox_close failed (pid=7780 still attached): mailbox busy" in (error.diagnostic or "")
    else:
        raise AssertionError("attach rollback masked incompatible after mailbox_close failure")
    send_signal.assert_not_called()
assert mailbox_fail._mailbox is fake_mailbox and not fake_mailbox.closed
assert mailbox_fail.process is mailbox_proc and mailbox_fail.pid == 7780 and mailbox_fail.cleanup_pending
fake_mailbox.fail_close = False
with patch("os.kill") as send_signal:
    mailbox_fail.detach()
    send_signal.assert_called_once_with(7780, signal.SIGCONT)
assert fake_mailbox.closed and mailbox_fail._mailbox is None
assert mailbox_proc.state == fake_lldb.eStateDetached
assert mailbox_fail.process is None and mailbox_fail.pid is None and not mailbox_fail.cleanup_pending

# 4) Recovery via close() detaches target, sends SIGCONT, clears quarantine, and destroys debugger.
close_recover, close_proc = make_attach_transport(triple="x86_64-apple-macosx", release_failed=True)
with patch("os.kill"):
    try:
        close_recover.attach(7781)
    except TransportError as error:
        assert error.code == "incompatible"
close_proc.release_failed = False
debugger_ref = close_recover.debugger
with patch("os.kill") as send_signal:
    close_recover.close()
    send_signal.assert_called_once_with(7781, signal.SIGCONT)
assert close_proc.state == fake_lldb.eStateDetached
assert debugger_ref._destroyed is True and close_recover.debugger is None
assert close_recover.process is None and close_recover.pid is None and not close_recover.cleanup_pending

# Persistently failing close() must preserve debugger + pending release for retry.
persistent_close, persistent_proc = make_attach_transport(triple="x86_64-apple-macosx", release_failed=True)
with patch("os.kill"):
    try:
        persistent_close.attach(7782)
    except TransportError as error:
        assert error.code == "incompatible"
debugger_ref = persistent_close.debugger
try:
    persistent_close.close()
except TransportError as error:
    assert error.code == "detach_failed"
else:
    raise AssertionError("terminal close incorrectly ignored failed LLDB Detach")
assert persistent_close.debugger is debugger_ref and not debugger_ref._destroyed
assert persistent_close.pid == 7782 and persistent_close.cleanup_pending
persistent_proc.release_failed = False
# A post-Detach LLDB event-drain failure must never block the mandatory SIGCONT.
persistent_close.drain = lambda: (
    (_ for _ in ()).throw(AssertionError("drain after Detach strands the OS stop"))
    if persistent_proc.state == fake_lldb.eStateDetached else None
)
with patch("os.kill") as send_signal:
    persistent_close.close()
    send_signal.assert_called_once_with(7782, signal.SIGCONT)
assert debugger_ref._destroyed and persistent_close.debugger is None
assert persistent_close.pid is None and not persistent_close.cleanup_pending

# C mailbox close can return a failure code without raising an exception.
from core.adapter import AdapterError
from games.hades2.mailbox import Hades2CommandMailbox
native_mailbox = Hades2CommandMailbox.__new__(Hades2CommandMailbox)
native_mailbox._closed = False
native_mailbox._mapping = object()
releases = []
native_mailbox._release = lambda: releases.append("released")
native_mailbox._call = lambda name: 4  # MGT_MAILBOX_INVALID
try:
    native_mailbox.close()
except AdapterError as error:
    assert error.code == "mailbox_close_failed"
    assert "MGTMailboxClose returned 4" in (error.diagnostic or "")
else:
    raise AssertionError("native mailbox close failure was silently discarded")
assert not native_mailbox._closed and releases == []
native_mailbox._call = lambda name: 0  # MGT_MAILBOX_OK
native_mailbox.close()
native_mailbox.close()
assert native_mailbox._closed and releases == ["released"]

# 5) Failures in attach()'s final resume step must also roll back cleanly.
resume_fail_attach, resume_proc = make_attach_transport(release_failed=False)
resume_fail_attach.resume = lambda deadline: (_ for _ in ()).throw(
    TransportError("resume_timeout", "hades2.error.resumeTimeout")
)
with patch.object(hades2_transport, "prepare_native_query", return_value=None), patch("os.kill") as send_signal:
    try:
        resume_fail_attach.attach(7778)
    except TransportError as error:
        assert error.code == "resume_timeout", f"expected resume_timeout, got {error.code}"
    else:
        raise AssertionError("attach resume failure was suppressed")
    send_signal.assert_called_once_with(7778, signal.SIGCONT)
assert resume_proc.state == fake_lldb.eStateDetached
assert resume_fail_attach.process is None and resume_fail_attach.pid is None

print("hades2_transport_detach_ok")
