import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
sys.path.insert(0, str(ROOT / 'tests'))

from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter, TransportError
from games.hades2.persistence import PersistenceError
from games.hades2.resident_session import ResidentMetrics, ResidentReply
from games.hades2.schema import TOGGLES
from hades2_resident_session_fakes import FakeResidentSession, FakeTimeWarpController


class PendingResidentSession(FakeResidentSession):
    def __init__(self):
        state = {
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
            'healthLocked': False,
            'health': 100.0,
            'maxHealth': 160.0,
            'stats': {},
            'resources': [],
            'elements': [],
            'gatheringProbabilities': {},
            'chaosGateProbability': None,
        }
        super().__init__(state, pid=123)
        self.state = self.payload
        self.fail_god_mode_once = True
        self.spawn_count = 0

    def _reply_state(self):
        return ResidentReply(
            payload=copy.deepcopy(self.state),
            metrics=ResidentMetrics(boundary_duration=0.001),
        )

    def status(self, params=None):
        self.calls.append({
            'kind': 'status',
            'command': 'status',
            'params': copy.deepcopy(params or {}),
            'batch': None,
        })
        return self._reply_state()

    def observe_status(self, params=None):
        self.calls.append({
            'kind': 'observe',
            'command': 'status',
            'params': copy.deepcopy(params or {}),
            'batch': None,
        })
        return self._reply_state()

    def mutate(self, command, params=None):
        params = dict(params or {})
        self.calls.append({
            'kind': 'mutate',
            'command': command,
            'params': copy.deepcopy(params),
            'batch': None,
        })
        self._apply(command, params)
        return self._reply_state()

    def reconcile(self, calls):
        calls = list(calls)
        self.calls.append({
            'kind': 'reconcile',
            'command': 'replay_preferences',
            'params': {},
            'batch': copy.deepcopy(calls),
        })
        for command, params in calls:
            self._apply(command, dict(params or {}))
        return self._reply_state()

    def _apply(self, command, params):
        if command == 'set_feature':
            feature = params.get('feature')
            value = bool(params.get('value'))
            if feature == 'invincibility' and value and self.fail_god_mode_once:
                self.fail_god_mode_once = False
                raise TransportError('lua_error', 'simulated durable feature failure')
            if feature in TOGGLES:
                self.state['desiredFeatures'][feature] = value
                self.state['activeFeatures'][feature] = value
            return
        if command == 'set_boon_rarity':
            self.state['boonRarity'] = {
                'target': params.get('target'),
                'multiplier': float(params.get('multiplier', 100.0)),
                'forceLegendary': bool(params.get('forceLegendary')),
                'forceDuo': bool(params.get('forceDuo')),
            }
            return
        if command == 'set_next_room_reward':
            reward = params.get('reward')
            self.state['nextRoomReward'] = reward
            if reward is None:
                self.state['runtimeDiagnostics'].pop('nextRoomRewardToken', None)
            else:
                token = params.get('token')
                if token is not None:
                    self.state['runtimeDiagnostics']['nextRoomRewardToken'] = token
            return
        if command == 'set_vital' and params.get('vital') == 'health':
            field = params.get('field')
            value = float(params.get('value'))
            if field == 'current':
                self.state['health'] = value
            elif field == 'max':
                self.state['maxHealth'] = value
            return
        if command == 'set_stat' and params.get('stat') == 'enemyHealth':
            locked = bool(params.get('locked'))
            value = params.get('value')
            self.state['stats']['enemyHealth'] = {
                'locked': locked,
                'target': float(value) if locked and value is not None else None,
                'value': float(value) if value is not None else 100.0,
            }
            return
        if command == 'spawn_reward':
            self.spawn_count += 1


def make_pending_adapter(prefix):
    base = Path(tempfile.mkdtemp(prefix=prefix))
    preparation.DATA = base
    session = PendingResidentSession()
    adapter = Hades2Adapter(
        resident_session=session,
        time_warp_controller=FakeTimeWarpController(),
    )
    adapter._apply_game_speed = lambda value: 1.0
    adapter.state.update(copy.deepcopy(session.state), connected=True, pid=session.pid)
    adapter.preference_initialized = True
    adapter.preference_dirty = False
    return base, session, adapter


base, transport, adapter = make_pending_adapter('mgt-pending-confirmation-')

# Durable A is persisted first, then its runtime application fails.
first = adapter.dispatch(
    'set_desired',
    {'feature': 'invincibility', 'value': True},
    'desired-a',
)
assert first['desiredFeatures']['invincibility'] is True
assert adapter.preferences['invincibility'] is True
assert adapter.preference_dirty is True
assert transport.state['desiredFeatures']['invincibility'] is False
persisted = json.loads((base / 'desired-state.json').read_text(encoding='utf-8'))
assert persisted['invincibility'] is True

