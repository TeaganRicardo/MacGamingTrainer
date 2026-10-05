import copy
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
sys.path.insert(0, str(ROOT / 'tests'))

from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter, TransportError
from games.hades2.preferences import Hades2PreferenceStore
from games.hades2.resident_session import ResidentMetrics, ResidentReply
from games.hades2.schema import MULTIPLIERS, TOGGLES, default_boon_rarity
from hades2_resident_session_fakes import FakeResidentSession, FakeTimeWarpController


def default_runtime_state():
    defaults = Hades2PreferenceStore.defaults()
    state = {
        'status': 'ready',
        'scene': 'run',
        'capabilities': {'setFeature': True},
        'desiredFeatures': {key: bool(defaults[key]) for key in TOGGLES},
        'activeFeatures': {key: False for key in TOGGLES},
        'dormantFeatures': {},
        'featureErrors': {},
        'boonRarity': copy.deepcopy(default_boon_rarity()),
        'gatheringProbabilities': {},
        'chaosGateProbability': None,
        'stats': {},
        'healthLocked': False,
        'health': 100,
        'maxHealth': 100,
        'manaLocked': False,
        'mana': 50,
        'maxMana': 50,
        'armorLocked': False,
        'armor': 0,
        'moneyLocked': False,
        'money': 0,
        'rerollsLocked': False,
        'rerolls': 0,
        'resources': [],
        'elements': [],
        'nextRoomReward': None,
        'runtimeDiagnostics': {},
    }
    for key in MULTIPLIERS:
        if key != 'gameSpeed':
            state[key] = defaults[key]
    return state


def seed_stale_locks(state):
    state['stats'] = {
        'grasp': {'locked': True, 'target': 30, 'value': 30},
        'enemyHealth': {'locked': True, 'target': 175, 'value': 175},
    }
    state.update(
        healthLocked=True,
        health=120,
        maxHealth=160,
        manaLocked=True,
        mana=50,
        maxMana=90,
        armorLocked=True,
        armor=25,
        moneyLocked=True,
        money=999,
        rerollsLocked=True,
        rerolls=7,
    )
    state['resources'] = [
        {'id': 'MetaCurrency', 'locked': True, 'count': 12},
        {'id': 'Bones', 'locked': True, 'count': 5},
    ]
    state['elements'] = [
        {'id': 'Fire', 'locked': True, 'count': 8},
        {'id': 'Water', 'locked': True, 'count': 4},
    ]


class ProfileSession(FakeResidentSession):
    def __init__(self, state=None, *, live=True):
        super().__init__(state or default_runtime_state(), pid=123)
        self.state = self.payload
        self.live = live
        self.fail_once = False

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

    def reconcile(self, calls):
        calls = copy.deepcopy(list(calls))
        self.calls.append({
            'kind': 'reconcile',
            'command': 'replay_preferences',
            'params': {},
            'batch': calls,
        })
        if self.fail_once:
            self.fail_once = False
            raise TransportError(
                'lua_error',
                'simulated known Lua command error before reconciliation',
            )
        for command, params in calls:
            self._apply(command, params)
        return self._reply_state()

    def _apply(self, command, params):
        if command == 'set_feature':
            feature = params['feature']
            if feature in TOGGLES:
                self.state['desiredFeatures'][feature] = bool(params['value'])
            else:
                self.state[feature] = float(params['value'])
            return
        if command == 'set_boon_rarity':
            self.state['boonRarity'] = copy.deepcopy(params)
            return
        if command == 'set_gathering_probabilities':
            self.state['gatheringProbabilities'] = copy.deepcopy(params['probabilities'])
            return
        if command == 'set_chaos_gate_probability':
            self.state['chaosGateProbability'] = params['probability']
            return
        if command == 'set_stat':
            stat = params['stat']
            row = self.state['stats'].setdefault(
                stat, {'locked': False, 'target': None, 'value': 0}
            )
            row['locked'] = bool(params['locked'])
            row['target'] = params.get('value') if params['locked'] else None
            if 'value' in params:
                row['value'] = params['value']
            return
        if command == 'set_vital':
            vital = params['vital']
            field = params['field']
            key = vital if field == 'current' else 'max' + vital.capitalize()
            self.state[key] = params['value']
            return
        if command == 'lock_vital':
            self.state[params['vital'] + 'Locked'] = bool(params['locked'])
            return
        if command == 'set_resource':
            resource = params['resource']
            amount = int(params['amount'])
            if resource == 'Money':
                self.state['money'] = amount
            else:
                row = next(
                    (item for item in self.state['resources'] if item.get('id') == resource),
                    None,
                )
                if row is None:
                    row = {'id': resource, 'locked': False, 'count': 0}
                    self.state['resources'].append(row)
                row['count'] = amount
            return
        if command == 'lock_resource':
            resource = params['resource']
            locked = bool(params['locked'])
            if resource == 'Money':
                self.state['moneyLocked'] = locked
            else:
                row = next(
                    (item for item in self.state['resources'] if item.get('id') == resource),
                    None,
                )
                if row is None:
                    row = {'id': resource, 'locked': False, 'count': 0}
                    self.state['resources'].append(row)
                row['locked'] = locked
            return
        if command == 'set_rerolls':
            self.state['rerolls'] = int(params['amount'])
            return
        if command == 'lock_rerolls':
            self.state['rerollsLocked'] = bool(params['locked'])
            return
        if command == 'set_element':
            element = params['element']
            row = next(
                (item for item in self.state['elements'] if item.get('id') == element),
                None,
            )
            if row is None:
                row = {'id': element, 'locked': False, 'count': 0}
                self.state['elements'].append(row)
            row['count'] = int(params['amount'])
            return
        if command == 'lock_element':
            element = params['element']
            row = next(
                (item for item in self.state['elements'] if item.get('id') == element),
                None,
            )
            if row is None:
                row = {'id': element, 'locked': False, 'count': 0}
                self.state['elements'].append(row)
            row['locked'] = bool(params['locked'])
            return
        if command == 'set_next_room_reward':
            self.state['nextRoomReward'] = params['reward']
            diagnostics = self.state.setdefault('runtimeDiagnostics', {})
            if params['reward'] is None:
                diagnostics.pop('nextRoomRewardToken', None)
            else:
                diagnostics['nextRoomRewardToken'] = params.get('token')
            return
        raise AssertionError('unexpected reconciliation command: ' + command)


