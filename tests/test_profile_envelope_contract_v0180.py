from pathlib import Path
import json
import logging
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'Backend'))

from games.hades2.persistence import UnsupportedSchemaVersionError
from games.hades2.profile_service import PROFILE_SCHEMA_VERSION, Hades2ProfileService


base = Path(tempfile.mkdtemp(prefix='mgt-profile-envelope-v0180-'))
service = Hades2ProfileService(base/'profiles')
desired = {'godMode': False}

# Current-version writes have the complete envelope and remain loadable.
service.save('stable', desired, {'godMode': 1})
stable_path = service.path('stable')
stable_doc = json.loads(stable_path.read_text(encoding='utf-8'))
assert set(stable_doc) == {'schemaVersion','name','updatedAt','desired','shortcuts'}
assert stable_doc['schemaVersion'] == PROFILE_SCHEMA_VERSION
assert service.load('stable')['desired'] == desired

# Profiles are current-schema-only; an old envelope is preserved but not read.
legacy_path = service.path('legacy')
legacy_bytes = json.dumps({
    'name':'legacy','updatedAt':'','desired':desired,'legacyMetadata':{'source':'old'},
}).encode('utf-8')
legacy_path.write_bytes(legacy_bytes)
assert all(row['name'] != 'legacy' for row in service.list())
try:
    service.load('legacy')
except UnsupportedSchemaVersionError:
    pass
else:
    raise AssertionError('legacy Profile was accepted')
assert legacy_path.read_bytes() == legacy_bytes

# An explicit save is a replacement operation and writes the current schema.
service.save('legacy', desired, {'godMode': 1})
assert service.load('legacy')['desired'] == desired
assert json.loads(legacy_path.read_text())['schemaVersion'] == PROFILE_SCHEMA_VERSION

logging.disable(logging.CRITICAL)
try:
    # Current schemas have an explicit envelope. Unknown top-level fields indicate that the
    # document does not match the schema it claims and are quarantined.
    unknown_path = service.path('unknown-field')
    unknown_path.write_text(json.dumps({
        'schemaVersion':PROFILE_SCHEMA_VERSION,
        'name':'unknown-field','updatedAt':'2026-09-18T00:00:00+0000',
        'desired':desired,'surprise':True,
    }), encoding='utf-8')
    assert all(row['name'] != 'unknown-field' for row in service.list())
    assert not unknown_path.exists()
    assert len(list((base/'profiles').glob(unknown_path.name + '.corrupt-*'))) == 1

    # Wrong container types are corrupt envelope data rather than a silent
    # request to reset shortcuts.
    bad_shortcuts_path = service.path('bad-shortcuts')
    bad_shortcuts_path.write_text(json.dumps({
        'schemaVersion':PROFILE_SCHEMA_VERSION,
        'name':'bad-shortcuts','updatedAt':'2026-09-18T00:00:00+0000',
        'desired':desired,'shortcuts':['godMode'],
    }), encoding='utf-8')
    try:
        service.load('bad-shortcuts')
    except ValueError:
        pass
    else:
        raise AssertionError('invalid shortcut container was accepted')
    assert not bad_shortcuts_path.exists()

    # A profile whose embedded name does not hash back to its actual file would
    # appear in the list but could never be loaded by that displayed name.
    ghost_path = service.path('actual-name')
    ghost_path.write_text(json.dumps({
        'schemaVersion':PROFILE_SCHEMA_VERSION,
        'name':'displayed-other-name','updatedAt':'2026-09-18T00:00:00+0000',
        'desired':desired,
    }), encoding='utf-8')
    assert all(row['name'] != 'displayed-other-name' for row in service.list())
    assert not ghost_path.exists()

    # Versioned writes always carry a usable timestamp; a malformed current
    # envelope cannot masquerade as a valid row.
    missing_time_path = service.path('missing-time')
    missing_time_path.write_text(json.dumps({
        'schemaVersion':PROFILE_SCHEMA_VERSION,
        'name':'missing-time','desired':desired,
    }), encoding='utf-8')
    assert all(row['name'] != 'missing-time' for row in service.list())
    assert not missing_time_path.exists()
finally:
    logging.disable(logging.NOTSET)

# Service callers cannot silently omit malformed desired/shortcut inputs.
try:
    service.save('invalid-desired', [], {})
except ValueError:
    pass
else:
    raise AssertionError('non-object desired state was saved')
assert not service.path('invalid-desired').exists()

try:
    service.save('invalid-shortcuts', desired, 'bad')
except ValueError:
    pass
else:
    raise AssertionError('non-object shortcuts were silently discarded')
assert not service.path('invalid-shortcuts').exists()

# Future schemas remain protected from implicit read/overwrite, but explicit
# delete is a deliberate user action and does not require schema interpretation.
future_path = service.path('future')
future_doc = {
    'schemaVersion':PROFILE_SCHEMA_VERSION + 1,
    'name':'future','updatedAt':'2026-09-18T00:00:00+0000','desired':desired,
}
future_path.write_text(json.dumps(future_doc, sort_keys=True), encoding='utf-8')
assert service.delete('future')['deleted'] is True
assert not future_path.exists()

print('profile_envelope_contract_v0180_ok')
