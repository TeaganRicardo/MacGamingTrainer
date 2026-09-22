from pathlib import Path
import copy
import json
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter, TransportError
from games.hades2.preferences import Hades2PreferenceStore


class FakeTransport:
    def __init__(self, live=True):
        self.pid = 777
        self.live = live
        self.last_duration = 0.0

    def alive(self):
        return self.live

    def detach(self):
        self.live = False

    def close(self):
        self.live = False


def seed_observed_locks(adapter):
    adapter.state.update({
        'connected': True,
        'status': 'ready',
        'desiredFeatures': {},
        'stats': {
            'grasp': {'locked': True, 'target': 30, 'value': 30},
            'enemyHealth': {'locked': True, 'target': 175, 'value': 175},
        },
        'healthLocked': True,
        'health': 120,
        'maxHealth': 160,
        'manaLocked': True,
        'mana': 50,
        'maxMana': 90,
        'armorLocked': True,
        'armor': 25,
        # Money is intentionally absent from resources. Runtime observation
        # reports its lock through dedicated moneyLocked/money fields.
        'moneyLocked': True,
        'money': 999,
        'resources': [
            {'id': 'MetaCurrency', 'locked': True, 'count': 12},
            {'id': 'Bones', 'locked': True, 'count': 5},
        ],
        'rerollsLocked': True,
        'rerolls': 7,
        'elements': [
            {'id': 'Fire', 'locked': True, 'count': 8},
            {'id': 'Water', 'locked': True, 'count': 4},
        ],
        'nextRoomReward': None,
    })


def has_call(batch, command, **expected):
    return any(
        item_command == command
        and all(params.get(key) == value for key, value in expected.items())
        for item_command, params in batch
    )


def make_adapter(prefix, live=True):
    base = Path(tempfile.mkdtemp(prefix=prefix))
    preparation.DATA = base
    return Hades2Adapter(transport=FakeTransport(live=live))


# Live Profile replacement must diff the replacement desired state against the
# real observed locks that existed before desired projection.
adapter = make_adapter('mgt-profile-reconcile-')
seed_observed_locks(adapter)
desired = Hades2PreferenceStore.defaults()
desired.update({
    'statLocks': {'enemyHealth': 200},
    'vitalLocks': {'mana': {'current': 40, 'max': 90}},
    'resourceLocks': {'MetaCurrency': 20},
    'rerollsLock': None,
    'elementLocks': {'Fire': 9},
})
adapter.profile_service.save('partial-locks', desired)

batches = []


def fake_execute(command, params, replay=False, read_only=False, batch=None):
    if command == 'replay_preferences':
        batches.append(list(batch or []))
    return dict(adapter.state)


adapter.execute = fake_execute
adapter.load_profile('partial-locks')
assert len(batches) == 1
batch = batches[0]

# Stale locks must be released.
assert has_call(batch, 'set_stat', stat='grasp', locked=False)
assert has_call(batch, 'lock_vital', vital='health', locked=False)
assert has_call(batch, 'lock_vital', vital='armor', locked=False)
assert has_call(batch, 'lock_resource', resource='Bones', locked=False)
assert has_call(batch, 'lock_resource', resource='Money', locked=False)
assert has_call(batch, 'lock_rerolls', locked=False)
assert has_call(batch, 'lock_element', element='Water', locked=False)

# Desired locks must be retained/updated, not spuriously released.
assert not has_call(batch, 'set_stat', stat='enemyHealth', locked=False)
assert has_call(batch, 'set_stat', stat='enemyHealth', locked=True, value=200)
assert not has_call(batch, 'lock_vital', vital='mana', locked=False)
assert has_call(batch, 'lock_vital', vital='mana', locked=True)
assert not has_call(batch, 'lock_resource', resource='MetaCurrency', locked=False)
assert has_call(batch, 'set_resource', resource='MetaCurrency', amount=20)
assert has_call(batch, 'lock_resource', resource='MetaCurrency', locked=True)
assert not has_call(batch, 'lock_element', element='Fire', locked=False)
assert has_call(batch, 'set_element', element='Fire', amount=9)
assert has_call(batch, 'lock_element', element='Fire', locked=True)

