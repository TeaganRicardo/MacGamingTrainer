"""Rosetta attach, Time Warp error propagation, timeout budgets, and EOF cleanup contracts."""
from pathlib import Path
import sys
import tempfile
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from core.adapter import AdapterError, GameAdapterContext
from games.hades.adapter import HadesAdapter
from games.hades.client import HadesRuntimeClient
from games.hades.lldb_worker import HadesLLDBWorker
from games.hades.preferences import HadesPreferenceStore
from games.hades.recovery import HadesRecoveryJournal
from games.hades.schema import DEFAULT_FEATURES, DEFERRED_TRAIT_COMMANDS
from games.hades.time_warp_worker import HadesTimeWarpWorker

fake_lldb = types.SimpleNamespace(
    SBError=lambda: types.SimpleNamespace(Fail=lambda: False, Success=lambda: True),
    eStateInvalid=0, eStateStopped=5, eStateRunning=6, eStateDetached=9, eStateExited=10,
    eStopReasonNone=1, eStopReasonBreakpoint=3,
)
with patch.dict(sys.modules, {'lldb': fake_lldb}), patch('subprocess.check_output', return_value=''):
    from games.hades import transport as transport_module


# 1. HadesTimeWarpWorker.close() must still detach/destroy debugger when reset()
# fails before taint (stop_timeout, runtime_not_ready, verify_failed, etc.),
# while still preserving attachment on outcome_unknown / already-tainted failures.
class TransportStub:
    pid = 42

    def __init__(self, *, tainted=False):
        self.attached = True
        self.tainted = tainted
        self.cleanup_pending = False
        self.vm_interrupted = False
        self.closes = 0

    def alive(self):
        return self.attached

    def close(self):
        self.closes += 1
        self.attached = False


class FailingTimeWarp:
    def __init__(self, error):
        self.error = error

    def reset(self):
        raise self.error

    def reset_for_close(self):
        raise self.error


for code, key in (
    ('stop_timeout', 'hades.error.stopTimeout'),
    ('stop_failed', 'hades.error.stopTimeout'),
    ('runtime_not_ready', 'hades.error.runtimeNotReady'),
    ('time_warp_verify_failed', 'host.timeWarp.error.verifyFailed'),
):
    clean_transport = TransportStub()
    worker = HadesTimeWarpWorker(
        transport=clean_transport,
        time_warp_factory=lambda _: FailingTimeWarp(AdapterError(code, key)),
    )
    try:
        worker.close()
    except AdapterError as error:
        assert error.code == code
    else:
        raise AssertionError(f'clean reset failure {code} was hidden')
    assert clean_transport.closes == 1 and not clean_transport.attached, (
        f'non-tainting EOF reset failure {code} leaked debugger attachment'
    )

unknown_transport = TransportStub()
unknown_worker = HadesTimeWarpWorker(
    transport=unknown_transport,
    time_warp_factory=lambda _: FailingTimeWarp(AdapterError('outcome_unknown', 'hades.error.outcomeUnknown')),
)
try:
    unknown_worker.close()
except AdapterError as error:
    assert error.code == 'outcome_unknown'
else:
    raise AssertionError('outcome_unknown EOF reset failure was hidden')
assert unknown_transport.closes == 0 and unknown_transport.attached

exited_tainted = TransportStub(tainted=True)
exited_worker = HadesTimeWarpWorker(
    transport=exited_tainted,
    time_warp_factory=lambda _: FailingTimeWarp(AdapterError('not_connected', 'hades.error.notConnected')),
)
try:
    exited_worker.close()
except AdapterError as error:
    assert error.code == 'not_connected'
else:
    raise AssertionError('not_connected reset_for_close failure was hidden')
assert exited_tainted.closes == 1 and not exited_tainted.attached


