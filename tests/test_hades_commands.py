import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
from core.adapter import AdapterError, GameAdapterContext
from games.hades.adapter import HadesAdapter
from games.hades.preferences import HadesPreferenceStore
from games.hades.schema import DEFAULT_FEATURES, DEFAULT_PREFERENCES


class Runtime:
    def __init__(self):
        self.events = []
        self.speed = 1.0
        self.speed_error = None
        self.state = {'connected': True, 'pid': 42, 'heroReady': True,
                      'heroId': 'generation:run:hero', 'target': {'heroId': 'generation:run:hero'},
                      'features': dict(DEFAULT_FEATURES), 'health': 50, 'maxHealth': 100,
                      'money': 25, 'rerolls': 3,
                      'healthLocked': False, 'healthLock': None,
                      'moneyLocked': False, 'moneyLock': None,
                      'rerollsLocked': False, 'rerollsLock': None,
                      'boonRarityTarget': 'Heroic', 'boonForceLegendary': False, 'boonForceDuo': False,
                      'fishingChance': None, 'chaosGateChance': None,
                      'resources': {}, 'traits': [], 'invincible': False}

    def connect(self, pid, executable, features=None):
        self.events.append(('connect', features))
        self.state['connected'] = True
        self.state['features'] = dict(features)
        return self.status()

    def status(self):
        return dict(self.state)

    def current_game_speed(self):
        self.events.append(('current_game_speed', {}))
        if self.speed_error:
            raise self.speed_error
        return self.speed

    def set_game_speed(self, value):
        self.events.append(('set_game_speed', value))
        if self.speed_error:
            raise self.speed_error
        self.speed = value
        return value

    def command(self, name, params):
        self.events.append((name, params))
        if name == 'set_feature':
            self.state['features'][params['feature']] = params['value']
            if params['feature'] == 'moneyNoDecrease' and params['value']:
                self.state['moneyLocked'] = False
                self.state['moneyLock'] = None
            if params['feature'] == 'rerollsNoDecrease' and params['value']:
                self.state['rerollsLocked'] = False
                self.state['rerollsLock'] = None
        if name == 'configure_locks':
            self.state['healthLock'] = params.get('health')
            self.state['healthLocked'] = params.get('health') is not None
            if self.state['healthLocked']:
                self.state['health'] = self.state['healthLock']['current']
                self.state['maxHealth'] = self.state['healthLock']['max']
            self.state['moneyLock'] = params.get('money')
            self.state['moneyLocked'] = params.get('money') is not None
            self.state['rerollsLock'] = params.get('rerolls')
            self.state['rerollsLocked'] = params.get('rerolls') is not None
            if 'resourceLocks' in params:
                self.state['resourceLocks'] = dict(params.get('resourceLocks') or {})
            if self.state['moneyLocked']:
                self.state['money'] = self.state['moneyLock']
            if self.state['rerollsLocked']:
                self.state['rerolls'] = self.state['rerollsLock']
        if name == 'lock_vital':
            assert params['vital'] == 'health'
            self.state['healthLocked'] = params['locked']
            self.state['healthLock'] = (
                {'current': self.state['health'], 'max': self.state['maxHealth']}
                if params['locked'] else None
            )
        if name == 'lock_resource':
            resource = params['resource']
            if resource == 'Money':
                self.state['moneyLocked'] = params['locked']
                self.state['moneyLock'] = self.state['money'] if params['locked'] else None
            else:
                locks = dict(self.state.get('resourceLocks') or {})
                if params['locked']:
                    locks[resource] = self.state.get('resources', {}).get(resource, 10)
                else:
                    locks.pop(resource, None)
                self.state['resourceLocks'] = locks
        if name == 'set_resource':
            res = params['resource']
            self.state.setdefault('resources', {})[res] = params['value']
            locks = dict(self.state.get('resourceLocks') or {})
            if res in locks:
                locks[res] = params['value']
                self.state['resourceLocks'] = locks
        if name == 'lock_rerolls':
            self.state['rerollsLocked'] = params['locked']
            self.state['rerollsLock'] = self.state['rerolls'] if params['locked'] else None
        if name == 'set_value':
            self.state[params['field']] = params['value']
            if params['field'] in ('health', 'maxHealth') and self.state['healthLocked']:
                self.state['healthLock'] = {
                    'current': min(self.state['health'], self.state['maxHealth']),
                    'max': self.state['maxHealth'],
                }
                self.state['health'] = self.state['healthLock']['current']
            if params['field'] == 'money' and self.state['moneyLocked']:
                self.state['moneyLock'] = params['value']
            if params['field'] == 'rerolls' and self.state['rerollsLocked']:
                self.state['rerollsLock'] = params['value']
        if name == 'set_boon_rarity':
            self.state['boonRarityTarget'] = params['target']
            self.state['boonForceLegendary'] = bool(params.get('forceLegendary', False))
            self.state['boonForceDuo'] = bool(params.get('forceDuo', False))
        if name == 'set_fishing_chance':
            self.state['fishingChance'] = params['chance']
        if name == 'set_chaos_gate_chance':
            self.state['chaosGateChance'] = params['chance']
        if name == 'disable_all':
            self.state['features'] = dict(DEFAULT_FEATURES)
            self.state['boonRarityTarget'] = 'Heroic'
            self.state['boonForceLegendary'] = False
            self.state['boonForceDuo'] = False
            self.state['fishingChance'] = None
            self.state['chaosGateChance'] = None
            self.state['healthLocked'] = False
            self.state['healthLock'] = None
            self.state['moneyLocked'] = False
            self.state['moneyLock'] = None
            self.state['rerollsLocked'] = False
            self.state['rerollsLock'] = None
            self.state['resourceLocks'] = {}
        return self.status()

    def disconnect(self):
        self.events.append(('disconnect', {}))
        self.speed = 1.0
        self.state['connected'] = False
        return self.status()

    def close(self):
        pass


