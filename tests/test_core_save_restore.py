from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from core.module_manifest import SaveManagementSpec, SaveRootSpec
from core.save_resolution import ResolvedSaveFile
from core.save_snapshots import SaveSnapshotStore
from core.save_restore import SaveBusyError, SaveRestoreError, SaveRollbackError, SaveRestoreTransaction
import core.save_restore as restore_module


base = Path(tempfile.mkdtemp(prefix='mgt-save-restore-'))
save_root = base / 'game-saves'; save_root.mkdir()
data_root = base / 'data'
spec = SaveManagementSpec(
    roots=(SaveRootSpec('main', str(save_root), ('*.sav',)),),
    provider=None, hot_backup=True, restore_policy='hotPreferred', staged_restore=True,
)
store = SaveSnapshotStore('example', data_root)


def resolved():
    rows = []
    for path in sorted(save_root.glob('*.sav')):
        if path.is_file() and not path.is_symlink():
            rows.append(ResolvedSaveFile('main', path.name, path))
    return rows


(save_root / 'Profile1.sav').write_bytes(b'target-profile')
(save_root / 'restored-only.sav').write_bytes(b'target-restored-only')
target = store.create_snapshot(resolved, hot=False, display_name='Target')

(save_root / 'Profile1.sav').write_bytes(b'current-profile')
(save_root / 'restored-only.sav').unlink()
(save_root / 'obsolete.sav').write_bytes(b'obsolete')
(save_root / 'settings.json').write_bytes(b'unrelated')

transaction = SaveRestoreTransaction(store, spec, resolved)
result = transaction.restore(target['id'], preserve_current=True, target_running=False)
assert result['restored'] is True
assert result['hot'] is False
assert result['previousSnapshotId'] is not None
assert (save_root / 'Profile1.sav').read_bytes() == b'target-profile'
assert (save_root / 'restored-only.sav').read_bytes() == b'target-restored-only'
assert not (save_root / 'obsolete.sav').exists()
assert (save_root / 'settings.json').read_bytes() == b'unrelated'
assert save_root.is_dir()
previous = store.load_verified_snapshot(result['previousSnapshotId'])
assert (previous['root'] / 'files/main/Profile1.sav').read_bytes() == b'current-profile'
assert (previous['root'] / 'files/main/obsolete.sav').read_bytes() == b'obsolete'

(save_root / 'Profile1.sav').write_bytes(b'live-current')
(save_root / 'restored-only.sav').write_bytes(b'live-current-extra')
live = transaction.restore(target['id'], preserve_current=False, target_running=True)
assert live['restored'] is True and live['hot'] is True
assert (save_root / 'Profile1.sav').read_bytes() == b'target-profile'

(save_root / 'Profile1.sav').write_bytes(b'busy-current')
blocked = SaveRestoreTransaction(store, spec, resolved, busy_probe=lambda files: True)
try:
    blocked.restore(target['id'], preserve_current=False, target_running=True)
except SaveBusyError:
    pass
else:
    raise AssertionError('provider busy veto did not block hot restore')
assert (save_root / 'Profile1.sav').read_bytes() == b'busy-current'

(save_root / 'Profile1.sav').write_bytes(b'race-current')
race_calls = 0
def racing_resolver():
    global race_calls
    race_calls += 1
    rows = resolved()
    if race_calls == 2:
        (save_root / 'Profile1.sav').write_bytes(b'race-changed')
    return rows
racing = SaveRestoreTransaction(store, spec, racing_resolver)
try:
    racing.restore(target['id'], preserve_current=False, target_running=True)
except SaveBusyError:
    pass
else:
    raise AssertionError('preflight race did not report busy')
assert (save_root / 'Profile1.sav').read_bytes() == b'race-changed'

(save_root / 'Profile1.sav').write_bytes(b'continuity-current')
real_replace = restore_module.os.replace
root_gap = []
def guarding_replace(source, destination):
    existed = save_root.exists()
    result = real_replace(source, destination)
    if existed and not save_root.exists():
        root_gap.append((source, destination))
    return result
