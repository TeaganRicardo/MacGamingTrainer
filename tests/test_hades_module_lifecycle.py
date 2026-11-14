"""Hades debugger state ownership and irreversible best-effort quit cleanup."""
from pathlib import Path
import subprocess
import sys
import tempfile
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
from core.adapter import AdapterError


class Error:
    def __init__(self, fail=False, message='synthetic lldb error'):
        self._fail = fail
        self._message = message

    def Fail(self):
        return self._fail

    def __str__(self):
        return self._message


fake_lldb = types.SimpleNamespace(
    SBError=Error, LLDB_INVALID_ADDRESS=-1,
    eStateInvalid=0, eStateStopped=5, eStateRunning=6, eStateDetached=9, eStateExited=10,
)
with patch.dict(sys.modules, {'lldb': fake_lldb}), patch('subprocess.check_output', return_value=''):
    from games.hades.transport import HadesLuaTransport


class Process:
    def __init__(self, state, focus=b'\x00', *, release_failed=False):
        self.state = state
        self.focus = focus
        self.writes = []
        self.write_failed = False
        self.release_failed = release_failed

    def GetState(self):
        return self.state

    def WriteMemory(self, address, value, error):
        self.writes.append((address, value))
        if self.write_failed:
            return 0
        self.focus = value
        return len(value)

    def ReadMemory(self, address, count, error):
        return self.focus

    def Detach(self):
        if not self.release_failed:
            self.state = fake_lldb.eStateDetached
        return Error(fail=self.release_failed, message='synthetic detach error')


focus_symbol = '_ZN3sgg13ConfigOptions20RequireFocusToUpdateE'
executable = '/tmp/Hades/Game.macOS.app/Contents/MacOS/Game.macOS'
old_process = Process(fake_lldb.eStateExited)
new_process = Process(fake_lldb.eStateStopped)
image = types.SimpleNamespace(
    GetFileSpec=lambda: executable, GetUUIDString=lambda: 'fixture-uuid',
    GetObjectFileHeaderAddress=lambda: types.SimpleNamespace(GetLoadAddress=lambda target: 1000),
)
target = types.SimpleNamespace(
    AttachToProcessWithID=lambda listener, pid, error: new_process,
    GetModuleAtIndex=lambda index: image, GetTriple=lambda: 'x86_64-apple-macosx',
    DeleteAllBreakpoints=lambda: None,
)
transport = HadesLuaTransport.__new__(HadesLuaTransport)
transport.manifest = {'symbols': {focus_symbol: {'rva': 16}}}
transport.supported_build = {'uuid': 'fixture-uuid', 'architecture': 'x86_64'}
transport.debugger = types.SimpleNamespace(CreateTarget=lambda path: target)
transport.listener = None
transport.target = target
transport.process = old_process
transport.pid = 42
transport.addresses = {focus_symbol: 200}
transport.focus_original = b'\x01'
transport._tainted_pid = None
transport._unsafe_vm_pid = 42
transport._drain = lambda: None
transport._resume = lambda deadline: None
transport._stop = lambda deadline: None

# The old process died during a leased call; its saved focus byte cannot own
# memory in the replacement process, whose original focus byte differs.
transport.attach(43, executable)
transport._restore_focus()
assert transport.pid == 43 and transport.process is new_process
assert transport._unsafe_vm_pid is None, 'a dead VM diagnosis leaked into a replacement attachment'
assert transport.focus_original is None
assert new_process.writes == [] and new_process.focus == b'\x00', 'old PID focus state leaked into a new process'

# A live failed restoration must retain ownership so disconnect can be retried.
transport.focus_original = b'\x01'
new_process.write_failed = True
try:
    transport.detach()
except AdapterError as error:
    assert error.code == 'restore_failed'
else:
    raise AssertionError('live focus restoration failure was hidden')
assert transport.process is new_process and transport.pid == 43
assert transport.focus_original == b'\x01' and transport.addresses[focus_symbol] == 1016
new_process.write_failed = False
transport.detach()
assert new_process.focus == b'\x01'
assert transport.process is None and transport.pid is None
assert transport.addresses == {} and transport.focus_original is None

# Failed attach rollback must keep the primary build error even if Detach fails,
# preserve quarantined process ownership, reject mutations, and recover once Detach works.
with patch.dict(sys.modules, {'lldb': fake_lldb}):
    from debugger.lldb_time_warp import LLDBProcessTimeWarpDriver, ProcessTimeWarpError
    from games.hades.lldb_worker import HadesLLDBWorker
    from games.hades.time_warp_worker import HadesTimeWarpWorker

destroyed_debuggers = []
fake_lldb.SBDebugger = types.SimpleNamespace(Destroy=lambda dbg: destroyed_debuggers.append(dbg))


