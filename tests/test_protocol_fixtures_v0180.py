from pathlib import Path
import copy
import json
import logging
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'Backend'))

from core.adapter import AdapterError, GameAdapter, GameAdapterContext
from core.protocol import APP_BACKEND_VERSION, HOST_PROTOCOL_VERSION, JsonlRequestRouter


fixture_path = root/'ContractFixtures/host_protocol_v5.json'
fixture = json.loads(fixture_path.read_text(encoding='utf-8'))
assert fixture['fixtureSchemaVersion'] == 1
assert fixture['hostProtocolVersion'] == HOST_PROTOCOL_VERSION

game = fixture['game']

class FixtureAdapter(GameAdapter):
    def __init__(self):
        super().__init__(GameAdapterContext(
            game_id=game['id'], display_name=game['displayName'],
            module_protocol_version=game['moduleProtocolVersion'],
            module_dir=root, public_metadata={},
        ))
        self.state = {'connected': False, 'scene': 'fixture'}
        self.dispatch_count = 0

    def dispatch(self, command, params, request_id):
        self.dispatch_count += 1
        if command == 'echo':
            return {'command': command, 'params': params, 'requestId': request_id}
        if command == 'fail':
            raise AdapterError('fixture_failure', 'fixture failure')
        raise ValueError('fixture command unsupported')

    def close(self):
        pass


adapter = FixtureAdapter()
router = JsonlRequestRouter(adapter)
logging.disable(logging.CRITICAL)
try:
    replies = []
    for step in fixture['steps']:
        reply = router.handle(step['request'])
        expected = copy.deepcopy(step['reply'])
        if expected.get('result', {}).get('backendVersion') == '__PRODUCT_VERSION__':
            expected['result']['backendVersion'] = APP_BACKEND_VERSION
        assert reply == expected, step['name']
        # Every fixture reply is strict JSON; this is the exact wire surface a
        # Swift decoder may consume without Python-specific values.
        json.dumps(reply, ensure_ascii=False, allow_nan=False)
        replies.append(reply)
finally:
    logging.disable(logging.NOTSET)

# hello does not dispatch, exact duplicate replay is served from the request-id
# cache, and duplicate-conflict is rejected before dispatch.
assert adapter.dispatch_count == 2

# The fixture is intentionally language-neutral. Keep the current Swift host
# decoder bound to these envelope keys so later XCTest can consume this same
# file rather than inventing a second protocol sample set.
swift = (root/'Sources/Core/Runtime/BackendClient.swift').read_text(encoding='utf-8')
for key in ('id','type','protocolVersion','moduleProtocolVersion','gameID','ok','result','state','error'):
    assert 'message["{}"]'.format(key) in swift, key

# Idempotent replies are historical JSON values. Neither a mutable object
# retained by the adapter nor the object handed to the first caller may rewrite
# what a later duplicate request observes.
class SnapshotAdapter(GameAdapter):
    def __init__(self):
        super().__init__(GameAdapterContext(
            game_id=game['id'], display_name=game['displayName'],
            module_protocol_version=game['moduleProtocolVersion'],
            module_dir=root, public_metadata={},
        ))
        self.state = {'nested': {'locked': False}}
        self.shared_result = {'nested': {'locked': False}}
        self.dispatch_count = 0

    def dispatch(self, command, params, request_id):
        self.dispatch_count += 1
        if command == 'snapshot':
            return self.shared_result
        if command == 'snapshot_fail':
            raise AdapterError('snapshot_failure', 'snapshot failure')
        raise ValueError('snapshot command unsupported')

    def close(self):
        pass


temporary_root = tempfile.TemporaryDirectory(prefix='mgt-protocol-snapshot-')
snapshot_root = Path(temporary_root.name)
snapshot_adapter = SnapshotAdapter()
snapshot_router = JsonlRequestRouter(snapshot_adapter, save_data_root=snapshot_root / 'snapshot')

caller_request = {'id': 'snapshot-caller', 'command': 'snapshot', 'params': {}}
caller_first = snapshot_router.handle(caller_request)
caller_first['result']['nested']['locked'] = True
assert snapshot_adapter.shared_result['nested']['locked'] is False
caller_replay = snapshot_router.handle(caller_request)
assert caller_replay['result']['nested']['locked'] is False
assert snapshot_adapter.dispatch_count == 1

adapter_request = {'id': 'snapshot-adapter', 'command': 'snapshot', 'params': {}}
adapter_first = snapshot_router.handle(adapter_request)
assert adapter_first['result']['nested']['locked'] is False
snapshot_adapter.shared_result['nested']['locked'] = True
adapter_replay = snapshot_router.handle(adapter_request)
assert adapter_replay['result']['nested']['locked'] is False
assert snapshot_adapter.dispatch_count == 2

error_request = {'id': 'snapshot-error', 'command': 'snapshot_fail', 'params': {}}
logging.disable(logging.CRITICAL)
try:
    error_first = snapshot_router.handle(error_request)
finally:
    logging.disable(logging.NOTSET)
assert error_first['state']['nested']['locked'] is False
error_first['state']['nested']['locked'] = True
assert snapshot_adapter.state['nested']['locked'] is False
snapshot_adapter.state['nested']['locked'] = True
error_replay = snapshot_router.handle(error_request)
assert error_replay['state']['nested']['locked'] is False
assert snapshot_adapter.dispatch_count == 3

# The existing FIFO cap remains exactly 256 entries: the oldest request is
# evicted, while the next-oldest duplicate still replays without dispatch.
eviction_adapter = SnapshotAdapter()
eviction_router = JsonlRequestRouter(eviction_adapter, save_data_root=snapshot_root / 'eviction')
for index in range(257):
    eviction_router.handle({'id': f'evict-{index}', 'command': 'snapshot', 'params': {}})
assert eviction_adapter.dispatch_count == 257
eviction_router.handle({'id': 'evict-1', 'command': 'snapshot', 'params': {}})
assert eviction_adapter.dispatch_count == 257
eviction_router.handle({'id': 'evict-0', 'command': 'snapshot', 'params': {}})
assert eviction_adapter.dispatch_count == 258
temporary_root.cleanup()

print('protocol_fixtures_v0180_ok')
