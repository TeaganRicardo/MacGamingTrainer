import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'Backend'))

from games.hades2.adapter import Hades2Adapter
from games.hades2.persistence import UnsupportedSchemaVersionError
from games.hades2.preferences import DESIRED_STATE_SCHEMA_VERSION, Hades2PreferenceStore
from games.hades2.profile_service import PROFILE_SCHEMA_VERSION, Hades2ProfileService
from hades2_resident_session_fakes import FakeTimeWarpController, hades2_adapter_context

base = Path(tempfile.mkdtemp(prefix='mgt-schema-version-v0180-'))
logging.disable(logging.CRITICAL)
try:
    # Legacy desired-state documents (no schemaVersion) remain readable and are
    # not rewritten merely because the backend starts.  The next explicit save
    # upgrades the durable document to the current schema.
    desired_path = base/'desired-state.json'
    legacy = Hades2PreferenceStore.defaults()
    legacy['godMode'] = True
    legacy['nextRoomReward'] = 'RoomRewardMoney'
    # Pre-v2 true meant merely "allow". It must not turn into a force action
    # after the semantic change.
    legacy['boonRarity']['allowLegendary'] = True
    legacy['boonRarity']['allowDuo'] = True
    desired_path.write_text(json.dumps(legacy), encoding='utf-8')
    legacy_bytes = desired_path.read_bytes()

    store = Hades2PreferenceStore(desired_path)
    loaded, initialized = store.load()
    assert initialized is True
    assert loaded['invincibility'] is True
    assert 'nextRoomReward' not in loaded and 'nextRoomRewardToken' not in loaded
    assert loaded['boonRarity']['forceLegendary'] is False
    assert loaded['boonRarity']['forceDuo'] is False
    assert 'boonChoiceEnabled' not in loaded and 'boonChoiceCount' not in loaded
    assert desired_path.read_bytes() == legacy_bytes

    # Schema 2 already used allow* as force semantics. It migrates exactly to
    # the canonical force* keys instead of resetting the user's current intent.
    v2_path = base/'desired-v2.json'
    v2_doc = Hades2PreferenceStore.defaults()
    v2_doc['schemaVersion'] = 2
    v2_doc['boonRarity'] = {
        'target':'Epic','multiplier':100.0,'allowLegendary':True,'allowDuo':False,
    }
    v2_path.write_text(json.dumps(v2_doc), encoding='utf-8')
    v2_loaded, v2_initialized = Hades2PreferenceStore(v2_path).load()
    assert v2_initialized is True
    assert v2_loaded['boonRarity']['forceLegendary'] is True
    assert v2_loaded['boonRarity']['forceDuo'] is False
    assert 'allowLegendary' not in v2_loaded['boonRarity'] and 'allowDuo' not in v2_loaded['boonRarity']

    store.save(loaded)
    upgraded = json.loads(desired_path.read_text(encoding='utf-8'))
    assert upgraded['schemaVersion'] == DESIRED_STATE_SCHEMA_VERSION
    assert upgraded['invincibility'] is True
    assert 'godMode' not in upgraded
    assert 'nextRoomReward' not in upgraded and 'nextRoomRewardToken' not in upgraded

    # A file produced by a newer Trainer must never be quarantined or silently
    # replaced by defaults.  This backend starts safely with defaults but keeps
    # the store write-protected until restart, surfacing an explicit error if a
    # mutation tries to persist through it.
    future_path = base/'future-desired.json'
    future_doc = dict(legacy, schemaVersion=DESIRED_STATE_SCHEMA_VERSION + 1)
    future_path.write_text(json.dumps(future_doc, sort_keys=True), encoding='utf-8')
    future_bytes = future_path.read_bytes()
    future_store = Hades2PreferenceStore(future_path)
    safe, initialized = future_store.load()
    assert initialized is False and safe['invincibility'] is False
    assert future_store.unsupported_schema_version == DESIRED_STATE_SCHEMA_VERSION + 1
    assert future_path.read_bytes() == future_bytes
    assert list(base.glob('future-desired.json.corrupt-*')) == []
    try:
        future_store.save(dict(safe, invincibility=True))
    except UnsupportedSchemaVersionError as error:
        assert error.code == 'unsupported_schema'
    else:
        raise AssertionError('newer desired-state schema was overwritten')
    assert future_path.read_bytes() == future_bytes

    # Adapter startup must distinguish "no desired-state yet" from a newer
    # desired-state that is intentionally write-protected.  A status read may
    # cross the live boundary, but it must not adopt/replay/save defaults and
    # therefore must not fail merely because the durable file is newer.
    adapter_base = base/'future-adapter'
    context = hades2_adapter_context(adapter_base)
    context.data_dir.mkdir(parents=True)
    adapter_desired = context.data_dir/'desired-state.json'
    adapter_desired.write_text(json.dumps(future_doc, sort_keys=True), encoding='utf-8')
    adapter_desired_bytes = adapter_desired.read_bytes()

    class FutureSchemaTransport:
        pid = 9001
        last_duration = 0.01
        def __init__(self):
            self.execute_calls = 0
        def alive(self): return True
        def execute(self, source):
            self.execute_calls += 1
            return json.dumps({
                'status':'ready','scene':'run','capabilities':{},
                'desiredFeatures':{'invincibility':True},
                'activeFeatures':{'invincibility':True},
            })
        def detach(self): pass
        def close(self): pass
        def create_time_warp_controller(self, helper_path, image_names): return FakeTimeWarpController()

    future_transport = FutureSchemaTransport()
    adapter = Hades2Adapter(context=context, transport=future_transport)
    assert adapter.preference_write_blocked is True
    assert adapter.preference_dirty is False
    state = adapter.execute('status', {})
    assert state['status'] == 'ready'
    assert adapter.preference_initialized is False
    assert adapter_desired.read_bytes() == adapter_desired_bytes

    # Forward-schema write protection must not block best-effort runtime
    # teardown. disable_all still reports unsupported_schema because durable
    # desired intent cannot be rewritten, but it must cross the live boundary
    # once so resident hooks/features are actually disabled.
    calls_before_teardown = future_transport.execute_calls
    try:
        adapter.execute('disable_all', {})
    except UnsupportedSchemaVersionError as error:
        assert error.code == 'unsupported_schema'
    else:
        raise AssertionError('future desired-state teardown hid its durable-state error')
    assert future_transport.execute_calls == calls_before_teardown + 1
    assert adapter_desired.read_bytes() == adapter_desired_bytes

    # Invalid version metadata is corrupt rather than "newer" and is moved out
    # of the active namespace so it cannot create an ambiguous write owner.
    invalid_path = base/'invalid-version.json'
    invalid_path.write_text(json.dumps(dict(legacy, schemaVersion='1')), encoding='utf-8')
    invalid_store = Hades2PreferenceStore(invalid_path)
    _, initialized = invalid_store.load()
    assert initialized is False
    assert not invalid_path.exists()
    assert len(list(base.glob('invalid-version.json.corrupt-*'))) == 1

    # Explicit null is metadata, not the absence of metadata. Treating it as
    # legacy v0 would bypass the version contract and could silently accept a
    # malformed document.
    null_version_path = base/'null-version.json'
    null_version_path.write_text(json.dumps(dict(legacy, schemaVersion=None)), encoding='utf-8')
    null_store = Hades2PreferenceStore(null_version_path)
    _, initialized = null_store.load()
    assert initialized is False
    assert not null_version_path.exists()
    assert len(list(base.glob('null-version.json.corrupt-*'))) == 1

    profiles = Hades2ProfileService(base/'profiles')

    # New profile writes are explicitly versioned.
    profiles.save('current', loaded, {'invincibility': {'keyCode':18,'modifiers':6144,'keyLabel':'1'}})
    current_path = profiles.path('current')
    current_doc = json.loads(current_path.read_text(encoding='utf-8'))
    assert current_doc['schemaVersion'] == PROFILE_SCHEMA_VERSION
    assert current_doc['desiredSchemaVersion'] == DESIRED_STATE_SCHEMA_VERSION

    # Pre-baseline Profile envelopes remain unsupported and untouched. Released
    # v3/v4 compatibility is covered by test_profile_version_compatibility.py.
    legacy_profile_path = profiles.path('legacy')
    legacy_profile = {'name':'legacy','updatedAt':'','desired':legacy}
    legacy_profile_path.write_text(json.dumps(legacy_profile), encoding='utf-8')
    legacy_profile_bytes = legacy_profile_path.read_bytes()
    assert 'legacy' not in [row['name'] for row in profiles.list()]
    try:
        profiles.load('legacy')
    except UnsupportedSchemaVersionError as error:
        assert error.code == 'unsupported_schema'
    else:
        raise AssertionError('legacy Profile schema was accepted')
    assert legacy_profile_path.read_bytes() == legacy_profile_bytes

    # Saving an explicitly named profile is a user-requested replacement, not a
    # migration. It atomically writes the current envelope over any old version.
    profiles.save('legacy', loaded, {'invincibility': {'keyCode':18,'modifiers':6144,'keyLabel':'1'}})
    replaced_profile = json.loads(legacy_profile_path.read_text(encoding='utf-8'))
    assert replaced_profile['schemaVersion'] == PROFILE_SCHEMA_VERSION
    assert profiles.load('legacy')['desired']['invincibility'] is True

    # Future Profile schemas are neither read/listed nor overwritten by save.
    # Explicit delete remains the only destructive operation that ignores schema.
    future_profile_path = profiles.path('future')
    future_profile = {
        'schemaVersion': PROFILE_SCHEMA_VERSION + 1,
        'name': 'future',
        'updatedAt': '2026-09-18T00:00:00+0000',
        'desired': {'invincibility': True},
    }
    future_profile_path.write_text(json.dumps(future_profile, sort_keys=True), encoding='utf-8')
    future_profile_bytes = future_profile_path.read_bytes()
    assert 'future' not in [row['name'] for row in profiles.list()]
    try:
        profiles.load('future')
    except UnsupportedSchemaVersionError as error:
        assert error.code == 'unsupported_schema'
    else:
        raise AssertionError('future Profile schema was accepted')
    assert future_profile_path.read_bytes() == future_profile_bytes

    try:
        profiles.save('future', loaded, {'invincibility': {'keyCode':18,'modifiers':6144,'keyLabel':'1'}})
    except UnsupportedSchemaVersionError as error:
        assert error.code == 'unsupported_schema'
    else:
        raise AssertionError('future Profile schema was overwritten by save')
    assert future_profile_path.read_bytes() == future_profile_bytes

    deleted = profiles.delete('future')
    assert deleted['deleted'] is True and not future_profile_path.exists()

    # Malformed Profile version metadata remains a corrupt-file case and is
    # quarantined instead of being confused with a forward-compatible file.
    invalid_profile_path = profiles.root/'invalid-schema.json'
    invalid_profile_path.write_text(json.dumps({
        'schemaVersion': True,
        'name': 'invalid',
        'desired': {},
    }), encoding='utf-8')
    profiles.list()
    assert not invalid_profile_path.exists()
    assert len(list(profiles.root.glob('invalid-schema.json.corrupt-*'))) == 1


    null_profile_path = profiles.root/'null-schema.json'
    null_profile_path.write_text(json.dumps({
        'schemaVersion': None,
        'name': 'null-schema',
        'desired': {},
    }), encoding='utf-8')
    profiles.list()
    assert not null_profile_path.exists()
    assert len(list(profiles.root.glob('null-schema.json.corrupt-*'))) == 1

    # WP4.2 root-to-hades2/ migration: pre-WP4.2 flat root desired-state.json,
    # profiles/, backups/, and diagnostics/ migrate into MacGamingTrainer/hades2/
    # without losing content or weakening newer/older schema refusal.
    mig_context = hades2_adapter_context(base / 'root-migration')
    legacy_root = mig_context.data_dir.parent
    legacy_root.mkdir(parents=True, exist_ok=True)
    legacy_desired = dict(loaded, invincibility=True)
    (legacy_root / 'desired-state.json').write_text(json.dumps(legacy_desired), encoding='utf-8')
    legacy_profiles = Hades2ProfileService(legacy_root / 'profiles')
    legacy_profiles.save('migrated-preset', legacy_desired, {'invincibility': {'keyCode': 18, 'modifiers': 6144, 'keyLabel': '1'}})
    old_root_profile = legacy_profiles.path('old-root-v1')
    old_root_profile.write_text(json.dumps({'schemaVersion': 1, 'name': 'old-root-v1', 'desired': {}}), encoding='utf-8')
    future_root_profile = legacy_profiles.path('future-root')
    future_root_profile.write_text(
        json.dumps({'schemaVersion': PROFILE_SCHEMA_VERSION + 1, 'name': 'future-root', 'desired': {}}),
        encoding='utf-8',
    )
    (legacy_root / 'backups/sig-1').mkdir(parents=True)
    (legacy_root / 'backups/sig-1/manifest.json').write_text('{"status":"prepared"}\n', encoding='utf-8')
    (legacy_root / 'diagnostics').mkdir(parents=True)
    (legacy_root / 'diagnostics/report.json').write_text('{"ok":true}\n', encoding='utf-8')

    mig_adapter = Hades2Adapter(context=mig_context, transport=FutureSchemaTransport())
    assert mig_adapter.preferences['invincibility'] is True
    assert not (legacy_root / 'desired-state.json').exists()
    assert (mig_context.data_dir / 'desired-state.json').is_file()
    assert not (legacy_root / 'profiles').exists()
    assert [row['name'] for row in mig_adapter.profile_service.list()] == ['migrated-preset']
    assert (mig_context.data_dir / 'backups/sig-1/manifest.json').is_file()
    assert (mig_context.data_dir / 'diagnostics/report.json').is_file()
    for refused_name in ('old-root-v1', 'future-root'):
        try:
            mig_adapter.profile_service.load(refused_name)
        except UnsupportedSchemaVersionError as error:
            assert error.code == 'unsupported_schema'
        else:
            raise AssertionError(f'migrated unsupported profile {refused_name} was accepted')

    # Existing namespaced files under MacGamingTrainer/hades2/ take precedence
    # over any stale root file left behind.
    (legacy_root / 'desired-state.json').write_text(json.dumps(dict(loaded, invincibility=False)), encoding='utf-8')
    mig_adapter_reload = Hades2Adapter(context=mig_context, transport=FutureSchemaTransport())
    assert mig_adapter_reload.preferences['invincibility'] is True

    # #821: OSError / PermissionError during legacy migration leaves files in place,
    # logs one warning, sets hades2.warning.dataMigrationFailed, and lets Hades2Adapter keep running.
    fail_context = hades2_adapter_context(base / 'migration-failure')
    fail_legacy_root = fail_context.data_dir.parent
    fail_legacy_root.mkdir(parents=True, exist_ok=True)
    fail_desired = fail_legacy_root / 'desired-state.json'
    fail_desired.write_text(json.dumps(dict(loaded, invincibility=True)), encoding='utf-8')
    fail_desired_bytes = fail_desired.read_bytes()
    fail_legacy_profiles = Hades2ProfileService(fail_legacy_root / 'profiles')
    fail_legacy_profiles.save('blocked-preset', legacy_desired, {'invincibility': {'keyCode': 18, 'modifiers': 6144, 'keyLabel': '1'}})
    fail_profile_path = fail_legacy_profiles.path('blocked-preset')
    fail_profile_bytes = fail_profile_path.read_bytes()

    captured_warnings = []

    class _CaptureWarningHandler(logging.Handler):
        def emit(self, record):
            if record.levelno >= logging.WARNING:
                captured_warnings.append(record.getMessage())

    handler = _CaptureWarningHandler()
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    logging.disable(logging.NOTSET)
    try:
        real_replace = os.replace

        def deny_legacy_replace(src, dst):
            if str(fail_legacy_root) in str(src):
                raise PermissionError(13, 'Permission denied', str(src))
            return real_replace(src, dst)

        with patch('games.hades2.persistence.os.replace', side_effect=deny_legacy_replace):
            fail_adapter = Hades2Adapter(context=fail_context, transport=FutureSchemaTransport())
    finally:
        logging.disable(logging.CRITICAL)
        root_logger.removeHandler(handler)

    assert len(captured_warnings) == 1, captured_warnings
    assert fail_desired.read_bytes() == fail_desired_bytes
    assert fail_profile_path.read_bytes() == fail_profile_bytes
    assert not (fail_context.data_dir / 'desired-state.json').exists()
    assert not (fail_context.data_dir / 'profiles' / 'blocked-preset.json').exists()
    assert fail_adapter.state['warnings'] == ['hades2.warning.dataMigrationFailed']
    with patch('games.hades2.adapter.locate_target', return_value=None), patch(
        'games.hades2.preparation.compatibility',
        return_value={
            'compatible': True,
            'version': '143476',
            'steam_build': '25481925',
            'warnings': ['hades2.warning.dataMigrationFailed'],
        },
    ):
        scanned = fail_adapter.scan()
    assert scanned['warnings'] == ['hades2.warning.dataMigrationFailed']

    # Real filesystem permission check: read-only legacy profiles/ while target hades2/profiles/ exists.
    if os.geteuid() != 0:
        ro_context = hades2_adapter_context(base / 'migration-readonly')
        ro_legacy_root = ro_context.data_dir.parent
        (ro_context.data_dir / 'profiles').mkdir(parents=True, exist_ok=True)
        ro_profiles = Hades2ProfileService(ro_legacy_root / 'profiles')
        ro_profiles.save('ro-preset', legacy_desired, {'invincibility': {'keyCode': 18, 'modifiers': 6144, 'keyLabel': '1'}})
        ro_profile_path = ro_profiles.path('ro-preset')
        ro_dir = ro_legacy_root / 'profiles'
        os.chmod(ro_dir, 0o555)
        try:
            ro_adapter = Hades2Adapter(context=ro_context, transport=FutureSchemaTransport())
        finally:
            os.chmod(ro_dir, 0o755)
        assert ro_profile_path.is_file()
        assert not (ro_context.data_dir / 'profiles' / 'ro-preset.json').exists()
        assert ro_adapter.state['warnings'] == ['hades2.warning.dataMigrationFailed']
finally:
    logging.disable(logging.NOTSET)

print('schema_versioning_v0180_ok')
