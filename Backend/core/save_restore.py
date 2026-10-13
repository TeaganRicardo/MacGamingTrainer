import errno
import hashlib
import os
import shutil
import stat
import tempfile
import time
import uuid
from contextlib import ExitStack
from pathlib import Path

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


class SaveRestorePreparationInterrupted(KeyboardInterrupt):
    """Rollback capture was interrupted before any save mutation began."""


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

    def _capture_rollback(self, target_running, require_idle=False):
        self._ensure_cold_target_still_stopped(target_running)
        current = list(self.resolver())
        if (
            self.busy_probe is not None
            and (target_running or require_idle)
            and self.busy_probe(tuple(current))
        ):
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
        except BaseException as error:
            shutil.rmtree(rollback, ignore_errors=True)
            if isinstance(error, KeyboardInterrupt):
                raise SaveRestorePreparationInterrupted() from error
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

    def _replace_file(self, source, destination, digest, *, directory_fd):
        temporary = '.trainer-save-' + uuid.uuid4().hex
        fd = os.open(temporary, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=directory_fd)
        try:
            with os.fdopen(fd, 'w+b') as staged, Path(source).open('rb') as original:
                shutil.copyfileobj(original, staged)
                staged.flush()
                staged.seek(0)
                actual = hashlib.sha256()
                for chunk in iter(lambda: staged.read(1024 * 1024), b''):
                    actual.update(chunk)
                if actual.hexdigest() != digest:
                    raise SaveRestoreError('Staged save file failed integrity verification.')
                metadata = os.fstat(original.fileno())
                os.fchmod(staged.fileno(), stat.S_IMODE(metadata.st_mode))
                os.utime(staged.fileno(), ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
                if hasattr(os, 'listxattr'):
                    # Match copy2's optional extended-metadata behavior while
                    # keeping both endpoints bound to open files.
                    ignored = {errno.ENOTSUP, errno.ENODATA, errno.EINVAL, errno.EPERM}
                    try:
                        for name in os.listxattr(original.fileno()):
                            os.setxattr(staged.fileno(), name, os.getxattr(original.fileno(), name))
                    except OSError as error:
                        if error.errno not in ignored:
                            raise
                if hasattr(os, 'fchflags'):
                    os.fchflags(staged.fileno(), metadata.st_flags)
                os.fsync(staged.fileno())
            # Both names are relative to the captured directory descriptor.
            # Renaming or redirecting its pathname cannot redirect mutation.
            os.replace(temporary, destination.name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
            os.fsync(directory_fd)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory_fd)
            except FileNotFoundError:
                pass

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

    def _capture_destinations(self, keys, stack):
        destinations = {}
        for key in sorted(keys):
            destination = self._destination(*key).resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            stack.callback(os.close, descriptor)
            destinations[key] = (destination, descriptor)
        self._verify_destinations(destinations)
        return destinations

    def _verify_destinations(self, destinations):
        for key, (destination, descriptor) in destinations.items():
            current = self._destination(*key).resolve()
            before, now = os.fstat(descriptor), current.parent.stat()
            if current != destination or (before.st_dev, before.st_ino) != (now.st_dev, now.st_ino):
                raise SaveRestoreError('Save transaction physical directory changed.')

    def _install_entries(self, entries, destinations):
        for key, source, digest in entries:
            destination, descriptor = destinations[key]
            self._replace_file(source, destination, digest, directory_fd=descriptor)

    def _delete_keys(self, keys, destinations):
        for key in keys:
            destination, descriptor = destinations[key]
            try:
                metadata = os.stat(destination.name, dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise SaveRestoreError('Save deletion target is not a regular file.')
            os.unlink(destination.name, dir_fd=descriptor)
            os.fsync(descriptor)

    def _rollback_entries(self, rollback_rows, hashes):
        entries = []
        for row in rollback_rows:
            key = self._key(row)
            entries.append((key, row.source_path, hashes[key]))
        return entries

    def _apply_captured(
        self,
        rollback_root,
        rollback_rows,
        baseline_hashes,
        target_entries,
        target_hashes,
        *,
        preserve_current,
        target_running,
        success,
        operation_name,
        post_install_verify=None,
        require_idle=False,
        expected_paths=None,
    ):
        previous_snapshot_id = None
        mutation_started = False
        cleanup_rollback = True
        destination_stack = ExitStack()

        try:
            destinations = self._capture_destinations(set(baseline_hashes) | set(target_hashes), destination_stack)
            if preserve_current and rollback_rows:
                previous = self.store.create_snapshot(
                    lambda: list(rollback_rows),
                    hot=target_running,
                    describe=self.snapshot_describer,
                )
                previous_snapshot_id = previous['id']

            if not self._verify_state(baseline_hashes):
                self._raise_race(target_running, 'Save changed before mutation could begin.')
            self._ensure_cold_target_still_stopped(target_running)
            if require_idle and self.busy_probe is not None:
                current = list(self.resolver())
                if self.busy_probe(tuple(current)):
                    raise SaveBusyError('Save files are currently busy.')
                if not self._verify_state(baseline_hashes):
                    self._raise_race(False, 'Save changed before mutation could begin.')
                self._ensure_cold_target_still_stopped(target_running)

            self._verify_target_paths(expected_paths)
            self._verify_destinations(destinations)
            mutation_started = True
            self._install_entries(target_entries, destinations)
            self._delete_keys(set(baseline_hashes) - set(target_hashes), destinations)
            self._verify_destinations(destinations)

            if not self._verify_state(target_hashes):
                raise SaveRestoreError('{} save set failed verification.'.format(operation_name))
            if post_install_verify is not None:
                post_install_verify()
                if not self._verify_state(target_hashes):
                    raise SaveRestoreError(
                        '{} save set changed during post-install validation.'.format(
                            operation_name
                        )
                    )
            if target_running:
                time.sleep(0.05)
                if not self._verify_state(target_hashes):
                    raise SaveRestoreError('Game rewrote save files immediately after hot restore.')

            return {
                **success,
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
                raise SaveRestoreError('{} failed before mutation.'.format(operation_name)) from error

            # Once real save mutation starts, every exit path attempts rollback
            # before returning or allowing process termination. Keep the
            # recovery copy until rollback has completed and verified.
            cleanup_rollback = False
            try:
                self._install_entries(self._rollback_entries(rollback_rows, baseline_hashes), destinations)
                self._delete_keys(set(target_hashes) - set(baseline_hashes), destinations)
                self._verify_destinations(destinations)
                if not self._verify_state(baseline_hashes):
                    raise SaveRestoreError('Rollback verification failed.')
            except BaseException as rollback_error:
                if not isinstance(rollback_error, Exception):
                    raise
                raise SaveRollbackError(
                    '{} failed and rollback could not be completed; recovery copy was preserved.'.format(
                        operation_name
                    ),
                    rollback_root,
                ) from error
            cleanup_rollback = True
            if not isinstance(error, Exception):
                raise
            raise SaveRestoreError(
                '{} failed; previous saves were rolled back.'.format(operation_name)
            ) from error
        finally:
            destination_stack.close()
            if cleanup_rollback:
                shutil.rmtree(rollback_root, ignore_errors=True)

    def _replacement_entries(self, replacements):
        if not isinstance(replacements, (list, tuple)) or not replacements:
            raise ValueError('Save replacement set must not be empty.')
        entries = []
        seen = set()
        for row in replacements:
            if not isinstance(row, ResolvedSaveFile):
                raise ValueError('Save replacement rows must be resolved save files.')
            key = self._key(row)
            if key in seen:
                raise ValueError('Save replacement set contains duplicate targets.')
            seen.add(key)
            source = Path(row.source_path)
            if source.is_symlink() or not source.is_file():
                raise SaveRestoreError('Save replacement source is missing or unsafe.')
            entries.append((key, source, _sha256(source)))
        return entries

    def _verify_target_paths(self, expected_paths):
        for (root_id, relative), expected in (expected_paths or {}).items():
            if self._destination(root_id, relative).resolve() != expected:
                raise SaveRestoreError('Save replacement physical target changed.')

    def replace_files(self, replacements, expected_hashes=None, post_install_verify=None, *, expected_paths=None):
        if post_install_verify is not None and not callable(post_install_verify):
            raise ValueError('Save replacement verifier must be callable.')
        entries = self._replacement_entries(replacements)
        replacement_keys = {key for key, _source, _digest in entries}
        if expected_hashes is not None and (
            not isinstance(expected_hashes, dict)
            or set(expected_hashes) != replacement_keys
        ):
            raise ValueError('Expected save hashes must cover every replacement target exactly.')
        if expected_paths is not None:
            if not isinstance(expected_paths, dict) or set(expected_paths) != replacement_keys:
                raise ValueError('Expected save paths must cover every replacement target exactly.')
            expected_paths = {key: Path(path) for key, path in expected_paths.items()}
            if any(not path.is_absolute() for path in expected_paths.values()):
                raise ValueError('Expected save paths must be captured absolute identities.')
            self._verify_target_paths(expected_paths)

        rollback_root, rollback_rows, baseline_hashes = self._capture_rollback(
            False,
            require_idle=True,
        )
        try:
            for key in replacement_keys:
                if key not in baseline_hashes:
                    raise SaveRestoreError('Save replacement target is not part of the current save set.')
                if (
                    expected_hashes is not None
                    and expected_hashes[key] != baseline_hashes[key]
                ):
                    raise SaveRestoreError('Save changed since the edit was prepared.')
            target_hashes = dict(baseline_hashes)
            for key, _source, digest in entries:
                target_hashes[key] = digest
        except BaseException:
            shutil.rmtree(rollback_root, ignore_errors=True)
            raise

        return self._apply_captured(
            rollback_root,
            rollback_rows,
            baseline_hashes,
            entries,
            target_hashes,
            preserve_current=True,
            target_running=False,
            success={'replaced': True},
            operation_name='Save replacement',
            post_install_verify=post_install_verify,
            require_idle=True,
            expected_paths=expected_paths,
        )

    def restore(self, snapshot_id, preserve_current=False, target_running=False):
        if type(preserve_current) is not bool or type(target_running) is not bool:
            raise ValueError('Restore options must be boolean.')
        verified = self.store.load_verified_snapshot(snapshot_id)
        target_entries, target_hashes = self._target_entries(verified)
        rollback_root, rollback_rows, baseline_hashes = self._capture_rollback(target_running)
        return self._apply_captured(
            rollback_root,
            rollback_rows,
            baseline_hashes,
            target_entries,
            target_hashes,
            preserve_current=preserve_current,
            target_running=target_running,
            success={'restored': True, 'snapshotId': snapshot_id},
            operation_name='Restore',
        )
