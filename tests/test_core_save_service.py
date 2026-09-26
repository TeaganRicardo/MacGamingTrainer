import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

import core.save_restore as save_restore_module
import core.save_service as save_service_module
from core.module_manifest import SaveManagementSpec, SaveRootSpec
from core.save_restore import SaveBusyError, SaveRollbackError
from core.save_service import (
    CoreSaveService,
    SaveManagementUnsupportedError,
    SaveStagedUnavailableError,
)
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

# Preserved rollback directories are the last recovery evidence if the backend
# dies while rollback itself is in progress. They must remain discoverable on
# the next service instance, while symlinked lookalikes stay excluded.
recovery_root = service.store.ensure_storage_root() / 'transactions'
recovery_root.mkdir(parents=True, exist_ok=True)
recovery_a = recovery_root / '.rollback-visible-a'; recovery_a.mkdir()
(recovery_a / 'files').mkdir()
recovery_b = recovery_root / '.rollback-visible-b'; recovery_b.mkdir()
(recovery_b / 'files').mkdir()
external_recovery = base / 'external-recovery'; external_recovery.mkdir()
unsafe_recovery = recovery_root / '.rollback-unsafe'
unsafe_recovery.symlink_to(external_recovery, target_is_directory=True)
recovery_state = CoreSaveService('example', spec, data, is_running).list_state()
assert recovery_state['recoveryPaths'] == [str(recovery_a.resolve()), str(recovery_b.resolve())]

# Reproduce the actual forced-death path: one target file is replaced, the next
# write fails, then rollback itself is interrupted. The next service instance
# must surface the preserved pre-restore bytes instead of leaving them hidden.
interrupted_saves = base / 'interrupted-rollback-saves'; interrupted_saves.mkdir()
interrupted_spec = SaveManagementSpec(
    roots=(SaveRootSpec('main', str(interrupted_saves), ('*.sav',)),), provider=None,
    hot_backup=False, restore_policy='stoppedOnly', staged_restore=True,
)
interrupted_service = CoreSaveService('interrupted-rollback', interrupted_spec, data, lambda: False)
(interrupted_saves / 'Profile1.sav').write_bytes(b'target-one')
(interrupted_saves / 'Profile2.sav').write_bytes(b'target-two')
interrupted_target = interrupted_service.backup()
(interrupted_saves / 'Profile1.sav').write_bytes(b'current-one')
(interrupted_saves / 'Profile2.sav').write_bytes(b'current-two')
real_replace = save_restore_module.os.replace
save_replace_count = 0
def interrupt_rollback_replace(source, destination):
    global save_replace_count
    destination = Path(destination)
    if interrupted_saves in destination.parents:
        save_replace_count += 1
        if save_replace_count == 2:
            raise OSError('simulated target install failure')
        if save_replace_count == 3:
            raise KeyboardInterrupt()
    return real_replace(source, destination)
save_restore_module.os.replace = interrupt_rollback_replace
try:
    try:
        interrupted_service.restore(interrupted_target['id'], preserve_current=False)
    except KeyboardInterrupt:
        pass
    else:
        raise AssertionError('rollback interruption unexpectedly succeeded')
finally:
    save_restore_module.os.replace = real_replace
interrupted_state = CoreSaveService('interrupted-rollback', interrupted_spec, data, lambda: False).list_state()
assert len(interrupted_state['recoveryPaths']) == 1
interrupted_recovery = Path(interrupted_state['recoveryPaths'][0])
assert (interrupted_recovery / 'files/main/Profile1.sav').read_bytes() == b'current-one'
assert (interrupted_recovery / 'files/main/Profile2.sav').read_bytes() == b'current-two'
assert (interrupted_saves / 'Profile1.sav').read_bytes() == b'target-one'
assert (interrupted_saves / 'Profile2.sav').read_bytes() == b'current-two'

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

