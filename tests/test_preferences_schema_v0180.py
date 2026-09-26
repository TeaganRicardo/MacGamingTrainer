import json
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'Backend'))

from games.hades2.preferences import DESIRED_STATE_SCHEMA_VERSION, Hades2PreferenceStore
from games.hades2.profile_service import PROFILE_SCHEMA_VERSION

# The persisted lock maps are executable desired state. Invalid nested values
# must be removed during load/normalization instead of reaching replay where
# int(...) conversions or game commands can fail later.
raw = {
    'statLocks': {
        'grasp': 30.0,
        'enemyHealth': 175.5,
        'dodge': 101,
        'unknown': 5,
        'crit': float('nan'),
    },
    'vitalLocks': {
        'health': {'current': 120, 'max': 160, 'ignored': 1},
        'mana': {'current': 0, 'max': 90},
        'armor': {'current': 25, 'max': 999},
        'broken-health': {'current': 1, 'max': 1},
        'health-missing-max': {'current': 50},
    },
    'resourceLocks': {
        'Money': 999,
        'MetaCurrency': 12.0,
        'bad-string': 'oops',
        'bad-float': 2.5,
        'bad-negative': -1,
        'bad-bool': True,
        '': 4,
    },
    'rerollsLock': 7.0,
    'elementLocks': {
        'Fire': 8,
        'Aether': 3.0,
        'Void': 2,
        'Water': 'oops',
    },
    'nextRoomReward': 'WeaponUpgrade',
}
normalized = Hades2PreferenceStore.normalize(raw)
assert normalized['statLocks'] == {'grasp': 30, 'enemyHealth': 175.5}
assert normalized['vitalLocks'] == {
    'health': {'current': 120, 'max': 160},
    'mana': {'current': 0, 'max': 90},
    'armor': {'current': 25},
}
assert normalized['resourceLocks'] == {'Money': 999, 'MetaCurrency': 12}
assert normalized['rerollsLock'] == 7
assert normalized['elementLocks'] == {'Fire': 8, 'Aether': 3}
assert normalized['nextRoomReward'] == 'WeaponUpgrade'

partial_vitals = Hades2PreferenceStore.normalize({
    'vitalLocks': {
        'health': {'current': 50},
        'mana': {'current': 10},
        'armor': {'current': 5},
    },
})
assert partial_vitals['vitalLocks'] == {'armor': {'current': 5}}

# Match the command-layer constraints exactly for persisted numeric locks.
invalid = Hades2PreferenceStore.normalize({
    'statLocks': {'grasp': 30.5, 'enemyHealth': 9},
    'vitalLocks': {
        'health': {'current': 0, 'max': 100},
        'mana': {'current': 20, 'max': float('inf')},
        'armor': {'current': -1},
    },
    'resourceLocks': {'Money': 1000000},
    'rerollsLock': 2.9,
    'elementLocks': {'Earth': 1000000},
    'nextRoomReward': 'x' * 129,
})
assert invalid['statLocks'] == {}
assert invalid['vitalLocks'] == {}
assert invalid['resourceLocks'] == {}
assert invalid['rerollsLock'] is None
assert invalid['elementLocks'] == {}
assert invalid['nextRoomReward'] is None

# The exact historical failure must now be sanitized on disk load.
base = Path(tempfile.mkdtemp(prefix='mgt-preference-schema-'))
path = base/'desired-state.json'
path.write_text(json.dumps({
    'resourceLocks': {'Money': 'oops'},
    'elementLocks': {'Fire': 'oops', 'Bogus': 3},
    'statLocks': {'grasp': 12.5, 'unknown': 5},
    'vitalLocks': {'health': 'oops', 'bogus': {'current': 1}},
    'rerollsLock': 2.9,
}), encoding='utf-8')
loaded, initialized = Hades2PreferenceStore(path).load()
assert initialized is True
assert loaded['resourceLocks'] == {}
assert loaded['elementLocks'] == {}
assert loaded['statLocks'] == {}
assert loaded['vitalLocks'] == {}
assert loaded['rerollsLock'] is None

