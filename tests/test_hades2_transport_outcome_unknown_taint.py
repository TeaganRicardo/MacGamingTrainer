import ast
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
from games.hades2.config import LUA_TRANSPORT_RESULT_LIMIT_BYTES, LUA_TRANSPORT_SOURCE_LIMIT_BYTES

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
    last_timeout_us = None

    def SetLanguage(self, value):
        pass

    def SetTimeoutInMicroSeconds(self, value):
        type(self).last_timeout_us = value

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
    'LUA_TRANSPORT_SOURCE_LIMIT_BYTES': LUA_TRANSPORT_SOURCE_LIMIT_BYTES,
    'LUA_TRANSPORT_RESULT_LIMIT_BYTES': LUA_TRANSPORT_RESULT_LIMIT_BYTES,
}
exec(compile(isolated, str(transport_path), 'exec'), namespace)
Transport = namespace['IsolatedTransport']


class SuccessfulProcess(FakeProcess):
    def __init__(self):
        self.allocated_size = None

    def AllocateMemory(self, size, permissions, error):
        self.allocated_size = size
        return 0x1000

    def ReadCStringFromMemory(self, address, capacity, error):
        return '{}'


# A fresh resident bootstrap is currently ~326 KiB. The trusted source-input
# budget must accept it without also enlarging the independent result buffer.
large = Transport.__new__(Transport)
large.tainted = False
large.process = SuccessfulProcess()
large.target = object()
large.last_duration = 0
large.boundary = lambda: (FakeThread(), 0x2000)
large.address = lambda name: 0x3000
large.alive = lambda: False
large_source = 'x' * 325_841
assert large.execute(large_source, expression_timeout_seconds=5.0) == '{}'
assert FakeExpressionOptions.last_timeout_us == 5_000_000
assert large.process.allocated_size == len(large_source.encode('utf-8')) + 1 + LUA_TRANSPORT_RESULT_LIMIT_BYTES

try:
    large.execute('x' * (LUA_TRANSPORT_SOURCE_LIMIT_BYTES + 1))
except FakeTransportError as error:
    assert error.code == 'invalid_request'
else:
    raise AssertionError('Lua source transport accepted an over-budget payload')


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

# A valid status response can observe an asynchronous one-shot becoming
# unknown after its accepted debugger reply. The adapter must stop trust before
# adopting desired state, while retaining the received runtime evidence.
import json
import tempfile
from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter
from games.hades2.preferences import Hades2PreferenceStore


class AsyncUnknownTransport:
    def __init__(self):
        self.tainted = False
        self.pid = 4242
        self.last_duration = 0.001
        self.calls = []
        self.payload = {
            'status': 'ready', 'scene': 'run', 'rerolls': 4,
            'lastAction': {'requestId': 'async-reroll', 'command': 'reroll_choice',
                           'outcome': 'outcome_unknown', 'duplicate': False,
                           'error': 'menu changed after spending'},
        }

    def alive(self):
        return True

    def execute(self, source):
        if self.tainted:
            raise AdapterError('restart_required', 'tainted transport')
        self.calls.append(source)
        return json.dumps(self.payload)


with tempfile.TemporaryDirectory(prefix='mgt-async-action-trust-') as temporary:
    prior_data, prior_game, prior_saves = preparation.DATA, preparation.GAME, preparation.SAVES
    try:
        preparation.DATA = Path(temporary) / 'data'
        preparation.GAME = Path(temporary) / 'Hades II.app'
        preparation.SAVES = Path(temporary) / 'Saves'
        async_transport = AsyncUnknownTransport()
        adapter = Hades2Adapter(transport=async_transport)
        try:
            adapter.execute('status', {})
        except AdapterError as error:
            assert error.code == 'outcome_unknown', error.code
        else:
            raise AssertionError('decoded asynchronous unknown action did not stop transport trust')
        assert async_transport.tainted
        assert len(async_transport.calls) == 1, 'unknown status automatically crossed another Lua boundary'
        assert not (preparation.DATA / 'desired-state.json').exists(), 'unknown status adopted preferences'
        assert adapter.state['status'] == 'restart_required'
        assert adapter.state['rerolls'] == 4
        assert adapter.state['lastAction']['requestId'] == 'async-reroll'
        try:
            adapter.execute('set_rerolls', {'amount': 99, 'requestId': 'unsafe-after-unknown'})
        except AdapterError as error:
            assert error.code == 'restart_required', error.code
        else:
            raise AssertionError('a later mutation reused the unknown transport')
        assert len(async_transport.calls) == 1

        # A persisted profile remains pending, while a separately proven
        # one-shot consumption must still prevent resurrection after restart.
        desired = Hades2PreferenceStore.defaults()
        desired.update(invincibility=True, nextRoomReward='RoomMoneyDrop', nextRoomRewardToken='consumed-room')
        store = Hades2PreferenceStore(preparation.DATA / 'desired-state.json')
        store.save(desired)
        dirty_transport = AsyncUnknownTransport()
        dirty_transport.payload.update(nextRoomReward=None, runtimeDiagnostics={'lastConsumedNextRoomRewardToken': 'consumed-room'})
        dirty_adapter = Hades2Adapter(transport=dirty_transport)
        try:
            dirty_adapter.execute('status', {})
        except AdapterError as error:
            assert error.code == 'outcome_unknown', error.code
        else:
            raise AssertionError('dirty desired intent bypassed asynchronous unknown')
        assert dirty_transport.tainted and len(dirty_transport.calls) == 1
        saved, initialized = store.load()
        assert initialized and saved['invincibility'] is True, 'unknown status overwrote durable desired intent'
        assert saved['nextRoomReward'] is None and saved['nextRoomRewardToken'] is None
        assert dirty_adapter.preference_dirty, 'unknown status pretended replay completed'
        assert dirty_adapter.state['lastAction']['outcome'] == 'outcome_unknown'
        assert dirty_adapter.state['runtimeDiagnostics']['lastConsumedNextRoomRewardToken'] == 'consumed-room'

        # Observation-only status has the same trust rule without adopting the
        # runtime's desired state, and known failures do not taint the session.
        observation_transport = AsyncUnknownTransport()
        observation_adapter = Hades2Adapter(transport=observation_transport)
        try:
            observation_adapter.observe_runtime()
        except AdapterError as error:
            assert error.code == 'outcome_unknown', error.code
        else:
            raise AssertionError('observation-only unknown left transport reusable')
        assert observation_transport.tainted and len(observation_transport.calls) == 1
        for outcome in ('accepted', 'completed', 'failed'):
            known_transport = AsyncUnknownTransport()
            known_transport.payload['lastAction']['outcome'] = outcome
            known_adapter = Hades2Adapter(transport=known_transport)
            result = known_adapter.observe_runtime()
            assert not known_transport.tainted and len(known_transport.calls) == 1
            assert result['lastAction']['outcome'] == outcome
    finally:
        preparation.DATA, preparation.GAME, preparation.SAVES = prior_data, prior_game, prior_saves

print('hades2_async_action_unknown_taint_ok')
