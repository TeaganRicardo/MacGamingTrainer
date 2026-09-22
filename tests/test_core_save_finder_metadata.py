from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from core.save_resolution import ResolvedSaveFile
from core.save_snapshots import SaveSnapshotStore


base = Path(tempfile.mkdtemp(prefix='mgt-save-finder-metadata-'))
source = base / 'source'
source.mkdir()
(source / 'Profile1.sav').write_bytes(b'profile-one')
(source / 'activeProfile').write_bytes(b'Profile1')


def rows():
    return [
        ResolvedSaveFile('main', 'Profile1.sav', source / 'Profile1.sav'),
        ResolvedSaveFile('main', 'activeProfile', source / 'activeProfile'),
    ]


store = SaveSnapshotStore('example', base / 'data')
created = store.create_snapshot(rows, hot=False, display_name='Finder metadata regression')
snapshot = Path(created['path'])

(snapshot / 'files/.DS_Store').write_bytes(b'finder-root-metadata')
(snapshot / 'files/main/.DS_Store').write_bytes(b'finder-nested-metadata')

verified = store.load_verified_snapshot(created['id'])
assert verified['manifest']['snapshotId'] == created['id']

listed = store.list_snapshots()
assert len(listed) == 1
assert listed[0]['id'] == created['id']
assert listed[0]['valid'] is True
assert listed[0]['error'] == ''

print('core_save_finder_metadata_ok')