# 2. HadesAdapter.dispatch('connect') must surface terminal speed reconciliation
# failures (outcome_unknown / restart_required / debugger_lost) instead of returning
# an offline snapshot as success, while keeping healthy connections for recoverable errors.
class FakeRuntime:
    def __init__(self, speed_error):
        self.connected = False
        self.speed_error = speed_error
        self.state = {
            'connected': True, 'pid': 42, 'heroReady': True,
            'heroId': 'gen:run:hero', 'target': {'heroId': 'gen:run:hero'},
            'features': dict(DEFAULT_FEATURES), 'health': 50, 'maxHealth': 100,
            'money': 25, 'resources': {}, 'traits': [], 'invincible': False,
        }

    def connect(self, pid, executable, features=None):
        self.connected = True
        return dict(self.state)

    def current_game_speed(self):
        return 1.0

    def set_game_speed(self, value):
        if self.speed_error.code in ('outcome_unknown', 'restart_required', 'debugger_lost'):
            self.connected = False
        raise self.speed_error

    def command(self, name, params):
        return dict(self.state)

    def close(self):
        pass


context = GameAdapterContext('hades', 'Hades', 2, ROOT / 'Backend/games/hades', {})
with tempfile.TemporaryDirectory(prefix='hades-connect-speed-') as directory:
    store = HadesPreferenceStore(Path(directory) / 'preferences.json')
    prefs = store.load()
    prefs['gameSpeed'] = 1.6
    store.save(prefs)

    for terminal_error in (
        AdapterError('outcome_unknown', 'hades.error.outcomeUnknown'),
        AdapterError('restart_required', 'hades.error.restartRequired'),
        AdapterError('debugger_lost', 'hades.error.debuggerLost'),
    ):
        adapter = HadesAdapter(
            context,
            runtime=FakeRuntime(terminal_error),
            locate_process=lambda: (42, '/tmp/Hades/Game.macOS'),
            preferences=store,
        )
        try:
            adapter.dispatch('connect', {}, 'connect-fails')
        except AdapterError as error:
            assert error.code == terminal_error.code
        else:
            raise AssertionError(f'connect swallowed terminal speed failure {terminal_error.code}')
        assert not adapter.connected

    recoverable = HadesAdapter(
        context,
        runtime=FakeRuntime(AdapterError('time_warp_verify_failed', 'host.timeWarp.error.verifyFailed', arguments=('1.6', '1'))),
        locate_process=lambda: (42, '/tmp/Hades/Game.macOS'),
        preferences=store,
    )
    connected_state = recoverable.dispatch('connect', {}, 'connect-recoverable-speed')
    assert connected_state['connected'] is True
    assert connected_state['features']['gameSpeed']['errorPresentation'] == 'host.timeWarp.error.verifyFailed'


# 3. HadesLLDBWorker.dispatch('connect') must roll back untainted attachment when
# initial configure fails, while preserving tainted/interrupted quarantine.
class ConnectRollbackTransport:
    def __init__(self, configure_error, *, tainted_on_error=False, detach_error=None):
        self.pid = None
        self.process = None
        self.tainted = False
        self.vm_interrupted = False
        self.cleanup_pending = False
        self.cleanup_failure = None
        self.configure_error = configure_error
        self.tainted_on_error = tainted_on_error
        self.detach_error = detach_error
        self.detaches = 0

    def alive(self):
        return self.pid is not None

    def attach(self, pid, executable):
        self.pid = pid
        self.process = object()

    def execute(self, source, *, mutating):
        if self.tainted_on_error:
            self.tainted = True
        raise self.configure_error

    def _quarantined_error(self):
        return AdapterError('detach_failed', 'hades.error.detachFailed', diagnostic='rollback detach failed')

    def _rollback_failed_attach(self, error):
        return transport_module.HadesLuaTransport._rollback_failed_attach(self, error)

    def detach(self):
        self.detaches += 1
        if self.detach_error is not None:
            self.cleanup_pending = True
            self.cleanup_failure = ('lldb_detach', self.detach_error.diagnostic or str(self.detach_error))
            raise self.detach_error
        self.pid = None
        self.process = None


clean_connect = ConnectRollbackTransport(AdapterError('runtime_not_ready', 'hades.error.runtimeNotReady'))
try:
    HadesLLDBWorker(clean_connect).dispatch('connect', {'pid': 42, 'executable': '/tmp/Hades/Game.macOS'})
except AdapterError as error:
    assert error.code == 'runtime_not_ready'
else:
    raise AssertionError('failed configure unexpectedly succeeded')
assert clean_connect.detaches == 1 and not clean_connect.alive(), 'failed clean configure leaked attachment'

