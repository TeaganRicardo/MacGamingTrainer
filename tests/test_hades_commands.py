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
                      'money': 25, 'resources': {}, 'traits': [], 'invincible': False}

    def connect(self, pid, executable, features=None):
        self.events.append(('connect', features))
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
        if name == 'disable_all':
            self.state['features'] = dict(DEFAULT_FEATURES)
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
    historical = {name: value for name, value in DEFAULT_FEATURES.items()
                  if name not in {'fullHealth', 'infiniteAmmo', 'forceRerolls', 'incomingDamageMultiplier'}}
    legacy = dict(historical)
    legacy.pop('boonRarityEnabled')
    store.path.write_text(json.dumps({'schemaVersion': 1, 'features': legacy}))
    assert store.load() == {**DEFAULT_PREFERENCES, **legacy}, 'original preferences did not migrate'
    store.path.write_text(json.dumps({'schemaVersion': 1, 'features': historical}))
    assert store.load() == {**DEFAULT_PREFERENCES, **historical}, 'post-rarity preferences did not migrate'
    offline = adapter.dispatch('catalog', {'language': 'en', 'query': 'Zeus'}, 'catalog')
    assert offline['catalog'] and 'connected' not in offline and runtime.events == []
    adapter.dispatch('connect', {}, 'connect')
    assert next(event for event in runtime.events if event[0] == 'connect')[1]['boonRarityEnabled'] is False
    assert 'gameSpeed' not in next(event for event in runtime.events if event[0] == 'connect')[1]
    adapter.dispatch('set_feature', {'feature': 'boonRarityEnabled', 'value': True}, 'rarity-on')
    assert store.load()['boonRarityEnabled'] is True
    assert runtime.events[-1] == ('set_feature', {'feature': 'boonRarityEnabled', 'value': True})
    calls = len(runtime.events)
    for bad in (1, 'true', None):
        try:
            adapter.dispatch('set_feature', {'feature': 'boonRarityEnabled', 'value': bad}, 'rarity-invalid')
        except AdapterError as error:
            assert error.code == 'invalid_value'
        else:
            raise AssertionError('invalid rarity toggle reached runtime')
    assert len(runtime.events) == calls and store.load()['boonRarityEnabled'] is True
    adapter.dispatch('set_feature', {'feature': 'moneyNoDecrease', 'value': True}, 'enable')
    assert store.load()['moneyNoDecrease'] is True
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
    adapter.dispatch('disable_all', {}, 'disable')
    assert store.load() == DEFAULT_PREFERENCES and runtime.speed == 1.0
    adapter.dispatch('set_feature', {'feature': 'gameSpeed', 'value': 4.0}, 'speed-before-detach')
    adapter.dispatch('disconnect', {}, 'detach')
    assert runtime.speed == 1.0
    adapter.dispatch('disable_all', {}, 'offline-disable')
    assert store.load() == DEFAULT_PREFERENCES
    assert json.loads(store.path.read_text())['schemaVersion'] == 1

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
