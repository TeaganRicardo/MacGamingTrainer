import json
import logging
import plistlib
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'Backend'))

from core.adapter import GameAdapter, GameAdapterContext
from core.game_spec import GameSpec
from core.module_manifest import GameModuleManifest, ManifestError
from core.protocol import (
    APP_BACKEND_VERSION,
    HOST_PROTOCOL_VERSION,
    PROTOCOL_VERSION,
    JsonlRequestRouter,
)
from core.registry import available_games, create_adapter
from core.server import encode_reply


class FakeAdapter(GameAdapter):
    def __init__(self, context):
        super().__init__(context)
        self.state = {'connected': False}
        self.calls = []
        self.closed = False

    def dispatch(self, command, params, request_id):
        self.calls.append((command, dict(params), request_id))
        if command == 'fail':
            raise ValueError('bad fake request')
        if command == 'scalar':
            return 1
        if command == 'nan':
            return {'value': float('nan')}
        if command == 'bytes':
            return {'value': b'not-json'}
        if command == 'bad-state':
            self.state = {'unsafe': {1, 2}}
            raise RuntimeError('bad state')
        return {'command': command, 'params': params, 'requestId': request_id}

    def close(self):
        self.closed = True


product_version = plistlib.loads((root/'Info.plist').read_bytes())['CFBundleShortVersionString']
assert HOST_PROTOCOL_VERSION == PROTOCOL_VERSION == 5
assert APP_BACKEND_VERSION == product_version
assert any(row['id'] == 'hades2' and row['protocolVersion'] == 5 for row in available_games())

context = GameAdapterContext(
    game_id='fake', display_name='Fake Game', module_protocol_version=7,
    module_dir=root, public_metadata={'id':'fake','displayName':'Fake Game','protocolVersion':7},
)
adapter = FakeAdapter(context)
router = JsonlRequestRouter(adapter)
hello = router.handle({'id':'hello','command':'hello','params':{}})
assert hello['ok'] and hello['protocolVersion'] == 5
assert hello['gameID'] == 'fake' and hello['moduleProtocolVersion'] == 7
assert hello['result']['backendVersion'] == product_version
reply = router.handle({'id':'a','command':'poke','params':{'x':1}})
assert reply['ok'] and reply['result']['command'] == 'poke'
assert router.handle({'id':'a','command':'poke','params':{'x':1}}) == reply
assert len(adapter.calls) == 1
assert router.handle({'id':'a','command':'poke','params':{'x':2}})['error']['code'] == 'duplicate_conflict'
logging.disable(logging.CRITICAL)
try:
    assert router.handle({'id':'b','command':'fail','params':{}})['error']['code'] == 'invalid_request'
    assert router.handle({'id':'c','command':'scalar','params':{}})['error']['code'] == 'operation_failed'
    for request_id, command in (('d','nan'),('e','bytes')):
        unsafe = router.handle({'id':request_id,'command':command,'params':{}})
        assert unsafe['ok'] is False and unsafe['error']['code'] == 'operation_failed'
        json.dumps(unsafe, ensure_ascii=False, allow_nan=False)
    bad_state = router.handle({'id':'f','command':'bad-state','params':{}})
    assert bad_state['ok'] is False and 'state' not in bad_state
    json.dumps(bad_state, ensure_ascii=False, allow_nan=False)
finally:
    logging.disable(logging.NOTSET)
assert router.handle({'id':'g','command':'poke','params':{'x':float('nan')}})['error']['code'] == 'invalid_request'
logging.disable(logging.CRITICAL)
try:
    fallback = json.loads(encode_reply(router, {'unsafe': {1, 2, 3}}))
finally:
    logging.disable(logging.NOTSET)
assert fallback['ok'] is False and fallback['error']['code'] == 'protocol_error'
router.close(); assert adapter.closed

# GameSpec stays distribution/layout agnostic until a game opts into a bundle.
spec = GameSpec(id='other', display_name='Other', process_name='otherd', executable_path=Path('/opt/other/game'))
assert spec.minimum_architecture is None and spec.app_bundle_path is None
try: _ = spec.app_path
except RuntimeError: pass
else: raise AssertionError('generic GameSpec unexpectedly requires an app bundle')

# Runtime manifest parses backend identity only; extra build/frontend keys are
# deliberately ignored by Backend/core and belong to Tools/ validation.
project = Path(tempfile.mkdtemp(prefix='mgt-core-module-'))
backend = project/'Backend'; games = backend/'games'; module_dir = games/'other'
module_dir.mkdir(parents=True)
(games/'__init__.py').write_text('')
(module_dir/'__init__.py').write_text('')
(module_dir/'adapter.py').write_text('''\nfrom core.adapter import GameAdapter\nclass OtherAdapter(GameAdapter):\n    def dispatch(self, command, params, request_id): return {"command": command}\n    def close(self): pass\n''')
(module_dir/'module.json').write_text(json.dumps({
    'id':'other','displayName':'Other Game','protocolVersion':11,
    'backend':{'adapter':'games.other.adapter:OtherAdapter'},
    'targetApplication':{'processName':'Other Game','bundleIdentifier':'com.example.other.game'},
    'frontend':{'sourceDirectory':'Sources/Other','moduleType':'OtherModule'},
    'app':{'bundleIdentifier':'com.example.other'},
    'buildRequirements':{'lldbPython':False},
}))
manifest = GameModuleManifest.load(module_dir/'module.json')
manifest.validate_backend_layout(backend)
assert manifest.public_metadata() == {
    'id':'other','displayName':'Other Game','protocolVersion':11,
    'targetApplication':{'processName':'Other Game','bundleIdentifier':'com.example.other.game'},
}

# Reuse framework core while importing only the temporary game package.
sys.path.insert(0, str(backend))
import games as framework_games

old_path = list(framework_games.__path__); framework_games.__path__.insert(0, str(games))
try:
    rows = available_games(games)
    assert rows == [{
        'id':'other','displayName':'Other Game','protocolVersion':11,
        'targetApplication':{'processName':'Other Game','bundleIdentifier':'com.example.other.game'},
    }]
    other = create_adapter('other', games)
    assert other.dispatch('ping', {}, 'x') == {'command':'ping'}
    other.close()
finally:
    framework_games.__path__[:] = old_path
    sys.path.remove(str(backend))
    for key in list(sys.modules):
        if key == 'games.other' or key.startswith('games.other.'):
            sys.modules.pop(key, None)

foreign = games/'foreign'; foreign.mkdir()
(foreign/'module.json').write_text(json.dumps({
    'id':'foreign','displayName':'Foreign','protocolVersion':1,
    'backend':{'adapter':'outside.adapter:Adapter'},
}))
try:
    GameModuleManifest.load(foreign/'module.json').validate_backend_layout(backend)
except ManifestError: pass
else: raise AssertionError('runtime manifest accepted adapter outside its game package')

core_text = '\n'.join(path.read_text() for path in (root/'Backend/core').glob('*.py'))
for token in ('Hades II','WeaponCast','CurrentRun','TraitData','1145350','import lldb','SteamSpec'):
    assert token not in core_text, token
print('backend_core_round12_ok')
