from pathlib import Path
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from games.hades2.preferences import (
    DESIRED_STATE_SCHEMA_VERSION,
    Hades2PreferenceStore,
    next_room_reward_consumed,
)

assert DESIRED_STATE_SCHEMA_VERSION == 4

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

adapter = (ROOT / 'Backend/games/hades2/adapter.py').read_text()
lua = (ROOT / 'Backend/games/hades2/runtime/hades.lua').read_text()

assert "preferences['nextRoomRewardToken']=" in adapter
load_profile = adapter[adapter.index('    def load_profile'):adapter.index('    def _overlay_preferences')]
assert "if preferences.get('nextRoomReward') is not None:" in load_profile
assert "preferences['nextRoomRewardToken']='profile-'+str(time.time_ns())" in load_profile
assert "preferences.get('nextRoomRewardToken') is None" not in load_profile
assert "'token':self.preferences.get('nextRoomRewardToken')" in adapter
assert 'next_room_reward_consumed(self.preferences,decoded,self.preference_dirty)' in adapter
assert adapter.index('next_room_reward_consumed(self.preferences,decoded,self.preference_dirty)') < adapter.index(
    "if not read_only and command=='status' and self.preference_dirty and not replay:"
)

assert 'previousModule.revision ~= 42' in lua
assert 'version = 1, revision = 42' in lua
assert 'nextRoomRewardToken = nil' in lua
assert 'lastConsumedNextRoomRewardToken = nil' in lua
assert 'M.lastConsumedNextRoomRewardToken = M.nextRoomRewardToken' in lua
assert 'M.nextRoomRewardToken = nil' in lua
assert 'lastConsumedNextRoomRewardToken = M.lastConsumedNextRoomRewardToken' in lua
assert 'nextRoomRewardToken = M.nextRoomRewardToken' in lua
assert 'params.token' in lua

print('next_room_reward_restart_semantics_ok')
