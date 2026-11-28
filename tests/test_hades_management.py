"""Hades feature-profile persistence, native reconciliation and diagnostic truth."""
from contextlib import ExitStack
import json
import logging
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from core.adapter import AdapterError, GameAdapterContext
from games.hades import config as hades_config
from games.hades.adapter import HadesAdapter
from games.hades.cheats import to_runtime_features
from games.hades.preferences import HadesPreferenceStore
from games.hades.profiles import HadesProfileStore
from games.hades.schema import DEFAULT_FEATURES, DEFAULT_PREFERENCES


def patched_environment(root, *, installed=True, lldb_ok=True, python_ok=True, rosetta_ok=True, mailbox_ok=True):
    stack = ExitStack()
    fake_app = root / 'Hades/Game.macOS.app'
    fake_exe = fake_app / 'Contents/MacOS/Game.macOS'
    fake_saves = root / 'Saves'
    if installed:
        fake_saves.mkdir(parents=True, exist_ok=True)
        (fake_saves / 'Profile1.sav').write_bytes(b'stub')
    install_report = {
        'gameApp': fake_app,
        'executable': fake_exe,
        'manifestPath': root / 'appmanifest_1145360.acf',
        'installed': installed,
        'version': hades_config.SUPPORTED_BUILD['contentBuildInfo'] if installed else '',
        'steamBuild': hades_config.SUPPORTED_BUILD['steamBuildID'] if installed else '',
        'uuid': hades_config.SUPPORTED_BUILD['uuid'] if installed else None,
        'compatible': installed,
        'warnings': [] if installed else ['not_installed'],
    }
    stack.enter_context(patch.object(hades_config, 'inspect_install', return_value=install_report))
    stack.enter_context(patch.object(hades_config, 'saves_dir', return_value=fake_saves))
    stack.enter_context(patch.object(hades_config, 'probe_lldb', return_value=(lldb_ok, '/usr/bin/lldb' if lldb_ok else 'missing')))
    stack.enter_context(patch.object(hades_config, 'probe_lldb_python', return_value=(python_ok, "<class 'lldb.SBDebugger'>" if python_ok else 'missing')))
    stack.enter_context(patch.object(hades_config, 'probe_rosetta', return_value=(rosetta_ok, 'x86_64')))
    stack.enter_context(patch.object(hades_config, 'probe_native_mailbox', return_value=(mailbox_ok, 'lldb', 'lldb · DEADBEEF' if mailbox_ok else 'missing')))
    return stack


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
                'heroReady': self.connected, 'status': 'ready' if self.connected else 'disconnected',
                'scene': 'run' if self.connected else 'unknown',
                'roomName': 'A_Combat01' if self.connected else None,
                'runtimeRevision': 'abc123def456' if self.connected else None,
                'target': {'heroId': 'run:hero:1'} if self.connected else None,
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
    with patch.object(adapter.profiles._store, 'list', wraps=adapter.profiles._store.list) as profile_scan:
        assert adapter.dispatch('save_profile', {'name': '  战斗  '}, 'save')['profiles'][0]['name'] == '战斗'
    assert profile_scan.call_count == 1, 'saving a Profile enumerated the directory more than once'
    assert runtime.calls == [], 'saving a preset must not enter a game/debugger'
    assert adapter.profiles.load('战斗') == desired
    assert HadesProfileStore(root / 'hades2/profiles').list() == [], 'profiles crossed the game boundary'

    preferences.save(DEFAULT_PREFERENCES)
    offline = adapter.dispatch('load_profile', {'name': '战斗'}, 'load-offline')
    assert not offline['connected'] and preferences.load() == desired
    assert offline['features']['gameSpeed']['desired'] == 2
    assert offline['features']['gameSpeed']['actual'] is None and runtime.calls == []
    with patched_environment(root):
        diagnostic_reply = adapter.dispatch('diagnostics', {}, 'diagnostics')
    assert diagnostic_reply['connected'] is False and diagnostic_reply['heroReady'] is False
    report = diagnostic_reply['diagnostics']
    assert report['gameID'] == 'hades' and report['desired'] == desired
    assert report['supportedBuild'] == json.loads((context.module_dir / 'module.json').read_text())['supportedBuild']
    assert len(report['checks']) == 19 and report['total'] == 19
    assert all(not check['detail'].startswith('{') for check in report['checks']), 'raw JSON leaked into diagnostics'
    assert not next(check for check in report['checks'] if check['name'] == 'hades.diagnostics.connection')['ok']
    assert not next(check for check in report['checks'] if check['name'] == 'hades.diagnostics.hero')['ok']
    assert runtime.calls == [], 'offline diagnostics must not attach or probe native state'

    adapter.dispatch('connect', {}, 'connect')
    assert runtime.features == to_runtime_features(desired, DEFAULT_FEATURES)
    assert runtime.speed == 2 and preferences.load() == desired
    reset = {**DEFAULT_PREFERENCES, 'damageMultiplier': 1.5, 'gameSpeed': 0.5}
    adapter.profiles.save('恢复', reset)
    state = adapter.dispatch('load_profile', {'name': '恢复'}, 'load-connected')
    assert runtime.features['damageMultiplier'] == 1.5 and not runtime.features['invincibility']
    assert runtime.speed == 0.5 and preferences.load() == reset
    assert state['health'] == 50 and state['money'] == 25, 'preset replay changed a one-shot value'
    assert state['features']['gameSpeed']['actual'] == 0.5
    assert [call[0] for call in runtime.calls if len(call) > 1 and call[0] == 'configure'] == ['configure']
    with patched_environment(root):
        report = adapter.dispatch('diagnostics', {}, 'diagnostics-connected')['diagnostics']
    assert len(report['checks']) == 19 and report['passed'] == 19 and report['total'] == 19
    assert all(check['ok'] for check in report['checks']), [c for c in report['checks'] if not c['ok']]
    assert report['desired'] == reset and report['state']['target']['heroId'] == 'run:hero:1'

    # Failing install/environment probes & unreadable preferences stay safe and structured.
    preferences.path.write_text('{corrupt-json')
    try:
        with patched_environment(root / 'missing-env', installed=False, lldb_ok=False, python_ok=False, rosetta_ok=False, mailbox_ok=False):
            corrupt_diag = adapter.dispatch('diagnostics', {}, 'diagnostics-failing')['diagnostics']
        corrupt_by_id = {c['id']: c for c in corrupt_diag['checks']}
        assert corrupt_diag['desired'] is None
        assert corrupt_by_id['install']['ok'] is False and corrupt_by_id['install']['detail'] == 'hades.diagnostics.detail.notInstalled'
        assert corrupt_by_id['lldb']['ok'] is False and corrupt_by_id['preferences']['ok'] is False
    finally:
        preferences.save(reset)

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
    assert document['schemaVersion'] == 6, 'a Profile must identify the current feature set as schema 6'
    schema_one_set = {
        {'infiniteHealth': 'fullHealth', 'infiniteMoney': 'moneyNoDecrease',
         'infiniteRerolls': 'rerollsNoDecrease', 'forceEnableRerolls': 'forceRerolls'}.get(key, key): value
        for key, value in document['features'].items()
        if key not in {'boonForceLegendary', 'boonForceDuo', 'fishingChance', 'chaosGateChance',
                       'healthLock', 'moneyLock', 'rerollsLock',
                       'moneyMultiplierEnabled', 'resourceMultiplierEnabled',
                       'moneyMultiplier', 'resourceMultiplier', 'resourceLocks'}
    }
    path.write_text(json.dumps({**document, 'schemaVersion': 1, 'features': schema_one_set}))
    assert adapter.profiles.load('战斗') == document['features'], 'a schema-1 Profile did not migrate'
    schema_two_set = {
        {'infiniteHealth': 'fullHealth', 'infiniteMoney': 'moneyNoDecrease',
         'infiniteRerolls': 'rerollsNoDecrease', 'forceEnableRerolls': 'forceRerolls'}.get(key, key): value
        for key, value in document['features'].items()
        if key not in {'boonForceLegendary', 'boonForceDuo', 'fishingChance', 'chaosGateChance',
                       'moneyMultiplierEnabled', 'resourceMultiplierEnabled',
                       'moneyMultiplier', 'resourceMultiplier', 'resourceLocks'}
    }
    path.write_text(json.dumps({
        **document,
        'schemaVersion': 2,
        'features': schema_two_set,
        'shortcuts': {'_layoutVersion': 1, 'fullHealth': {'keyCode': 21, 'modifiers': 6144, 'keyLabel': '4'}},
    }))
    migrated_record = adapter.profiles.load_record('战斗')
    assert migrated_record['features'] == document['features'], 'a schema-2 Profile did not migrate'
    assert migrated_record['shortcuts']['infiniteHealth'] == {'keyCode': 21, 'modifiers': 6144, 'keyLabel': '4'}
    assert 'fullHealth' not in migrated_record['shortcuts']
    schema_three_set = {
        key: value for key, value in document['features'].items()
        if key not in {'boonForceLegendary', 'boonForceDuo', 'fishingChance', 'chaosGateChance',
                       'moneyMultiplierEnabled', 'resourceMultiplierEnabled',
                       'moneyMultiplier', 'resourceMultiplier', 'resourceLocks'}
    }
    path.write_text(json.dumps({**document, 'schemaVersion': 3, 'features': schema_three_set}))
    assert adapter.profiles.load('战斗') == document['features'], 'a schema-3 Profile did not migrate'
    schema_four_set = {
        key: value for key, value in document['features'].items()
        if key not in {'fishingChance', 'chaosGateChance',
                       'moneyMultiplierEnabled', 'resourceMultiplierEnabled',
                       'moneyMultiplier', 'resourceMultiplier', 'resourceLocks'}
    }
    path.write_text(json.dumps({**document, 'schemaVersion': 4, 'features': schema_four_set}))
    assert adapter.profiles.load('战斗') == document['features'], 'a schema-4 Profile did not migrate'
    schema_five_set = {
        key: value for key, value in document['features'].items()
        if key not in {'moneyMultiplierEnabled', 'resourceMultiplierEnabled',
                       'moneyMultiplier', 'resourceMultiplier', 'resourceLocks'}
    }
    path.write_text(json.dumps({**document, 'schemaVersion': 5, 'features': schema_five_set}))
    assert adapter.profiles.load('战斗') == document['features'], 'a schema-5 Profile did not migrate'
    for key, value in [('gameID', 'hades2'), ('schemaVersion', 0), ('schemaVersion', True),
                       ('features', {'health': 100}), ('features', schema_one_set), ('features', schema_two_set),
                       ('features', schema_three_set), ('features', schema_four_set), ('features', schema_five_set)]:
        malformed = {**document, key: value}
        path.write_text(json.dumps(malformed))
        rejected('profile_read_failed', lambda: adapter.profiles.load('战斗'))
        assert json.loads(path.read_text()) == malformed, 'reading modified an invalid profile'
    # A Profile from a newer Trainer is refused, skipped by listing and never
    # replaced by saving the same name; deleting it stays an explicit choice.
    newer = json.dumps({**document, 'schemaVersion': 7, 'features': {'futureFeature': True}})
    path.write_text(newer)
    try:
        adapter.dispatch('load_profile', {'name': '战斗'}, 'load-newer')
    except AdapterError as error:
        assert (error.code, error.presentation) == ('profile_unsupported_schema', 'hades.error.profileNewerFormat')
    else:
        raise AssertionError('a Profile from a newer Trainer was loaded')
    rejected('profile_unsupported_schema', lambda: adapter.dispatch('save_profile', {'name': '战斗'}, 'replace-newer'))
    logging.disable(logging.CRITICAL)
    try:
        listed = adapter.dispatch('list_profiles', {}, 'list-with-newer')['profiles']
    finally:
        logging.disable(logging.NOTSET)
    assert [row['name'] for row in listed] == ['恢复'], listed
    assert path.read_text() == newer, 'a Profile from a newer Trainer was modified'
    path.write_text(json.dumps(document))
    # One unreadable Profile (truncated write or a newer format) is skipped:
    # it neither hides the others nor fails a save/delete that completed.
    damaged = adapter.profiles.root / ('0' * 64 + '.json')
    damaged.write_text('{"schemaVersion": 1, "gameID": "hades"')
    logging.disable(logging.CRITICAL)
    try:
        listed = adapter.dispatch('list_profiles', {}, 'list-with-damaged')['profiles']
        assert sorted(row['name'] for row in listed) == ['恢复', '战斗'], listed
        saved = adapter.dispatch('save_profile', {'name': '第三'}, 'save-with-damaged')['profiles']
        assert '第三' in [row['name'] for row in saved]
        adapter.dispatch('delete_profile', {'name': '第三'}, 'delete-with-damaged')
    finally:
        logging.disable(logging.NOTSET)
    assert damaged.read_text() == '{"schemaVersion": 1, "gameID": "hades"', 'listing modified a damaged profile'
    damaged.unlink()
    with patch.object(adapter.profiles._store, 'list', wraps=adapter.profiles._store.list) as profile_scan:
        deleted = adapter.dispatch('delete_profile', {'name': '恢复'}, 'delete')
    assert profile_scan.call_count == 1, 'deleting a Profile enumerated the directory more than once'
    assert [row['name'] for row in deleted['profiles']] == ['战斗']
    assert [row['name'] for row in adapter.dispatch('list_profiles', {}, 'list-final')['profiles']] == ['战斗']

print('hades_management_profiles_and_diagnostics_ok')
