from pathlib import Path
import json
import logging
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'Backend'))

from core.adapter import AdapterError, GameAdapter, GameAdapterContext
from core.protocol import APP_BACKEND_VERSION, HOST_PROTOCOL_VERSION, JsonlRequestRouter


fixture_path = root/'ContractFixtures/host_protocol_v5.json'
fixture = json.loads(fixture_path.read_text(encoding='utf-8'))
assert fixture['fixtureSchemaVersion'] == 1
assert fixture['hostProtocolVersion'] == HOST_PROTOCOL_VERSION
assert fixture['backendVersion'] == APP_BACKEND_VERSION

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
        assert reply == step['reply'], step['name']
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

print('protocol_fixtures_v0180_ok')
