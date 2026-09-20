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
assert '+' not in staged['stagedAt'] and not staged['stagedAt'].endswith('Z')
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
    describe_calls = 0
    def resolve(self, roots, declared):
        return [(row.root_id, row.relative_path) for row in declared]
    def restore_busy(self, files):
        return self.busy
    def describe_snapshot(self, files, created_at):
        self.describe_calls += 1
        assert '+' not in created_at and not created_at.endswith('Z')
        assert any(row.relative_path == 'Profile1.sav' for row in files)
        return {'defaultName': 'Run 42 · Crossroads', 'nameDetails': ['Run 42', 'Crossroads']}
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
assert provider_target['name'] == 'Run 42 · Crossroads'
assert provider_target['nameDetails'] == ['Run 42', 'Crossroads']
assert provider.describe_calls == 1
explicit_provider_target = provider_service.backup(display_name='My manual name')
assert explicit_provider_target['name'] == 'My manual name'
assert explicit_provider_target['nameDetails'] == ['Run 42', 'Crossroads']
assert provider.describe_calls == 2
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
assert len(provider_service.list_state()['snapshots']) == 3

# Provider naming is evaluated inside the successful hot-snapshot attempt.
# If the save changes after the first description, the retry must describe the
# bytes that are actually committed rather than keeping stale naming metadata.
class NamingRaceProvider:
    def __init__(self):
        self.resolve_calls = 0
    def resolve(self, roots, declared):
        self.resolve_calls += 1
        if self.resolve_calls == 2:
            (saves / 'Profile1.sav').write_bytes(b'name-v2')
        return [(row.root_id, row.relative_path) for row in declared]
    def describe_snapshot(self, files, created_at):
        row = next(row for row in files if row.relative_path == 'Profile1.sav')
        value = row.source_path.read_bytes().decode('utf-8')
        return {'defaultName': value, 'nameDetails': [value]}

naming_provider = NamingRaceProvider()
naming_spec = SaveManagementSpec(
    roots=(SaveRootSpec('main', str(saves), ('*.sav',)),),
    provider='games.example.naming_provider:Provider', hot_backup=True,
    restore_policy='hotPreferred', staged_restore=True,
)
(saves / 'Profile1.sav').write_bytes(b'name-v1')
running = True
naming_service = CoreSaveService(
    'naming-race', naming_spec, data, is_running,
    provider_loader=lambda target: naming_provider,
)
named = naming_service.backup()
assert named['name'] == 'name-v2', named
assert named['nameDetails'] == ['name-v2'], named
assert (Path(named['path']) / 'files/main/Profile1.sav').read_bytes() == b'name-v2'
running = False

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

# Staged restore must not follow a game-specific internal-data symlink either.
# Preserve a valid snapshot tree, move the game data directory outside the
# configured data root, then replace it with a symlink to reproduce the escape.
running = False
stage_guard_spec = SaveManagementSpec(
    roots=(SaveRootSpec('main', str(saves), ('*.sav',)),), provider=None,
    hot_backup=False, restore_policy='stoppedOnly', staged_restore=True,
)
(saves / 'Profile1.sav').write_bytes(b'stage-guard-target')
stage_guard = CoreSaveService('stage-guard', stage_guard_spec, data, is_running)
stage_guard_target = stage_guard.backup()
stage_guard_game_root = data / 'stage-guard'
stage_guard_external = base / 'stage-guard-external'
stage_guard_game_root.rename(stage_guard_external)
stage_guard_game_root.symlink_to(stage_guard_external, target_is_directory=True)
(saves / 'Profile1.sav').write_bytes(b'stage-guard-current')
running = True
try:
    stage_guard.restore(stage_guard_target['id'], preserve_current=False)
except SaveSnapshotError:
    pass
else:
    raise AssertionError('staged restore followed a symlinked game data directory')
assert not (stage_guard_external / 'saves/staged-restore.json').exists()
running = False

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