tainted_connect = ConnectRollbackTransport(
    AdapterError('outcome_unknown', 'hades.error.outcomeUnknown'), tainted_on_error=True
)
try:
    HadesLLDBWorker(tainted_connect).dispatch('connect', {'pid': 42, 'executable': '/tmp/Hades/Game.macOS'})
except AdapterError as error:
    assert error.code == 'outcome_unknown'
else:
    raise AssertionError('tainted configure unexpectedly succeeded')
assert tainted_connect.detaches == 0 and tainted_connect.alive()

failed_rollback = ConnectRollbackTransport(
    AdapterError('unexpected_stop', 'hades.error.unexpectedStop'),
    detach_error=AdapterError('detach_failed', 'hades.error.detachFailed', diagnostic='detach rejected'),
)
try:
    HadesLLDBWorker(failed_rollback).dispatch('connect', {'pid': 42, 'executable': '/tmp/Hades/Game.macOS'})
except AdapterError as error:
    assert error.code == 'unexpected_stop'
    assert 'rollback lldb_detach failed' in (error.diagnostic or '')
else:
    raise AssertionError('failed rollback masked unexpected_stop')
assert failed_rollback.cleanup_pending and failed_rollback.alive()


# 4. HadesRuntimeClient sidecar timeouts and Swift request timeouts stay aligned:
# connect=90s, deferred trait commands=50s, single-boundary commands=22s, and every
# HadesModule.swift command timeout exceeds the worst-case sequential RPC sum.
class TimeoutSidecar:
    started = True
    terminal = False

    def __init__(self):
        self.reply_timeout_seconds = None
        self.recorded = []

    def request(self, method, params, **options):
        self.recorded.append((method, self.reply_timeout_seconds))
        if method == 'time_warp.current_speed':
            return {'result': {'connected': True, 'pid': 42, 'gameSpeed': 1.0}}
        if method == 'time_warp.set_speed':
            return {'result': {'connected': True, 'pid': 42, 'gameSpeed': params['value']}}
        return {'result': {'connected': True, 'pid': 42, 'heroReady': True}}


with tempfile.TemporaryDirectory(prefix='hades-timeouts-') as directory:
    sidecar = TimeoutSidecar()
    client = HadesRuntimeClient(
        sidecar, recovery=HadesRecoveryJournal(Path(directory) / 'r.json'), identity=lambda pid: str(pid)
    )
    client.connect(42, '/tmp/Hades/Game.macOS')
    client.current_game_speed()
    client.set_game_speed(1.5)
    for trait_command in DEFERRED_TRAIT_COMMANDS:
        client.command(trait_command, {})
    assert sidecar.recorded == [
        ('connect', 90),
        ('time_warp.current_speed', 22),
        ('time_warp.set_speed', 22),
    ] + [(command, 50) for command in DEFERRED_TRAIT_COMMANDS], sidecar.recorded

from games.hades.command_contract import command_budget_audit, command_metadata

hades_module_swift = (ROOT / 'Sources/Hades/HadesModule.swift').read_text(encoding='utf-8')
hades_command_swift = (ROOT / 'Sources/Hades/Generated/HadesCommand.generated.swift').read_text(encoding='utf-8')
assert 'request.command.timeout' in hades_module_swift
metadata = {row['name']: row for row in command_metadata()}
assert metadata['connect']['timeoutSeconds'] == 190.0 and 190 > 90 + 4 * 22
assert metadata['load_profile']['timeoutSeconds'] == 120.0 and 120 > 5 * 22
for command in ('add_trait', 'update_trait', 'remove_trait', 'set_trait_uses', 'expire_trait', 'refresh_trait', 'add_chaos_pair'):
    assert metadata[command]['timeoutSeconds'] == 60.0 and 60 > 50, command
assert set(('add_trait', 'update_trait', 'remove_trait', 'set_trait_uses', 'expire_trait', 'refresh_trait', 'add_chaos_pair')) == set(DEFERRED_TRAIT_COMMANDS)
for command in ('set_feature', 'disable_all', 'lock_vital', 'lock_resource', 'lock_rerolls', 'set_value'):
    assert metadata[command]['timeoutSeconds'] == 55.0 and 55 > 2 * 22, command
