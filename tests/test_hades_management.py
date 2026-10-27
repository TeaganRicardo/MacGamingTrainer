"""Hades feature-profile persistence, native reconciliation and diagnostic truth."""
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from core.adapter import AdapterError, GameAdapterContext
from games.hades.adapter import HadesAdapter
from games.hades.preferences import HadesPreferenceStore
from games.hades.profiles import HadesProfileStore
from games.hades.schema import DEFAULT_FEATURES, DEFAULT_PREFERENCES


class Runtime:
    def __init__(self):
        self.connected = False
        self.calls = []
        self.speed = 1.0
        self.features = dict(DEFAULT_FEATURES)
        self.unknown = False

    def status(self):
        self.calls.append(('status',))
        return {'connected': self.connected, 'pid': 42 if self.connected else None,
                'heroReady': self.connected, 'target': {'heroId': 'run:hero:1'} if self.connected else None,
                'features': dict(self.features), 'health': 50, 'money': 25}

    def connect(self, pid, executable, features):
        self.calls.append(('connect', dict(features)))
        self.connected = True
        self.features = dict(features)
        return self.status()

    def command(self, command, params):
        self.calls.append((command, params))
        assert command == 'configure'
        if self.unknown:
            self.connected = False
            raise AdapterError('outcome_unknown', 'hades.error.outcomeUnknown')
        self.features = dict(params['features'])
        return self.status()

    def current_game_speed(self):
        self.calls.append(('current_game_speed',))
        return self.speed

    def set_game_speed(self, value):
        self.calls.append(('set_game_speed', value))
        self.speed = value
        return value


def rejected(code, action):
    try:
        action()
    except AdapterError as error:
        assert error.code == code, (error.code, code)
    else:
        raise AssertionError('Invalid profile operation succeeded')


context = GameAdapterContext('hades', 'Hades', 2, ROOT / 'Backend/games/hades', {})
with tempfile.TemporaryDirectory(prefix='mgt-hades-management-') as directory:
    root = Path(directory)
    preferences = HadesPreferenceStore(root / 'hades/preferences.json')
    runtime = Runtime()
    adapter = HadesAdapter(context, runtime=runtime, preferences=preferences,
                           locate_process=lambda: (42, '/tmp/Hades/Game.macOS'))
    desired = {**DEFAULT_PREFERENCES, 'invincibility': True, 'damageMultiplier': 3, 'gameSpeed': 2}
    preferences.save(desired)
    assert adapter.dispatch('list_profiles', {}, 'list') == {'profiles': []}
    rejected('profile_invalid', lambda: adapter.dispatch('save_profile', {'name': '../escape'}, 'invalid'))
    assert adapter.dispatch('save_profile', {'name': '  战斗  '}, 'save')['profiles'][0]['name'] == '战斗'
    assert runtime.calls == [], 'saving a preset must not enter a game/debugger'
    assert adapter.profiles.load('战斗') == desired
    assert HadesProfileStore(root / 'hades2/profiles').list() == [], 'profiles crossed the game boundary'

    preferences.save(DEFAULT_PREFERENCES)
    offline = adapter.dispatch('load_profile', {'name': '战斗'}, 'load-offline')
    assert not offline['connected'] and preferences.load() == desired
    assert offline['features']['gameSpeed']['desired'] == 2
    assert offline['features']['gameSpeed']['actual'] is None and runtime.calls == []
    report = adapter.dispatch('diagnostics', {}, 'diagnostics')['diagnostics']
    assert report['gameID'] == 'hades' and report['desired'] == desired
    assert report['supportedBuild'] == json.loads((context.module_dir / 'module.json').read_text())['supportedBuild']
    assert not next(check for check in report['checks'] if check['name'] == 'hades.diagnostics.connection')['ok']
    assert not next(check for check in report['checks'] if check['name'] == 'hades.diagnostics.hero')['ok']
    assert runtime.calls == [], 'offline diagnostics must not attach or probe native state'

    adapter.dispatch('connect', {}, 'connect')
    assert runtime.features == {key: value for key, value in desired.items() if key in DEFAULT_FEATURES}
    assert runtime.speed == 2 and preferences.load() == desired
    reset = {**DEFAULT_PREFERENCES, 'damageMultiplier': 1.5, 'gameSpeed': 0.5}
    adapter.profiles.save('恢复', reset)
    state = adapter.dispatch('load_profile', {'name': '恢复'}, 'load-connected')
    assert runtime.features['damageMultiplier'] == 1.5 and not runtime.features['invincibility']
    assert runtime.speed == 0.5 and preferences.load() == reset
    assert state['health'] == 50 and state['money'] == 25, 'preset replay changed a one-shot value'
    assert state['features']['gameSpeed']['actual'] == 0.5
    assert [call[0] for call in runtime.calls if len(call) > 1 and call[0] == 'configure'] == ['configure']
    report = adapter.dispatch('diagnostics', {}, 'diagnostics-connected')['diagnostics']
    assert all(check['ok'] for check in report['checks'])
    assert report['desired'] == reset and report['state']['target']['heroId'] == 'run:hero:1'

    calls = list(runtime.calls)
    with patch.object(preferences, 'save', side_effect=AdapterError('preferences_failed', 'hades.error.preferencesFailed')):
        rejected('preferences_failed', lambda: adapter.dispatch('load_profile', {'name': '战斗'}, 'write-fails'))
    assert runtime.calls == calls, 'failed durable write still changed the runtime'

    with patch.object(runtime, 'current_game_speed', side_effect=AdapterError(
            'time_warp_verify_failed', 'host.timeWarp.error.verifyFailed')):
        rejected('time_warp_verify_failed', lambda: adapter.dispatch('load_profile', {'name': '战斗'}, 'speed-fails'))
    assert preferences.load() == desired and adapter._game_speed_error is not None
    assert adapter.connected, 'known speed failure incorrectly discarded the healthy runtime connection'

    runtime.unknown = True
    rejected('outcome_unknown', lambda: adapter.dispatch('load_profile', {'name': '战斗'}, 'unknown'))
    assert not adapter.connected and preferences.load() == desired
    assert runtime.calls[-1][0] == 'configure', 'unknown configure continued into another native operation'
    calls = list(runtime.calls)
    adapter.dispatch('list_profiles', {}, 'after-unknown')
    assert runtime.calls == calls, 'profile listing replayed uncertain native work'
    runtime.unknown = False
    adapter.dispatch('connect', {}, 'explicit-reconnect')
    assert runtime.features['invincibility'] and runtime.speed == 2

    path = adapter.profiles.path('战斗')
    document = json.loads(path.read_text())
    for key, value in [('gameID', 'hades2'), ('schemaVersion', 2), ('schemaVersion', True), ('features', {'health': 100})]:
        malformed = {**document, key: value}
        path.write_text(json.dumps(malformed))
        rejected('profile_read_failed', lambda: adapter.profiles.load('战斗'))
        assert json.loads(path.read_text()) == malformed, 'reading modified an invalid or future profile'
    path.write_text(json.dumps(document))
    adapter.dispatch('delete_profile', {'name': '恢复'}, 'delete')
    assert [row['name'] for row in adapter.dispatch('list_profiles', {}, 'list-final')['profiles']] == ['战斗']

print('hades_management_profiles_and_diagnostics_ok')