context = GameAdapterContext('hades', 'Hades', 2, ROOT / 'Backend/games/hades', {})
with tempfile.TemporaryDirectory(prefix='hades-commands-') as directory:
    store = HadesPreferenceStore(Path(directory) / 'preferences.json')
    runtime = Runtime()
    adapter = HadesAdapter(context, runtime=runtime, locate_process=lambda: (42, '/tmp/Hades/Game.macOS'), preferences=store)
    to_legacy = {
        'infiniteHealth': 'fullHealth',
        'infiniteMoney': 'moneyNoDecrease',
        'infiniteRerolls': 'rerollsNoDecrease',
        'forceEnableRerolls': 'forceRerolls',
    }
    historical = {
        to_legacy.get(name, name): value for name, value in DEFAULT_FEATURES.items()
        if name not in {'infiniteHealth', 'infiniteAmmo', 'forceEnableRerolls', 'incomingDamageMultiplier',
                        'moneyMultiplierEnabled', 'resourceMultiplierEnabled', 'moneyMultiplier', 'resourceMultiplier'}
    }
    legacy = dict(historical)
    legacy.pop('boonRarityEnabled')
    store.path.write_text(json.dumps({'schemaVersion': 1, 'features': legacy}))
    assert store.load() == DEFAULT_PREFERENCES, 'original preferences did not migrate'
    store.path.write_text(json.dumps({'schemaVersion': 1, 'features': historical}))
    assert store.load() == DEFAULT_PREFERENCES, 'post-rarity preferences did not migrate'
    previous_before_rarity_target = {
        to_legacy.get(name, name): value for name, value in DEFAULT_PREFERENCES.items()
        if name not in {'boonRarityTarget', 'boonForceLegendary', 'boonForceDuo',
                        'fishingChance', 'chaosGateChance',
                        'healthLock', 'moneyLock', 'rerollsLock',
                        'moneyMultiplierEnabled', 'resourceMultiplierEnabled',
                        'moneyMultiplier', 'resourceMultiplier', 'resourceLocks'}
    }
    previous_before_rarity_target['boonRarityEnabled'] = True
    previous_before_rarity_target['gameSpeed'] = 2.0
    previous_before_rarity_target['fullHealth'] = True
    store.path.write_text(json.dumps({'schemaVersion': 1, 'features': previous_before_rarity_target}))
    assert store.load() == {
        **DEFAULT_PREFERENCES, 'boonRarityEnabled': True, 'gameSpeed': 2.0, 'infiniteHealth': True,
    }, 'older schema-1 preferences did not acquire the neutral rarity/lock targets and canonical IDs'
    schema_five = {
        name: value for name, value in DEFAULT_PREFERENCES.items()
        if name not in {'moneyMultiplierEnabled', 'resourceMultiplierEnabled',
                        'moneyMultiplier', 'resourceMultiplier', 'resourceLocks'}
    }
    schema_four = {
        name: value for name, value in schema_five.items()
        if name not in {'fishingChance', 'chaosGateChance'}
    }
    schema_three = {
        name: value for name, value in schema_four.items()
        if name not in {'boonForceLegendary', 'boonForceDuo'}
    }
    schema_two = {
        to_legacy.get(name, name): value for name, value in schema_three.items()
    }
    schema_two['boonRarityEnabled'] = True
    schema_two['boonRarityTarget'] = 'Rare'
    schema_two['fullHealth'] = True
    schema_two['moneyNoDecrease'] = True
    schema_two['rerollsNoDecrease'] = True
    schema_two['forceRerolls'] = True
    store.path.write_text(json.dumps({'schemaVersion': 2, 'features': schema_two}))
    assert store.load() == {
        **DEFAULT_PREFERENCES,
        'boonRarityEnabled': True,
        'boonRarityTarget': 'Rare',
        'infiniteHealth': True,
        'infiniteMoney': True,
        'infiniteRerolls': True,
        'forceEnableRerolls': True,
    }, 'schema-2 legacy cheat IDs did not migrate onto canonical IDs'
    schema_three['boonRarityTarget'] = 'Epic'
    store.path.write_text(json.dumps({'schemaVersion': 3, 'features': schema_three}))
    assert store.load() == {
        **DEFAULT_PREFERENCES,
        'boonRarityTarget': 'Epic',
        'boonForceLegendary': False,
        'boonForceDuo': False,
        'fishingChance': None,
        'chaosGateChance': None,
    }, 'schema-3 canonical preferences did not migrate forced rarity flags'
    schema_four['boonForceLegendary'] = True
    store.path.write_text(json.dumps({'schemaVersion': 4, 'features': schema_four}))
    assert store.load() == {
        **DEFAULT_PREFERENCES,
        'boonForceLegendary': True,
        'fishingChance': None,
        'chaosGateChance': None,
    }, 'schema-4 canonical preferences did not migrate spawn chances'
    schema_five['fishingChance'] = 25.0
    store.path.write_text(json.dumps({'schemaVersion': 5, 'features': schema_five}))
    assert store.load() == {
        **DEFAULT_PREFERENCES,
        'fishingChance': 25.0,
    }, 'schema-5 canonical preferences did not migrate economy multipliers and resource locks'
    # Schema 1/2/3/4/5 named those historical feature sets. The next write
    # identifies the current canonical set as schema 6.
    expected_canonical = store.load()
    store.save(expected_canonical)
    assert json.loads(store.path.read_text()) == {
        'schemaVersion': 6, 'features': expected_canonical}
    for shipped in (legacy, historical, previous_before_rarity_target, schema_two, schema_three, schema_four, schema_five):
        store.path.write_text(json.dumps({'schemaVersion': 6, 'features': shipped}))
        try:
            store.load()
        except AdapterError as error:
            assert (error.code, error.presentation) == ('preferences_failed', 'hades.error.preferencesReadFailed')
        else:
            raise AssertionError('schema 6 accepted a pre-canonical feature set')

    # Settings written by a newer Trainer are refused and never replaced: not by
    # edits, a Profile load, or the Disable All the Host sends on app exit.
    newer = json.dumps({'schemaVersion': 7, 'features': {'futureFeature': True}})
    store.path.write_text(newer)
    newer_runtime = Runtime()
    newer_adapter = HadesAdapter(context, runtime=newer_runtime, preferences=store,
                                 locate_process=lambda: (42, '/tmp/Hades/Game.macOS'))
    newer_adapter.profiles.save('Older', DEFAULT_PREFERENCES)
    refusals = [store.load, lambda: store.save(DEFAULT_PREFERENCES)] + [
        lambda command=command, params=params: newer_adapter.dispatch(command, params, command)
        for command, params in (('connect', {}), ('set_feature', {'feature': 'invincibility', 'value': True}),
                                ('set_boon_rarity', {'target': 'Rare', 'forceLegendary': False, 'forceDuo': False}),
                                ('set_fishing_chance', {'chance': 50}),
                                ('set_chaos_gate_chance', {'chance': 25}),
                                ('save_profile', {'name': 'Newer'}),
                                ('load_profile', {'name': 'Older'}), ('disable_all', {}))]
    for refused in refusals:
        try:
            refused()
        except AdapterError as error:
            assert (error.code, error.presentation) == (
                'preferences_unsupported_schema', 'hades.error.preferencesNewerFormat'), error.code
        else:
            raise AssertionError('settings from a newer Trainer were accepted')
        assert store.path.read_text() == newer, 'settings from a newer Trainer were replaced'
    assert newer_runtime.events == [], 'refused settings reached the runtime'
    assert [row['name'] for row in newer_adapter.profiles.list()] == ['Older']
    newer_adapter.profiles.delete('Older')
    store.path.unlink()

    adapter.profiles.root.mkdir(parents=True, exist_ok=True)
    profile_name = 'Previous Current'
    previous_current = {
        to_legacy.get(name, name): value for name, value in DEFAULT_PREFERENCES.items()
        if name not in {'boonForceLegendary', 'boonForceDuo',
                        'fishingChance', 'chaosGateChance',
                        'healthLock', 'moneyLock', 'rerollsLock',
                        'moneyMultiplierEnabled', 'resourceMultiplierEnabled',
                        'moneyMultiplier', 'resourceMultiplier', 'resourceLocks'}
    }
    previous_current['boonRarityEnabled'] = True
    previous_current['boonRarityTarget'] = 'Rare'
    adapter.profiles.path(profile_name).write_text(json.dumps({
        'schemaVersion': 1, 'gameID': 'hades', 'name': profile_name,
        'updatedAt': '2026-11-04T00:00:00+00:00', 'features': previous_current,
    }))
    loaded_profile = adapter.dispatch('load_profile', {'name': profile_name}, 'load-previous-profile')
    assert loaded_profile['boonRarityTarget'] == 'Rare'
    assert loaded_profile['boonForceLegendary'] is False and loaded_profile['boonForceDuo'] is False
    assert loaded_profile['healthLock'] is None
    assert loaded_profile['moneyLock'] is None and loaded_profile['rerollsLock'] is None
    assert store.load()['healthLock'] is None
    assert store.load()['moneyLock'] is None and store.load()['rerollsLock'] is None
    assert runtime.events == []

    offline = adapter.dispatch('catalog', {'language': 'en', 'query': 'Zeus'}, 'catalog')
    assert offline['catalog'] and 'connected' not in offline and runtime.events == []

    # Durable desired state is editable while detached. No runtime command is
    # issued until connect, where the complete preference document is replayed.
    detached = adapter.dispatch(
        'set_boon_rarity',
        {'target': 'Rare', 'forceLegendary': True, 'forceDuo': False},
        'rarity-target-offline',
    )
    adapter.dispatch('set_feature', {'feature': 'boonRarityEnabled', 'value': True}, 'rarity-on-offline')
    adapter.dispatch('set_feature', {'feature': 'gameSpeed', 'value': 1.5}, 'speed-offline')
    assert runtime.events == []
    assert detached['boonRarityTarget'] == 'Rare'
    assert detached['boonForceLegendary'] is True and detached['boonForceDuo'] is False
    assert 'boonRarityTarget' not in detached['features']
    assert detached['dormantFeatures'] == {}, 'a detached projection fabricated a dormant observation'
    assert store.load()['boonRarityTarget'] == 'Rare'
    assert store.load()['boonForceLegendary'] is True and store.load()['boonForceDuo'] is False
    assert store.load()['boonRarityEnabled'] is True
    assert store.load()['gameSpeed'] == 1.5

    runtime.state['dormantFeatures'] = {'boonRarityEnabled': True, 'retiredFeature': True}
    live = adapter.dispatch('connect', {}, 'connect')
    assert live['dormantFeatures'] == {'boonRarityEnabled': True}, (
        'the live dormant observation was not projected over the current feature set'
    )
    del runtime.state['dormantFeatures']
    connect_features = next(event for event in runtime.events if event[0] == 'connect')[1]
    assert connect_features['boonRarityEnabled'] is True
    assert 'boonRarityTarget' not in connect_features
    assert 'gameSpeed' not in connect_features
    assert not any(event[0] == 'configure_locks' for event in runtime.events), (
        'neutral locks added a redundant native status round-trip'
    )
    assert ('set_boon_rarity', {'target': 'Rare', 'forceLegendary': True, 'forceDuo': False}) in runtime.events
    assert ('set_game_speed', 1.5) in runtime.events
    calls = len(runtime.events)
    for bad in (1, 'true', None):
        try:
            adapter.dispatch('set_feature', {'feature': 'boonRarityEnabled', 'value': bad}, 'rarity-invalid')
        except AdapterError as error:
            assert error.code == 'invalid_value'
        else:
            raise AssertionError('invalid rarity toggle reached runtime')
    for bad in ('Legendary', 'Duo', 1, None):
        try:
            adapter.dispatch('set_boon_rarity', {'target': bad, 'forceLegendary': False, 'forceDuo': False}, 'rarity-target-invalid')
        except AdapterError as error:
            assert error.code == 'invalid_value'
        else:
            raise AssertionError('invalid rarity target reached runtime')
    for bad_flag in (1, 'true', None):
        for bad_params in (
            {'target': 'Rare', 'forceLegendary': bad_flag, 'forceDuo': False},
            {'target': 'Rare', 'forceLegendary': False, 'forceDuo': bad_flag},
        ):
            try:
                adapter.dispatch('set_boon_rarity', bad_params, 'rarity-force-invalid')
            except AdapterError as error:
                assert error.code == 'invalid_value'
            else:
                raise AssertionError('invalid force flag reached runtime')
    assert len(runtime.events) == calls and store.load()['boonRarityEnabled'] is True

    # Fishing and Chaos Gate spawn chances: offline editing, validation, connect replay, and reset.
    detached_fish = adapter.dispatch('set_fishing_chance', {'chance': 42.5}, 'fish-offline')
    assert detached_fish['fishingChance'] == 42.5 and store.load()['fishingChance'] == 42.5
    detached_chaos = adapter.dispatch('set_chaos_gate_chance', {'chance': 100}, 'chaos-offline')
    assert detached_chaos['chaosGateChance'] == 100.0 and store.load()['chaosGateChance'] == 100.0
    before_chance_calls = len(runtime.events)
    for bad_chance in (-1, 101, True, '50', float('nan'), float('inf')):
        for chance_cmd in ('set_fishing_chance', 'set_chaos_gate_chance'):
            try:
                adapter.dispatch(chance_cmd, {'chance': bad_chance}, 'invalid-chance')
            except AdapterError as error:
                assert error.code == 'invalid_value', (chance_cmd, bad_chance, error.code)
            else:
                raise AssertionError((chance_cmd, bad_chance))
    assert len(runtime.events) == before_chance_calls
    adapter.dispatch('disconnect', {}, 'detach-before-chance-connect')
    runtime.events.clear()
    reconnect_chances = adapter.dispatch('connect', {}, 'connect-with-chances')
    assert reconnect_chances['fishingChance'] == 42.5 and reconnect_chances['chaosGateChance'] == 100.0
    assert ('set_fishing_chance', {'chance': 42.5}) in runtime.events
    assert ('set_chaos_gate_chance', {'chance': 100.0}) in runtime.events

    connected_profile = dict(store.load())
    connected_profile['boonRarityTarget'] = 'Epic'
    connected_profile['boonForceLegendary'] = False
    connected_profile['boonForceDuo'] = True
    connected_profile['fishingChance'] = 12.5
    connected_profile['chaosGateChance'] = 0.0
    connected_name = 'Connected Epic'
    adapter.profiles.path(connected_name).write_text(json.dumps({
        'schemaVersion': 6, 'gameID': 'hades', 'name': connected_name,
        'updatedAt': '2026-11-04T00:00:01+00:00', 'features': connected_profile,
    }))
    before_profile_events = len(runtime.events)
    profile_state = adapter.dispatch('load_profile', {'name': connected_name}, 'load-connected-profile')
    assert profile_state['boonRarityTarget'] == 'Epic'
    assert profile_state['boonForceLegendary'] is False and profile_state['boonForceDuo'] is True
    assert profile_state['fishingChance'] == 12.5 and profile_state['chaosGateChance'] == 0.0
    assert ('set_boon_rarity', {'target': 'Epic', 'forceLegendary': False, 'forceDuo': True}) in runtime.events[before_profile_events:]
    assert ('set_fishing_chance', {'chance': 12.5}) in runtime.events[before_profile_events:]
    assert ('set_chaos_gate_chance', {'chance': 0.0}) in runtime.events[before_profile_events:]
    assert store.load()['boonRarityTarget'] == 'Epic' and store.load()['boonForceDuo'] is True
    assert store.load()['fishingChance'] == 12.5 and store.load()['chaosGateChance'] == 0.0

    owner = {'heroId': 'generation:run:hero'}
    locked_health = adapter.dispatch(
        'lock_vital', {'vital': 'health', 'locked': True, 'target': owner}, 'lock-health'
    )
    assert locked_health['healthLocked'] is True
    assert store.load()['healthLock'] == {'current': 50, 'max': 100}
    adapter.dispatch('set_value', {'field': 'health', 'value': 40, 'target': owner}, 'edit-locked-health')
    assert store.load()['healthLock'] == {'current': 40, 'max': 100}
    adapter.dispatch('set_value', {'field': 'maxHealth', 'value': 80, 'target': owner}, 'edit-locked-max-health')
    assert store.load()['healthLock'] == {'current': 40, 'max': 80}
    adapter.dispatch('disconnect', {}, 'detach-health-lock')
    # The resident keeps enforcing its lock across a detach; reconnect only
    # replays durable lock intent the resident no longer holds.
    before_reconnect = len(runtime.events)
    reconnected = adapter.dispatch('connect', {}, 'reconnect-health-lock')
    assert reconnected['healthLocked'] is True
    assert reconnected['healthLock'] == {'current': 40, 'max': 80}
    assert not any(event[0] == 'configure_locks' for event in runtime.events[before_reconnect:]), (
        'reconnect re-sent a lock the resident already enforced'
    )
    adapter.dispatch('disconnect', {}, 'detach-before-restart')
    runtime.state.update(healthLocked=False, healthLock=None)  # a restarted game has no resident lock
    before_reconnect = len(runtime.events)
    reconnected = adapter.dispatch('connect', {}, 'reconnect-after-restart')
    assert reconnected['healthLocked'] is True
    assert ('configure_locks', {
        'health': {'current': 40, 'max': 80}, 'money': None, 'rerolls': None
    }) in runtime.events[before_reconnect:], 'durable health lock did not replay on reconnect'
    adapter.dispatch(
        'lock_vital', {'vital': 'health', 'locked': False, 'target': owner}, 'unlock-health'
    )
    assert store.load()['healthLock'] is None

    locked_money = adapter.dispatch(
        'lock_resource', {'resource': 'Money', 'locked': True, 'target': owner}, 'lock-money'
    )
    assert locked_money['moneyLocked'] is True and locked_money['moneyLock'] == 25
    assert store.load()['moneyLock'] == 25
    adapter.dispatch('set_value', {'field': 'money', 'value': 44, 'target': owner}, 'edit-locked-money')
    assert store.load()['moneyLock'] == 44 and runtime.state['moneyLock'] == 44
    adapter.dispatch(
        'lock_resource', {'resource': 'Money', 'locked': False, 'target': owner}, 'unlock-money'
    )
    assert store.load()['moneyLock'] is None

    locked_rerolls = adapter.dispatch(
        'lock_rerolls', {'locked': True, 'target': owner}, 'lock-rerolls'
    )
    assert locked_rerolls['rerollsLocked'] is True and locked_rerolls['rerollsLock'] == 3
    assert store.load()['rerollsLock'] == 3
    adapter.dispatch('set_value', {'field': 'rerolls', 'value': 7, 'target': owner}, 'edit-locked-rerolls')
    assert store.load()['rerollsLock'] == 7 and runtime.state['rerollsLock'] == 7
    adapter.dispatch('set_feature', {'feature': 'infiniteRerolls', 'value': True}, 'infinite-rerolls')
    assert store.load()['rerollsLock'] is None and runtime.state['rerollsLocked'] is False
    adapter.dispatch('set_feature', {'feature': 'infiniteRerolls', 'value': False}, 'normal-rerolls')

    class RejectingLockPreferences:
        def save(self, features):
            raise AdapterError('preferences_failed', 'hades.error.preferencesFailed')

    # Health pair rollback uses the same durable-owner contract as scalar locks.
    adapter.preferences = store
    adapter.dispatch(
        'lock_vital', {'vital': 'health', 'locked': True, 'target': owner}, 'lock-health-before-edit-failure'
    )
    previous_health_lock = dict(store.load()['healthLock'])
    adapter.preferences = RejectingLockPreferences()
    try:
        adapter.dispatch(
            'set_value', {'field': 'maxHealth', 'value': previous_health_lock['max'] - 5, 'target': owner},
            'locked-health-edit-disk-failure'
        )
    except AdapterError as error:
        assert error.code == 'preferences_failed'
    else:
        raise AssertionError('failed health-lock edit persistence was presented as success')
    assert runtime.state['healthLock'] == previous_health_lock
    assert runtime.state['health'] == previous_health_lock['current']
    assert runtime.state['maxHealth'] == previous_health_lock['max'], (
        'failed max-health lock edit did not restore the previous native pair'
    )
    adapter.preferences = store
    adapter.dispatch(
        'lock_vital', {'vital': 'health', 'locked': False, 'target': owner}, 'unlock-health-after-rollback'
    )

    adapter.preferences = RejectingLockPreferences()
    before_lock_failure = dict(runtime.state)
    try:
        adapter.dispatch(
            'lock_resource', {'resource': 'Money', 'locked': True, 'target': owner}, 'lock-money-disk-failure'
        )
    except AdapterError as error:
        assert error.code == 'preferences_failed'
    else:
        raise AssertionError('failed fixed-lock persistence was presented as success')
    assert runtime.state['moneyLocked'] is False and runtime.state['moneyLock'] is None
    assert runtime.state['money'] == before_lock_failure['money'], (
        'failed lock persistence left a native fixed-value owner mounted'
    )

    adapter.preferences = store
    adapter.dispatch(
        'lock_resource', {'resource': 'Money', 'locked': False, 'target': owner}, 'unlock-money-before-gems-rollback'
    )
    adapter.preferences = RejectingLockPreferences()
    try:
        adapter.dispatch(
            'lock_resource', {'resource': 'Gems', 'locked': True, 'target': owner}, 'lock-gems-disk-failure'
        )
    except AdapterError as error:
        assert error.code == 'preferences_failed'
    else:
        raise AssertionError('failed permanent-resource lock persistence was presented as success')
    assert runtime.state['resourceLocks'] == {}, (
        'failed permanent-resource lock persistence left resource lock mounted'
    )
    adapter.preferences = store
    locked_gems = adapter.dispatch(
        'lock_resource', {'resource': 'Gems', 'locked': True, 'target': owner}, 'lock-gems-before-edit-failure'
    )
    assert locked_gems['resourceLocks'] == {'Gems': 10}
    previous_gems = store.load()['resourceLocks']['Gems']
    adapter.preferences = RejectingLockPreferences()
    try:
        adapter.dispatch(
            'set_resource', {'resource': 'Gems', 'value': previous_gems + 5, 'target': owner}, 'locked-gems-edit-disk-failure'
        )
    except AdapterError as error:
        assert error.code == 'preferences_failed'
    else:
        raise AssertionError('failed locked resource edit persistence was presented as success')
    assert runtime.state['resourceLocks'].get('Gems') == previous_gems, (
        'failed locked resource edit did not roll back runtime lock'
    )
    adapter.preferences = store
    adapter.dispatch(
        'lock_resource', {'resource': 'Gems', 'locked': False, 'target': owner}, 'unlock-gems-after-rollback'
    )
    adapter.dispatch(
        'lock_resource', {'resource': 'Money', 'locked': True, 'target': owner}, 'lock-money-before-edit-failure'
    )
    previous_lock = store.load()['moneyLock']
    adapter.preferences = RejectingLockPreferences()
    try:
        adapter.dispatch(
            'set_value', {'field': 'money', 'value': previous_lock + 9, 'target': owner}, 'locked-edit-disk-failure'
        )
    except AdapterError as error:
        assert error.code == 'preferences_failed'
    else:
        raise AssertionError('failed locked edit persistence was presented as success')
    assert runtime.state['moneyLock'] == previous_lock and runtime.state['money'] == previous_lock, (
        'failed locked edit did not restore the previous native lock target'
    )
    adapter.preferences = store
    adapter.dispatch(
        'lock_resource', {'resource': 'Money', 'locked': False, 'target': owner}, 'unlock-after-rollback'
    )

    adapter.dispatch('set_feature', {'feature': 'infiniteMoney', 'value': True}, 'enable')
    assert store.load()['infiniteMoney'] is True
    state = adapter.dispatch('set_feature', {'feature': 'gameSpeed', 'value': 2.5}, 'speed-up')
    assert runtime.speed == 2.5 and store.load()['gameSpeed'] == 2.5
    assert state['features']['gameSpeed']['actual'] == 2.5
    assert state['features']['gameSpeed']['active'] is True
    before = store.path.read_bytes()
    calls = len(runtime.events)
    for bad in (True, -1, float('nan'), float('inf')):
        try:
            adapter.dispatch('set_feature', {'feature': 'damageMultiplier', 'value': bad}, 'invalid')
        except AdapterError as error:
            assert error.code == 'invalid_value'
        else:
            raise AssertionError('invalid input reached the runtime')
    assert len(runtime.events) == calls and store.path.read_bytes() == before
    try:
        adapter.dispatch('set_resource', {'resource': 'Gems', 'value': 123}, 'stale')
    except AdapterError as error:
        assert error.code == 'stale_target'
    else:
        raise AssertionError('one-shot action without a captured hero was accepted')
    assert len(runtime.events) == calls
    params = {'resource': 'Gems', 'value': 123, 'target': {'heroId': 'generation:run:hero'}}
    adapter.dispatch('set_resource', params, 'edit')
    assert runtime.events[-1] == ('set_resource', params)
    long_token = 'trait:AmmoBoltTrait:' + ','.join(map(str, range(1, 101)))
    adapter.dispatch('remove_trait', {'instanceId': long_token, 'target': params['target']}, 'level-100-remove')
    assert runtime.events[-1] == ('remove_trait', {'instanceId': long_token, 'target': params['target']})
    try:
        adapter.dispatch('open_sell_traits', {}, 'stale-sell-traits')
    except AdapterError as error:
        assert error.code == 'stale_target'
    else:
        raise AssertionError('open_sell_traits without a captured hero was accepted')
    runtime.state['canOpenSellTraits'] = True
    sell_state = adapter.dispatch('open_sell_traits', {'target': params['target']}, 'open-sell-traits')
    assert runtime.events[-1] == ('open_sell_traits', {'target': params['target']})
    assert sell_state['canOpenSellTraits'] is True
    runtime.state['canOpenSellTraits'] = False
    adapter.dispatch('disable_all', {}, 'disable')
    assert store.load() == DEFAULT_PREFERENCES and runtime.speed == 1.0
    adapter.dispatch('set_feature', {'feature': 'gameSpeed', 'value': 4.0}, 'speed-before-detach')
    adapter.dispatch('disconnect', {}, 'detach')
    assert runtime.speed == 1.0
    adapter.dispatch('disable_all', {}, 'offline-disable')
    assert store.load() == DEFAULT_PREFERENCES
    assert json.loads(store.path.read_text())['schemaVersion'] == 6

    class UnwritablePreferences:
        def save(self, features):
            raise AdapterError('preferences_failed', 'hades.error.preferencesFailed')

    adapter.preferences = UnwritablePreferences()
    adapter.connected = True
    try:
        adapter.dispatch('disable_all', {}, 'exit-cleanup')
    except AdapterError as error:
        assert error.code == 'preferences_failed'
    else:
        raise AssertionError('cleanup hid the failed durable reset')
    assert ('disable_all', {}) in runtime.events, 'disk failure blocked resident cleanup'
    assert runtime.events[-1] == ('set_game_speed', 1.0), 'Disable All skipped speed reset after persistence failure'

print('hades_command_validation_preferences_and_target_ownership_ok')
