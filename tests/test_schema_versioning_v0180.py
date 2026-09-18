from pathlib import Path
import json
import logging
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'Backend'))

from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter
from games.hades2.persistence import UnsupportedSchemaVersionError
from games.hades2.preferences import DESIRED_STATE_SCHEMA_VERSION, Hades2PreferenceStore
from games.hades2.profile_service import PROFILE_SCHEMA_VERSION, Hades2ProfileService


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
    assert loaded['godMode'] is True
    assert loaded['nextRoomReward'] == 'RoomMoneyDrop'
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
    assert upgraded['godMode'] is True
    assert upgraded['nextRoomReward'] == 'RoomMoneyDrop'

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
    assert initialized is False and safe['godMode'] is False
    assert future_store.unsupported_schema_version == DESIRED_STATE_SCHEMA_VERSION + 1
    assert future_path.read_bytes() == future_bytes
    assert list(base.glob('future-desired.json.corrupt-*')) == []
    try:
        future_store.save(dict(safe, godMode=True))
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
    adapter_base.mkdir()
    preparation.DATA = adapter_base
    adapter_desired = adapter_base/'desired-state.json'
    adapter_desired.write_text(json.dumps(future_doc, sort_keys=True), encoding='utf-8')
    adapter_desired_bytes = adapter_desired.read_bytes()

    class FutureSchemaTransport:
        pid = 9001
        last_duration = 0.01
        def alive(self): return True
        def execute(self, source):
            return json.dumps({
                'status':'ready','scene':'run','capabilities':{},
                'desiredFeatures':{'godMode':True},
                'activeFeatures':{'godMode':True},
            })
        def detach(self): pass
        def close(self): pass

    adapter = Hades2Adapter(transport=FutureSchemaTransport())
    assert adapter.preference_write_blocked is True
    assert adapter.preference_dirty is False
    state = adapter.execute('status', {})
    assert state['status'] == 'ready'
    assert adapter.preference_initialized is False
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
    profiles.save('current', loaded, {'godMode': 1})
    current_path = profiles.path('current')
    current_doc = json.loads(current_path.read_text(encoding='utf-8'))
    assert current_doc['schemaVersion'] == PROFILE_SCHEMA_VERSION

    # Profiles are intentionally current-schema-only. Older envelopes remain
    # untouched and hidden instead of accumulating compatibility migrations.
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
    profiles.save('legacy', loaded, {'godMode': 1})
    replaced_profile = json.loads(legacy_profile_path.read_text(encoding='utf-8'))
    assert replaced_profile['schemaVersion'] == PROFILE_SCHEMA_VERSION
    assert profiles.load('legacy')['desired']['godMode'] is True

    # Future Profile schemas are likewise not read or listed. An explicit save
    # with the same name replaces them; Profile compatibility is not maintained.
    future_profile_path = profiles.path('future')
    future_profile = {
        'schemaVersion': PROFILE_SCHEMA_VERSION + 1,
        'name': 'future',
        'updatedAt': '2026-09-18T00:00:00+0000',
        'desired': {'godMode': True},
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

    profiles.save('future', loaded, {'godMode': 1})
    assert json.loads(future_profile_path.read_text(encoding='utf-8'))['schemaVersion'] == PROFILE_SCHEMA_VERSION
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
finally:
    logging.disable(logging.NOTSET)

print('schema_versioning_v0180_ok')
