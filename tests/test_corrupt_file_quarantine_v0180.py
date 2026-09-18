from pathlib import Path
import json
import logging
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'Backend'))

from games.hades2 import persistence
from games.hades2.persistence import PersistenceError
from games.hades2.preferences import Hades2PreferenceStore
from games.hades2.profile_service import PROFILE_SCHEMA_VERSION, Hades2ProfileService


base = Path(tempfile.mkdtemp(prefix='mgt-corrupt-quarantine-v0180-'))
logging.disable(logging.CRITICAL)
try:
    # A syntactically corrupt desired-state file is preserved as evidence and
    # startup falls back to clean defaults.  A later save creates a fresh owner
    # without touching the quarantined bytes.
    desired_path = base/'desired-state.json'
    corrupt_bytes = b'{"godMode": true, broken'
    desired_path.write_bytes(corrupt_bytes)
    store = Hades2PreferenceStore(desired_path)
    desired, initialized = store.load()
    assert initialized is False
    assert desired['godMode'] is False
    assert not desired_path.exists()
    quarantined = list(base.glob('desired-state.json.corrupt-*'))
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == corrupt_bytes

    replacement = store.defaults(); replacement['godMode'] = True
    store.save(replacement)
    assert json.loads(desired_path.read_text(encoding='utf-8'))['godMode'] is True
    assert quarantined[0].read_bytes() == corrupt_bytes

    # A valid JSON value with the wrong top-level shape is equally unusable as
    # executable desired state and receives the same quarantine treatment.
    wrong_shape = base/'wrong-shape.json'
    wrong_shape.write_text('[1, 2, 3]', encoding='utf-8')
    _, initialized = Hades2PreferenceStore(wrong_shape).load()
    assert initialized is False
    assert not wrong_shape.exists()
    assert len(list(base.glob('wrong-shape.json.corrupt-*'))) == 1

    # Quarantine itself is best-effort.  If the filesystem refuses the rename,
    # startup must still use safe defaults and leave the original evidence in
    # place rather than escalating a recoverable corrupt-config case.
    stuck = base/'stuck.json'
    stuck.write_text('{broken', encoding='utf-8')
    original_replace = persistence.os.replace
    persistence.os.replace = lambda source, destination: (_ for _ in ()).throw(OSError('rename denied'))
    try:
        stuck_store = Hades2PreferenceStore(stuck)
        safe, initialized = stuck_store.load()
    finally:
        persistence.os.replace = original_replace
    assert initialized is False and safe['godMode'] is False
    assert isinstance(stuck_store.write_blocked_error, PersistenceError)
    assert stuck.read_text(encoding='utf-8') == '{broken'
    assert list(base.glob('stuck.json.corrupt-*')) == []
    try:
        stuck_store.save(dict(safe, godMode=True))
    except PersistenceError:
        pass
    else:
        raise AssertionError('failed quarantine allowed the original file to be overwritten')
    assert stuck.read_text(encoding='utf-8') == '{broken'

    # A read I/O failure is not evidence of corruption. Preserve the existing
    # file in place and write-protect the store for this backend lifetime rather
    # than treating it as a missing first-run preference file.
    unreadable = base/'unreadable.json'
    unreadable.write_text(json.dumps({'godMode': True}), encoding='utf-8')
    unreadable_bytes = unreadable.read_bytes()
    original_read_text = Path.read_text
    def failing_read_text(path, *args, **kwargs):
        if path == unreadable: raise OSError('read denied')
        return original_read_text(path, *args, **kwargs)
    Path.read_text = failing_read_text
    try:
        unreadable_store = Hades2PreferenceStore(unreadable)
        safe, initialized = unreadable_store.load()
    finally:
        Path.read_text = original_read_text
    assert initialized is False and safe['godMode'] is False
    assert isinstance(unreadable_store.write_blocked_error, PersistenceError)
    try:
        unreadable_store.save(dict(safe, godMode=True))
    except PersistenceError:
        pass
    else:
        raise AssertionError('read failure was treated as a writable missing preference file')
    assert unreadable.read_bytes() == unreadable_bytes

    # A disappearance race is different from an unreadable existing file. If
    # the file vanishes after the initial existence check, the store may safely
    # behave like first run and remain writable.
    vanished = base/'vanished.json'
    vanished.write_text(json.dumps({'godMode': True}), encoding='utf-8')
    original_read_text = Path.read_text
    def vanished_read_text(path, *args, **kwargs):
        if path == vanished:
            vanished.unlink(missing_ok=True)
            raise FileNotFoundError('vanished')
        return original_read_text(path, *args, **kwargs)
    Path.read_text = vanished_read_text
    try:
        vanished_store = Hades2PreferenceStore(vanished)
        safe, initialized = vanished_store.load()
    finally:
        Path.read_text = original_read_text
    assert initialized is False and safe['godMode'] is False
    assert vanished_store.write_blocked_error is None
    vanished_store.save(dict(safe, godMode=True))
    assert json.loads(vanished.read_text(encoding='utf-8'))['godMode'] is True


    # Adapter integration: a write-protected existing desired-state is distinct
    # from true first-run state. Even a successful live status must not adopt
    # Lua desired values and then attempt to overwrite the preserved file.
    from games.hades2 import preparation as prep
    from games.hades2.adapter import Hades2Adapter

    adapter_base = base/'blocked-adapter'
    adapter_base.mkdir()
    prep.DATA = adapter_base
    blocked_path = adapter_base/'desired-state.json'
    blocked_path.write_text('{broken', encoding='utf-8')
    blocked_bytes = blocked_path.read_bytes()

    class LiveTransport:
        pid = 7001
        last_duration = 0.01
        def alive(self): return True
        def execute(self, source):
            return json.dumps({
                'status':'ready','scene':'run','capabilities':{},
                'desiredFeatures':{'godMode':True},'activeFeatures':{'godMode':True},
            })
        def detach(self): pass
        def close(self): pass

    original_replace = persistence.os.replace
    persistence.os.replace = lambda source, destination: (_ for _ in ()).throw(OSError('rename denied'))
    try:
        blocked_adapter = Hades2Adapter(transport=LiveTransport())
    finally:
        persistence.os.replace = original_replace
    assert blocked_adapter.preference_write_blocked is True
    assert blocked_adapter.preference_initialized is False
    blocked_adapter.execute('status', {})
    assert blocked_adapter.preference_initialized is False
    assert blocked_adapter.preferences['godMode'] is False
    assert blocked_path.read_bytes() == blocked_bytes

    # Profile discovery may otherwise leave a permanently invisible .json file
    # in the live namespace.  Invalid JSON and invalid envelopes are moved out
    # of the *.json set, while healthy profiles remain available.
    profiles = Hades2ProfileService(base/'profiles')
    good = store.defaults(); good['gardenQoL'] = True
    profiles.save('healthy', good, {'godMode': 1})

    bad_json = profiles.root/'bad-json.json'
    bad_json.write_text('{broken', encoding='utf-8')
    bad_envelope = profiles.root/'bad-envelope.json'
    bad_envelope.write_text(json.dumps({'schemaVersion': PROFILE_SCHEMA_VERSION, 'name': 'broken', 'updatedAt':'2026-09-18T00:00:00+0000', 'desired': 'not-an-object'}), encoding='utf-8')

    rows = profiles.list()
    assert [row['name'] for row in rows] == ['healthy']
    assert not bad_json.exists() and not bad_envelope.exists()
    assert len(list(profiles.root.glob('bad-json.json.corrupt-*'))) == 1
    assert len(list(profiles.root.glob('bad-envelope.json.corrupt-*'))) == 1

    # Direct load of a corrupt profile gives a stable user-facing validation
    # error and also removes the broken file from the active profile namespace.
    direct_path = profiles.path('direct-corrupt')
    direct_path.write_text(json.dumps({'schemaVersion': PROFILE_SCHEMA_VERSION, 'name':'direct-corrupt', 'updatedAt':'2026-09-18T00:00:00+0000', 'desired':None}), encoding='utf-8')
    try:
        profiles.load('direct-corrupt')
    except ValueError as error:
        assert '损坏' in str(error)
    else:
        raise AssertionError('corrupt profile load unexpectedly succeeded')
    assert not direct_path.exists()
    assert len(list(profiles.root.glob(direct_path.name + '.corrupt-*'))) == 1
finally:
    logging.disable(logging.NOTSET)

print('corrupt_file_quarantine_v0180_ok')