# A no-lock Profile must release every observed lock family.
no_lock_adapter = make_adapter('mgt-profile-reconcile-empty-')
seed_observed_locks(no_lock_adapter)
no_lock_adapter.profile_service.save('no-locks', Hades2PreferenceStore.defaults())
no_lock_batches = []


def fake_no_lock_execute(command, params, replay=False, read_only=False, batch=None):
    if command == 'replay_preferences':
        no_lock_batches.append(list(batch or []))
    return dict(no_lock_adapter.state)


no_lock_adapter.execute = fake_no_lock_execute
no_lock_adapter.load_profile('no-locks')
assert len(no_lock_batches) == 1
empty_batch = no_lock_batches[0]
for stat in ('grasp', 'enemyHealth'):
    assert has_call(empty_batch, 'set_stat', stat=stat, locked=False)
for vital in ('health', 'mana', 'armor'):
    assert has_call(empty_batch, 'lock_vital', vital=vital, locked=False)
for resource in ('MetaCurrency', 'Bones', 'Money'):
    assert has_call(empty_batch, 'lock_resource', resource=resource, locked=False)
assert has_call(empty_batch, 'lock_rerolls', locked=False)
for element in ('Fire', 'Water'):
    assert has_call(empty_batch, 'lock_element', element=element, locked=False)

# Offline Profile load remains pending. A later ready observation must still
# reconcile dedicated Money plus the other observed lock families.
offline_adapter = make_adapter('mgt-profile-reconcile-offline-', live=False)
offline_adapter.profile_service.save('offline-no-locks', Hades2PreferenceStore.defaults())
offline_adapter.load_profile('offline-no-locks')
assert offline_adapter.preference_dirty is True
seed_observed_locks(offline_adapter)
offline_adapter.transport.live = True
offline_batches = []


def fake_offline_execute(command, params, replay=False, read_only=False, batch=None):
    if command == 'replay_preferences':
        offline_batches.append(list(batch or []))
    return dict(offline_adapter.state)


offline_adapter.execute = fake_offline_execute
offline_adapter._replay_preferences(force_full=True)
assert len(offline_batches) == 1
offline_batch = offline_batches[0]
assert has_call(offline_batch, 'set_stat', stat='grasp', locked=False)
assert has_call(offline_batch, 'lock_vital', vital='health', locked=False)
assert has_call(offline_batch, 'lock_resource', resource='Money', locked=False)
assert has_call(offline_batch, 'lock_rerolls', locked=False)
assert has_call(offline_batch, 'lock_element', element='Water', locked=False)

# A failed replay must remain dirty and surface the transport failure instead
# of being reported as successfully applied.
failure_adapter = make_adapter('mgt-profile-reconcile-failure-')
seed_observed_locks(failure_adapter)
failure_adapter.profile_service.save('failure-no-locks', Hades2PreferenceStore.defaults())


def failing_execute(command, params, replay=False, read_only=False, batch=None):
    raise TransportError('outcome_unknown', 'simulated replay failure')


failure_adapter.execute = failing_execute
try:
    failure_adapter.load_profile('failure-no-locks')
except TransportError as error:
    assert error.code == 'outcome_unknown'
else:
    raise AssertionError('Profile replay failure was reported as success')
assert failure_adapter.preference_dirty is True

print('profile_lock_reconciliation_ok')


