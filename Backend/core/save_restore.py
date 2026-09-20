from pathlib import Path
import os
import shutil
import tempfile
import time

from .save_resolution import ResolvedSaveFile
from .save_snapshots import SaveSnapshotError, _safe_relative, _sha256


class SaveBusyError(RuntimeError):
    code = 'save_busy'


class SaveRestoreError(RuntimeError):
    code = 'restore_failed'


class SaveRollbackError(SaveRestoreError):
    code = 'rollback_failed'

    def __init__(self, message, recovery_path):
        super().__init__(message)
        self.recovery_path = str(recovery_path)


class SaveRestoreTransaction:
    def __init__(self, store, spec, resolver, busy_probe=None, snapshot_describer=None, target_running_probe=None):
        self.store = store
        self.resolver = resolver
        self.busy_probe = busy_probe
        self.snapshot_describer = snapshot_describer
        self.target_running_probe = target_running_probe
        self.roots = {root.id: Path(root.path).expanduser() for root in spec.roots}

    @staticmethod
    def _key(row):
        return row.root_id, row.relative_path

    def _raise_race(self, target_running, message):
        if target_running:
            raise SaveBusyError(message)
        raise SaveRestoreError(message)

    def _transaction_parent(self):
        root = self.store.ensure_storage_root()
        parent = root / 'transactions'
        if parent.is_symlink():
            raise SaveRestoreError('Save transaction storage path is unsafe.')
        parent.mkdir(parents=True, exist_ok=True)
        if parent.is_symlink() or not parent.is_dir():
            raise SaveRestoreError('Save transaction storage path is unsafe.')
        return parent

    def _ensure_cold_target_still_stopped(self, target_running):
        if not target_running and self.target_running_probe is not None and self.target_running_probe():
            raise SaveBusyError('Game started while preparing restore.')

    def _capture_rollback(self, target_running):
        self._ensure_cold_target_still_stopped(target_running)
        current = list(self.resolver())
        if target_running and self.busy_probe is not None and self.busy_probe(tuple(current)):
            raise SaveBusyError('Save files are currently busy.')

        rollback = Path(tempfile.mkdtemp(prefix='.rollback-', dir=str(self._transaction_parent())))
        rollback_rows = []
        hashes = {}
        try:
            for row in current:
                before = _sha256(row.source_path)
                destination = rollback / 'files' / row.root_id / _safe_relative(row.relative_path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(row.source_path, destination)
                if _sha256(destination) != before or _sha256(row.source_path) != before:
                    self._raise_race(target_running, 'Save changed while preparing restore.')
                key = self._key(row)
                hashes[key] = before
                rollback_rows.append(ResolvedSaveFile(row.root_id, row.relative_path, destination))

            after = list(self.resolver())
            if [self._key(row) for row in after] != [self._key(row) for row in current]:
                self._raise_race(target_running, 'Save file set changed while preparing restore.')
            for row in after:
                if _sha256(row.source_path) != hashes[self._key(row)]:
                    self._raise_race(target_running, 'Save changed while preparing restore.')
            self._ensure_cold_target_still_stopped(target_running)
            return rollback, rollback_rows, hashes
        except Exception:
            shutil.rmtree(rollback, ignore_errors=True)
            raise

    def _verify_state(self, expected_hashes):
        current = list(self.resolver())
        if [self._key(row) for row in current] != sorted(expected_hashes):
            return False
        for row in current:
            if _sha256(row.source_path) != expected_hashes[self._key(row)]:
                return False
        return True

    def _destination(self, root_id, relative):
        root = self.roots.get(root_id)
        if root is None:
            raise SaveRestoreError('Snapshot references an unknown save root.')
        if root.is_symlink():
            raise SaveRestoreError('Save root cannot be a symbolic link.')
        root.mkdir(parents=True, exist_ok=True)
        if root.is_symlink() or not root.is_dir():
            raise SaveRestoreError('Save root is unsafe.')
        relative_path = _safe_relative(relative)
        destination = root / relative_path
        if destination.is_symlink():
            raise SaveRestoreError('Save destination cannot be a symbolic link.')
        try:
            destination.resolve(strict=False).relative_to(root.resolve(strict=False))
        except ValueError as error:
            raise SaveRestoreError('Save destination escaped its declared root.') from error
        return destination

    def _replace_file(self, source, destination, digest):
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix='.trainer-save-', dir=str(destination.parent))
        os.close(fd)
        temporary = Path(temp_name)
        try:
            shutil.copy2(source, temporary)
            if _sha256(temporary) != digest:
                raise SaveRestoreError('Staged save file failed integrity verification.')
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    def _target_entries(self, verified):
        root = verified['root']
        entries = []
        hashes = {}
        for item in verified['manifest']['files']:
            key = (item['rootId'], item['relativePath'])
            if key[0] not in self.roots:
                raise SaveRestoreError('Snapshot references an unknown save root.')
            source = root / 'files' / key[0] / _safe_relative(key[1])
            entries.append((key, source, item['sha256']))
            hashes[key] = item['sha256']
        return entries, hashes

    def _install_entries(self, entries):
        for (root_id, relative), source, digest in entries:
            self._replace_file(source, self._destination(root_id, relative), digest)

    def _delete_keys(self, keys):
        for root_id, relative in keys:
            destination = self._destination(root_id, relative)
            if destination.is_symlink():
                raise SaveRestoreError('Save deletion target cannot be a symbolic link.')
            if destination.exists():
                if not destination.is_file():
                    raise SaveRestoreError('Save deletion target is not a regular file.')
                destination.unlink()

    def _rollback_entries(self, rollback_rows, hashes):
        entries = []
        for row in rollback_rows:
            key = self._key(row)
            entries.append((key, row.source_path, hashes[key]))
        return entries

    def restore(self, snapshot_id, preserve_current=False, target_running=False):
        if type(preserve_current) is not bool or type(target_running) is not bool:
            raise ValueError('Restore options must be boolean.')
        verified = self.store.load_verified_snapshot(snapshot_id)
        target_entries, target_hashes = self._target_entries(verified)
        rollback_root, rollback_rows, baseline_hashes = self._capture_rollback(target_running)
        previous_snapshot_id = None
        mutation_started = False
        cleanup_rollback = True

        try:
            if preserve_current and rollback_rows:
                previous = self.store.create_snapshot(
                    lambda: list(rollback_rows),
                    hot=target_running,
                    describe=self.snapshot_describer,
                )
                previous_snapshot_id = previous['id']

            if not self._verify_state(baseline_hashes):
                self._raise_race(target_running, 'Save changed before restore could begin.')
            self._ensure_cold_target_still_stopped(target_running)

            mutation_started = True
            self._install_entries(target_entries)
            self._delete_keys(set(baseline_hashes) - set(target_hashes))

            if not self._verify_state(target_hashes):
                raise SaveRestoreError('Restored save set failed verification.')
            if target_running:
                time.sleep(0.05)
                if not self._verify_state(target_hashes):
                    raise SaveRestoreError('Game rewrote save files immediately after hot restore.')

            return {
                'restored': True,
                'snapshotId': snapshot_id,
                'previousSnapshotId': previous_snapshot_id,
                'fileCount': len(target_entries),
                'hot': target_running,
            }
        except BaseException as error:
            if not mutation_started:
                if not isinstance(error, Exception):
                    raise
                if isinstance(error, (SaveBusyError, SaveSnapshotError, SaveRestoreError, ValueError)):
                    raise
                raise SaveRestoreError('Restore failed before mutation.') from error

            # The backend translates SIGTERM into KeyboardInterrupt. Once real
            # save mutation has started, every exit path must attempt rollback
            # before the worker is allowed to terminate. Keep the recovery copy
            # until rollback has both completed and verified.
            cleanup_rollback = False
            try:
                self._install_entries(self._rollback_entries(rollback_rows, baseline_hashes))
                self._delete_keys(set(target_hashes) - set(baseline_hashes))
                if not self._verify_state(baseline_hashes):
                    raise SaveRestoreError('Rollback verification failed.')
            except BaseException as rollback_error:
                if not isinstance(rollback_error, Exception):
                    raise
                raise SaveRollbackError(
                    'Restore failed and rollback could not be completed; recovery copy was preserved.',
                    rollback_root,
                ) from error
            cleanup_rollback = True
            if not isinstance(error, Exception):
                raise
            raise SaveRestoreError('Restore failed; previous saves were rolled back.') from error
        finally:
            if cleanup_rollback:
                shutil.rmtree(rollback_root, ignore_errors=True)