def make_mismatched_target(proc):
    bad_image = types.SimpleNamespace(
        GetFileSpec=lambda: executable, GetUUIDString=lambda: 'wrong-uuid',
        GetObjectFileHeaderAddress=lambda: types.SimpleNamespace(GetLoadAddress=lambda target: 1000),
    )
    return types.SimpleNamespace(
        AttachToProcessWithID=lambda listener, pid, error: proc,
        GetModuleAtIndex=lambda index: bad_image, GetTriple=lambda: 'x86_64-apple-macosx',
        DeleteAllBreakpoints=lambda: None,
    )


bad_process = Process(fake_lldb.eStateStopped, release_failed=True)
bad_target = make_mismatched_target(bad_process)
transport.debugger = types.SimpleNamespace(
    CreateTarget=lambda path: bad_target,
    Destroy=lambda dbg: destroyed_debuggers.append(dbg),
)
try:
    transport.attach(44, executable)
except AdapterError as error:
    assert error.code == 'incompatible', f'expected incompatible, got {error.code}'
    assert error.presentation == 'hades.error.unsupportedBuild'
    assert 'rollback lldb_detach failed (pid=44 still attached): synthetic detach error' in (error.diagnostic or '')
else:
    raise AssertionError('mismatched attach build error was hidden')

assert transport.alive() is True
assert transport.cleanup_pending is True
assert transport.cleanup_failure == ('lldb_detach', 'synthetic detach error')
assert transport.process is bad_process and transport.pid == 44
assert bad_process.state == fake_lldb.eStateStopped

# Quarantined transport must block execution, boundary, TimeWarp, and worker commands.
for action in (
    lambda: transport.execute('return {}', mutating=True),
    lambda: transport._boundary(),
):
    try:
        action()
    except AdapterError as error:
        assert error.code == 'detach_failed'
        assert 'pid=44 still attached' in (error.diagnostic or '')
    else:
        raise AssertionError('quarantined transport allowed debugger execution')

with patch.dict(sys.modules, {'lldb': fake_lldb}):
    try:
        with LLDBProcessTimeWarpDriver(transport, fake_lldb).session():
            raise AssertionError('quarantined transport entered TimeWarp session')
    except ProcessTimeWarpError as error:
        assert error.code == 'detach_failed'
        assert error.presentation == 'host.timeWarp.error.restartRequired'

lldb_worker = HadesLLDBWorker(transport=transport)
for method, params in (('status', {}), ('set_feature', {'feature': 'godMode', 'value': True})):
    try:
        lldb_worker.dispatch(method, params)
    except AdapterError as error:
        assert error.code == 'detach_failed'
    else:
        raise AssertionError(f'quarantined HadesLLDBWorker allowed {method}')


class FakeTimeWarp:
    def __init__(self, wrapped):
        self.wrapped = wrapped
        self.reset_calls = 0

    def current_speed(self):
        return 1.0

    def set_speed(self, value):
        return float(value)

    def reset(self):
        self.reset_calls += 1
        return 1.0


tw_worker = HadesTimeWarpWorker(transport=transport, time_warp_factory=FakeTimeWarp)
for method, params in (
    ('time_warp.current_speed', {}),
    ('time_warp.set_speed', {'value': 2.0}),
    ('disconnect', {}),
    ('connect', {'pid': 44, 'executable': executable}),
):
    try:
        tw_worker.dispatch(method, params)
    except AdapterError as error:
        assert error.code == 'detach_failed', f'{method} returned {error.code}'
    else:
        raise AssertionError(f'quarantined HadesTimeWarpWorker allowed {method}')
assert tw_worker.time_warp.reset_calls == 0, 'disconnect ran TimeWarp reset on quarantined transport'
assert transport.process is bad_process and transport.pid == 44

# Re-attach cannot reuse quarantined attachment; once Detach succeeds, detach() clears ownership.
try:
    transport.attach(44, executable)
except AdapterError as error:
    assert error.code == 'detach_failed'
else:
    raise AssertionError('attach reused quarantined attachment')

bad_process.release_failed = False
transport.detach()
assert bad_process.state == fake_lldb.eStateDetached
assert not transport.alive() and transport.process is None and transport.pid is None
assert not transport.cleanup_pending and transport.cleanup_failure is None

# Recovery via worker.close() / transport.close() must skip TimeWarp reset, detach, and destroy debugger.
proc45 = Process(fake_lldb.eStateStopped, release_failed=True)
target45 = make_mismatched_target(proc45)
transport.debugger = types.SimpleNamespace(
    CreateTarget=lambda path: target45,
    Destroy=lambda dbg: destroyed_debuggers.append(dbg),
)
try:
    transport.attach(45, executable)
