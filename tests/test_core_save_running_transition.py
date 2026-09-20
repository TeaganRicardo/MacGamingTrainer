from pathlib import Path
from types import SimpleNamespace
import hashlib
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from core.save_resolution import ResolvedSaveFile
from core.save_restore import SaveBusyError, SaveRestoreTransaction

base = Path(tempfile.mkdtemp(prefix='mgt-save-running-transition-'))
save_root = base / 'game-saves'
save_root.mkdir()
current = save_root / 'Profile1.sav'
current.write_bytes(b'current')

snapshot_root = base / 'snapshot'
snapshot_file = snapshot_root / 'files/main/Profile1.sav'
snapshot_file.parent.mkdir(parents=True)
snapshot_file.write_bytes(b'target')
target_digest = hashlib.sha256(b'target').hexdigest()

class Store:
    def ensure_storage_root(self):
        path = base / 'trainer-storage'
        path.mkdir(exist_ok=True)
        return path

    def load_verified_snapshot(self, snapshot_id):
        return {
            'root': snapshot_root,
            'manifest': {
                'files': [{
                    'rootId': 'main',
                    'relativePath': 'Profile1.sav',
                    'sha256': target_digest,
                }],
            },
        }

store = Store()
spec = SimpleNamespace(
    roots=(SimpleNamespace(id='main', path=str(save_root)),),
)

def resolver():
    return [ResolvedSaveFile('main', 'Profile1.sav', current)]

probe_calls = 0

def running_probe():
    global probe_calls
    probe_calls += 1
    return True

transaction = SaveRestoreTransaction(
    store,
    spec,
    resolver,
    target_running_probe=running_probe,
)

try:
    transaction.restore('target', preserve_current=False, target_running=False)
except SaveBusyError:
    pass
else:
    raise AssertionError('cold restore ignored a target that started before mutation')

assert current.read_bytes() == b'current'
assert probe_calls >= 1

service_source = (ROOT / 'Backend/core/save_service.py').read_text()
transaction_factory = service_source[
    service_source.index('    def _transaction(self):'):
    service_source.index('    def _staged_path(self):')
]
assert 'target_running_probe=self._running' in transaction_factory

print('core_save_running_transition_ok')
