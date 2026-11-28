import ctypes
import errno
import hashlib
import json
import logging
import os
import shutil
import stat
import sys
import tempfile
import time
import uuid
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .errors import CoreSaveError
from .persistence import atomic_write_text, fsync_directory
from .save_resolution import HOT_SAVE_HOLDING_PREFIX, ResolvedSaveFile
from .save_metadata import copy_owned_save_file, copy_save_metadata, remove_owned_save_tree
from .save_snapshots import SaveSnapshotError, _safe_relative, _sha256


def _rename_hot(source, destination, directory_fd, *, exchange=False):
    # Both variants leave an existing destination intact, either by exchanging
    # it with source or by refusing to rename. A normal rename may discard it.
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == 'darwin':
        rename = libc.renameatx_np
        flags = 2 if exchange else 4  # RENAME_SWAP / RENAME_EXCL
    else:
        rename = libc.renameat2
        flags = 2 if exchange else 1  # RENAME_EXCHANGE / RENAME_NOREPLACE
    rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    rename.restype = ctypes.c_int
    if rename(directory_fd, os.fsencode(source), directory_fd, os.fsencode(destination), flags) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), destination)


def _hot_identity_and_hash(name, directory_fd):
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    except FileNotFoundError:
        return None, None
    with os.fdopen(descriptor, 'rb') as handle:
        metadata = os.fstat(handle.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise SaveRestoreError('Save mutation target is not a regular file.')
        digest = hashlib.sha256()
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
        return metadata.st_ino, digest.hexdigest()


class SaveBusyError(CoreSaveError):
    code = 'save_busy'
    presentation_key = 'host.save.error.busy'


class SaveRestoreError(CoreSaveError):
    code = 'restore_failed'
    presentation_key = 'host.save.error.restoreFailed'


class SaveRollbackError(SaveRestoreError):
    code = 'rollback_failed'
    presentation_key = 'host.save.error.rollbackFailed'

    def __init__(self, message, recovery_path):
        raw = '' if recovery_path is None else str(recovery_path)
        if not raw.strip():
            super().__init__(message, presentation_key='host.save.error.restoreFailed')
            return
        super().__init__(message, arguments=(raw,), recovery_path=raw)


class SaveRestorePreparationInterrupted(KeyboardInterrupt):
    """Rollback capture was interrupted before any save mutation began."""


@dataclass
class _HotSaveChange:
    destination: Path
    directory_fd: int
    before: str
    baseline_digest: Optional[str]
    installed_digest: Optional[str]
    installed_inode: Optional[int] = None

    @property
    def name(self):
        return self.destination.name

    def directory_is_current(self):
        captured = os.fstat(self.directory_fd)
        try:
            return os.path.samestat(captured, self.destination.parent.stat())
        except OSError:
            return False

    def verify_displaced(self):
        if self.baseline_digest is not None:
            _, digest = _hot_identity_and_hash(self.before, self.directory_fd)
            if digest != self.baseline_digest:
                raise SaveRestoreError('Game saved new data just before the hot save mutation.')

    def rollback(self, has_checkpoint):
        if not self.directory_is_current():
            raise SaveRestoreError('The save directory changed before hot rollback.')
        # Check whether the mutation ran before an interruption. For a
        # replacement, the incoming inode still occupies the holding name
        # until the exchange. A deletion has no staged incoming inode.
        before_inode, before_digest = _hot_identity_and_hash(self.before, self.directory_fd)
        if before_inode == self.installed_inode:
            return False, None

        live_inode, live_digest = _hot_identity_and_hash(self.name, self.directory_fd)
        if (live_inode, live_digest) != (self.installed_inode, self.installed_digest):
            # An independent writer has already published another version.
            # Leave it in place. A displaced version that lacks a verified
            # pre-write copy must remain available too.
            if self.baseline_digest is not None:
                if before_digest != self.baseline_digest:
                    raise SaveRestoreError('Two independently written hot save versions were preserved.')
                if not has_checkpoint:
                    raise SaveRestoreError('A new live save prevented rollback; the original save was preserved.')
            return False, None

        if self.baseline_digest is None:
            _rename_hot(self.name, self.before, self.directory_fd)
        else:
            _rename_hot(self.before, self.name, self.directory_fd, exchange=self.installed_digest is not None)
        os.fsync(self.directory_fd)
        if self.installed_inode is not None:
            # A writer can publish after the read above and before rollback
            # itself. The inverse rename retains its exact bytes in this case.
            peer = _hot_identity_and_hash(self.before, self.directory_fd)
            if peer != (self.installed_inode, self.installed_digest):
                if self.baseline_digest is None and self.directory_is_current():
                    # Undo a removal of a game-created file when the live
                    # name is still free. Another save keeps both versions.
                    try:
                        _rename_hot(self.before, self.name, self.directory_fd)
                    except FileExistsError:
                        pass
                    else:
                        os.fsync(self.directory_fd)
                        return False, None
                raise SaveRestoreError('Game saved concurrently with rollback; its bytes were preserved.')
        return True, before_digest

    def copy_recovery_file(self, name, destination):
        try:
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.directory_fd)
        except FileNotFoundError:
            return False
        with os.fdopen(descriptor, 'rb') as original:
            if not stat.S_ISREG(os.fstat(original.fileno()).st_mode):
                return False
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open('xb') as copy:
                shutil.copyfileobj(original, copy)
                copy.flush()
                copy_save_metadata(original.fileno(), copy.fileno())
                os.fsync(copy.fileno())
        fsync_directory(destination.parent)
        return True


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
        if self.busy_probe is not None and (target_running or require_idle) and self.busy_probe(tuple(current)):
            raise SaveBusyError('Save files are currently busy.')

        rollback = Path(tempfile.mkdtemp(prefix='.rollback-', dir=str(self._transaction_parent())))
        rollback_rows = []
        hashes = {}
        try:
            for row in current:
                before = _sha256(row.source_path)
                destination = rollback / 'files' / row.root_id / _safe_relative(row.relative_path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                copy_owned_save_file(row.source_path, destination)
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
            try:
                remove_owned_save_tree(rollback)
            except OSError:
                logging.exception('Rollback preparation cleanup failed: %s', rollback)
            if isinstance(error, KeyboardInterrupt):
                raise SaveRestorePreparationInterrupted() from error
            raise

    def _physical_target_path(self, key):
        root_id, relative = key
        root = self.roots.get(root_id)
        if root is None:
            raise SaveRestoreError('Save transaction references an unknown root.')
        return (root.expanduser() / _safe_relative(relative)).resolve(strict=False)

    @staticmethod
    def _target_matches_baseline(path, digest):
        if path.is_symlink():
            return False
        if digest is None:
            return not path.exists()
        return path.is_file() and _sha256(path) == digest

    def _unresolved_recovery_targets(self, *, exclude_root=None):
        parent = self._transaction_parent()
        unresolved = []
        excluded = Path(exclude_root).resolve(strict=False) if exclude_root is not None else None
        for recovery_root in sorted(parent.glob('.rollback-*')):
            if excluded is not None and recovery_root.resolve(strict=False) == excluded:
                continue
            if recovery_root.is_symlink() or not recovery_root.is_dir():
                continue
            marker = recovery_root / 'unresolved-targets.json'
            if marker.is_symlink():
                unresolved.append((None, recovery_root))
                continue
            if marker.is_file():
                try:
                    payload = json.loads(marker.read_text(encoding='utf-8'))
                    if payload.get('schemaVersion') != 1 or not isinstance(payload.get('targets'), list):
                        raise ValueError('invalid unresolved target marker')
                    entries = payload['targets']
                    resolved_changed = False
                    for entry in entries:
                        if not isinstance(entry, dict) or type(entry.get('resolved', False)) is not bool:
                            raise ValueError('invalid unresolved target entry')
                        if entry.get('resolved') is True:
                            continue
                        path_text, digest = entry.get('path'), entry.get('sha256')
                        if not isinstance(path_text, str) or not Path(path_text).is_absolute():
                            raise ValueError('invalid unresolved target path')
                        if digest is not None and (
                            not isinstance(digest, str)
                            or len(digest) != 64
                            or any(character not in '0123456789abcdef' for character in digest)
                        ):
                            raise ValueError('invalid unresolved target digest')
                        path = Path(path_text)
                        if self._target_matches_baseline(path, digest):
                            entry['resolved'] = True
                            resolved_changed = True
                        else:
                            unresolved.append((path, recovery_root))
                    if resolved_changed:
                        atomic_write_text(
                            marker,
                            json.dumps(payload, ensure_ascii=False, allow_nan=False),
                        )
                except (OSError, ValueError, TypeError, AttributeError):
                    unresolved.append((None, recovery_root))
                continue

            # Migrate older full-set recovery copies before a later edit can
            # make a restored target differ from its captured baseline again.
            files_root = recovery_root / 'files'
            try:
                if files_root.is_symlink() or not files_root.is_dir():
                    unresolved.append((None, recovery_root))
                    continue
                baseline = {}
                for root_dir in files_root.iterdir():
                    if root_dir.is_symlink() or not root_dir.is_dir() or root_dir.name not in self.roots:
                        raise ValueError('invalid legacy recovery root')
                    for backup in root_dir.rglob('*'):
                        if backup.is_symlink():
                            raise ValueError('symlink in legacy recovery copy')
                        if not backup.is_file():
                            continue
                        relative = backup.relative_to(root_dir).as_posix()
                        key = (root_dir.name, relative)
                        baseline[key] = _sha256(backup)
                current = {self._key(row): None for row in self.resolver()}
                payload = self._target_marker(baseline, current)
                for entry in payload['targets']:
                    path = Path(entry['path'])
                    entry['resolved'] = self._target_matches_baseline(path, entry['sha256'])
                    if not entry['resolved']:
                        unresolved.append((path, recovery_root))
                atomic_write_text(marker, json.dumps(payload, ensure_ascii=False, allow_nan=False))
            except (OSError, ValueError, SaveRestoreError):
                unresolved.append((None, recovery_root))
        return unresolved

    def has_unresolved_recovery(self):
        return bool(self._unresolved_recovery_targets())

    def _require_targets_recovered(self, keys, *, exclude_root=None):
        requested = {self._physical_target_path(key) for key in keys}
        for unresolved_path, recovery_root in self._unresolved_recovery_targets(exclude_root=exclude_root):
            if unresolved_path is None or unresolved_path in requested:
                raise SaveRollbackError(
                    'A previous Save Editor rollback remains unresolved for this physical target.',
                    recovery_root,
                )

    def _target_marker(self, baseline_hashes, target_hashes):
        keys = set(baseline_hashes) | set(target_hashes)
        targets = []
        for key in sorted(keys):
            targets.append(
                {
                    'rootId': key[0],
                    'relativePath': key[1],
                    'path': str(self._physical_target_path(key)),
                    'sha256': baseline_hashes.get(key),
                    'resolved': False,
                }
            )
        return {'schemaVersion': 1, 'targets': targets}

    @staticmethod
    def _write_target_marker(rollback_root, payload):
        atomic_write_text(
            Path(rollback_root) / 'unresolved-targets.json',
            json.dumps(payload, ensure_ascii=False, allow_nan=False),
        )

    def _current_files(self, owned_keys=None):
        current = list(self.resolver())
        if owned_keys is not None:
            current = [row for row in current if self._key(row) in owned_keys]
        return current

    def _verify_state(self, expected_hashes, owned_keys=None):
        current = self._current_files(owned_keys)
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

    def _stage_file(self, source, temporary, digest, directory_fd, *, mode=None):
        descriptor = os.open(temporary, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=directory_fd)
        try:
            with os.fdopen(descriptor, 'w+b') as staged, Path(source).open('rb') as original:
                shutil.copyfileobj(original, staged)
                staged.flush()
                staged.seek(0)
                actual = hashlib.sha256()
                for chunk in iter(lambda: staged.read(1024 * 1024), b''):
                    actual.update(chunk)
                if actual.hexdigest() != digest:
                    raise SaveRestoreError('Staged save file failed integrity verification.')
                copy_save_metadata(original.fileno(), staged.fileno(), mode=mode)
                os.fsync(staged.fileno())
                return os.fstat(staged.fileno()).st_ino
        except BaseException:
            os.unlink(temporary, dir_fd=directory_fd)
            raise

    def _replace_file(self, source, destination, digest, *, directory_fd, progress=None, key=None, mode=None):
        temporary = '.trainer-save-' + uuid.uuid4().hex
        self._stage_file(source, temporary, digest, directory_fd, mode=mode)
        try:
            # Both names are relative to the captured directory descriptor.
            # Renaming or redirecting its pathname cannot redirect mutation.
            if progress is not None:
                progress.add(key)
            try:
                os.replace(temporary, destination.name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
            except OSError:
                if progress is not None:
                    progress.discard(key)
                raise
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
        directories = {}
        for key in sorted(keys):
            destination = self._destination(*key).resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            descriptor = directories.get(destination.parent)
            if descriptor is None:
                descriptor = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                stack.callback(os.close, descriptor)
                directories[destination.parent] = descriptor
            destinations[key] = (destination, descriptor)
        self._verify_destinations(destinations)
        return destinations

    def _verify_destinations(self, destinations):
        for key, (destination, descriptor) in destinations.items():
            current = self._destination(*key).resolve()
            before, now = os.fstat(descriptor), current.parent.stat()
            if current != destination or (before.st_dev, before.st_ino) != (now.st_dev, now.st_ino):
                raise SaveRestoreError('Save transaction physical directory changed.')

    def _install_entries(self, entries, destinations, progress=None, *, modes=None):
        for key, source, digest in entries:
            destination, descriptor = destinations[key]
            self._replace_file(
                source,
                destination,
                digest,
                directory_fd=descriptor,
                progress=progress,
                key=key,
                mode=modes.get(key) if modes is not None else None,
            )

    def _delete_keys(self, keys, destinations, progress=None):
        for key in keys:
            destination, descriptor = destinations[key]
            try:
                metadata = os.stat(destination.name, dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise SaveRestoreError('Save deletion target is not a regular file.')
            if progress is not None:
                progress.add(key)
            try:
                os.unlink(destination.name, dir_fd=descriptor)
            except OSError:
                if progress is not None:
                    progress.discard(key)
                raise
            os.fsync(descriptor)

    def _hot_changes(self, destinations, baseline_hashes, target_hashes):
        changes = {}
        for key, (destination, directory_fd) in destinations.items():
            temporary = HOT_SAVE_HOLDING_PREFIX + uuid.uuid4().hex
            changes[key] = _HotSaveChange(
                destination,
                directory_fd,
                temporary,
                baseline_hashes.get(key),
                target_hashes.get(key),
            )
        return changes

    @staticmethod
    def _write_hot_recovery_note(rollback_root, changes, reason, recovered=None):
        files = []
        for key, change in changes.items():
            file = {
                'target': str(change.destination),
                'holdingPath': str(change.destination.with_name(change.before)),
            }
            if recovered and key in recovered:
                file.update(recovered[key])
            files.append(file)
        atomic_write_text(
            rollback_root / 'hot-files.json',
            json.dumps({'reason': reason, 'files': files}, ensure_ascii=False),
        )

    @staticmethod
    def _preserve_redirected_hot_files(rollback_root, changes, mutated):
        recovered = {}
        for key in mutated:
            change = changes[key]
            if change.directory_is_current():
                continue
            # The move can happen during the inverse exchange. Read both
            # entries through the captured directory to retain either result.
            for name, subfolder, evidence_key in (
                (change.before, 'hot-displaced', 'recoveryCopyPath'),
                (change.name, 'hot-relocated-live', 'relocatedLiveCopyPath'),
            ):
                destination = rollback_root / subfolder / key[0] / _safe_relative(key[1])
                try:
                    if change.copy_recovery_file(name, destination):
                        recovered.setdefault(key, {})[evidence_key] = str(destination)
                except OSError:
                    logging.exception('Relocated hot save could not be copied: %s', destination)
        return recovered

    def _install_hot_changes(self, changes, target_entries, progress, *, modes):
        sources = {key: source for key, source, _ in target_entries}
        keys = list(sources) + sorted(changes.keys() - sources.keys())
        for key in keys:
            change = changes[key]
            if change.installed_digest is not None:
                change.installed_inode = self._stage_file(
                    sources[key], change.before, change.installed_digest, change.directory_fd, mode=modes.get(key)
                )
            progress.add(key)
            try:
                if change.installed_digest is None:
                    _rename_hot(change.name, change.before, change.directory_fd)
                else:
                    _rename_hot(
                        change.before,
                        change.name,
                        change.directory_fd,
                        exchange=change.baseline_digest is not None,
                    )
            except OSError as error:
                progress.remove(key)
                if error.errno == errno.ENOTSUP and not progress:
                    raise SaveBusyError('The filesystem cannot safely mutate saves while the game runs.') from error
                raise
            os.fsync(change.directory_fd)
            change.verify_displaced()

    @staticmethod
    def _clean_hot_changes(changes):
        for change in changes.values():
            try:
                os.unlink(change.before, dir_fd=change.directory_fd)
            except FileNotFoundError:
                continue
            os.fsync(change.directory_fd)

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
        owned_keys=None,
        snapshot_origin="preRestore",
    ):
        # Recovery evidence can preserve the whole save set. Mutation authority
        # is narrower for a selected replacement: unrelated live files must not
        # participate in its validation, deletion, or rollback.
        snapshot_rows = rollback_rows
        if owned_keys is not None:
            rollback_rows = [row for row in rollback_rows if self._key(row) in owned_keys]
            baseline_hashes = {key: digest for key, digest in baseline_hashes.items() if key in owned_keys}
            target_hashes = {key: digest for key, digest in target_hashes.items() if key in owned_keys}
        previous_snapshot_id = None
        mutated = set()
        cleanup_rollback = True
        hot_changes = {}
        destination_stack = ExitStack()
        result = None

        try:
            # Editor output supplies replacement bytes. The verified pre-write
            # copy supplies the edited file's mode. A Restore uses snapshot metadata.
            modes = (
                {self._key(row): stat.S_IMODE(row.source_path.stat().st_mode) for row in rollback_rows}
                if owned_keys is not None
                else {}
            )
            self._require_targets_recovered(set(baseline_hashes) | set(target_hashes), exclude_root=rollback_root)
            destinations = self._capture_destinations(set(baseline_hashes) | set(target_hashes), destination_stack)
            if preserve_current and snapshot_rows:
                previous = self.store.create_snapshot(
                    lambda: list(snapshot_rows),
                    hot=target_running,
                    describe=self.snapshot_describer,
                    origin=snapshot_origin,
                )
                previous_snapshot_id = previous['id']

            if not self._verify_state(baseline_hashes, owned_keys):
                self._raise_race(target_running, 'Save changed before mutation could begin.')
            self._ensure_cold_target_still_stopped(target_running)
            if require_idle and self.busy_probe is not None:
                current = list(self.resolver())
                if self.busy_probe(tuple(current)):
                    raise SaveBusyError('Save files are currently busy.')
                if not self._verify_state(baseline_hashes, owned_keys):
                    self._raise_race(target_running, 'Save changed before mutation could begin.')
                self._ensure_cold_target_still_stopped(target_running)

            self._verify_target_paths(expected_paths)
            self._verify_destinations(destinations)
            recovery_marker = self._target_marker(baseline_hashes, target_hashes)
            self._write_target_marker(rollback_root, recovery_marker)
            if target_running:
                hot_changes = self._hot_changes(destinations, baseline_hashes, target_hashes)
                # Keep the names of the exact inodes reachable if this process
                # exits between the atomic operation and rollback.
                self._write_hot_recovery_note(
                    rollback_root,
                    hot_changes,
                    'An interrupted hot transaction may leave staged or displaced save data at these holding paths.',
                )
                fsync_directory(rollback_root.parent)
                self._install_hot_changes(hot_changes, target_entries, mutated, modes=modes)
            else:
                self._install_entries(target_entries, destinations, progress=mutated, modes=modes)
                self._delete_keys(set(baseline_hashes) - set(target_hashes), destinations, progress=mutated)
            self._verify_destinations(destinations)

            if not self._verify_state(target_hashes, owned_keys):
                raise SaveRestoreError('{} save set failed verification.'.format(operation_name))
            if post_install_verify is not None:
                post_install_verify()
                if not self._verify_state(target_hashes, owned_keys):
                    raise SaveRestoreError('{} save set changed during post-install validation.'.format(operation_name))
            if target_running:
                time.sleep(0.05)
                if not self._verify_state(target_hashes, owned_keys):
                    raise SaveRestoreError('Game rewrote save files immediately after hot restore.')
                for change in hot_changes.values():
                    change.verify_displaced()

            self._verify_destinations(destinations)
            result = {
                **success,
                'previousSnapshotId': previous_snapshot_id,
                'fileCount': len(target_entries),
                'hot': target_running,
            }
            if previous_snapshot_id and previous.get('namingWarning'):
                result['namingWarning'] = previous['namingWarning']
            return result
        except BaseException as error:
            if not mutated:
                if isinstance(error, KeyboardInterrupt) and not isinstance(error, SaveRestorePreparationInterrupted):
                    raise SaveRestorePreparationInterrupted() from error
                if not isinstance(error, Exception):
                    raise
                if isinstance(error, (SaveBusyError, SaveSnapshotError, SaveRestoreError, ValueError)):
                    raise
                raise SaveRestoreError('{} failed before mutation.'.format(operation_name)) from error

            # Once real save mutation starts, every exit path attempts rollback
            # before returning or allowing process termination. Keep the
            # recovery copy until rollback has completed and verified.
            cleanup_rollback = False
            newer_live_preserved = False
            try:
                rollback_destinations = {key: destinations[key] for key in mutated}
                if target_running:
                    rollback_hashes = {}
                    hot_rollback_error = None
                    for key in sorted(mutated, reverse=True):
                        try:
                            restored, digest = hot_changes[key].rollback(previous_snapshot_id is not None)
                        except Exception as revert_error:
                            hot_rollback_error = revert_error
                            continue
                        if restored:
                            rollback_hashes[key] = digest
                        if not restored or digest != baseline_hashes.get(key):
                            newer_live_preserved = True
                    if hot_rollback_error is not None:
                        raise hot_rollback_error
                else:
                    rollback_hashes = {key: baseline_hashes.get(key) for key in mutated}
                    entries = []
                    for row in rollback_rows:
                        key = self._key(row)
                        if key in rollback_hashes:
                            entries.append((key, row.source_path, rollback_hashes[key]))
                    self._install_entries(entries, rollback_destinations)
                    self._delete_keys(mutated - baseline_hashes.keys(), rollback_destinations)
                self._verify_destinations(rollback_destinations)
                if not all(
                    self._target_matches_baseline(rollback_destinations[key][0], digest)
                    for key, digest in rollback_hashes.items()
                ):
                    raise SaveRestoreError('Rollback verification failed.')
                self._verify_destinations(rollback_destinations)
            except BaseException as rollback_error:
                # A process that reached rollback knows more than the crash
                # marker written before the first possible mutation.
                recovery_marker['targets'] = [
                    target
                    for target in recovery_marker['targets']
                    if (target['rootId'], target['relativePath']) in mutated
                ]
                try:
                    self._write_target_marker(rollback_root, recovery_marker)
                    if target_running:
                        recovered = self._preserve_redirected_hot_files(rollback_root, hot_changes, mutated)
                        self._write_hot_recovery_note(rollback_root, hot_changes, str(rollback_error), recovered)
                except OSError:
                    logging.exception('Save rollback evidence could not be updated: %s', rollback_root)
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
            if newer_live_preserved:
                raise SaveRestoreError('{} failed; a newer live save was preserved.'.format(operation_name)) from error
            raise SaveRestoreError('{} failed; previous saves were rolled back.'.format(operation_name)) from error
        finally:
            if cleanup_rollback:
                try:
                    self._clean_hot_changes(hot_changes)
                    remove_owned_save_tree(rollback_root)
                except OSError:
                    logging.exception('Verified save transaction cleanup failed: %s', rollback_root)
                    if result is not None:
                        result['maintenanceWarning'] = 'rollback_cleanup_failed'
                    if result is not None or mutated:
                        # A verified install or rollback may leave cleanup
                        # residue, but its recorded targets are resolved.
                        for target in recovery_marker['targets']:
                            target['resolved'] = True
                        try:
                            self._write_target_marker(rollback_root, recovery_marker)
                        except OSError:
                            logging.exception(
                                'Completed save transaction marker could not be updated: %s', rollback_root
                            )
                finally:
                    destination_stack.close()
            else:
                destination_stack.close()

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

    def replace_files(
        self,
        replacements,
        expected_hashes=None,
        post_install_verify=None,
        *,
        expected_paths=None,
        target_running=False,
    ):
        if type(target_running) is not bool:
            raise ValueError('Save replacement target_running must be boolean.')
        if post_install_verify is not None and not callable(post_install_verify):
            raise ValueError('Save replacement verifier must be callable.')
        entries = self._replacement_entries(replacements)
        replacement_keys = {key for key, _source, _digest in entries}
        if expected_hashes is not None and (
            not isinstance(expected_hashes, dict) or set(expected_hashes) != replacement_keys
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
            target_running,
            require_idle=True,
        )
        try:
            for key in replacement_keys:
                if key not in baseline_hashes:
                    raise SaveRestoreError('Save replacement target is not part of the current save set.')
                if expected_hashes is not None and expected_hashes[key] != baseline_hashes[key]:
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
            target_running=target_running,
            success={'replaced': True},
            operation_name='Save replacement',
            post_install_verify=post_install_verify,
            require_idle=True,
            expected_paths=expected_paths,
            owned_keys=replacement_keys,
            snapshot_origin="automaticPreEdit",
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