# An unrelated successful one-shot must not adopt the stale runtime projection
# over durable desired state or clear the pending reconciliation.
adapter.dispatch(
    'spawn_reward',
    {'reward': 'EmptyMaxHealthDrop'},
    'spawn-1',
)
assert transport.spawn_count == 1
assert adapter.preferences['invincibility'] is True
assert adapter.preference_dirty is True
persisted = json.loads((base / 'desired-state.json').read_text(encoding='utf-8'))
assert persisted['invincibility'] is True

# A later status reconciliation must still apply A. The one-shot is never replayed.
adapter.dispatch('status', {}, 'status-1')
assert transport.state['desiredFeatures']['invincibility'] is True
assert adapter.preferences['invincibility'] is True
assert adapter.preference_dirty is False
assert transport.spawn_count == 1
persisted = json.loads((base / 'desired-state.json').read_text(encoding='utf-8'))
assert persisted['invincibility'] is True

print('pending_preference_confirmation_spawn_ok')


# A successful durable B may confirm B, but it must not clear an older pending A.
base_b, transport_b, adapter_b = make_pending_adapter(
    'mgt-pending-confirmation-feature-b-'
)

adapter_b.dispatch(
    'set_desired',
    {'feature': 'invincibility', 'value': True},
    'desired-a-b',
)
assert adapter_b.preference_dirty is True
assert transport_b.state['desiredFeatures']['invincibility'] is False

adapter_b.dispatch(
    'set_desired',
    {'feature': 'gardenQoL', 'value': True},
    'desired-b',
)
assert transport_b.state['desiredFeatures']['gardenQoL'] is True
assert adapter_b.preferences['gardenQoL'] is True
assert adapter_b.preferences['invincibility'] is True
assert adapter_b.preference_dirty is True, (
    'successful feature B must not confirm failed feature A'
)
persisted_b = json.loads((base_b / 'desired-state.json').read_text(encoding='utf-8'))
assert persisted_b['invincibility'] is True
assert persisted_b['gardenQoL'] is True

adapter_b.dispatch('status', {}, 'status-b')
assert transport_b.state['desiredFeatures']['invincibility'] is True
assert adapter_b.preference_dirty is False

print('pending_preference_confirmation_feature_b_ok')


# Boon rarity is another durable desired family. Its success must not clear an
# older failed feature that is still waiting for reconciliation.
base_rarity, transport_rarity, adapter_rarity = make_pending_adapter(
    'mgt-pending-confirmation-rarity-'
)

adapter_rarity.dispatch(
    'set_desired',
    {'feature': 'invincibility', 'value': True},
    'desired-a-rarity',
)
assert adapter_rarity.preference_dirty is True

rarity_config = {
    'target': 'Heroic',
    'multiplier': 250,
    'forceLegendary': True,
    'forceDuo': False,
}
adapter_rarity.dispatch(
    'set_boon_rarity_desired',
    rarity_config,
    'desired-rarity',
)
assert transport_rarity.state['boonRarity']['target'] == 'Heroic'
assert adapter_rarity.preferences['invincibility'] is True
assert adapter_rarity.preferences['boonRarity']['target'] == 'Heroic'
assert adapter_rarity.preference_dirty is True, (
    'successful boon rarity B must not confirm failed feature A'
)
persisted_rarity = json.loads(
    (base_rarity / 'desired-state.json').read_text(encoding='utf-8')
)
assert persisted_rarity['invincibility'] is True
assert persisted_rarity['boonRarity']['target'] == 'Heroic'

adapter_rarity.dispatch('status', {}, 'status-rarity')
assert transport_rarity.state['desiredFeatures']['invincibility'] is True
assert adapter_rarity.preference_dirty is False

print('pending_preference_confirmation_rarity_ok')


# nextRoomReward is a durable one-shot with an identity token. Arming it while
# another field is pending must preserve that older pending work. Once the
# resident reports consumption of this exact token, later reconciliation must
# not resurrect the one-shot.
base_reward, transport_reward, adapter_reward = make_pending_adapter(
    'mgt-pending-confirmation-next-room-'
)

adapter_reward.dispatch(
    'set_desired',
    {'feature': 'invincibility', 'value': True},
    'desired-a-reward',
)
assert adapter_reward.preference_dirty is True

