import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from core.save_resolution import ResolvedSaveFile
from core.save_snapshots import (
    SaveSnapshotBusyError,
    SaveSnapshotError,
    SaveSnapshotStore,
)

base = Path(tempfile.mkdtemp(prefix='mgt-save-snapshots-'))
source = base / 'source'
source.mkdir()
(source / 'Profile1.sav').write_bytes(b'profile-one')
(source / 'activeProfile').write_bytes(b'Profile1')
(source / 'settings.json').write_bytes(b'not-save')


def rows():
    return [
        ResolvedSaveFile('main', 'Profile1.sav', source / 'Profile1.sav'),
        ResolvedSaveFile('main', 'activeProfile', source / 'activeProfile'),
    ]


store = SaveSnapshotStore('example', base / 'data')
# Write payload fsyncs must precede opening the manifest for persistence.
fsync_events = []
opened_files = {}
original_path_open = Path.open
original_fsync = os.fsync

def tracked_path_open(path, mode='r', *args, **kwargs):
    handle = original_path_open(path, mode, *args, **kwargs)
    if path.name == 'manifest.json' and 'w' in mode:
        fsync_events.append('manifest-open')
        opened_files[handle.fileno()] = 'manifest'
    elif mode == 'rb+' and path.name in ('Profile1.sav', 'activeProfile'):
        opened_files[handle.fileno()] = 'payload'
    return handle

def tracked_fsync(fd):
    fsync_events.append('fsync:' + opened_files.get(fd, 'unknown'))
    return original_fsync(fd)

Path.open = tracked_path_open
os.fsync = tracked_fsync
try:
    created = store.create_snapshot(rows, hot=False, display_name='Before boss', name_details=['Run 12', 'Crossroads'])
finally:
    Path.open = original_path_open
    os.fsync = original_fsync
assert fsync_events.count('fsync:payload') == 2, fsync_events
manifest_open_index = fsync_events.index('manifest-open')
payload_fsync_indexes = [index for index, event in enumerate(fsync_events) if event == 'fsync:payload']
assert max(payload_fsync_indexes) < manifest_open_index, fsync_events
assert created['valid'] is True
assert created['name'] == 'Before boss'
assert created['fileCount'] == 2
assert created['hot'] is False
assert created['nameDetails'] == ['Run 12', 'Crossroads']
snapshot = Path(created['path'])
assert snapshot.parent.resolve() == (base / 'data' / 'example' / 'saves' / 'snapshots').resolve()
assert (snapshot / 'files/main/Profile1.sav').read_bytes() == b'profile-one'
assert (snapshot / 'files/main/activeProfile').read_bytes() == b'Profile1'
assert not (snapshot / 'files/main/settings.json').exists()

manifest = json.loads((snapshot / 'manifest.json').read_text(encoding='utf-8'))
assert manifest['schemaVersion'] == 1
assert manifest['snapshotId'] == created['id']
assert manifest['gameId'] == 'example'
assert manifest['displayName'] == 'Before boss'
assert manifest['nameDetails'] == ['Run 12', 'Crossroads']
assert '+' not in manifest['createdAt'] and not manifest['createdAt'].endswith('Z')
assert manifest['hot'] is False
assert [(item['rootId'], item['relativePath'], item['size']) for item in manifest['files']] == [
    ('main', 'Profile1.sav', len(b'profile-one')),
    ('main', 'activeProfile', len(b'Profile1')),
]
assert all(len(item['sha256']) == 64 for item in manifest['files'])

verified = store.load_verified_snapshot(created['id'])
assert verified['manifest']['snapshotId'] == created['id']
assert verified['root'] == snapshot

renamed = store.rename_snapshot(created['id'], 'After rename')
assert renamed['name'] == 'After rename'
assert store.list_snapshots()[0]['name'] == 'After rename'
try:
    store.rename_snapshot(created['id'], '../bad')
except (ValueError, SaveSnapshotError):
    pass
else:
    raise AssertionError('unsafe display name accepted')

(snapshot / 'files/main/unlisted.bin').write_bytes(b'extra')
listed = store.list_snapshots()[0]
assert listed['id'] == created['id'] and listed['valid'] is False
assert listed['error']
try:
    store.load_verified_snapshot(created['id'])
except SaveSnapshotError:
    pass
else:
    raise AssertionError('snapshot with unexpected file verified')
deleted = store.delete_snapshot(created['id'])
assert deleted['deleted'] is True and not snapshot.exists()

# Non-canonical inventory rows remain explicitly revealable/deletable, but
# only as their own contained snapshots directory.
store._ensure_parent()
invalid_folder = store.snapshots / 'snap-bad'
invalid_folder.mkdir()
invalid_rows = store.list_snapshots()
assert len(invalid_rows) == 1 and invalid_rows[0]['id'] == 'snap-bad'
assert invalid_rows[0]['valid'] is False
assert Path(store.snapshot_folder('snap-bad')) == invalid_folder.resolve()
deleted_invalid = store.delete_snapshot('snap-bad')
assert deleted_invalid['deleted'] is True and not invalid_folder.exists()
assert not any(row['id'] == 'snap-bad' for row in store.list_snapshots())

