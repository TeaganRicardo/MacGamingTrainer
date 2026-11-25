"""Damage has one durable intent: damageMultiplier, with retired toggle migration."""

import json
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'Backend'))
sys.path.insert(0, str(root / 'tests'))

from games.hades2 import preparation as prep
from games.hades2.adapter import Hades2Adapter
from games.hades2.command_contract import Hades2CommandContract
from games.hades2.persistence import UnsupportedSchemaVersionError
from games.hades2.preferences import DESIRED_STATE_SCHEMA_VERSION, Hades2PreferenceStore
from games.hades2.profile_service import PROFILE_SCHEMA_VERSION, Hades2ProfileService
from hades2_resident_session_fakes import FakeTimeWarpController, hades2_adapter_context

assert DESIRED_STATE_SCHEMA_VERSION == 13

base = Path(tempfile.mkdtemp(prefix='mgt-hades2-damage-intent-'))
context = hades2_adapter_context(base)
prep.GAME = base / 'Hades II.app'
prep.SAVES = base / 'Saves'
prep.official_display_names = lambda ids, language='zh-CN': {}


class FakeTransport:
    def __init__(self):
        self.pid = None
        self.live = False
        self.last_duration = 0

    def alive(self):
        return self.live

    def attach(self, pid):
        self.pid = pid
        self.live = True

    def detach(self):
        self.pid = None
        self.live = False

    def close(self):
        self.live = False

    def create_time_warp_controller(self, helper_path, image_names):
        return FakeTimeWarpController()


adapter = Hades2Adapter(context=context, transport=FakeTransport())
adapter.runtime.attach(4242)
adapter.state['capabilities'] = {'setFeature': True}

calls = []


def recording_execute(command, params):
    calls.append((command, dict(params)))
    return {'status': 'ready', 'capabilities': {'setFeature': True}, 'desiredFeatures': {}}


adapter.execute = recording_execute
contract = Hades2CommandContract(adapter)


def write_multiplier(value):
    calls.clear()
    contract.dispatch('set_desired', {'feature': 'damageMultiplier', 'value': value}, f'dmg-{value}')
    assert len(calls) == 1, calls
    command, params = calls[0]
    assert command == 'set_feature', calls
    assert params['feature'] == 'damageMultiplier', calls
    return params['value']


assert adapter.preferences['damageMultiplier'] == 1.0
assert 'damageEnabled' not in adapter.preferences
assert 'damageEnabled' not in adapter.state['desiredFeatures']

# Command contract rejects the retired damageEnabled toggle fail-closed.
try:
    contract.dispatch('set_desired', {'feature': 'damageEnabled', 'value': True}, 'retired-toggle')
except Exception as error:
    assert (getattr(error, 'diagnostic', None) or str(error)) == '未知功能。'
    assert getattr(error, 'presentation', None) == 'hades2.error.unknownFeature'
else:
    raise AssertionError('retired damageEnabled toggle was accepted by command contract')
assert calls == []

assert write_multiplier(3) == 3.0
assert adapter.preferences['damageMultiplier'] == 3.0
assert adapter.state['damageMultiplier'] == 3.0
assert 'damageEnabled' not in adapter.preferences
assert 'damageEnabled' not in adapter.state['desiredFeatures']

document = json.loads(Path(adapter.preference_store.path).read_text(encoding='utf-8'))
assert document['schemaVersion'] == DESIRED_STATE_SCHEMA_VERSION
assert document['damageMultiplier'] == 3.0
assert 'damageEnabled' not in document
assert 'gardenQoL' not in document

assert write_multiplier(1.0) == 1.0
document = json.loads(Path(adapter.preference_store.path).read_text(encoding='utf-8'))
assert document['damageMultiplier'] == 1.0
assert 'damageEnabled' not in document

# Saving current-schema state strips any stale retired toggle without letting it veto.
adapter.preference_store.save({'damageMultiplier': 4.0, 'damageEnabled': False, 'gardenQoL': True})
document = json.loads(Path(adapter.preference_store.path).read_text(encoding='utf-8'))
assert document['damageMultiplier'] == 4.0
assert 'damageEnabled' not in document
assert 'gardenQoL' not in document

# An irrelevant historical multiplier can be an arbitrarily large JSON integer.
# With damageEnabled=false, migration must ignore it and preserve unrelated state.
huge_legacy_multiplier = 10 ** 4000
huge_legacy_path = base / 'legacy-v12-huge-damage.json'
huge_legacy_raw = json.dumps({
    'schemaVersion': 12,
    'damageEnabled': False,
    'damageMultiplier': huge_legacy_multiplier,
    'invincibility': True,
}).encode('utf-8')
huge_legacy_path.write_bytes(huge_legacy_raw)
huge_loaded, huge_initialized = Hades2PreferenceStore(huge_legacy_path).load()
assert huge_initialized is True
assert huge_loaded['damageMultiplier'] == 1.0 and huge_loaded['invincibility'] is True
assert huge_legacy_path.read_bytes() == huge_legacy_raw

# Legacy v12 desired-state & Profile migrate non-destructively while refusing v14.
legacy_desired_path = base / 'legacy-v12-desired.json'
legacy_desired_raw = json.dumps({
    'schemaVersion': 12,
    'damageEnabled': False,
    'damageMultiplier': 5.0,
    'gardenQoL': True,
}).encode('utf-8')
legacy_desired_path.write_bytes(legacy_desired_raw)
loaded_v12, initialized = Hades2PreferenceStore(legacy_desired_path).load()
assert initialized is True
assert loaded_v12['damageMultiplier'] == 1.0
assert 'damageEnabled' not in loaded_v12
assert 'gardenQoL' not in loaded_v12
assert legacy_desired_path.read_bytes() == legacy_desired_raw

future_desired_path = base / 'future-v14-desired.json'
future_raw = json.dumps({'schemaVersion': DESIRED_STATE_SCHEMA_VERSION + 1, 'damageMultiplier': 9.0}).encode('utf-8')
future_desired_path.write_bytes(future_raw)
future_store = Hades2PreferenceStore(future_desired_path)
safe_defaults, loaded = future_store.load()
assert loaded is False and safe_defaults['damageMultiplier'] == 1.0
try:
    future_store.save({'damageMultiplier': 2.0})
except UnsupportedSchemaVersionError:
    pass
else:
    raise AssertionError('future v14 desired-state was overwritten')
assert future_desired_path.read_bytes() == future_raw

profiles = Hades2ProfileService(base / 'profiles')
custom_chord = {'keyCode': 26, 'modifiers': 6144, 'keyLabel': '7'}
legacy_profile_path = profiles.path('legacy-damage-v12')
legacy_profile_bytes = json.dumps({
    'schemaVersion': PROFILE_SCHEMA_VERSION,
    'desiredSchemaVersion': 12,
    'name': 'legacy-damage-v12',
    'updatedAt': '2026-11-23T00:00:00+0000',
    'desired': {'damageEnabled': True, 'gardenQoL': True},
    'shortcuts': {'damageEnabled': custom_chord, 'gardenQoL': custom_chord, 'invincibility': custom_chord},
}).encode('utf-8')
legacy_profile_path.write_bytes(legacy_profile_bytes)
loaded_profile = profiles.load('legacy-damage-v12')
assert loaded_profile['desired']['damageMultiplier'] == 2.0
assert 'damageEnabled' not in loaded_profile['desired']
assert 'gardenQoL' not in loaded_profile['desired']
assert loaded_profile['shortcuts'] == {'invincibility': custom_chord}
assert legacy_profile_path.read_bytes() == legacy_profile_bytes

print('hades2_damage_intent_boundary_ok')