# Regression for a failed live Profile replay followed by an immediate second
# load of the same Profile. This uses production load_profile() and execute();
# only the LLDB/Lua transport boundary is simulated.
class RuntimeTransport:
    pid = 123
    last_duration = 0.001

    def __init__(self):
        self.live = True
        self.fail_once = False
        self.sources = []
        self.state = {
            'status': 'ready',
            'scene': 'run',
            'capabilities': {'setFeature': True},
            'desiredFeatures': {},
            'activeFeatures': {},
            'featureErrors': {},
            'stats': {'grasp': {'locked': True, 'target': 30, 'value': 30}},
            'healthLocked': True,
            'health': 120,
            'maxHealth': 160,
            'manaLocked': True,
            'mana': 50,
            'maxMana': 90,
            'armorLocked': True,
            'armor': 25,
            'moneyLocked': True,
            'money': 500,
            'rerollsLocked': True,
            'rerolls': 2,
            'resources': [{'id': 'MetaCurrency', 'locked': True, 'count': 10}],
            'elements': [{'id': 'Fire', 'locked': True, 'count': 2}],
            'nextRoomReward': None,
        }

    def alive(self):
        return self.live

    def detach(self):
        self.live = False

    def close(self):
        self.live = False

    def execute(self, source):
        self.sources.append(source)
        if self.fail_once:
            self.fail_once = False
            raise TransportError(
                'lua_error',
                'simulated known Lua command error before lock release',
            )
        for command, fields in re.findall(r'dispatch\\("([^"]+)",(\\{[^}]*\\})\\)', source):
            params = {}
            for key, value in re.findall(
                r'\\["([^"]+)"\\]=(true|false|nil|"[^"]*"|-?[\\d.]+)',
                fields,
            ):
                params[key] = None if value == 'nil' else json.loads(value)
            if command == 'set_stat':
                self.state['stats'][params['stat']]['locked'] = params['locked']
            elif command == 'lock_vital':
                self.state[params['vital'] + 'Locked'] = params['locked']
            elif command == 'lock_rerolls':
                self.state['rerollsLocked'] = params['locked']
            elif command == 'lock_resource':
                if params['resource'] == 'Money':
                    self.state['moneyLocked'] = params['locked']
                else:
                    for item in self.state['resources']:
                        if item['id'] == params['resource']:
                            item['locked'] = params['locked']
            elif command == 'lock_element':
                for item in self.state['elements']:
                    if item['id'] == params['element']:
                        item['locked'] = params['locked']
        return json.dumps(self.state)


def runtime_locks(state):
    return [
        state['stats']['grasp']['locked'],
        state['healthLocked'],
        state['manaLocked'],
        state['armorLocked'],
        state['moneyLocked'],
        state['rerollsLocked'],
        state['resources'][0]['locked'],
        state['elements'][0]['locked'],
    ]


retry_base = Path(tempfile.mkdtemp(prefix='mgt-profile-reconcile-retry-'))
preparation.DATA = retry_base
retry_transport = RuntimeTransport()
retry_adapter = Hades2Adapter(transport=retry_transport)
retry_adapter._runtime_bootstrapped = True
retry_adapter._catalog_initialized = True
retry_adapter._apply_game_speed = lambda value: 1
retry_adapter.state.update(copy.deepcopy(retry_transport.state), connected=True)
retry_adapter.preference_initialized = True
retry_adapter._capture_runtime_preferences(copy.deepcopy(retry_transport.state))
retry_adapter.profile_service.save('retry-unlocked', retry_adapter._default_preferences())

retry_transport.fail_once = True
try:
    retry_adapter.load_profile('retry-unlocked')
except TransportError as error:
    assert error.code == 'lua_error'
else:
    raise AssertionError('expected first Profile replay to fail')

assert all(runtime_locks(retry_transport.state))
assert retry_adapter.preference_dirty is True
assert retry_adapter.state['status'] == 'ready'

second_result = retry_adapter.load_profile('retry-unlocked')
assert not any(runtime_locks(retry_transport.state)), (
    'second Profile load must re-observe runtime locks and release them'
)
assert retry_adapter.preference_dirty is False
assert not any(runtime_locks(second_result))
assert not any(runtime_locks(retry_adapter.state))

print('profile_lock_reconciliation_retry_ok')
