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
    def Fail(self):
        return False


fake_lldb = types.SimpleNamespace(
    SBError=Error, LLDB_INVALID_ADDRESS=-1,
    eStateInvalid=0, eStateStopped=5, eStateRunning=6, eStateDetached=9, eStateExited=10,
)
with patch.dict(sys.modules, {'lldb': fake_lldb}), patch('subprocess.check_output', return_value=''):
    from games.hades.transport import HadesLuaTransport


class Process:
    def __init__(self, state, focus=b'\x00'):
        self.state = state
        self.focus = focus
        self.writes = []
        self.write_failed = False

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
        self.state = fake_lldb.eStateDetached
        return Error()


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
transport.manifest = {'uuid': 'fixture-uuid', 'symbols': {focus_symbol: {'rva': 16}}}
transport.debugger = types.SimpleNamespace(CreateTarget=lambda path: target)
transport.listener = None
transport.target = target
transport.process = old_process
transport.pid = 42
transport.addresses = {focus_symbol: 200}
transport.focus_original = b'\x01'
transport._tainted_pid = None
transport._drain = lambda: None
transport._resume = lambda deadline: None
transport._stop = lambda deadline: None

# The old process died during a leased call; its saved focus byte cannot own
# memory in the replacement process, whose original focus byte differs.
transport.attach(43, executable)
transport._restore_focus()
assert transport.pid == 43 and transport.process is new_process
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
print('hades_transport_focus_ownership_ok')

if sys.platform != 'darwin':
    print('hades_termination_swift_macos_only')
    raise SystemExit(0)

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
        precondition(offline.session.events == ["flush", "stop", "complete"])
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
