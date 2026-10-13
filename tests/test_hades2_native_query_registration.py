"""Replay a rejected native registration through the actual leased transport.

The original incident did not retain the C rejection code. This fixture proves
diagnostic/trust behavior, not which guard rejected the user's running game.
"""
import io
import json
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
from core.adapter import AdapterError
from games.hades2.native_effect_query import NativeQueryLibrary
from games.hades2.lldb_worker import Hades2LLDBWorker, serve_requests
from games.hades2.transport_client import _LLDBWorkerClient

fixture = runpy.run_path(str(ROOT / 'tests/test_hades2_transport_outcome_unknown_taint.py'))
fixture['namespace']['TransportError'] = AdapterError
Transport = fixture['Transport']


class RejectedProcess(fixture['SuccessfulProcess']):
    def __init__(self, text):
        super().__init__()
        self.text = text

    def ReadCStringFromMemory(self, address, capacity, error):
        return self.text


for status, reason in (
    (-1, 'Native query registration requires Darwin MainThread'),
    (-2, 'Native query registration cannot reserve Lua stack space'),
    (-4, 'Native query target UUID does not match Hades II 1.143476'),
    (-100, 'Native query target binding mismatch: lua_gettop'),
    (-200, 'Native query target binding is unreadable: lua_gettop'),
):
    transport = Transport.__new__(Transport)
    transport.native_runtime_installer = NativeQueryLibrary(200, 300)
    transport.tainted = False
    transport.process = RejectedProcess(reason)
    transport.target = fixture['FakeTarget']()
    transport.last_duration = 0
    transport.boundary = lambda status=status: (
        fixture['FakeThread'](status), 0x2000, fixture['FakeBreakpoint']()
    )
    transport.address = lambda name: 0x3000
    transport.alive = lambda: False
    try:
        transport.execute("return '{}'", expression_timeout_seconds=2)
    except AdapterError as error:
        assert error.code == 'incompatible', (
            f'Native registration status {status} was reported as {error.code}; '
            'the resident operation never executed'
        )
        assert error.presentation == 'hades2.error.nativeQueryUnavailable'
        assert reason in error.diagnostic and f'status={status}' in error.diagnostic
    else:
        raise AssertionError('Native registration rejection was accepted')
    assert transport.target.deleted == [1], 'Rejected install leaked its leased breakpoint'
    assert not transport.tainted, 'Known pre-resident rejection was labeled outcome-unknown'

    # Pass the same rejection through the actual worker JSONL envelope and
    # client decoder used by the application backend.
    transport.pid = 4242
    output = io.StringIO()
    requests = [
        {'id': 'hello', 'method': 'hello', 'params': {}},
        {'id': 'install', 'method': 'transport.execute', 'params': {'source': "return '{}'"}},
    ]
    serve_requests(
        io.StringIO(''.join(json.dumps(row) + '\n' for row in requests)),
        output, Hades2LLDBWorker(transport=transport),
    )

    class ReplayedSidecar:
        started = True
        terminal = False

        def __init__(self):
            self.responses = [json.loads(line) for line in output.getvalue().splitlines()]
            self.calls = []

        def request(self, method, params, **options):
            self.calls.append(method)
            return self.responses.pop(0)

    sidecar = ReplayedSidecar()
    client = _LLDBWorkerClient(sidecar=sidecar)
    try:
        client.call('transport.execute', {'source': "return '{}'"})
    except AdapterError as error:
        assert error.code == 'incompatible'
        assert error.presentation == 'hades2.error.nativeQueryUnavailable'
        assert reason in error.diagnostic and f'status={status}' in error.diagnostic
    else:
        raise AssertionError('Worker lost the native registration rejection')
    assert sidecar.calls == ['hello', 'transport.execute'], 'Native rejection was replayed'
    assert not client.terminal, 'Known native rejection terminalized sidecar trust'

print('hades2_native_query_registration_ok: precise rejection, worker envelope, no replay, leased cleanup')
