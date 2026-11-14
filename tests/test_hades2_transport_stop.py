"""Portable stop and boundary behavior; real debugger lifecycles run on macOS."""
import json
import sys
import time
import types
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

fake_lldb = types.SimpleNamespace(
    eStateInvalid=0, eStateStopped=5, eStateRunning=6,
    eStateExited=10, eStateDetached=9,
    eStopReasonBreakpoint=3,
    SBError=lambda: types.SimpleNamespace(Fail=lambda: False, Success=lambda: True),
)
with patch.dict(sys.modules, {"lldb": fake_lldb}), patch(
    "subprocess.check_output", return_value="",
):
    from games.hades2.native_mailbox import install_command_mailbox
    from games.hades2.transport import Hades2LuaTransport, TransportError


class StopError:
    def __init__(self, failed, message):
        self._failed = failed
        self._message = message

    def Fail(self):
        return self._failed

    def __str__(self):
        return self._message


class Process:
    def __init__(self, state, *, stop_error=None):
        self.state = state
        self.stops = 0
        self.stop_requested = False
        self.stop_error = stop_error

    def GetState(self):
        return self.state

    def Stop(self):
        self.stops += 1
        self.stop_requested = True
        return StopError(self.stop_error is not None, self.stop_error or "")

    def SendAsyncInterrupt(self):
        raise AssertionError("Hades II must use the acknowledged LLDB Stop API")


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


# Only a debugger stop request produces the observed stop event in this process.
# An external signal may succeed without updating LLDB's process state.
transport = make_transport(fake_lldb.eStateRunning)
def observe_requested_stop():
    if transport.process.stop_requested:
        transport.process.state = fake_lldb.eStateStopped
transport.drain = observe_requested_stop
with patch("time.monotonic", side_effect=[0, 1, 4]), patch("time.sleep"), patch("os.kill") as send_signal:
    transport.stop(3)
    assert transport.process.stops == 1
    assert transport.process.GetState() == fake_lldb.eStateStopped
    send_signal.assert_not_called()


# A completed stop must be observed by LLDB, not inferred from the request.
transport = make_transport(fake_lldb.eStateRunning)
observations = iter((fake_lldb.eStateRunning, fake_lldb.eStateRunning, fake_lldb.eStateStopped))
transport.process.GetState = lambda: next(observations)
with patch("os.kill") as send_signal:
    transport.stop(time.monotonic() + 1)
    assert transport.process.stops == 1
    send_signal.assert_not_called()

# An already stopped process and a spent budget must not request another stop.
transport = make_transport(fake_lldb.eStateStopped)
with patch("os.kill") as send_signal:
    transport.stop(time.monotonic() - 1)
    assert transport.process.stops == 0
    send_signal.assert_not_called()

transport = make_transport(fake_lldb.eStateRunning)
with patch("os.kill") as send_signal:
    try:
        transport.stop(time.monotonic() - 1, phase="execute.cleanup_stop", primary_error_code="lua_error")
    except TransportError as error:
        assert error.code == "stop_failed"
        assert json.loads(error.diagnostic) == {
            "phase": "execute.cleanup_stop",
            "expectedStates": [fake_lldb.eStateStopped],
            "lastObservedState": fake_lldb.eStateRunning,
            "primary_error_code": "lua_error",
        }
    else:
        raise AssertionError("expired pre-Stop deadline unexpectedly succeeded")
    assert transport.process.stops == 0
    send_signal.assert_not_called()

# Null process fails immediately as disconnected rather than crashing on GetState.
null_transport = make_transport(fake_lldb.eStateRunning)
null_transport.process = None
for invoke in (
    lambda: null_transport.stop(time.monotonic() + 1),
    lambda: null_transport.wait_state((fake_lldb.eStateStopped,), time.monotonic() + 1),
    lambda: null_transport.resume(time.monotonic() + 1),
):
    try:
        invoke()
    except TransportError as error:
        assert error.code == "disconnected", error.code
    else:
        raise AssertionError("None process did not fail closed with disconnected")