adapter_reward.dispatch(
    'set_next_room_reward_desired',
    {'reward': 'WeaponUpgrade'},
    'desired-reward',
)
armed_token = adapter_reward.preferences['nextRoomRewardToken']
assert isinstance(armed_token, str) and armed_token
assert transport_reward.state['nextRoomReward'] == 'WeaponUpgrade'
assert transport_reward.state['runtimeDiagnostics']['nextRoomRewardToken'] == armed_token
assert adapter_reward.preferences['invincibility'] is True
assert adapter_reward.preference_dirty is True, (
    'successful next-room arm must not confirm failed feature A'
)
persisted_reward = json.loads(
    (base_reward / 'desired-state.json').read_text(encoding='utf-8')
)
assert persisted_reward['nextRoomReward'] == 'WeaponUpgrade'
assert persisted_reward['nextRoomRewardToken'] == armed_token
assert persisted_reward['invincibility'] is True

# Simulate resident consumption before the next status. The exact receipt proves
# that this one-shot ran even though another durable field remains pending.
transport_reward.state['nextRoomReward'] = None
transport_reward.state['runtimeDiagnostics'].pop('nextRoomRewardToken', None)
transport_reward.state['runtimeDiagnostics'][
    'lastConsumedNextRoomRewardToken'
] = armed_token

adapter_reward.dispatch('status', {}, 'status-reward')
assert transport_reward.state['desiredFeatures']['invincibility'] is True
assert transport_reward.state['nextRoomReward'] is None
assert adapter_reward.preferences['nextRoomReward'] is None
assert adapter_reward.preferences['nextRoomRewardToken'] is None
assert adapter_reward.preference_dirty is False
persisted_reward = json.loads(
    (base_reward / 'desired-state.json').read_text(encoding='utf-8')
)
assert persisted_reward['nextRoomReward'] is None
assert persisted_reward['nextRoomRewardToken'] is None
assert persisted_reward['invincibility'] is True

print('pending_preference_confirmation_next_room_ok')


# A successful runtime replay is not fully confirmed until the durable state can
# also be persisted. If the confirmation write fails, the error is visible and
# pending remains true. The already-persisted desired value on disk must remain
# intact rather than being replaced by a false runtime projection.
base_persist, transport_persist, adapter_persist = make_pending_adapter(
    'mgt-pending-confirmation-persist-'
)

adapter_persist.dispatch(
    'set_desired',
    {'feature': 'invincibility', 'value': True},
    'desired-a-persist',
)
assert adapter_persist.preference_dirty is True
persisted_before = json.loads(
    (base_persist / 'desired-state.json').read_text(encoding='utf-8')
)
assert persisted_before['invincibility'] is True

original_persist_save = adapter_persist.preference_store.save
fail_confirmation_once = True


def fail_confirmation_save(preferences):
    global fail_confirmation_once
    if fail_confirmation_once:
        fail_confirmation_once = False
        raise PersistenceError('simulated confirmation persistence failure')
    return original_persist_save(preferences)


adapter_persist.preference_store.save = fail_confirmation_save
try:
    adapter_persist.dispatch('status', {}, 'status-persist-fail')
except PersistenceError as error:
    assert 'simulated confirmation persistence failure' in str(error)
else:
    raise AssertionError('confirmation persistence failure was hidden')

assert transport_persist.state['desiredFeatures']['invincibility'] is True
assert adapter_persist.preferences['invincibility'] is True
assert adapter_persist.preference_dirty is True, (
    'failed confirmation persistence must remain pending'
)
persisted_after_failure = json.loads(
    (base_persist / 'desired-state.json').read_text(encoding='utf-8')
)
assert persisted_after_failure['invincibility'] is True

# Once persistence recovers, a later status may confirm the already-applied
# durable state without replaying any one-shot operation.
adapter_persist.dispatch('status', {}, 'status-persist-retry')
assert adapter_persist.preference_dirty is False
persisted_after_retry = json.loads(
    (base_persist / 'desired-state.json').read_text(encoding='utf-8')
)
assert persisted_after_retry['invincibility'] is True

print('pending_preference_confirmation_persistence_ok')


# A successful durable lock B owns only its lock family. While feature A remains
# pending, B must still be captured and persisted without adopting unrelated
# stale runtime fields. The later full reconciliation must preserve B.
base_lock, transport_lock, adapter_lock = make_pending_adapter(
    'mgt-pending-confirmation-lock-'
)

adapter_lock.dispatch(
    'set_desired',
    {'feature': 'invincibility', 'value': True},
    'desired-a-lock',
)
assert adapter_lock.preference_dirty is True