# Inventory actions must not admit paths, parent directories, or symlinked
# snapshot folders, even when their basename resembles an inventory ID.
for invalid in ('../snap-x', '/tmp/snap-x', 'snapshot-x', 'snap-../../x', 'snapshots'):
    for action in (store.snapshot_folder, store.delete_snapshot):
        try:
            action(invalid)
        except (ValueError, SaveSnapshotError):
            pass
        else:
            raise AssertionError('unsafe snapshot id accepted: ' + invalid)

outside_folder = base / 'outside-snap'; outside_folder.mkdir()
nested_link_folder = store.snapshots / 'snap-bad-nested-link'
nested_link_folder.mkdir()
(nested_link_folder / 'outside').symlink_to(outside_folder, target_is_directory=True)
assert any(row['id'] == nested_link_folder.name and not row['valid'] for row in store.list_snapshots())
store.delete_snapshot(nested_link_folder.name)
assert not nested_link_folder.exists() and outside_folder.exists()

symlinked_folder = store.snapshots / 'snap-symlink'
symlinked_folder.symlink_to(outside_folder, target_is_directory=True)
for action in (store.snapshot_folder, store.delete_snapshot):
    try:
        action('snap-symlink')
    except (ValueError, SaveSnapshotError):
        pass
    else:
        raise AssertionError('symlinked inventory folder accepted')
assert outside_folder.exists()
symlinked_folder.unlink()

# Canonical IDs with corrupt contents are still inventory rows and may be
# revealed/deleted, while verified operations continue to reject them.
corrupt_folder = store.snapshots / 'snap-20260925-120000-deadbeef'
corrupt_folder.mkdir()
assert any(row['id'] == corrupt_folder.name and not row['valid'] for row in store.list_snapshots())
assert Path(store.snapshot_folder(corrupt_folder.name)) == corrupt_folder.resolve()
store.delete_snapshot(corrupt_folder.name)
assert not any(row['id'] == corrupt_folder.name for row in store.list_snapshots())

created = store.create_snapshot(rows, hot=False)
snapshot = Path(created['path'])
target = snapshot / 'files/main/Profile1.sav'
target.unlink()
target.symlink_to(source / 'Profile1.sav')
assert store.list_snapshots()[0]['valid'] is False
store.delete_snapshot(created['id'])

created = store.create_snapshot(rows, hot=False, display_name='Internal name')
snapshot = Path(created['path'])
manifest_path = snapshot / 'manifest.json'
external_manifest = base / 'external-manifest.json'
external = json.loads(manifest_path.read_text(encoding='utf-8'))
external['displayName'] = 'LEAKED EXTERNAL NAME'
external_manifest.write_text(json.dumps(external), encoding='utf-8')
manifest_path.unlink()
manifest_path.symlink_to(external_manifest)
listed = store.list_snapshots()[0]
assert listed['valid'] is False
assert listed['name'] == created['id'], listed
store.delete_snapshot(created['id'])

# A parseable-but-malformed manifest must still produce a UI-decodable invalid
# row. Untrusted metadata cannot replace the string/bool fields Swift relies on.
created = store.create_snapshot(rows, hot=False, display_name='Safe before corruption')
snapshot = Path(created['path'])
manifest_path = snapshot / 'manifest.json'
malformed = json.loads(manifest_path.read_text(encoding='utf-8'))
malformed['displayName'] = {'unexpected': 'object'}
malformed['createdAt'] = ['not', 'a', 'timestamp']
malformed['hot'] = 'yes'
malformed['nameDetails'] = {'unexpected': 'object'}
manifest_path.write_text(json.dumps(malformed), encoding='utf-8')
rows_after_corruption = store.list_snapshots()
assert len(rows_after_corruption) == 1
listed = rows_after_corruption[0]
assert listed['id'] == created['id']
assert listed['valid'] is False
assert listed['name'] == created['id']
assert listed['createdAt'] == ''
assert listed['hot'] is False
assert listed['nameDetails'] == []
assert isinstance(listed['error'], str) and listed['error']
store.delete_snapshot(created['id'])

(source / 'Profile2.sav').write_bytes(b'second')
cold_calls = 0
def cold_racing_resolver():
    global cold_calls
    cold_calls += 1
    if cold_calls == 1:
        return rows()
    return rows() + [ResolvedSaveFile('main', 'Profile2.sav', source / 'Profile2.sav')]
try:
    store.create_snapshot(cold_racing_resolver, hot=False)
except SaveSnapshotBusyError as error:
    assert error.code == 'save_busy'
else:
    raise AssertionError('cold snapshot committed while save set changed')