for state in (fake_lldb.eStateInvalid, fake_lldb.eStateExited, fake_lldb.eStateDetached):
    transport = make_transport(state)
    with patch("os.kill") as send_signal:
        expect_error(transport, time.monotonic() + 1, "disconnected")
        assert transport.process.stops == 0
        send_signal.assert_not_called()

# A Stop() failure on a running process fails immediately with structured
# diagnostic; concurrent transitions to stopped or exited keep their semantics.
transport = make_transport(fake_lldb.eStateRunning)
transport.process.stop_error = "simulated LLDB stop error"
with patch("os.kill") as send_signal:
    try:
        transport.stop(time.monotonic() + 3, phase="execute.cleanup_stop", primary_error_code="lua_error")
    except TransportError as error:
        assert error.code == "stop_failed"
        assert json.loads(error.diagnostic) == {
            "phase": "execute.cleanup_stop",
            "expectedStates": [5],
            "lastObservedState": 6,
            "lldbError": "simulated LLDB stop error",
            "primary_error_code": "lua_error",
        }
    else:
        raise AssertionError("stop_failed unexpectedly succeeded")
    assert transport.process.stops == 1
    send_signal.assert_not_called()

concurrent_stop = make_transport(fake_lldb.eStateRunning)
concurrent_stop.process.stop_error = "Process is not running."
concurrent_observations = iter((fake_lldb.eStateRunning, fake_lldb.eStateStopped))
concurrent_stop.process.GetState = lambda: next(concurrent_observations)
concurrent_stop.stop(time.monotonic() + 1)
assert concurrent_stop.process.stops == 1

concurrent_exit = make_transport(fake_lldb.eStateRunning)
concurrent_exit.process.stop_error = "Process exited."
concurrent_exit_observations = iter((fake_lldb.eStateRunning, fake_lldb.eStateExited))
concurrent_exit.process.GetState = lambda: next(concurrent_exit_observations)
expect_error(concurrent_exit, time.monotonic() + 1, "disconnected")
assert concurrent_exit.process.stops == 1

# A terminal event after the request remains a known pre-call failure.
for state in (fake_lldb.eStateInvalid, fake_lldb.eStateExited, fake_lldb.eStateDetached):
    transport = make_transport(fake_lldb.eStateRunning)
    observations = iter((fake_lldb.eStateRunning, state))
    transport.process.GetState = lambda: next(observations)
    with patch("os.kill") as send_signal:
        expect_error(transport, time.monotonic() + 1, "disconnected")
        assert transport.process.stops == 1, "failed stop was retried"
        send_signal.assert_not_called()
    assert not getattr(transport, "tainted", False), "pre-call stop failure invented an unknown mutation"

# resume() and boundary() also classify eStateInvalid as immediate disconnect.
invalid_resume = make_transport(fake_lldb.eStateStopped)
resume_states = iter((fake_lldb.eStateStopped, fake_lldb.eStateInvalid))
invalid_resume.process.GetState = lambda: next(resume_states)
invalid_resume.process.GetStopID = lambda: 1
invalid_resume.process.Continue = lambda: StopError(False, "")
try:
    invalid_resume.resume(time.monotonic() + 1)
except TransportError as error:
    assert error.code == "disconnected", error.code
else:
    raise AssertionError("eStateInvalid during resume did not fail closed")

# A Stop request cannot open a boundary while LLDB still sees running.
transport = make_transport(fake_lldb.eStateRunning)
with patch("os.kill") as send_signal:
    error = expect_error(transport, time.monotonic() + .015, "process_timeout")
    assert transport.process.stops == 1, "unobserved stop was blindly resent"
    send_signal.assert_not_called()
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

