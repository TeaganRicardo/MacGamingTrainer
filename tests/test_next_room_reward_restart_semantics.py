import json
import sys
import tempfile
from pathlib import Path

from runtime_revision_support import runtime_revision

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
sys.path.insert(0, str(ROOT / 'tests'))

from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter
from games.hades2.schema import MULTIPLIERS, TOGGLES, default_boon_rarity
from games.hades2.resident_session import ResidentMetrics, ResidentReply
from hades2_resident_session_fakes import FakeResidentSession, FakeTimeWarpController
from games.hades2.preferences import (
    DESIRED_STATE_SCHEMA_VERSION,
    Hades2PreferenceStore,
    next_room_reward_consumed,
)

assert DESIRED_STATE_SCHEMA_VERSION == 7

# Early-access reward ids migrate to current identities or are retired.
for old, expected in (
    ('RoomRewardMoney', 'RoomMoneyDrop'),
    ('RoomRewardPom', 'StackUpgrade'),
    ('RoomRewardMixerFabric', None),
):
    assert Hades2PreferenceStore.normalize({'nextRoomReward': old})['nextRoomReward'] == expected

# Schema-3 desired state has no token. Migration must derive a stable token so
# repeated backend restarts can correlate a resident consumption with the same
# persisted one-shot instead of minting a new identity every time.
base = Path(tempfile.mkdtemp(prefix='mgt-next-room-restart-'))
legacy_path = base / 'desired-state.json'
legacy_path.write_text(json.dumps({
    'schemaVersion': 3,
    'nextRoomReward': 'WeaponUpgrade',
}), encoding='utf-8')
legacy_store = Hades2PreferenceStore(legacy_path)
legacy, initialized = legacy_store.load()
assert initialized is True
assert legacy['nextRoomReward'] == 'WeaponUpgrade'
assert isinstance(legacy['nextRoomRewardToken'], str)
assert legacy['nextRoomRewardToken'].startswith('legacy-')
assert len(legacy['nextRoomRewardToken']) <= 128
assert Hades2PreferenceStore(legacy_path).load()[0]['nextRoomRewardToken'] == legacy['nextRoomRewardToken']

preferences = Hades2PreferenceStore.defaults()
preferences['nextRoomReward'] = 'WeaponUpgrade'
preferences['nextRoomRewardToken'] = 'one-shot-token'

# The resident module explicitly proves this exact one-shot was consumed.
consumed = {
    'nextRoomReward': None,
    'runtimeDiagnostics': {
        'lastConsumedNextRoomRewardToken': 'one-shot-token',
    },
}
assert next_room_reward_consumed(preferences, consumed, preference_dirty=True) is True

# A missing/different receipt means the durable desired value may simply never
# have reached Lua before the old backend died. It must remain replayable.
not_delivered = {
    'nextRoomReward': None,
    'runtimeDiagnostics': {
        'lastConsumedNextRoomRewardToken': None,
    },
}
assert next_room_reward_consumed(preferences, not_delivered, preference_dirty=True) is False

# Existing same-backend behavior remains: once a clean status sees the armed
# runtime value disappear after a previously successful set, consumption is
# confirmed even before a restart.
assert next_room_reward_consumed(preferences, not_delivered, preference_dirty=False) is True

lua = (ROOT / 'Backend/games/hades2/runtime/hades.lua').read_text()

# The resident runtime owns the durable one-shot receipt identity.
assert runtime_revision(lua) >= 42
assert 'nextRoomRewardToken = nil' in lua
assert 'lastConsumedNextRoomRewardToken = nil' in lua
assert 'M.lastConsumedNextRoomRewardToken = M.nextRoomRewardToken' in lua
assert 'M.nextRoomRewardToken = nil' in lua
assert 'lastConsumedNextRoomRewardToken = M.lastConsumedNextRoomRewardToken' in lua
assert 'nextRoomRewardToken = M.nextRoomRewardToken' in lua
assert 'params.token' in lua


def status_payload(*, reward=None, token=None, consumed_token=None):
    defaults = Hades2PreferenceStore.defaults()
    payload = {
        'status': 'ready',
        'scene': 'run',
        'capabilities': {},
        'desiredFeatures': {key: bool(defaults[key]) for key in TOGGLES},
        'activeFeatures': {key: False for key in TOGGLES},
        'dormantFeatures': {},
        'featureErrors': {},
        'boonRarity': default_boon_rarity(),
        'gatheringProbabilities': {},
        'chaosGateProbability': None,
        'stats': {},
        'resources': [],
        'elements': [],
        'healthLocked': False,
        'manaLocked': False,
        'armorLocked': False,
        'moneyLocked': False,
        'rerollsLocked': False,
        'nextRoomReward': reward,
        'runtimeDiagnostics': {
            'nextRoomRewardToken': token,
            'lastConsumedNextRoomRewardToken': consumed_token,
        },
    }
    for key in MULTIPLIERS:
        if key != 'gameSpeed':
            payload[key] = defaults[key]
    return payload


