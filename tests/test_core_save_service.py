from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from core.module_manifest import SaveManagementSpec, SaveRootSpec
from core.save_restore import SaveBusyError
from core.save_service import CoreSaveService, SaveManagementUnsupportedError, SaveStagedUnavailableError
from core.save_snapshots import SaveSnapshotError


base = Path(tempfile.mkdtemp(prefix='mgt-save-service-'))
saves = base / 'saves'; saves.mkdir()
data = base / 'data'
running = False

def is_running():
    return running

spec = SaveManagementSpec(
    roots=(SaveRootSpec('main', str(saves), ('*.sav',)),), provider=None,
    hot_backup=True, restore_policy='hotPreferred', staged_restore=True,
)
service = CoreSaveService('example', spec, data, is_running)

# Unsupported modules have a distinct Core error.
unsupported = CoreSaveService('unsupported', None, data, lambda: False)
try:
    unsupported.list_state()
except SaveManagementUnsupportedError as error:
    assert error.code == 'save_unsupported'
else:
    raise AssertionError('unsupported save management was accepted')

# Cold target snapshot, then running hot backup.
(saves / 'Profile1.sav').write_bytes(b'target')
target = service.backup(display_name='Target')
assert target['hot'] is False
(saves / 'Profile1.sav').write_bytes(b'live-current')
running = True
hot = service.backup(display_name='Live')
assert hot['hot'] is True
assert service.list_state()['snapshots'][0]['valid'] is True

# A game that disables hot backup refuses backup while running.
no_hot_spec = SaveManagementSpec(
    roots=(SaveRootSpec('main', str(saves), ('*.sav',)),), provider=None,
    hot_backup=False, restore_policy='stoppedOnly', staged_restore=True,
)
no_hot = CoreSaveService('no_hot', no_hot_spec, data, is_running)
try:
    no_hot.backup()
except SaveBusyError:
    pass
else:
    raise AssertionError('running backup ignored hotBackup=false')

# stoppedOnly does not mutate while running; it stages and survives service recreation.
running = False
stopped_only = CoreSaveService('stopped', no_hot_spec, data, is_running)
(saves / 'Profile1.sav').write_bytes(b'stopped-target')
stopped_target = stopped_only.backup()
(saves / 'Profile1.sav').write_bytes(b'stopped-current')
running = True
staged = stopped_only.restore(stopped_target['id'], preserve_current=False)
assert staged['staged'] is True
assert (saves / 'Profile1.sav').read_bytes() == b'stopped-current'
reloaded = CoreSaveService('stopped', no_hot_spec, data, is_running)
assert reloaded.pending_restore()['snapshotId'] == stopped_target['id']
running = False
applied = reloaded.apply_staged()
assert applied['applied'] is True
assert (saves / 'Profile1.sav').read_bytes() == b'stopped-target'
assert reloaded.pending_restore() is None

# hotPreferred busy provider falls back to staged restore without mutation.
class Provider:
    busy = False
    def resolve(self, roots, declared):
        return [(row.root_id, row.relative_path) for row in declared]
    def restore_busy(self, files):
        return self.busy
provider = Provider()
provider_spec = SaveManagementSpec(
    roots=(SaveRootSpec('main', str(saves), ('*.sav',)),),
    provider='games.example.save_provider:Provider', hot_backup=True,
    restore_policy='hotPreferred', staged_restore=True,
)
running = False
provider_service = CoreSaveService('provider', provider_spec, data, is_running, provider_loader=lambda target: provider)
(saves / 'Profile1.sav').write_bytes(b'provider-target')
provider_target = provider_service.backup()
(saves / 'Profile1.sav').write_bytes(b'provider-current')
provider.busy = True
running = True
staged = provider_service.restore(provider_target['id'], preserve_current=True)
assert staged['staged'] is True
assert (saves / 'Profile1.sav').read_bytes() == b'provider-current'
provider.busy = False
running = False
provider_service.apply_staged()
assert (saves / 'Profile1.sav').read_bytes() == b'provider-target'
# preserveCurrent on staged apply creates a normal inventory snapshot.
assert len(provider_service.list_state()['snapshots']) == 2

# If staging is disabled, a running stoppedOnly restore reports that exact capability failure.
no_stage_spec = SaveManagementSpec(
    roots=(SaveRootSpec('main', str(saves), ('*.sav',)),), provider=None,
    hot_backup=False, restore_policy='stoppedOnly', staged_restore=False,
)
running = False
no_stage = CoreSaveService('no_stage', no_stage_spec, data, is_running)
(saves / 'Profile1.sav').write_bytes(b'no-stage-target')
no_stage_target = no_stage.backup()
(saves / 'Profile1.sav').write_bytes(b'no-stage-current')
running = True
try:
    no_stage.restore(no_stage_target['id'])
except SaveStagedUnavailableError as error:
    assert error.code == 'staged_unavailable'
else:
    raise AssertionError('stoppedOnly running restore ignored stagedRestore=false')
assert (saves / 'Profile1.sav').read_bytes() == b'no-stage-current'

# Corrupt staged metadata is quarantined and ignored; cancel is idempotent.
running = False
marker = data / 'stopped/saves/staged-restore.json'
marker.parent.mkdir(parents=True, exist_ok=True)
marker.write_text('{ broken json', encoding='utf-8')
assert reloaded.pending_restore() is None
assert not marker.exists()
assert len(list(marker.parent.glob('staged-restore.json.corrupt-*'))) == 1
assert reloaded.cancel_staged()['cancelled'] is False

# A pending target cannot be deleted until staging is cancelled.
(saves / 'Profile1.sav').write_bytes(b'delete-target')
delete_target = reloaded.backup()
(saves / 'Profile1.sav').write_bytes(b'delete-current')
running = True
reloaded.restore(delete_target['id'], preserve_current=False)
try:
    reloaded.delete(delete_target['id'])
except ValueError:
    pass
else:
    raise AssertionError('pending restore snapshot was deleted')
assert reloaded.cancel_staged()['cancelled'] is True
assert reloaded.delete(delete_target['id'])['deleted'] is True

# Empty real-save set fails instead of creating an empty snapshot.
running = False
for path in saves.glob('*.sav'):
    path.unlink()
try:
    service.backup()
except SaveSnapshotError:
    pass
else:
    raise AssertionError('empty save set created a snapshot')

print('core_save_service_ok')
