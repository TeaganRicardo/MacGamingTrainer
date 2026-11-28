"""Hades I durable desired state against the real adapter, worker and resident Lua."""
from pathlib import Path
import tempfile

from hades_lua_fixture import adapter_for, assert_projection_matches_resident
from core.adapter import AdapterError
from games.hades.schema import DEFAULT_PREFERENCES

# A Disable All issued while detached must still clear the resident lock on the
# next connect: the game kept enforcing it, so reconnect is the cleanup point.
with tempfile.TemporaryDirectory(prefix='hades-desired-') as directory:
    adapter, runtime, game, store = adapter_for(directory)
    state = adapter.dispatch('connect', {}, 'connect-1')
    adapter.dispatch('lock_resource', {'resource': 'Money', 'locked': True, 'target': state['target']}, 'lock')
    adapter.dispatch('disconnect', {}, 'detach')
    adapter.dispatch('disable_all', {}, 'offline-disable')
    assert store.load()['moneyLock'] is None
    state = adapter.dispatch('connect', {}, 'connect-2')
    assert runtime.replies[-1]['moneyLocked'] is False, 'resident kept a lock after offline Disable All'
    assert_projection_matches_resident(state, runtime.replies[-1], 'offline disable + reconnect')
    game.native('SpendMoney(60)')
    assert game.value('CurrentRun.Money') == '40', 'released lock still pinned native gold'

# Loading a lock-free Profile while detached releases a resident health lock.
with tempfile.TemporaryDirectory(prefix='hades-desired-') as directory:
    adapter, runtime, game, store = adapter_for(directory)
    adapter.dispatch('save_profile', {'name': 'Clean'}, 'save-clean')
    state = adapter.dispatch('connect', {}, 'connect-1')
    adapter.dispatch('lock_vital', {'vital': 'health', 'locked': True, 'target': state['target']}, 'lock-health')
    adapter.dispatch('disconnect', {}, 'detach')
    adapter.dispatch('load_profile', {'name': 'Clean'}, 'load-clean')
    state = adapter.dispatch('connect', {}, 'connect-2')
    assert runtime.replies[-1]['healthLocked'] is False, 'resident kept a health lock the Profile removed'
    assert_projection_matches_resident(state, runtime.replies[-1], 'offline profile + reconnect')

# Permanent resource locks survive detach/restart and set_resource updates the lock.
with tempfile.TemporaryDirectory(prefix='hades-desired-reslock-') as directory:
    adapter, runtime, game, store = adapter_for(directory)
    state = adapter.dispatch('connect', {}, 'connect')
    game.native('GameState.Resources.Gems=18')
    locked = adapter.dispatch('lock_resource', {'resource': 'Gems', 'locked': True, 'target': state['target']}, 'lock-gems')
    assert locked['resourceLocks'] == {'Gems': 18}
    assert store.load()['resourceLocks'] == {'Gems': 18}
    updated = adapter.dispatch('set_resource', {'resource': 'Gems', 'value': 77, 'target': state['target']}, 'edit-gems')
    assert updated['resourceLocks'] == {'Gems': 77} and store.load()['resourceLocks'] == {'Gems': 77}
    adapter.dispatch('disconnect', {}, 'detach')
    restarted, runtime, game, _ = adapter_for(directory)
    state = restarted.dispatch('connect', {}, 'reconnect-restarted')
    assert runtime.replies[-1]['resourceLocks'] == {'Gems': 77}
    assert_projection_matches_resident(state, runtime.replies[-1], 'restarted game resource lock')

# A same-process Lua reset replays every durable desired value, not only the
# boolean features: fixed locks and the boon rarity target come back too.
with tempfile.TemporaryDirectory(prefix='hades-desired-') as directory:
    adapter, runtime, game, store = adapter_for(directory)
    adapter.dispatch('set_feature', {'feature': 'boonRarityEnabled', 'value': True}, 'rarity-on')
    adapter.dispatch('set_boon_rarity', {'target': 'Epic', 'forceLegendary': True, 'forceDuo': True}, 'rarity-epic')
    adapter.dispatch('set_fishing_chance', {'chance': 37.5}, 'fish-chance')
    adapter.dispatch('set_chaos_gate_chance', {'chance': 0.0}, 'chaos-chance')
    state = adapter.dispatch('connect', {}, 'connect')
    state = adapter.dispatch('lock_resource', {'resource': 'Money', 'locked': True, 'target': state['target']}, 'lock')
    assert state['moneyLock'] == 100
    game.lua_reset()
    state = adapter.dispatch('status', {}, 'status-after-reset')
    resident = runtime.replies[-1]
    assert resident['boonRarityTarget'] == 'Epic', 'Lua reset dropped the rarity target'
    assert resident['boonForceLegendary'] is True and resident['boonForceDuo'] is True, 'Lua reset dropped force flags'
    assert resident['fishingChance'] == 37.5 and resident['chaosGateChance'] == 0.0, 'Lua reset dropped spawn chances'
    assert resident['moneyLocked'] is True and resident['moneyLock'] == 100, 'Lua reset dropped the gold lock'
    assert_projection_matches_resident(state, resident, 'after Lua reset')
    game.native('SpendMoney(60)')
    state = adapter.dispatch('status', {}, 'status-after-spend')
    assert state['money'] == 100, 'replayed gold lock did not hold the native value'
    # An exact edit while locked updates the lock target instead of failing as a
    # protocol error and restoring the stale value.
    edited = adapter.dispatch('set_value', {'field': 'money', 'value': 44, 'target': state['target']}, 'edit')
    assert edited['money'] == 44 and edited['moneyLock'] == 44
    assert store.load()['moneyLock'] == 44