assert not store.list_snapshots()

symlink_base = base / 'symlink-data'
external_snapshots = base / 'external-snapshots'; external_snapshots.mkdir()
link_parent = symlink_base / 'example/saves'; link_parent.mkdir(parents=True)
(link_parent / 'snapshots').symlink_to(external_snapshots, target_is_directory=True)
symlink_store = SaveSnapshotStore('example', symlink_base)
try:
    symlink_store.create_snapshot(rows, hot=False)
except SaveSnapshotError:
    pass
else:
    raise AssertionError('snapshot store followed a symlinked snapshots directory')

# The game-specific data directory is part of the trusted internal storage
# boundary too. A symlink one level above saves/ must not redirect snapshots
# outside the configured MacGamingTrainer data root.
ancestor_data = base / 'ancestor-data'; ancestor_data.mkdir()
ancestor_external = base / 'ancestor-external'; ancestor_external.mkdir()
(ancestor_data / 'example').symlink_to(ancestor_external, target_is_directory=True)
ancestor_store = SaveSnapshotStore('example', ancestor_data)
try:
    ancestor_store.create_snapshot(rows, hot=False)
except SaveSnapshotError:
    pass
else:
    raise AssertionError('snapshot store followed a symlinked game data directory')
assert not (ancestor_external / 'saves').exists()

(source / 'Profile1.sav').write_bytes(b'first-version')
(source / 'Profile2.sav').unlink()
resolve_calls = 0

def racing_resolver():
    global resolve_calls
    resolve_calls += 1
    if resolve_calls == 2:
        (source / 'Profile1.sav').write_bytes(b'stable-second-version')
    return rows()

hot = store.create_snapshot(racing_resolver, hot=True)
assert hot['hot'] is True
assert (Path(hot['path']) / 'files/main/Profile1.sav').read_bytes() == b'stable-second-version'
assert resolve_calls >= 4
assert len(store.list_snapshots()) == 1
assert not list((base / 'data/example/saves/snapshots').glob('.snapshot-*'))

print('core_save_snapshots_ok')


for bad_details in (
    [''] ,
    ['a', 'b', 'c', 'd', 'e'],
    ['ok', 'bad\nline'],
    'not-a-list',
):
    try:
        store.create_snapshot(rows, hot=False, name_details=bad_details)
    except (ValueError, SaveSnapshotError):
        pass
    else:
        raise AssertionError('unsafe snapshot nameDetails accepted: {!r}'.format(bad_details))

# Inventory reclaims only old, contained snapshot/manifest staging artifacts.
created = store.create_snapshot(rows, hot=False, display_name='Keep normal snapshot')
snapshots_root = store.snapshots
old_cutoff = time.time() - 8 * 24 * 60 * 60
stale_stage = snapshots_root / '.snapshot-orphaned123'
stale_stage.mkdir()
(stale_stage / 'partial').write_bytes(b'partial')
os.utime(stale_stage, (old_cutoff, old_cutoff))
fresh_stage = snapshots_root / '.snapshot-active123'
fresh_stage.mkdir()
(fresh_stage / 'partial').write_bytes(b'in progress')
stale_manifest = Path(created['path']) / '.manifest-abandoned.json'
stale_manifest.write_bytes(b'partial manifest')
os.utime(stale_manifest, (old_cutoff, old_cutoff))
fresh_manifest = Path(created['path']) / '.manifest-current.json'
fresh_manifest.write_bytes(b'current manifest')
bad_manifest_prefix = Path(created['path']) / '.manifest-abandoned.json.extra'
bad_manifest_prefix.write_bytes(b'not the staging suffix')
os.utime(bad_manifest_prefix, (old_cutoff, old_cutoff))
outside = base / 'outside-stage'
outside.mkdir()
(outside / 'preserve').write_bytes(b'outside')
manifest_escape = Path(created['path']) / '.manifest-external123.json'
manifest_escape.symlink_to(outside / 'preserve')
escape = snapshots_root / '.snapshot-ABCDEFGH'
escape.symlink_to(outside, target_is_directory=True)
unrelated = snapshots_root / 'snapshot-lookalike'
unrelated.mkdir()
bad_prefix = snapshots_root / '.snapshot-ABCDEFGH-extra'
bad_prefix.mkdir()
os.utime(bad_prefix, (old_cutoff, old_cutoff))

inventory = store.list_snapshots()
assert any(row['id'] == created['id'] and row['valid'] for row in inventory), inventory
assert not stale_stage.exists()
assert not stale_manifest.exists()
assert fresh_stage.is_dir() and fresh_manifest.is_file()
assert bad_manifest_prefix.is_file() and manifest_escape.is_symlink()
assert escape.is_symlink() and (outside / 'preserve').read_bytes() == b'outside'
assert unrelated.is_dir() and bad_prefix.is_dir()
print('core_save_snapshot_staging_cleanup_ok')