restore_module.os.replace = guarding_replace
try:
    transaction.restore(target['id'], preserve_current=False, target_running=False)
finally:
    restore_module.os.replace = real_replace
assert root_gap == [] and save_root.is_dir()

(save_root / 'Profile1.sav').write_bytes(b'rollback-profile')
(save_root / 'restored-only.sav').write_bytes(b'rollback-restored-only')
(save_root / 'obsolete.sav').write_bytes(b'rollback-obsolete')
replace_calls = 0
def fail_second_target_replace(source, destination):
    global replace_calls
    destination = Path(destination)
    if save_root in destination.parents:
        replace_calls += 1
        if replace_calls == 2:
            raise OSError('forced target replace failure')
    return real_replace(source, destination)
restore_module.os.replace = fail_second_target_replace
try:
    try:
        transaction.restore(target['id'], preserve_current=False, target_running=False)
    except SaveRestoreError:
        pass
    else:
        raise AssertionError('partial target install unexpectedly succeeded')
finally:
    restore_module.os.replace = real_replace
assert (save_root / 'Profile1.sav').read_bytes() == b'rollback-profile'
assert (save_root / 'restored-only.sav').read_bytes() == b'rollback-restored-only'
assert (save_root / 'obsolete.sav').read_bytes() == b'rollback-obsolete'

# SIGTERM is translated to KeyboardInterrupt by the backend server. Once restore
# mutation has started, that control-flow exception must still roll back the
# real save set before the worker is allowed to exit.
(save_root / 'Profile1.sav').write_bytes(b'interrupt-profile')
(save_root / 'restored-only.sav').write_bytes(b'interrupt-restored-only')
(save_root / 'obsolete.sav').write_bytes(b'interrupt-obsolete')
replace_calls = 0
def interrupt_second_target_replace(source, destination):
    global replace_calls
    destination = Path(destination)
    if save_root in destination.parents:
        replace_calls += 1
        if replace_calls == 2:
            raise KeyboardInterrupt()
    return real_replace(source, destination)
restore_module.os.replace = interrupt_second_target_replace
try:
    try:
        transaction.restore(target['id'], preserve_current=False, target_running=False)
    except KeyboardInterrupt:
        pass
    else:
        raise AssertionError('interrupted restore unexpectedly succeeded')
finally:
    restore_module.os.replace = real_replace
assert (save_root / 'Profile1.sav').read_bytes() == b'interrupt-profile'
assert (save_root / 'restored-only.sav').read_bytes() == b'interrupt-restored-only'
assert (save_root / 'obsolete.sav').read_bytes() == b'interrupt-obsolete'

(save_root / 'Profile1.sav').write_bytes(b'preserve-me')
(save_root / 'restored-only.sav').write_bytes(b'preserve-me-too')
(save_root / 'obsolete.sav').write_bytes(b'preserve-obsolete')
replace_calls = 0
def fail_target_then_rollback(source, destination):
    global replace_calls
    destination = Path(destination)
    if save_root in destination.parents:
        replace_calls += 1
        if replace_calls >= 2:
            raise OSError('forced target/rollback failure')
    return real_replace(source, destination)
restore_module.os.replace = fail_target_then_rollback
try:
    try:
        transaction.restore(target['id'], preserve_current=False, target_running=False)
    except SaveRollbackError as error:
        recovery_path = Path(error.recovery_path)
    else:
        raise AssertionError('double failure unexpectedly succeeded')
finally:
    restore_module.os.replace = real_replace
assert recovery_path.is_dir()
assert (recovery_path / 'files/main/Profile1.sav').read_bytes() == b'preserve-me'
assert (recovery_path / 'files/main/obsolete.sav').read_bytes() == b'preserve-obsolete'

print('core_save_restore_ok')