adapter_lock.dispatch(
    'set_stat',
    {'stat': 'enemyHealth', 'locked': True, 'value': 175},
    'lock-b',
)
assert transport_lock.state['stats']['enemyHealth']['locked'] is True
assert adapter_lock.preferences['invincibility'] is True
assert adapter_lock.preferences['statLocks'] == {'enemyHealth': 175.0}, (
    'successful stat lock B must persist its own durable field while A is pending'
)
assert adapter_lock.preference_dirty is True
persisted_lock = json.loads(
    (base_lock / 'desired-state.json').read_text(encoding='utf-8')
)
assert persisted_lock['invincibility'] is True
assert persisted_lock['statLocks'] == {'enemyHealth': 175.0}

adapter_lock.dispatch('status', {}, 'status-lock')
assert transport_lock.state['desiredFeatures']['invincibility'] is True
assert transport_lock.state['stats']['enemyHealth']['locked'] is True
assert adapter_lock.preferences['statLocks'] == {'enemyHealth': 175.0}
assert adapter_lock.preference_dirty is False

print('pending_preference_confirmation_owned_lock_ok')


# A durable lock may apply in the runtime before its post-success persistence
# commit runs. If that write fails, the error must remain visible and the
# in-memory desired lock must stay pending for a later status reconciliation.
base_lock_persist, transport_lock_persist, adapter_lock_persist = make_pending_adapter(
    'mgt-pending-lock-persist-'
)
transport_lock_persist.fail_god_mode_once = False
adapter_lock_persist.preference_store.save(adapter_lock_persist.preferences)

original_lock_persist_save = adapter_lock_persist.preference_store.save
fail_lock_persist_once = True


def fail_lock_persist_save(preferences):
    global fail_lock_persist_once
    if fail_lock_persist_once:
        fail_lock_persist_once = False
        raise PersistenceError('simulated lock persistence failure')
    return original_lock_persist_save(preferences)


adapter_lock_persist.preference_store.save = fail_lock_persist_save
try:
    adapter_lock_persist.dispatch(
        'set_stat',
        {'stat': 'enemyHealth', 'locked': True, 'value': 175},
        'lock-persist-fail',
    )
except PersistenceError as error:
    assert 'simulated lock persistence failure' in str(error)
else:
    raise AssertionError('post-success lock persistence failure was hidden')

assert transport_lock_persist.state['stats']['enemyHealth']['locked'] is True
assert adapter_lock_persist.preferences['statLocks'] == {'enemyHealth': 175.0}
assert adapter_lock_persist.preference_dirty is True, (
    'runtime-applied lock with failed persistence must remain pending'
)
persisted_lock_failure = json.loads(
    (base_lock_persist / 'desired-state.json').read_text(encoding='utf-8')
)
assert persisted_lock_failure['statLocks'] == {}

adapter_lock_persist.dispatch('status', {}, 'lock-persist-retry')
assert adapter_lock_persist.preference_dirty is False
persisted_lock_retry = json.loads(
    (base_lock_persist / 'desired-state.json').read_text(encoding='utf-8')
)
assert persisted_lock_retry['statLocks'] == {'enemyHealth': 175.0}

print('pending_preference_confirmation_owned_lock_persistence_ok')


# A direct value edit does not own the lock switch. If the same vital has a
# durable lock still pending in preferences while runtime remains unlocked,
# set_vital may update the desired value but must not erase the pending lock.
base_vital_value, transport_vital_value, adapter_vital_value = make_pending_adapter(
    'mgt-pending-vital-value-'
)
transport_vital_value.fail_god_mode_once = False
adapter_vital_value.preferences['vitalLocks'] = {
    'health': {'current': 120.0, 'max': 160.0},
}
adapter_vital_value.preference_store.save(adapter_vital_value.preferences)
adapter_vital_value.preference_dirty = True
adapter_vital_value._overlay_preferences()

adapter_vital_value.dispatch(
    'set_vital',
    {'vital': 'health', 'field': 'current', 'value': 130},
    'vital-value-edit',
)

assert transport_vital_value.state['healthLocked'] is False
assert adapter_vital_value.preferences['vitalLocks'] == {
    'health': {'current': 130.0, 'max': 160.0},
}, 'set_vital must update the pending lock value without clearing its lock intent'
assert adapter_vital_value.preference_dirty is True
persisted_vital_value = json.loads(
    (base_vital_value / 'desired-state.json').read_text(encoding='utf-8')
)
assert persisted_vital_value['vitalLocks'] == {
    'health': {'current': 130.0, 'max': 160.0},
}

print('pending_preference_confirmation_direct_value_keeps_lock_ok')