# Initial boundary and detach stops keep their deadline and error rules,
# while the diagnostic identifies which owning phase exhausted its budget.
# boundary.initial_stop adds one post-failure GetState check so a late stop
# that paused the target is released instead of leaving it frozen.
for phase, invoke, expected_observations in (
    ('boundary.initial_stop', lambda t: t.boundary(), 3),
    ('detach.stop', lambda t: t.detach(), 2),
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
        assert observe.call_count == expected_observations and transport.process.stops == 1
        send_signal.assert_not_called()
    assert not transport.tainted
    assert not getattr(transport, '_boundary_initial_stop_pending', False)

# A default request stops at World::Update. Mailbox installation can select the
# App::Update rendezvous instead. Both use one entry breakpoint, rather than
# probing every Lua call, and lease its identity until expression cleanup.
focus_symbol = '_ZN3sgg13ConfigOptions20RequireFocusToUpdateE'
world_symbol = '_ZN3sgg5World6UpdateEf'
lua_state_symbol = '_ZN3sgg13ScriptManager12LuaInterfaceE'
symbols = json.loads((ROOT / 'Backend/games/hades2/symbols.json').read_text())['symbols']
assert world_symbol in symbols
addresses = {focus_symbol: 0x1000, world_symbol: 0x2000, lua_state_symbol: 0x3000}
app_rendezvous = 0x4010
for entry_address in (None, app_rendezvous):
    transport = make_transport(fake_lldb.eStateStopped)
    transport.tainted = False
    transport.alive = lambda: True
    transport.focus_original = None
    transport.address = Mock(side_effect=addresses.__getitem__)
    transport.resume = Mock()
    transport.target = Mock()
    breakpoint = transport.target.BreakpointCreateByAddress.return_value
    breakpoint.GetID.return_value = 17
    thread = Mock()
    thread.GetName.return_value = 'MainThread'
    thread.GetStopReason.return_value = fake_lldb.eStopReasonBreakpoint
    thread.GetStopReasonDataAtIndex.return_value = breakpoint.GetID()
    transport.process = MagicMock()
    transport.process.GetState.return_value = fake_lldb.eStateStopped
    transport.process.__iter__.return_value = iter((thread,))
    transport.process.ReadMemory.return_value = b'\x01'
    transport.process.WriteMemory.return_value = 1
    transport.process.ReadPointerFromMemory.return_value = 0x5000

    result = (transport.boundary() if entry_address is None
              else transport.boundary(entry_address=entry_address))

    expected_address = addresses[world_symbol] if entry_address is None else entry_address
    transport.target.BreakpointCreateByAddress.assert_called_once_with(expected_address)
    resolved_symbols = [call.args[0] for call in transport.address.call_args_list]
    assert resolved_symbols == ([focus_symbol, world_symbol, lua_state_symbol]
                                if entry_address is None else [focus_symbol, lua_state_symbol])
    assert result == (thread, 0x5000, breakpoint)
    breakpoint.SetEnabled.assert_called_once_with(False)
    transport.target.BreakpointDelete.assert_not_called()
    transport.resume.assert_called_once()
    assert transport.resume.call_args.kwargs == {'breakpoint_expected': True}
    assert transport.focus_original == b'\x01'

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
    assert transport.process.stops == 1
    send_signal.assert_not_called()
assert transport.tainted

# Pre-mutation boundary.initial_stop failure in _execute_lldb or
# install_command_mailbox leaves the target untouched: it must neither attempt
# a redundant cleanup stop nor falsely taint/poison a healthy live session.
for fail_reason, expected_code in (
    (None, 'process_timeout'),
    ('simulated LLDB stop error', 'stop_failed'),
):
    pre_exec = make_transport(fake_lldb.eStateRunning)
    pre_exec.process.stop_error = fail_reason
    pre_exec.tainted = False
    pre_exec.alive = lambda: True
    pre_exec.target = Mock()
    clock = [0, 0, 1, 2, 4, 5, 6] if fail_reason is None else [0, 0, 0, 1, 2]
    with patch('time.monotonic', side_effect=clock), patch('time.sleep'), patch('os.kill') as send_signal:
        try:
            pre_exec._execute_lldb('return 1')
        except TransportError as error:
            assert error.code == expected_code, (fail_reason, error.code)
            assert json.loads(error.diagnostic)['phase'] == 'boundary.initial_stop'
        else:
            raise AssertionError('boundary.initial_stop failure was hidden in _execute_lldb')
        assert pre_exec.process.stops == 1, 'pre-mutation failure triggered execute.cleanup_stop'
        send_signal.assert_not_called()
    assert not pre_exec.tainted, 'pre-mutation boundary.initial_stop tainted transport'
    assert not pre_exec._boundary_initial_stop_pending

mailbox_pre = make_transport(fake_lldb.eStateRunning)
mailbox_pre.process.stop_error = 'simulated LLDB stop error'
mailbox_pre.tainted = False
mailbox_pre.alive = lambda: True
mailbox_pre.target = Mock()
mailbox_pre.restore_focus = Mock()
mailbox_pre.resume = Mock()
mailbox_fake = types.SimpleNamespace(path='/tmp/fixture-mailbox', poisoned=0, poison=lambda: None)
poison_calls = []
mailbox_fake.poison = lambda: poison_calls.append('poisoned')
library_fake = types.SimpleNamespace(main_update=0x5000)
try:
    install_command_mailbox(mailbox_pre, fake_lldb, mailbox_fake, library_fake)
except TransportError as error:
    assert error.code == 'stop_failed'
    assert json.loads(error.diagnostic)['phase'] == 'boundary.initial_stop'
else:
    raise AssertionError('boundary.initial_stop failure was hidden in install_command_mailbox')
assert mailbox_pre.process.stops == 1
assert not mailbox_pre.tainted
assert not mailbox_pre._boundary_initial_stop_pending
assert poison_calls == []
mailbox_pre.restore_focus.assert_not_called()
mailbox_pre.resume.assert_not_called()

# An acknowledged stop may complete at the state-observation deadline. Even
# though boundary.initial_stop raises before Lua mutation, the process can be
# left stopped. Release the known stop, retain the original timeout, and skip
# redundant cleanup without poisoning a recovered session.
def make_late_initial_stop_transport():
    transport = make_transport(fake_lldb.eStateRunning)
    transport.tainted = False
    transport.alive = lambda: True
    transport.target = Mock()

    def late_stop(*args, **kwargs):
        transport.process.stops += 1
        transport.process.state = fake_lldb.eStateStopped
        raise TransportError("process_timeout", "stop observation missed deadline")

    transport.stop = Mock(side_effect=late_stop)
    transport.resume = Mock(
        side_effect=lambda deadline: setattr(transport.process, "state", fake_lldb.eStateRunning)
    )
    return transport


late_exec = make_late_initial_stop_transport()
try:
    late_exec._execute_lldb("return 1")
except TransportError as error:
    assert error.code == "process_timeout", error.code
else:
    raise AssertionError("late initial stop timeout was hidden")
assert late_exec.process.state == fake_lldb.eStateRunning
assert late_exec.process.stops == 1, "late stop caused a redundant cleanup stop"
late_exec.resume.assert_called_once()
assert not late_exec.tainted
assert not late_exec._boundary_initial_stop_pending

late_mailbox = make_late_initial_stop_transport()
late_poison = []
late_mailbox_object = types.SimpleNamespace(
    path="/tmp/fixture-mailbox", poison=lambda: late_poison.append("poisoned")
)
try:
    install_command_mailbox(late_mailbox, fake_lldb, late_mailbox_object, library_fake)
except TransportError as error:
    assert error.code == "process_timeout", error.code
else:
    raise AssertionError("late mailbox installation stop timeout was hidden")
assert late_mailbox.process.state == fake_lldb.eStateRunning
assert late_mailbox.process.stops == 1
late_mailbox.resume.assert_called_once()
assert not late_mailbox.tainted and late_poison == []

# A failed release of that known debugger-owned stop is a recovery failure.
late_release_failure = make_late_initial_stop_transport()
late_release_failure.resume.side_effect = TransportError("resume_failed", "cannot release stopped process")
try:
    late_release_failure._execute_lldb("return 1")
except TransportError as error:
    assert error.code == "resume_failed", error.code
else:
    raise AssertionError("failed release of a late stop was hidden")
assert late_release_failure.tainted, "failure to release a stop cannot leave a trusted session"
assert not late_release_failure._boundary_initial_stop_pending

# Failed release during mailbox installation also taints and skips redundant cleanup.
late_mailbox_release_failure = make_late_initial_stop_transport()
late_mailbox_release_failure.resume.side_effect = TransportError("resume_failed", "cannot release stopped process")
late_mailbox_failure_poison = []
late_mailbox_failure_object = types.SimpleNamespace(
    path="/tmp/fixture-mailbox", poison=lambda: late_mailbox_failure_poison.append("poisoned")
)
try:
    install_command_mailbox(late_mailbox_release_failure, fake_lldb, late_mailbox_failure_object, library_fake)
except TransportError as error:
    assert error.code == "resume_failed", error.code
else:
    raise AssertionError("failed mailbox late-stop release was hidden")
assert late_mailbox_release_failure.process.stops == 1
assert late_mailbox_release_failure.tainted
assert not late_mailbox_release_failure._boundary_initial_stop_pending
assert late_mailbox_failure_poison == []

# Unmocked stop/wait_state/resume releases a stop that arrives during the final sleep.
unmocked_late = make_transport(fake_lldb.eStateRunning)
unmocked_late.tainted = False
unmocked_late.alive = lambda: True
unmocked_late.target = Mock()
unmocked_late.process.GetStopID = lambda: 1
unmocked_late.process.Continue = lambda: (
    setattr(unmocked_late.process, "state", fake_lldb.eStateRunning),
    StopError(False, ""),
)[1]
with patch("time.monotonic", side_effect=[0, 0, 1, 2, 4, 5, 6, 7]), patch(
    "time.sleep", side_effect=lambda _: setattr(unmocked_late.process, "state", fake_lldb.eStateStopped)
):
    try:
        unmocked_late._execute_lldb("return 1")
    except TransportError as error:
        assert error.code == "process_timeout", error.code
    else:
        raise AssertionError("unmocked late initial stop timeout was hidden")
assert unmocked_late.process.state == fake_lldb.eStateRunning
assert unmocked_late.process.stops == 1
assert not unmocked_late.tainted
assert not unmocked_late._boundary_initial_stop_pending

# Terminal disconnect during initial stop or late-stop release must not re-probe or taint.
disconnect_exec = make_transport(fake_lldb.eStateRunning)
disconnect_exec.tainted = False
disconnect_exec.alive = lambda: True
disconnect_exec.target = Mock()
disconnect_states = iter((fake_lldb.eStateRunning, fake_lldb.eStateExited))
disconnect_exec.process.GetState = lambda: next(disconnect_states)
try:
    disconnect_exec._execute_lldb("return 1")
except TransportError as error:
    assert error.code == "disconnected", error.code
else:
    raise AssertionError("disconnect during boundary.initial_stop was hidden")
assert disconnect_exec.process.stops == 1
assert not disconnect_exec.tainted
assert not disconnect_exec._boundary_initial_stop_pending

late_disconnect_release = make_late_initial_stop_transport()
late_disconnect_release.resume.side_effect = TransportError("disconnected", "process exited during resume")
try:
    late_disconnect_release._execute_lldb("return 1")
except TransportError as error:
    assert error.code == "disconnected", error.code
else:
    raise AssertionError("disconnect during late-stop release was hidden")
assert not late_disconnect_release.tainted
assert not late_disconnect_release._boundary_initial_stop_pending

# Post-initial-stop failure inside install_command_mailbox (after the target was
# paused) still cleans up and taints/poisons if cleanup fails.
mailbox_post = make_transport(fake_lldb.eStateRunning)
mailbox_post.tainted = False
mailbox_post.alive = lambda: True
mailbox_post.target = Mock()
mailbox_post.boundary = Mock(side_effect=TransportError('lua_error', 'post-stop failure'))
mailbox_post.restore_focus = Mock()
mailbox_post.resume = Mock()
mailbox_post.process.stop_error = 'cleanup stop error'
post_poison_calls = []
mailbox_fake2 = types.SimpleNamespace(path='/tmp/fixture-mailbox', poison=lambda: post_poison_calls.append('poisoned'))
try:
    install_command_mailbox(mailbox_post, fake_lldb, mailbox_fake2, library_fake)
except TransportError as error:
    assert error.code == 'stop_failed'
    assert json.loads(error.diagnostic)['phase'] == 'mailbox.install_cleanup'
else:
    raise AssertionError('post-initial-stop cleanup failure was hidden')
assert mailbox_post.process.stops == 1
assert mailbox_post.tainted
assert post_poison_calls == ['poisoned']

# Already tainted or quarantined sessions fail closed BEFORE entering cleanup
# try/finally in _execute_lldb and install_command_mailbox (never running
# redundant cleanup stops or altering cleanup error codes).
for pre_state, expected_code in (('tainted', 'restart_required'), ('quarantined', 'detach_failed')):
    exec_rejected = make_transport(fake_lldb.eStateRunning)
    exec_rejected.tainted = pre_state == 'tainted'
    exec_rejected._cleanup_pending = pre_state == 'quarantined'
    exec_rejected._cleanup_failure = ('lldb_detach', 'stuck detach') if pre_state == 'quarantined' else None
    exec_rejected.alive = lambda: True
    exec_rejected.restore_focus = Mock()
    exec_rejected.resume = Mock()
    try:
        exec_rejected._execute_lldb('return 1')
    except TransportError as error:
        assert error.code == expected_code, (pre_state, error.code)
    else:
        raise AssertionError(f'_execute_lldb entered on {pre_state} session')
    assert exec_rejected.process.stops == 0
    exec_rejected.restore_focus.assert_not_called()
    exec_rejected.resume.assert_not_called()

    mb_rejected = make_transport(fake_lldb.eStateRunning)
    mb_rejected.tainted = pre_state == 'tainted'
    mb_rejected._cleanup_pending = pre_state == 'quarantined'
    mb_rejected._cleanup_failure = ('lldb_detach', 'stuck detach') if pre_state == 'quarantined' else None
    mb_rejected.alive = lambda: True
    mb_rejected.restore_focus = Mock()
    mb_rejected.resume = Mock()
    rejected_poison = []
    mb_fake = types.SimpleNamespace(path='/tmp/fixture-mailbox', poison=lambda: rejected_poison.append('poisoned'))
    try:
        install_command_mailbox(mb_rejected, fake_lldb, mb_fake, library_fake)
    except TransportError as error:
        assert error.code == expected_code, (pre_state, error.code)
    else:
        raise AssertionError(f'install_command_mailbox entered on {pre_state} session')
    assert mb_rejected.process.stops == 0
    assert rejected_poison == []
    mb_rejected.restore_focus.assert_not_called()
    mb_rejected.resume.assert_not_called()

# install_command_mailbox process_timeout during boundary.initial_stop also skips
# cleanup stop, tainting and poisoning.
mailbox_timeout = make_transport(fake_lldb.eStateRunning)
mailbox_timeout.tainted = False
mailbox_timeout.alive = lambda: True
mailbox_timeout.target = Mock()
mailbox_timeout.restore_focus = Mock()
mailbox_timeout.resume = Mock()
timeout_poison = []
mailbox_fake_timeout = types.SimpleNamespace(path='/tmp/fixture-mailbox', poison=lambda: timeout_poison.append('poisoned'))
with patch('time.monotonic', side_effect=[0, 0, 1, 2, 4, 5]), patch('time.sleep'), patch('os.kill') as send_signal:
    try:
        install_command_mailbox(mailbox_timeout, fake_lldb, mailbox_fake_timeout, library_fake)
    except TransportError as error:
        assert error.code == 'process_timeout'
        assert json.loads(error.diagnostic)['phase'] == 'boundary.initial_stop'
    else:
        raise AssertionError('mailbox initial_stop timeout was hidden')
    send_signal.assert_not_called()
assert mailbox_timeout.process.stops == 1
assert not mailbox_timeout.tainted
assert not mailbox_timeout._boundary_initial_stop_pending
assert timeout_poison == []

# Real boundary() (unmocked) that passes boundary.initial_stop and then fails
# inside post-stop boundary steps clears _boundary_initial_stop_pending and
# still triggers execute.cleanup_stop / mailbox.install_cleanup + taint/poison.
def make_post_initial_stop_fail_transport(cleanup_stop_error):
    t = make_transport(fake_lldb.eStateStopped)
    t.tainted = False
    t.alive = lambda: True
    t.focus_original = None
    t.target = Mock()
    t.address = Mock(return_value=0x1000)
    t.process.ReadMemory = Mock(return_value=b'\x99')  # invalid focus flag -> incompatible AFTER initial_stop
    # On initial_stop GetState is Stopped (no Stop() call); on cleanup stop we flip to Running + fail Stop().
    calls = {'n': 0}
    def get_state():
        calls['n'] += 1
        return fake_lldb.eStateStopped if calls['n'] == 1 else fake_lldb.eStateRunning
    t.process.GetState = get_state
    orig_stop = t.process.Stop
    def failing_cleanup_stop():
        t.process.stop_error = cleanup_stop_error
        return orig_stop()
    t.process.Stop = failing_cleanup_stop
    return t

real_exec_post = make_post_initial_stop_fail_transport('cleanup stop error')
try:
    real_exec_post._execute_lldb('return 1')
except TransportError as error:
    assert error.code == 'stop_failed'
    assert json.loads(error.diagnostic) == {
        'phase': 'execute.cleanup_stop',
        'expectedStates': [fake_lldb.eStateStopped],
        'lastObservedState': fake_lldb.eStateRunning,
        'lldbError': 'cleanup stop error',
        'primary_error_code': 'incompatible',
    }
else:
    raise AssertionError('real boundary post-stop failure did not run execute cleanup')
assert real_exec_post.process.stops == 1
assert real_exec_post.tainted
assert not real_exec_post._boundary_initial_stop_pending

real_mb_post = make_post_initial_stop_fail_transport('mailbox cleanup stop error')
real_mb_poison = []
real_mb_fake = types.SimpleNamespace(path='/tmp/fixture-mailbox', poison=lambda: real_mb_poison.append('poisoned'))
try:
    install_command_mailbox(real_mb_post, fake_lldb, real_mb_fake, library_fake)
except TransportError as error:
    assert error.code == 'stop_failed'
    assert json.loads(error.diagnostic) == {
        'phase': 'mailbox.install_cleanup',
        'expectedStates': [fake_lldb.eStateStopped],
        'lastObservedState': fake_lldb.eStateRunning,
        'lldbError': 'mailbox cleanup stop error',
    }
else:
    raise AssertionError('real boundary post-stop failure did not run mailbox cleanup')
assert real_mb_post.process.stops == 1
assert real_mb_post.tainted
assert real_mb_poison == ['poisoned']
assert not real_mb_post._boundary_initial_stop_pending

print("hades2_transport_stop_ok")