class RewardSession(FakeResidentSession):
    def __init__(self, payload):
        super().__init__(payload, pid=4242)
        self.state = self.payload

    def status(self, params=None):
        self.calls.append({
            'kind': 'status',
            'command': 'status',
            'params': dict(params or {}),
            'batch': None,
        })
        return ResidentReply(
            payload=json.loads(json.dumps(self.state)),
            metrics=ResidentMetrics(boundary_duration=0.001),
        )

    def reconcile(self, calls):
        calls = list(calls)
        self.calls.append({
            'kind': 'reconcile',
            'command': 'replay_preferences',
            'params': {},
            'batch': json.loads(json.dumps(calls)),
        })
        for command, params in calls:
            if command == 'set_next_room_reward':
                self.state['nextRoomReward'] = params.get('reward')
                diagnostics = self.state.setdefault('runtimeDiagnostics', {})
                if params.get('reward') is None:
                    diagnostics.pop('nextRoomRewardToken', None)
                else:
                    diagnostics['nextRoomRewardToken'] = params.get('token')
            else:
                raise AssertionError('unexpected reconciliation during reward test: ' + command)
        return ResidentReply(
            payload=json.loads(json.dumps(self.state)),
            metrics=ResidentMetrics(boundary_duration=0.001),
        )


old_data = preparation.DATA
try:
    # A matching consumption receipt must clear durable intent before any
    # reconciliation plan is built. Otherwise the just-consumed reward would be
    # immediately resurrected after reconnect.
    preparation.DATA = Path(tempfile.mkdtemp(prefix='mgt-next-room-consumed-'))
    consumed_session = RewardSession(status_payload(
        reward=None,
        consumed_token='one-shot-token',
    ))
    consumed_adapter = Hades2Adapter(
        resident_session=consumed_session,
        time_warp_controller=FakeTimeWarpController(),
    )
    consumed_adapter.preferences = consumed_adapter._default_preferences()
    consumed_adapter.preferences['nextRoomReward'] = 'MaxHealthDrop'
    consumed_adapter.preferences['nextRoomRewardToken'] = 'one-shot-token'
    consumed_adapter.preference_store.save(consumed_adapter.preferences)
    consumed_adapter.preference_initialized = True
    consumed_adapter.preference_dirty = True
    state = consumed_adapter.execute('status', {})
    assert consumed_adapter.preferences['nextRoomReward'] is None
    assert consumed_adapter.preferences['nextRoomRewardToken'] is None
    assert state['nextRoomReward'] is None
    assert [call['kind'] for call in consumed_session.calls] == ['status']
    persisted = json.loads(
        (preparation.DATA / 'desired-state.json').read_text(encoding='utf-8')
    )
    assert persisted['nextRoomReward'] is None
    assert persisted['nextRoomRewardToken'] is None

    # Without a matching receipt, a missing runtime value is only evidence that
    # the old backend may not have delivered the durable one-shot. The status
    # reconciliation must re-arm the exact existing token, once.
    preparation.DATA = Path(tempfile.mkdtemp(prefix='mgt-next-room-redeliver-'))
    pending_session = RewardSession(status_payload(
        reward=None,
        consumed_token=None,
    ))
    pending_adapter = Hades2Adapter(
        resident_session=pending_session,
        time_warp_controller=FakeTimeWarpController(),
    )
    pending_adapter.preferences = pending_adapter._default_preferences()
    pending_adapter.preferences['nextRoomReward'] = 'WeaponUpgrade'
    pending_adapter.preferences['nextRoomRewardToken'] = 'one-shot-token'
    pending_adapter.preference_store.save(pending_adapter.preferences)
    pending_adapter.preference_initialized = True
    pending_adapter.preference_dirty = True
    state = pending_adapter.execute('status', {})
    assert [call['kind'] for call in pending_session.calls] == ['status', 'reconcile']
    reward_calls = [
        params
        for command, params in pending_session.calls[-1]['batch']
        if command == 'set_next_room_reward'
    ]
    assert reward_calls == [{
        'reward': 'WeaponUpgrade',
        'token': 'one-shot-token',
    }]
    assert pending_session.state['nextRoomReward'] == 'WeaponUpgrade'
    assert pending_session.state['runtimeDiagnostics']['nextRoomRewardToken'] == 'one-shot-token'
    assert pending_adapter.preferences['nextRoomReward'] == 'WeaponUpgrade'
    assert pending_adapter.preferences['nextRoomRewardToken'] == 'one-shot-token'
    assert pending_adapter.preference_dirty is False
    assert state['nextRoomReward'] == 'WeaponUpgrade'
finally:
    preparation.DATA = old_data

print('next_room_reward_restart_semantics_ok')