except AdapterError as error:
    assert error.code == 'incompatible'
assert transport.cleanup_pending and transport.pid == 45
proc45.release_failed = False
tw_close_worker = HadesTimeWarpWorker(transport=transport, time_warp_factory=FakeTimeWarp)
tw_close_worker.close()
assert tw_close_worker.time_warp.reset_calls == 0
assert proc45.state == fake_lldb.eStateDetached
assert destroyed_debuggers == [transport.debugger]
assert transport.process is None and transport.pid is None and not transport.cleanup_pending

# A terminal close must not destroy the debugger while Detach still fails.
proc47 = Process(fake_lldb.eStateStopped, release_failed=True)
target47 = make_mismatched_target(proc47)
debugger47 = types.SimpleNamespace(CreateTarget=lambda path: target47)
transport.debugger = debugger47
try:
    transport.attach(47, executable)
except AdapterError as error:
    assert error.code == 'incompatible'
else:
    raise AssertionError('failed attach did not enter cleanup quarantine')
destroyed_before = len(destroyed_debuggers)
try:
    transport.close()
except AdapterError as error:
    assert error.code == 'detach_failed'
else:
    raise AssertionError('failed close was silently accepted')
assert len(destroyed_debuggers) == destroyed_before
assert transport.debugger is debugger47 and transport.pid == 47
assert transport.cleanup_pending and proc47.state == fake_lldb.eStateStopped
proc47.release_failed = False
transport.close()
assert destroyed_debuggers[-1] is debugger47
assert transport.process is None and transport.pid is None and not transport.cleanup_pending

# External target exit clears stale quarantine cleanly on detach().
proc46 = Process(fake_lldb.eStateStopped, release_failed=True)
target46 = make_mismatched_target(proc46)
transport.debugger = types.SimpleNamespace(CreateTarget=lambda path: target46)
try:
    transport.attach(46, executable)
except AdapterError as error:
    assert error.code == 'incompatible'
assert transport.cleanup_pending and transport.pid == 46
proc46.state = fake_lldb.eStateExited
transport.detach()
assert not transport.alive() and transport.process is None and transport.pid is None
assert not transport.cleanup_pending and transport.cleanup_failure is None
print('hades_transport_focus_ownership_ok')

# The termination harness imports only Foundation, so it runs in the portable
# lane; the macOS lanes execute only Tools/macos_only_tests.txt.
model = (ROOT / 'Sources/Hades/HadesModule.swift').read_text()
start = model.index('    func prepareForTermination(')
termination = model[start:model.index('\n    private func send(', start)]
swift = r'''
import Foundation
final class Session {
    var events: [String] = []
    var diagnostics: [String] = []
    func flushDiagnostics() { events.append("flush") }
    func stop(suppressTerminationError: Bool) {
        precondition(suppressTerminationError)
        events.append("stop")
    }
}
final class ExitHarness {
    var connected = true
    var backendAvailable = true
    let session = Session()
    var failures: Set<String> = []
    func send(_ command: String, operation: String, announceSuccess: Bool,
              completion: @escaping (Bool) -> Void) {
        session.events.append(command)
        if failures.contains(command) { session.diagnostics.append("recovery: " + command) }
        completion(!failures.contains(command))
    }
''' + termination + r'''
}
@main struct Main {
    static func main() {
        let failureCases: [Set<String>] = [[], ["disable_all"], ["disconnect"], ["disable_all", "disconnect"]]
        for failures in failureCases {
            let model = ExitHarness()
            model.failures = failures
            var completions = 0
            model.prepareForTermination { completions += 1; model.session.events.append("complete") }
            precondition(model.session.events == ["disable_all", "disconnect", "flush", "stop", "complete"])
            precondition(Set(model.session.diagnostics) == Set(failures.map { "recovery: " + $0 }))
            precondition(completions == 1)
        }
        let offline = ExitHarness()
        offline.connected = false
        offline.prepareForTermination { offline.session.events.append("complete") }
        precondition(offline.session.events == ["disable_all", "disconnect", "flush", "stop", "complete"])
        let unavailable = ExitHarness()
        unavailable.connected = false
        unavailable.backendAvailable = false
        unavailable.prepareForTermination { unavailable.session.events.append("complete") }
        precondition(unavailable.session.events == ["flush", "stop", "complete"])
    }
}
'''
with tempfile.TemporaryDirectory(prefix='mgt-hades-lifecycle-') as directory:
    source = Path(directory) / 'Exit.swift'
    executable_path = Path(directory) / 'exit'
    source.write_text(swift)
    subprocess.run(['swiftc', '-parse-as-library', str(source), '-o', str(executable_path)], check=True)
    subprocess.run([str(executable_path)], check=True)
print('hades_termination_best_effort_ok')