# A durable lock reaches a newly started game, whose resident has none.
with tempfile.TemporaryDirectory(prefix='hades-desired-') as directory:
    adapter, runtime, game, store = adapter_for(directory)
    state = adapter.dispatch('connect', {}, 'connect-first-game')
    adapter.dispatch('lock_resource', {'resource': 'Money', 'locked': True, 'target': state['target']}, 'lock')
    adapter.dispatch('disconnect', {}, 'detach')
    restarted, runtime, game, _ = adapter_for(directory)
    state = restarted.dispatch('connect', {}, 'connect-restarted-game')
    assert runtime.replies[-1]['moneyLocked'] is True and runtime.replies[-1]['moneyLock'] == 100
    assert_projection_matches_resident(state, runtime.replies[-1], 'restarted game')

# A fresh backend presents the saved desired document, and a detached edit
# merges into it instead of replacing it with defaults plus one change.
with tempfile.TemporaryDirectory(prefix='hades-desired-') as directory:
    first, _, _, store = adapter_for(directory)
    first.dispatch('set_feature', {'feature': 'invincibility', 'value': True}, 'inv')
    first.dispatch('set_feature', {'feature': 'gameSpeed', 'value': 2.0}, 'speed')
    first.dispatch('set_boon_rarity', {'target': 'Epic', 'forceLegendary': True, 'forceDuo': False}, 'epic')
    saved = store.load()
    fresh, _, _, store = adapter_for(directory)
    state = fresh.dispatch('status', {}, 'fresh-status')
    assert state['features']['invincibility'] is True
    assert state['features']['gameSpeed']['desired'] == 2.0
    assert state['boonRarityTarget'] == 'Epic'
    assert state['boonForceLegendary'] is True and state['boonForceDuo'] is False
    fresh.dispatch('set_feature', {'feature': 'infiniteHealth', 'value': True}, 'detached-edit')
    assert store.load() == {**saved, 'infiniteHealth': True}, 'detached edit discarded saved desired state'

# An unreadable document is never overwritten by a merging edit; a deliberate
# whole-document replacement remains available.
with tempfile.TemporaryDirectory(prefix='hades-desired-') as directory:
    damaged = Path(directory) / 'preferences.json'
    damaged.write_text('{"schemaVersion": 1, "features": ')
    adapter, _, _, store = adapter_for(directory)
    try:
        adapter.dispatch('set_feature', {'feature': 'infiniteHealth', 'value': True}, 'merge-into-unknown')
    except AdapterError as error:
        assert error.code == 'preferences_failed'
    else:
        raise AssertionError('a merging edit overwrote an unreadable desired-state document')
    assert damaged.read_text() == '{"schemaVersion": 1, "features": '
    adapter.dispatch('disable_all', {}, 'deliberate-reset')
    assert store.load() == DEFAULT_PREFERENCES
    adapter.dispatch('set_feature', {'feature': 'infiniteHealth', 'value': True}, 'after-reset')
    assert store.load()['infiniteHealth'] is True

# A manual detach keeps desired features visible in its own reply.
with tempfile.TemporaryDirectory(prefix='hades-desired-') as directory:
    adapter, _, _, _ = adapter_for(directory)
    adapter.dispatch('set_feature', {'feature': 'invincibility', 'value': True}, 'inv')
    adapter.dispatch('connect', {}, 'connect')
    detached = adapter.dispatch('disconnect', {}, 'detach')
    assert detached['connected'] is False
    assert detached['features']['invincibility'] is True, 'detach reply dropped desired features'

# Neutral rarity is durable intent too: both Profile replacement and an offline
# Disable All must release a non-default target left in the existing resident.
with tempfile.TemporaryDirectory(prefix='hades-desired-') as directory:
    adapter, runtime, game, _ = adapter_for(directory)
    adapter.profiles.save('Heroic', DEFAULT_PREFERENCES)
    adapter.dispatch('connect', {}, 'connect')
    adapter.dispatch('set_boon_rarity', {'target': 'Epic', 'forceLegendary': True, 'forceDuo': True}, 'epic')
    adapter.dispatch('set_fishing_chance', {'chance': 80.0}, 'fish-profile')
    adapter.dispatch('set_chaos_gate_chance', {'chance': 15.0}, 'chaos-profile')
    state = adapter.dispatch('load_profile', {'name': 'Heroic'}, 'neutral-profile')
    assert state['boonRarityTarget'] == 'Heroic', 'neutral Profile kept the previous rarity target'
    assert state['boonForceLegendary'] is False and state['boonForceDuo'] is False, 'neutral Profile kept force flags'
    assert state['fishingChance'] is None and state['chaosGateChance'] is None, 'neutral Profile kept spawn chances'
    adapter.dispatch('set_boon_rarity', {'target': 'Rare', 'forceLegendary': False, 'forceDuo': True}, 'rare')
    adapter.dispatch('set_fishing_chance', {'chance': 50.0}, 'fish-offline')
    adapter.dispatch('set_chaos_gate_chance', {'chance': 100.0}, 'chaos-offline')
    adapter.dispatch('disconnect', {}, 'detach')
    adapter.dispatch('disable_all', {}, 'offline-disable')
    state = adapter.dispatch('connect', {}, 'reconnect')
    assert state['boonRarityTarget'] == 'Heroic', 'offline Disable All kept the previous rarity target'
    assert state['boonForceLegendary'] is False and state['boonForceDuo'] is False, 'offline Disable All kept force flags'
    assert state['fishingChance'] is None and state['chaosGateChance'] is None, 'offline Disable All kept spawn chances'

print('hades_desired_state_replay_ok')