# A restore that begins while the target is stopped must fail closed if the
# target launches before real-save mutation. hotPreferred may stage that restore,
# but it must not silently continue as a cold transaction using stale process state.
class LaunchDuringRestoreProbe:
    def __init__(self):
        self.armed = False
        self.calls = 0
    def __call__(self):
        if not self.armed:
            return False
        self.calls += 1
        return self.calls >= 2

launch_probe = LaunchDuringRestoreProbe()
launch_saves = base / 'launch-race-saves'; launch_saves.mkdir()
launch_spec = SaveManagementSpec(
    roots=(SaveRootSpec('main', str(launch_saves), ('*.sav',)),), provider=None,
    hot_backup=True, restore_policy='hotPreferred', staged_restore=True,
)
launch_service = CoreSaveService('launch-race', launch_spec, data, launch_probe)
(launch_saves / 'Profile1.sav').write_bytes(b'launch-target')
launch_target = launch_service.backup()
(launch_saves / 'Profile1.sav').write_bytes(b'launch-current')
launch_probe.armed = True
launch_result = launch_service.restore(launch_target['id'], preserve_current=False)
assert launch_result['staged'] is True
assert (launch_saves / 'Profile1.sav').read_bytes() == b'launch-current'
assert launch_service.pending_restore()['snapshotId'] == launch_target['id']

# Backend SIGTERM becomes KeyboardInterrupt. If staged apply is interrupted after
# claiming its marker, the transaction layer rolls back real saves and the
# staged instruction must be restored instead of disappearing into a hidden
# applying marker.
(saves / 'Profile1.sav').write_bytes(b'interrupt-stage-target')
interrupt_service = CoreSaveService('interrupt-stage', no_hot_spec, data, is_running)
interrupt_target = interrupt_service.backup()
(saves / 'Profile1.sav').write_bytes(b'interrupt-stage-current')
running = True
interrupt_service.restore(interrupt_target['id'], preserve_current=False)
running = False
real_restore = save_service_module.SaveRestoreTransaction.restore
def interrupt_staged_restore(self, *args, **kwargs):
    raise KeyboardInterrupt()
save_service_module.SaveRestoreTransaction.restore = interrupt_staged_restore
try:
    try:
        interrupt_service.apply_staged()
    except KeyboardInterrupt:
        pass
    else:
        raise AssertionError('interrupted staged apply unexpectedly succeeded')
finally:
    save_service_module.SaveRestoreTransaction.restore = real_restore
interrupt_pending = interrupt_service.pending_restore()
assert interrupt_pending['snapshotId'] == interrupt_target['id']
assert interrupt_pending['indeterminate'] is True
assert interrupt_service.apply_staged()['indeterminate'] is True
assert interrupt_service.cancel_staged()['cancelled'] is True

# An interruption while preparing the rollback copy is known to precede save
# mutation: remove its temporary directory and return the staged marker to pending.
precopy_saves = base / 'precopy-interrupt-saves'; precopy_saves.mkdir()
precopy_spec = SaveManagementSpec(
    roots=(SaveRootSpec('main', str(precopy_saves), ('*.sav',)),), provider=None,
    hot_backup=False, restore_policy='stoppedOnly', staged_restore=True,
)
precopy_service = CoreSaveService('precopy-interrupt', precopy_spec, data, is_running)
(precopy_saves / 'Profile1.sav').write_bytes(b'precopy-target')
precopy_target = precopy_service.backup()
(precopy_saves / 'Profile1.sav').write_bytes(b'precopy-current')
running = True
precopy_service.restore(precopy_target['id'], preserve_current=False)
running = False
real_copy2 = save_restore_module.shutil.copy2
def interrupt_rollback_copy(source, destination, *args, **kwargs):
    if '.rollback-' in str(destination):
        raise KeyboardInterrupt()
    return real_copy2(source, destination, *args, **kwargs)
