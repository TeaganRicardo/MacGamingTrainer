import ast
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
transport_path = ROOT / 'Backend/games/hades2/transport.py'
tree = ast.parse(transport_path.read_text())

transport_class = next(
    node for node in tree.body
    if isinstance(node, ast.ClassDef) and node.name == 'Hades2LuaTransport'
)
methods = [
    node for node in transport_class.body
    if isinstance(node, ast.FunctionDef) and node.name in {'boundary', 'execute'}
]
assert {node.name for node in methods} == {'boundary', 'execute'}

isolated = ast.Module(
    body=[ast.ClassDef(
        name='IsolatedTransport',
        bases=[],
        keywords=[],
        body=methods,
        decorator_list=[],
    )],
    type_ignores=[],
)
ast.fix_missing_locations(isolated)


class FakeTransportError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class FakeError:
    def __init__(self):
        self.failed = False

    def Fail(self):
        return self.failed

    def __str__(self):
        return 'fake error'


class FakeExpressionOptions:
    def SetLanguage(self, value):
        pass

    def SetTimeoutInMicroSeconds(self, value):
        pass

    def SetIgnoreBreakpoints(self, value):
        pass

    def SetUnwindOnError(self, value):
        pass


class FakeResult:
    def __init__(self, value=0):
        self.value = value

    def GetError(self):
        return FakeError()

    def GetValueAsSigned(self):
        return self.value


class FakeFrame:
    def __init__(self, value=0):
        self.value = value

    def EvaluateExpression(self, expression, options):
        return FakeResult(self.value)


class FakeThread:
    def __init__(self, value=0):
        self.value = value

    def GetFrameAtIndex(self, index):
        return FakeFrame(self.value)


class FakeProcess:
    def AllocateMemory(self, size, permissions, error):
        return 0x1000

    def WriteMemory(self, address, payload, error):
        return len(payload)

    def ReadCStringFromMemory(self, address, capacity, error):
        error.failed = True
        return ''


fake_lldb = types.SimpleNamespace(
    SBError=FakeError,
    SBExpressionOptions=FakeExpressionOptions,
    ePermissionsReadable=1,
    ePermissionsWritable=2,
    eLanguageTypeC_plus_plus=0,
)
namespace = {
    'lldb': fake_lldb,
    'TransportError': FakeTransportError,
    'time': time,
}
exec(compile(isolated, str(transport_path), 'exec'), namespace)
Transport = namespace['IsolatedTransport']

transport = Transport.__new__(Transport)
transport.tainted = False
transport.process = FakeProcess()
transport.target = object()
transport.last_duration = 0
transport.boundary = lambda: (FakeThread(), 0x2000)
transport.address = lambda name: 0x3000
transport.alive = lambda: False

try:
    transport.execute('return true')
except FakeTransportError as error:
    assert error.code == 'outcome_unknown'
else:
    raise AssertionError('simulated result-read failure did not surface outcome_unknown')

assert transport.tainted is True, 'outcome_unknown result-read failure left transport reusable'

try:
    Transport.boundary(transport)
except FakeTransportError as error:
    assert error.code == 'restart_required'
else:
    raise AssertionError('tainted transport allowed another Lua boundary')

# A resident action can also know that its own non-idempotent outcome became
# uncertain after the Lua boundary was crossed. That sentinel must use the same
# terminal trust semantics as a debugger result-read failure.
class ResidentOutcomeUnknownProcess(FakeProcess):
    def ReadCStringFromMemory(self, address, capacity, error):
        return 'MGT_OUTCOME_UNKNOWN: native operation may have executed'


resident = Transport.__new__(Transport)
resident.tainted = False
resident.process = ResidentOutcomeUnknownProcess()
resident.target = object()
resident.last_duration = 0
resident.boundary = lambda: (FakeThread(1), 0x2000)
resident.address = lambda name: 0x3000
resident.alive = lambda: False

try:
    resident.execute('return true')
except FakeTransportError as error:
    assert error.code == 'outcome_unknown'
else:
    raise AssertionError('resident outcome-unknown marker did not surface outcome_unknown')

assert resident.tainted is True, 'resident outcome-unknown marker left transport reusable'

# A host decode failure after Lua returned is an unknown outcome, even for
# status: the read-only flag suppresses host adoption but status may perform
# resident maintenance. Transport-side failures retain their own semantics.
import sys as _sys
_sys.path.insert(0, str(ROOT / 'Backend'))
from core.adapter import AdapterError
from games.hades2.boundary_ledger import execute_with_ledger


class LedgerFakeTransport:
    def __init__(self):
        self.tainted = False

    def execute(self, source):
        return '{"ok": true'


class LedgerFailingTransport:
    def __init__(self):
        self.tainted = False

    def execute(self, source):
        raise RuntimeError('transport failed before returning a result')


def json_decode(raw):
    import json
    return json.loads(raw)


ledger_transport = LedgerFakeTransport()
try:
    execute_with_ledger(ledger_transport, 'test', 'return 1', json_decode)
except AdapterError as error:
    assert error.code == 'outcome_unknown', error.code
else:
    raise AssertionError('decode failure should raise')
assert ledger_transport.tainted is True, 'decode failure left transport untainted'

read_only_transport = LedgerFakeTransport()
try:
    execute_with_ledger(read_only_transport, 'test', 'return 1', json_decode, read_only=True)
except AdapterError as error:
    assert error.code == 'outcome_unknown', error.code
else:
    raise AssertionError('decode failure should raise')
assert read_only_transport.tainted is True, 'read_only decode failure left transport reusable'

failing_transport = LedgerFailingTransport()
try:
    execute_with_ledger(failing_transport, 'test', 'return 1', json_decode)
except RuntimeError:
    pass
else:
    raise AssertionError('transport failure should raise')
assert failing_transport.tainted is False, (
    'transport-side failure was tainted by the ledger; transport owns its own taint semantics'
)

print('hades2_transport_outcome_unknown_taint_ok')
