import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
from core.adapter import AdapterError, GameAdapterContext
from games.hades.adapter import HadesAdapter
from games.hades.preferences import HadesPreferenceStore
from games.hades.schema import DEFAULT_FEATURES


class Runtime:
    def __init__(self):
        self.events = []
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

    def command(self, name, params):
        self.events.append((name, params))
        if name == 'set_feature':
            self.state['features'][params['feature']] = params['value']
        if name == 'disable_all':
            self.state['features'] = dict(DEFAULT_FEATURES)
        return self.status()

    def disconnect(self):
        self.state['connected'] = False
        return self.status()

    def close(self):
        pass


context = GameAdapterContext('hades', 'Hades', 2, ROOT / 'Backend/games/hades', {})
with tempfile.TemporaryDirectory(prefix='hades-commands-') as directory:
    store = HadesPreferenceStore(Path(directory) / 'preferences.json')
    runtime = Runtime()
    adapter = HadesAdapter(context, runtime=runtime, locate_process=lambda: (42, '/tmp/Hades/Game.macOS'), preferences=store)
    legacy = dict(DEFAULT_FEATURES)
    legacy.pop('boonRarityEnabled')
    store.path.write_text(json.dumps({'schemaVersion': 1, 'features': legacy}))
    assert store.load() == {**legacy, 'boonRarityEnabled': False}, 'old preferences cannot load after feature addition'
    offline = adapter.dispatch('catalog', {'language': 'en', 'query': 'Zeus'}, 'catalog')
    assert offline['catalog'] and 'connected' not in offline and runtime.events == []
    adapter.dispatch('connect', {}, 'connect')
    assert runtime.events[-1][1]['boonRarityEnabled'] is False
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
    assert store.load() == DEFAULT_FEATURES
    adapter.dispatch('disconnect', {}, 'detach')
    adapter.dispatch('disable_all', {}, 'offline-disable')
    assert store.load() == DEFAULT_FEATURES
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
    assert runtime.events[-1] == ('disable_all', {}), 'disk failure blocked resident cleanup'

print('hades_command_validation_preferences_and_target_ownership_ok')
