from pathlib import Path
import ast
import time
import types

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
    def GetError(self):
        return FakeError()

    def GetValueAsSigned(self):
        return 0


class FakeFrame:
    def EvaluateExpression(self, expression, options):
        return FakeResult()


class FakeThread:
    def GetFrameAtIndex(self, index):
        return FakeFrame()


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

print('hades2_transport_outcome_unknown_taint_ok')