assert metadata['status']['timeoutSeconds'] == 30.0 and 30 > 22
assert 'case .connect: return 190.0' in hades_command_swift
assert 'default: return 30.0' in hades_command_swift
for row in command_budget_audit():
    assert row['timeoutSeconds'] > row['worstCaseInnerSeconds'], row


# 5. _boundary() must grant _resume()/breakpoint wait a fresh 3s budget after _stop()
# and report thread stop reasons when unexpected_stop fires.
clock = [0.0]


def make_boundary_transport(*, stop_cost=0.0, hit_breakpoint=True, stop_reason=1):
    running = [True]
    bp = types.SimpleNamespace(GetID=lambda: 7, SetEnabled=lambda enabled: None)
    main_thread = types.SimpleNamespace(
        GetStopReason=lambda: fake_lldb.eStopReasonBreakpoint if hit_breakpoint else stop_reason,
        GetStopReasonDataAtIndex=lambda i: 7 if hit_breakpoint else 17,
        GetName=lambda: 'MainThread',
        GetThreadID=lambda: 101,
    )
    transport = transport_module.HadesLuaTransport.__new__(transport_module.HadesLuaTransport)
    transport.pid = 42
    transport._cleanup_pending = False
    transport.focus_original = None
    transport.addresses = {
        '_ZN3sgg13ConfigOptions20RequireFocusToUpdateE': 100,
        '_ZN3sgg3App6UpdateEf': 200,
        '_ZN3sgg13ScriptManager13LUA_INTERFACEE': 300,
    }
    transport.target = types.SimpleNamespace(BreakpointCreateByAddress=lambda addr: bp)
    class BoundaryProcess:
        def ReadMemory(self, addr, n, err):
            return b'\x01'

        def WriteMemory(self, addr, val, err):
            return len(val)

        def ReadPointerFromMemory(self, addr, err):
            return 0xdeadbeef

        def GetState(self):
            return fake_lldb.eStateRunning if running[0] else fake_lldb.eStateStopped

        def __iter__(self):
            return iter([main_thread])

    transport.process = BoundaryProcess()
    transport._running = running
    transport.tainted = False
    transport.alive = lambda: True
    transport._drain = lambda: None
    transport._restore_focus = lambda: None

    def slow_stop(deadline):
        clock[0] += stop_cost
        running[0] = False

    def fast_resume(deadline, **kwargs):
        clock[0] += 0.5
        assert deadline > clock[0], f'_stop starved _resume deadline: {clock[0]} >= {deadline}'
        running[0] = False if kwargs.get('breakpoint_expected') else True

    transport._stop = slow_stop
    transport._resume = fast_resume
    return transport


clock[0] = 0.0
with patch.object(transport_module.time, 'monotonic', side_effect=lambda: clock[0]):
    t_slow_stop = make_boundary_transport(stop_cost=2.8, hit_breakpoint=True)
    thread, state = t_slow_stop._boundary()
    assert state == 0xdeadbeef

clock[0] = 0.0
with patch.object(transport_module.time, 'monotonic', side_effect=lambda: clock[0]):
    t_unexpected = make_boundary_transport(stop_cost=0.0, hit_breakpoint=False, stop_reason=5)
    try:
        t_unexpected._boundary()
    except AdapterError as error:
        assert error.code == 'unexpected_stop'
        assert 'MainThread#101:reason=5' in (error.diagnostic or ''), error.diagnostic
    else:
        raise AssertionError('unexpected stop succeeded')

# Late physical stop inside _boundary()'s initial _stop() must release Hades back
# to running rather than stranding it stopped while leaving _boundary_initial_stop_pending=True.
t_late_stop = make_boundary_transport()
resumed = []

def late_physical_stop(deadline):
    t_late_stop._running[0] = False
    raise AdapterError('stop_timeout', 'hades.error.stopTimeout')

def record_resume(deadline, **kwargs):
    resumed.append(deadline)
    t_late_stop._running[0] = True

t_late_stop._stop = late_physical_stop
t_late_stop._resume = record_resume
t_late_stop.process.Continue = lambda: fake_lldb.SBError()
try:
    t_late_stop._boundary()
except AdapterError as error:
    assert error.code == 'stop_timeout'
else:
    raise AssertionError('late stop unexpectedly succeeded')
assert resumed and t_late_stop._running[0] is True and not t_late_stop.tainted

print('hades_rosetta_attach_cleanup_ok')
