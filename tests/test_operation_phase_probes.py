"""Body-free correlation, neutral protocol/replay, and sidecar failure receipts."""
import io
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
from core.adapter import GameAdapter, GameAdapterContext
from core.protocol import JsonlRequestRouter
from core.server import process_line
from core.operation_profile import correlation, operation, phase, record
from core.sidecar import JsonLineSidecarClient, SidecarTerminalError, serve_jsonl_requests

class Fixture(GameAdapter):
    def __init__(self):
        super().__init__(GameAdapterContext(game_id='independent', display_name='Fixture',
            module_protocol_version=1, module_dir=ROOT, public_metadata={}))
        self.calls = 0
    def dispatch(self, command, params, request_id):
        self.calls += 1
        return {'secret': params.get('secret'), 'value': self.calls}
    def close(self):
        pass

stream = io.StringIO()
handler = logging.StreamHandler(stream)
logger = logging.getLogger(); previous = logger.level
logger.addHandler(handler); logger.setLevel(logging.INFO)
try:
    with tempfile.TemporaryDirectory(prefix='mgt-profile-contract-') as temporary:
        request = json.dumps({'id': 'request-1', 'command': 'echo', 'params': {'secret': 'PRIVATE-BODY'}})
        fixture = Fixture(); router = JsonlRequestRouter(fixture, save_data_root=temporary)
        with patch.dict(os.environ, {'MGT_PROFILE_OPERATIONS': '0'}):
            reply = process_line(router, request)
        assert 'OperationProfile' not in stream.getvalue()
        stream.seek(0); stream.truncate()
        with patch.dict(os.environ, {'MGT_PROFILE_OPERATIONS': '1'}):
            profiled_reply = process_line(router, request)
            assert correlation() is None
        assert reply == profiled_reply and fixture.calls == 1, 'profiling broke cached one-shot replay'
        rows = [json.loads(line.split('OperationProfile ', 1)[1]) for line in stream.getvalue().splitlines()
                if 'OperationProfile ' in line]
        assert {'backend.request_decode', 'backend.routing', 'backend.stdout_serialize'} <= {r['phase'] for r in rows}
        assert all(r['request_id'] == 'request-1' for r in rows)
        assert 'PRIVATE-BODY' not in stream.getvalue()
        assert next(r for r in rows if r['phase'] == 'backend.stdout_serialize')['reply_bytes'] == len(reply.encode()) + 1

    class Process:
        def __init__(self, reply):
            self.stdin, self.stdout = io.BytesIO(), io.BytesIO(reply)
            self.dead = False
        def poll(self): return 1 if self.dead else None
        def terminate(self): self.dead = True
        def wait(self, **kwargs): return 1

    stream.seek(0); stream.truncate()
    raw = b'{"id":"1","result":true}\n'
    child = Process(raw)
    client = JsonLineSidecarClient(['fixture'], reply_timeout_seconds=1, process_factory=lambda *a, **k: child)
    with patch.dict(os.environ, {'MGT_PROFILE_OPERATIONS': '1'}):
        with operation('request-2', 'echo'):
            assert client.request('liveness', {'secret': 'PRIVATE-BODY'})['result'] is True
            sent = child.stdin.getvalue()
            assert json.loads(sent)['profile'] == {'request_id': 'request-2', 'command': 'echo'}
        with operation('request-3', 'mutate'):
            try: client.request('mutate', outcome_unknown_on_loss=True)
            except SidecarTerminalError as error: assert error.outcome_unknown and client.terminal
            else: raise AssertionError('lost acknowledgement accepted')
        assert correlation() is None
    rows = [json.loads(line.split('OperationProfile ', 1)[1]) for line in stream.getvalue().splitlines()]
    assert len(rows) == 2 and rows[0]['method'] == 'liveness' and rows[1]['outcome'] == 'failed'
    assert rows[0]['request_bytes'] == len(sent) and rows[0]['reply_bytes'] == len(raw)
    assert 'PRIVATE-BODY' not in stream.getvalue()

    # An exception or a nested scope cannot associate the next request with
    # the preceding request. The optional metadata never changes a reply.
    incoming = io.BytesIO(sent); outgoing = io.BytesIO(); seen = []
    with patch.dict(os.environ, {'MGT_PROFILE_OPERATIONS': '1'}):
        serve_jsonl_requests(incoming, outgoing,
            lambda method, params: seen.append(correlation()) or True,
            error_payload=lambda error: {'code': 'fixture'})
    assert seen == [{'request_id': 'request-2', 'command': 'echo'}]
    assert json.loads(outgoing.getvalue()) == {'id': '1', 'result': True, 'state': {}}
    assert correlation() is None
finally:
    logger.removeHandler(handler); logger.setLevel(previous)
print('operation_phase_probes_ok')