save_restore_module.shutil.copy2 = interrupt_rollback_copy
try:
    try:
        precopy_service.apply_staged()
    except KeyboardInterrupt:
        pass
    else:
        raise AssertionError('rollback pre-copy interruption unexpectedly succeeded')
finally:
    save_restore_module.shutil.copy2 = real_copy2
precopy_transactions = precopy_service.store.ensure_storage_root() / 'transactions'
assert not list(precopy_transactions.glob('.rollback-*'))
assert precopy_service._staged_path().exists()
precopy_pending = precopy_service.pending_restore()
assert precopy_pending['snapshotId'] == precopy_target['id']
assert precopy_pending['indeterminate'] is False
assert (precopy_saves / 'Profile1.sav').read_bytes() == b'precopy-current'

# A transaction that explicitly reports rollback_failed has already told Core
# that real-save state cannot be proven. The claimed staged marker must stay in
# the indeterminate namespace instead of becoming an ordinary auto-retry.
(saves / 'Profile1.sav').write_bytes(b'rollback-failed-target')
rollback_failed_service = CoreSaveService('rollback-failed-stage', no_hot_spec, data, is_running)
rollback_failed_target = rollback_failed_service.backup()
(saves / 'Profile1.sav').write_bytes(b'rollback-failed-current')
running = True
rollback_failed_service.restore(rollback_failed_target['id'], preserve_current=False)
running = False
rollback_recovery = base / 'rollback-failed-recovery'
rollback_recovery.mkdir()
real_restore = save_service_module.SaveRestoreTransaction.restore
def fail_staged_rollback(self, *args, **kwargs):
    raise SaveRollbackError('simulated rollback failure', rollback_recovery)
save_service_module.SaveRestoreTransaction.restore = fail_staged_rollback
try:
    try:
        rollback_failed_service.apply_staged()
    except SaveRollbackError as error:
        assert error.recovery_path == str(rollback_recovery)
    else:
        raise AssertionError('rollback_failed staged restore unexpectedly succeeded')
finally:
    save_service_module.SaveRestoreTransaction.restore = real_restore
rollback_failed_pending = rollback_failed_service.pending_restore()
assert rollback_failed_pending['snapshotId'] == rollback_failed_target['id']
assert rollback_failed_pending['indeterminate'] is True
assert rollback_failed_service.apply_staged()['indeterminate'] is True
assert rollback_failed_service.cancel_staged()['cancelled'] is True

# A hard process loss can leave only the claimed marker. Its outcome is
# indeterminate: it must be surfaced, never auto-replayed, must block staging a
# second restore, and explicit cancellation must clear the unresolved claim.
(saves / 'Profile1.sav').write_bytes(b'indeterminate-target')
indeterminate_service = CoreSaveService('indeterminate-stage', no_hot_spec, data, is_running)
indeterminate_target = indeterminate_service.backup()
indeterminate_recovery = indeterminate_service.backup(display_name='Recovery option')
(saves / 'Profile1.sav').write_bytes(b'indeterminate-current')
running = True
indeterminate_service.restore(indeterminate_target['id'], preserve_current=False)
indeterminate_path = indeterminate_service._staged_path()
indeterminate_claim = indeterminate_path.with_name('.staged-restore-applying-hard-crash.json')
os.replace(indeterminate_path, indeterminate_claim)
running = False
indeterminate_pending = indeterminate_service.pending_restore()
assert indeterminate_pending['snapshotId'] == indeterminate_target['id']
assert indeterminate_pending['indeterminate'] is True
indeterminate_apply = indeterminate_service.apply_staged()
assert indeterminate_apply['applied'] is False
assert indeterminate_apply['indeterminate'] is True
assert (saves / 'Profile1.sav').read_bytes() == b'indeterminate-current'
try:
    indeterminate_service.delete(indeterminate_recovery['id'])
except ValueError:
    pass
else:
    raise AssertionError('backup deletion remained enabled during indeterminate restore recovery')