print('preferences_schema_v0180_ok')

# Integration guard: a malformed legacy desired-state file must never make the
# adapter's reconnect replay fail before it reaches the transport boundary.
from games.hades2 import preparation as prep
from games.hades2.adapter import Hades2Adapter

adapter_base = Path(tempfile.mkdtemp(prefix='mgt-preference-adapter-'))
prep.DATA = adapter_base
(adapter_base/'desired-state.json').write_text(json.dumps({
    'gardenQoL': True,
    'resourceLocks': {'Money': 'oops'},
    'elementLocks': {'Fire': 'oops'},
    'statLocks': {'grasp': 12.5},
    'rerollsLock': 2.9,
}), encoding='utf-8')

class FakeTransport:
    def __init__(self):
        self.pid = 123
        self.last_duration = 0.0
    def alive(self): return True
    def detach(self): pass
    def close(self): pass

adapter = Hades2Adapter(transport=FakeTransport())
adapter.state.update({
    'connected': True,
    'status': 'ready',
    'desiredFeatures': {},
    'stats': {},
    'resources': [],
    'elements': [],
    'healthLocked': False,
    'manaLocked': False,
    'armorLocked': False,
    'rerollsLocked': False,
    'nextRoomReward': None,
})
replay_calls = []
def fake_execute(command, params, replay=False, batch=None):
    replay_calls.append((command, dict(params), replay, batch))
    return dict(adapter.state)
adapter.execute = fake_execute
adapter._replay_preferences(force_full=True)
assert replay_calls[-1][0] == 'replay_preferences' and replay_calls[-1][2] is True
replay_batch = replay_calls[-1][3]
assert any(command == 'set_feature' and params.get('feature') == 'gardenQoL' and params.get('value') is True
           for command, params in replay_batch)
assert not any(command in ('set_resource', 'set_element', 'set_rerolls', 'set_stat')
               for command, _ in replay_batch)

print('preferences_schema_adapter_replay_ok')


# ProfileService deliberately owns only the file envelope. Hades semantic desired
# validation remains single-sourced in Hades2PreferenceStore via Adapter.load_profile;
# do not duplicate a second nested desired schema in profile_service.py.
profile_base = Path(tempfile.mkdtemp(prefix='mgt-profile-desired-boundary-'))
prep.DATA = profile_base

class OfflineTransport:
    pid = None
    last_duration = 0.0
    def alive(self): return False
    def detach(self): pass
    def close(self): pass

profile_adapter = Hades2Adapter(transport=OfflineTransport())
profile_path = profile_adapter.profile_service.path('bad-desired')
profile_path.write_text(json.dumps({
    'schemaVersion': PROFILE_SCHEMA_VERSION,
    'desiredSchemaVersion': DESIRED_STATE_SCHEMA_VERSION,
    'name':'bad-desired',
    'updatedAt':'2026-09-18T00:00:00+0000',
    'desired':{
        'gardenQoL': True,
        'resourceLocks': {'Money':'oops', 'MetaCurrency':12.0},
        'elementLocks': {'Fire':'oops', 'Water':4.0},
        'statLocks': {'grasp':30.0, 'enemyHealth':9},
    },
}), encoding='utf-8')
loaded_profile_state = profile_adapter.load_profile('bad-desired')
assert loaded_profile_state['loadedProfile'] == 'bad-desired'
assert profile_adapter.preferences['gardenQoL'] is True
assert profile_adapter.preferences['resourceLocks'] == {'MetaCurrency':12}
assert profile_adapter.preferences['elementLocks'] == {'Water':4}
assert profile_adapter.preferences['statLocks'] == {'grasp':30}
persisted = json.loads((profile_base/'desired-state.json').read_text(encoding='utf-8'))
assert persisted['resourceLocks'] == {'MetaCurrency':12}
assert persisted['elementLocks'] == {'Water':4}
assert persisted['statLocks'] == {'grasp':30}

print('profile_desired_single_source_boundary_ok')
