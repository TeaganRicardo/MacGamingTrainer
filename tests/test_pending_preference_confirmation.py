from pathlib import Path
import copy
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from games.hades2 import adapter as adapter_module
from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter, TransportError
from games.hades2.schema import TOGGLES


class PendingTransport:
    pid = 123
    last_duration = 0.001

    def __init__(self):
        self.live = True
        self.fail_god_mode_once = True
        self.spawn_count = 0
        self.state = {
            'status': 'ready',
            'scene': 'run',
            'capabilities': {'setFeature': True},
            'desiredFeatures': {key: False for key in TOGGLES},
            'activeFeatures': {key: False for key in TOGGLES},
            'dormantFeatures': {},
            'featureErrors': {},
            'damageMultiplier': 2.0,
            'moneyMultiplier': 2.0,
            'resourceMultiplier': 2.0,
            'boonRarity': {
                'target': 'Epic',
                'multiplier': 100.0,
                'forceLegendary': False,
                'forceDuo': False,
            },
            'nextRoomReward': None,
            'runtimeDiagnostics': {},
            'stats': {},
            'resources': [],
            'elements': [],
        }

    def alive(self):
        return self.live

    def detach(self):
        self.live = False

    def close(self):
        self.live = False

    def execute(self, source):
        for feature in TOGGLES:
            marker = '["feature"]="' + feature + '"'
            if 'dispatch("set_feature"' not in source or marker not in source:
                continue
            value = '["value"]=true' in source[source.index(marker):]
            if feature == 'godMode' and value and self.fail_god_mode_once:
                self.fail_god_mode_once = False
                raise TransportError('lua_error', 'simulated durable feature failure')
            self.state['desiredFeatures'][feature] = value
            self.state['activeFeatures'][feature] = value
        if 'dispatch("spawn_reward"' in source:
            self.spawn_count += 1
        return json.dumps(self.state)


base = Path(tempfile.mkdtemp(prefix='mgt-pending-confirmation-'))
preparation.DATA = base
adapter_module.localize_catalog = lambda payload: payload
transport = PendingTransport()
adapter = Hades2Adapter(transport=transport)
adapter._runtime_bootstrapped = True
adapter._catalog_initialized = True
adapter._apply_game_speed = lambda value: 1.0
adapter.state.update(copy.deepcopy(transport.state), connected=True, pid=transport.pid)
adapter.preference_initialized = True
adapter.preference_dirty = False

# Durable A is persisted first, then its runtime application fails.
first = adapter.dispatch(
    'set_desired',
    {'feature': 'godMode', 'value': True},
    'desired-a',
)
assert first['desiredFeatures']['godMode'] is True
assert adapter.preferences['godMode'] is True
assert adapter.preference_dirty is True
assert transport.state['desiredFeatures']['godMode'] is False
persisted = json.loads((base / 'desired-state.json').read_text(encoding='utf-8'))
assert persisted['godMode'] is True

# An unrelated successful one-shot must not adopt the stale runtime projection
# over durable desired state or clear the pending reconciliation.
adapter.dispatch(
    'spawn_reward',
    {'reward': 'EmptyMaxHealthDrop'},
    'spawn-1',
)
assert transport.spawn_count == 1
assert adapter.preferences['godMode'] is True
assert adapter.preference_dirty is True
persisted = json.loads((base / 'desired-state.json').read_text(encoding='utf-8'))
assert persisted['godMode'] is True

# A later status reconciliation must still apply A. The one-shot is never replayed.
adapter.dispatch('status', {}, 'status-1')
assert transport.state['desiredFeatures']['godMode'] is True
assert adapter.preferences['godMode'] is True
assert adapter.preference_dirty is False
assert transport.spawn_count == 1
persisted = json.loads((base / 'desired-state.json').read_text(encoding='utf-8'))
assert persisted['godMode'] is True

print('pending_preference_confirmation_spawn_ok')


# A successful durable B may confirm B, but it must not clear an older pending A.
base_b = Path(tempfile.mkdtemp(prefix='mgt-pending-confirmation-feature-b-'))
preparation.DATA = base_b
transport_b = PendingTransport()
adapter_b = Hades2Adapter(transport=transport_b)
adapter_b._runtime_bootstrapped = True
adapter_b._catalog_initialized = True
adapter_b._apply_game_speed = lambda value: 1.0
adapter_b.state.update(copy.deepcopy(transport_b.state), connected=True, pid=transport_b.pid)
adapter_b.preference_initialized = True
adapter_b.preference_dirty = False

adapter_b.dispatch(
    'set_desired',
    {'feature': 'godMode', 'value': True},
    'desired-a-b',
)
assert adapter_b.preference_dirty is True
assert transport_b.state['desiredFeatures']['godMode'] is False

adapter_b.dispatch(
    'set_desired',
    {'feature': 'gardenQoL', 'value': True},
    'desired-b',
)
assert transport_b.state['desiredFeatures']['gardenQoL'] is True
assert adapter_b.preferences['gardenQoL'] is True
assert adapter_b.preferences['godMode'] is True
assert adapter_b.preference_dirty is True, (
    'successful feature B must not confirm failed feature A'
)
persisted_b = json.loads((base_b / 'desired-state.json').read_text(encoding='utf-8'))
assert persisted_b['godMode'] is True
assert persisted_b['gardenQoL'] is True

adapter_b.dispatch('status', {}, 'status-b')
assert transport_b.state['desiredFeatures']['godMode'] is True
assert adapter_b.preference_dirty is False

print('pending_preference_confirmation_feature_b_ok')
