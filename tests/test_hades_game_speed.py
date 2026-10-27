"""Hades game-speed preference, connection, and applied-state contract."""
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
        self.status_reads = 0
        self.state = {'connected': True, 'pid': 42, 'heroReady': True,
                      'heroId': 'generation:run:hero', 'target': {'heroId': 'generation:run:hero'},
                      'features': dict(DEFAULT_FEATURES), 'health': 50, 'maxHealth': 100,
                      'money': 25, 'resources': {}, 'traits': [], 'invincible': False}

    def connect(self, pid, executable, features=None):
        self.events.append(('connect', features))
        self.state['connected'] = True
        self.state['pid'] = pid
        self.state['features'] = dict(features)
        return self.status()

    def status(self):
        self.status_reads += 1
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
        return self.speed

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
with tempfile.TemporaryDirectory(prefix='hades-speed-') as directory:
    path = Path(directory) / 'preferences.json'
    store = HadesPreferenceStore(path)
    historical = {name: value for name, value in DEFAULT_FEATURES.items()
                  if name not in {'fullHealth', 'infiniteAmmo', 'forceRerolls', 'incomingDamageMultiplier'}}
    legacy = dict(historical)
    legacy.pop('boonRarityEnabled')
    path.write_text(json.dumps({'schemaVersion': 1, 'features': legacy}))
    assert store.load() == {**DEFAULT_PREFERENCES, **legacy}
    path.write_text(json.dumps({'schemaVersion': 1, 'features': historical}))
    assert store.load() == {**DEFAULT_PREFERENCES, **historical}

    runtime = Runtime()
    adapter = HadesAdapter(context, runtime=runtime,
                           locate_process=lambda: (42, '/tmp/Hades/Game.macOS'), preferences=store)
    state = adapter.dispatch('connect', {}, 'connect')
    assert state['connected']
    assert runtime.status_reads == 1, 'connect issued a redundant full native status round-trip'
    assert 'gameSpeed' not in runtime.events[0][1], 'process-owned speed leaked into Lua resident settings'
    assert state['features']['gameSpeed'] == {
        'desired': 1.0, 'actual': 1.0, 'active': False,
        'errorPresentation': None, 'errorArguments': [],
    }

    state = adapter.dispatch('set_feature', {'feature': 'gameSpeed', 'value': 2.5}, 'speed-up')
    assert runtime.speed == 2.5 and store.load()['gameSpeed'] == 2.5
    assert state['features']['gameSpeed'] == {
        'desired': 2.5, 'actual': 2.5, 'active': True,
        'errorPresentation': None, 'errorArguments': [],
    }

    runtime.speed_error = AdapterError('time_warp_set_failed', 'host.timeWarp.error.setFailed', arguments=(7,))
    try:
        adapter.dispatch('set_feature', {'feature': 'gameSpeed', 'value': 3.0}, 'speed-fails')
    except AdapterError as error:
        assert error.code == 'time_warp_set_failed'
    else:
        raise AssertionError('failed native speed update was reported as success')
    assert store.load()['gameSpeed'] == 3.0, 'desired speed was not persisted after a known native failure'
    state = adapter.dispatch('status', {}, 'status-after-failure')
    assert state['features']['gameSpeed'] == {
        'desired': 3.0, 'actual': 2.5, 'active': True,
        'errorPresentation': 'host.timeWarp.error.setFailed', 'errorArguments': ['7'],
    }
    runtime.speed_error = None

    state = adapter.dispatch('disable_all', {}, 'disable')
    assert store.load() == DEFAULT_PREFERENCES
    assert runtime.speed == 1.0 and state['features']['gameSpeed']['desired'] == 1.0

    adapter.dispatch('set_feature', {'feature': 'gameSpeed', 'value': 4.0}, 'speed-before-detach')
    state = adapter.dispatch('disconnect', {}, 'disconnect')
    assert not state['connected'] and state['features']['gameSpeed']['actual'] == 1.0
    assert state['features']['gameSpeed']['desired'] == 4.0, 'disconnect discarded durable desired speed'

    for bad in (True, -0.1, 10.1, float('nan'), float('inf'), '2'):
        try:
            adapter.dispatch('set_feature', {'feature': 'gameSpeed', 'value': bad}, 'speed-invalid')
        except AdapterError as error:
            assert error.code == 'invalid_value'
        else:
            raise AssertionError(f'invalid game speed accepted: {bad!r}')

print('hades_game_speed_preference_and_applied_state_ok')