def make_adapter(prefix, session):
    base = Path(tempfile.mkdtemp(prefix=prefix))
    preparation.DATA = base
    adapter = Hades2Adapter(
        resident_session=session,
        time_warp_controller=FakeTimeWarpController(),
    )
    adapter.state.update(copy.deepcopy(session.state), connected=session.live)
    adapter.preference_initialized = True
    adapter.preference_dirty = False
    return adapter


def locks_are_clear(state):
    return (
        not any(
            isinstance(row, dict) and row.get('locked')
            for row in state.get('stats', {}).values()
        )
        and not state.get('healthLocked')
        and not state.get('manaLocked')
        and not state.get('armorLocked')
        and not state.get('moneyLocked')
        and not state.get('rerollsLocked')
        and not any(row.get('locked') for row in state.get('resources', []))
        and not any(row.get('locked') for row in state.get('elements', []))
    )


# Live Profile replacement must reconcile against the full pre-projection
# observation. If Adapter projected the new profile first and then planned from
# its public state, the stale runtime locks below would survive.
live_state = default_runtime_state()
seed_stale_locks(live_state)
live_session = ProfileSession(live_state)
adapter = make_adapter('mgt-profile-reconcile-', live_session)
desired = Hades2PreferenceStore.defaults()
desired.update({
    'statLocks': {'enemyHealth': 200},
    'vitalLocks': {'mana': {'current': 40, 'max': 90}},
    'resourceLocks': {'MetaCurrency': 20},
    'rerollsLock': None,
    'elementLocks': {'Fire': 9},
})
adapter.profile_service.save('partial-locks', desired)
result = adapter.load_profile('partial-locks')

assert [call['kind'] for call in live_session.calls] == ['observe', 'reconcile']
assert live_session.state['stats']['grasp']['locked'] is False
assert live_session.state['stats']['enemyHealth']['locked'] is True
assert live_session.state['stats']['enemyHealth']['target'] == 200
assert live_session.state['healthLocked'] is False
assert live_session.state['armorLocked'] is False
assert live_session.state['manaLocked'] is True
assert live_session.state['mana'] == 40
assert live_session.state['maxMana'] == 90
assert live_session.state['moneyLocked'] is False
assert next(row for row in live_session.state['resources'] if row['id'] == 'Bones')['locked'] is False
meta = next(row for row in live_session.state['resources'] if row['id'] == 'MetaCurrency')
assert meta['locked'] is True and meta['count'] == 20
assert live_session.state['rerollsLocked'] is False
assert next(row for row in live_session.state['elements'] if row['id'] == 'Water')['locked'] is False
fire = next(row for row in live_session.state['elements'] if row['id'] == 'Fire')
assert fire['locked'] is True and fire['count'] == 9
assert adapter.preference_dirty is False
assert result['loadedProfile'] == 'partial-locks'

print('profile_lock_reconciliation_live_ok')


# Offline Profile load remains pending. The first later status provides the real
# observation and one semantic reconciliation clears the stale runtime locks.
offline_state = default_runtime_state()
seed_stale_locks(offline_state)
offline_session = ProfileSession(offline_state, live=False)
offline_adapter = make_adapter('mgt-profile-reconcile-offline-', offline_session)
offline_adapter.profile_service.save('offline-no-locks', Hades2PreferenceStore.defaults())
offline_adapter.load_profile('offline-no-locks')
assert offline_adapter.preference_dirty is True
assert offline_session.calls == []

offline_session.live = True
offline_adapter.state.update(connected=True, status='ready')
offline_adapter.execute('status', {})
assert [call['kind'] for call in offline_session.calls] == ['status', 'reconcile']
assert locks_are_clear(offline_session.state)
assert offline_adapter.preference_dirty is False

print('profile_lock_reconciliation_offline_ok')


# A failed live reconciliation must remain pending. Loading the same Profile a
# second time re-observes the untouched runtime and can then converge.
retry_state = default_runtime_state()
seed_stale_locks(retry_state)
retry_session = ProfileSession(retry_state)
retry_adapter = make_adapter('mgt-profile-reconcile-retry-', retry_session)
retry_adapter.profile_service.save('retry-unlocked', Hades2PreferenceStore.defaults())

retry_session.fail_once = True
try:
    retry_adapter.load_profile('retry-unlocked')
except TransportError as error:
    assert error.code == 'lua_error'
else:
    raise AssertionError('expected first Profile reconciliation to fail')

assert not locks_are_clear(retry_session.state)
assert retry_adapter.preference_dirty is True
assert locks_are_clear(retry_adapter.state), (
    'failed reconciliation may project desired UI state, but must remain pending'
)

second_result = retry_adapter.load_profile('retry-unlocked')
assert locks_are_clear(retry_session.state)
assert retry_adapter.preference_dirty is False
assert locks_are_clear(second_result)
assert [call['kind'] for call in retry_session.calls] == [
    'observe', 'reconcile', 'observe', 'reconcile'
]

print('profile_lock_reconciliation_retry_ok')