# Staging a new restore while the prior outcome is unresolved is unsafe.
running = True
try:
    indeterminate_service.restore(indeterminate_target['id'], preserve_current=False)
except Exception as error:
    assert getattr(error, 'code', None) == 'staged_indeterminate'
else:
    raise AssertionError('new staged restore replaced an indeterminate prior restore')
running = False
assert indeterminate_service.cancel_staged()['cancelled'] is True
assert not indeterminate_claim.exists()
assert indeterminate_service.pending_restore() is None

# A successful staged restore must not remain pending just because cleanup of
# its consumed marker fails. Otherwise the next target-stop event can reapply
# a restore that already committed.
(saves / 'Profile1.sav').write_bytes(b'cleanup-target')
cleanup_service = CoreSaveService('cleanup-failure', no_hot_spec, data, is_running)
cleanup_target = cleanup_service.backup()
(saves / 'Profile1.sav').write_bytes(b'cleanup-current')
running = True
cleanup_service.restore(cleanup_target['id'], preserve_current=False)
running = False
real_unlink = Path.unlink
def fail_staged_marker_cleanup(path, *args, **kwargs):
    if 'staged-restore' in path.name:
        raise PermissionError('simulated staged marker cleanup failure')
    return real_unlink(path, *args, **kwargs)
Path.unlink = fail_staged_marker_cleanup
try:
    cleanup_applied = cleanup_service.apply_staged()
finally:
    Path.unlink = real_unlink
assert cleanup_applied['applied'] is True
assert (saves / 'Profile1.sav').read_bytes() == b'cleanup-target'
assert cleanup_service.pending_restore() is None
cleanup_dir = cleanup_service._staged_path().parent
assert not list(cleanup_dir.glob('.staged-restore-applying-*.json'))
assert len(list(cleanup_dir.glob('.staged-restore-applied-*.json'))) == 1

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

# Transient marker reads must not consume or quarantine staged bytes.
read_error_marker = marker.parent / 'staged-restore.json'
read_error_marker.write_text(
    '{"snapshotId":"' + stopped_target['id'] + '","preserveCurrent":false,"stagedAt":"test"}',
    encoding='utf-8',
)
read_error_bytes = read_error_marker.read_bytes()
real_read_text = Path.read_text
def fail_pending_marker_read(path, *args, **kwargs):
    if path == read_error_marker:
        raise PermissionError('simulated temporary marker read failure')
    return real_read_text(path, *args, **kwargs)
Path.read_text = fail_pending_marker_read
try:
    try:
        reloaded.pending_restore()
    except PermissionError:
        pass
    else:
        raise AssertionError('temporary marker read failure was swallowed')
finally:
    Path.read_text = real_read_text
assert read_error_marker.exists()
assert read_error_marker.read_bytes() == read_error_bytes
assert len(list(marker.parent.glob('staged-restore.json.corrupt-*'))) == 1
read_error_marker.unlink()

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

# Cancellation is destructive too: it must validate the internal storage root
# before unlinking a staged marker through a symlinked game-data parent.
cancel_guard_data = base / 'cancel-guard-data'; cancel_guard_data.mkdir()
cancel_guard_external = base / 'cancel-guard-external'
(cancel_guard_external / 'saves').mkdir(parents=True)
cancel_guard_marker = cancel_guard_external / 'saves/staged-restore.json'
cancel_guard_marker.write_text('external-marker', encoding='utf-8')
(cancel_guard_data / 'cancel-guard').symlink_to(cancel_guard_external, target_is_directory=True)
cancel_guard = CoreSaveService(
    'cancel-guard', stage_guard_spec, cancel_guard_data, is_running
)
try:
    cancel_guard.cancel_staged()
except SaveSnapshotError:
    pass
else:
    raise AssertionError('cancel staged followed a symlinked game data directory')
assert cancel_guard_marker.read_text(encoding='utf-8') == 'external-marker'

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
