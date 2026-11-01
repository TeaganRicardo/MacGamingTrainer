import datetime
import json
import logging
import os
import tempfile
import time
import uuid
from pathlib import Path

from .save_resolution import ResolvedSaveFile, SaveResolutionError, load_save_provider, read_resolved_save_file, resolve_save_files
from .save_restore import (
    SaveBusyError,
    SaveRestorePreparationInterrupted,
    SaveRestoreTransaction,
    SaveRollbackError,
)
from .save_snapshots import SaveSnapshotError, SaveSnapshotStore
from .save_retention import SaveBackupRetention


class SaveManagementUnsupportedError(RuntimeError):
    code = 'save_unsupported'


class SaveStagedUnavailableError(RuntimeError):
    code = 'staged_unavailable'


class SaveStagedIndeterminateError(RuntimeError):
    code = 'staged_indeterminate'


class CoreSaveService:
    def __init__(self, game_id, spec, data_root, target_running_probe, provider_loader=None):
        self.game_id = game_id
        self.spec = spec
        self.target_running_probe = target_running_probe
        self.store = SaveSnapshotStore(game_id, Path(data_root))
        self.retention = SaveBackupRetention(self.store)
        self.provider = None
        if spec is not None and spec.provider is not None:
            loader = provider_loader or load_save_provider
            self.provider = loader(spec.provider)

    def _require_supported(self):
        if self.spec is None:
            raise SaveManagementUnsupportedError('This game does not support save management.')

    def _resolve(self):
        self._require_supported()
        if self.provider is None:
            return resolve_save_files(self.spec)
        return resolve_save_files(self.spec, provider_loader=lambda target: self.provider)

    def _provider_busy(self, files):
        if self.provider is None:
            return False
        probe = getattr(self.provider, 'restore_busy', None)
        if probe is None:
            return False
        if not callable(probe):
            raise RuntimeError('Save Provider restore_busy must be callable.')
        value = probe(files)
        if type(value) is not bool:
            raise RuntimeError('Save Provider restore_busy must return bool.')
        return value

    def _snapshot_naming(self, files, created_at):
        if self.provider is None:
            return None, [], {}
        describe = getattr(self.provider, 'describe_snapshot', None)
        if describe is None:
            return None, [], {}
        if not callable(describe):
            raise RuntimeError('Save Provider describe_snapshot must be callable.')
        value = describe(tuple(files), created_at)
        if value is None:
            return None, [], {}
        if not isinstance(value, dict):
            raise RuntimeError('Save Provider describe_snapshot must return an object.')
        default_name = value.get('defaultName')
        if default_name is not None and not isinstance(default_name, str):
            raise RuntimeError('Save Provider defaultName must be a string or null.')
        localized = value.get('localizedPresentation', {})
        if not isinstance(localized, dict):
            raise RuntimeError('Save Provider localizedPresentation must be an object.')
        return default_name, value.get('nameDetails', []), localized

    def _running(self):
        return bool(self.target_running_probe())

    def _transaction(self):
        return SaveRestoreTransaction(
            self.store,
            self.spec,
            self._resolve,
            busy_probe=self._provider_busy if self.provider is not None else None,
            snapshot_describer=self._snapshot_naming if self.provider is not None else None,
            target_running_probe=self._running,
        )

    def resolved_files(self):
        self._require_supported()
        return tuple(self._resolve())

    def source_files(self, snapshot_id=None):
        """Return declared live files or the members of one verified snapshot."""
        self._require_supported()
        if snapshot_id is None:
            return self.resolved_files()
        verified = self.store.load_verified_snapshot(snapshot_id)
        return tuple(
            ResolvedSaveFile(item['rootId'], item['relativePath'],
                verified['root'] / 'files' / item['rootId'] / item['relativePath'])
            for item in verified['manifest']['files']
        )

    def read_source_file(self, root_id, relative_path, snapshot_id=None):
        """Read by contained identity; never accept a caller-supplied file path."""
        self._require_supported()
        if snapshot_id is not None:
            return self.store.read_source_file(snapshot_id, root_id, relative_path)
        matches = [row for row in self.resolved_files()
            if (row.root_id, row.relative_path) == (root_id, relative_path)]
        if len(matches) != 1:
            raise SaveResolutionError('Save source is missing or ambiguous.')
        root = next(root for root in self.spec.roots if root.id == root_id)
        return matches[0], read_resolved_save_file(root.path, matches[0])

    def replace_files(
        self,
        replacements,
        expected_hashes=None,
        post_install_verify=None,
        *,
        expected_paths=None,
        allow_running=False,
    ):
        self._require_supported()
        if type(allow_running) is not bool:
            raise ValueError('allow_running must be boolean.')
        running = self._running()
        if running and not allow_running:
            raise SaveBusyError('Game must be stopped before applying a save edit.')
        result = self._transaction().replace_files(
            replacements,
            expected_hashes,
            post_install_verify=post_install_verify,
            expected_paths=expected_paths,
            target_running=running,
        )
        # The transaction has already committed and verified. Retention errors
        # are separate maintenance feedback, never a failed Apply or rollback.
        try:
            pending = self.pending_restore()
            pinned = (pending['snapshotId'],) if pending and pending.get('snapshotId') else ()
            result['retention'] = self.retention.after_successful_edit(
                result['previousSnapshotId'], pinned,
                recovery_pending=bool(self._recovery_paths()) or bool(pending and pending.get('indeterminate')),
            )
        except Exception:
            logging.exception('Automatic backup checkpoint failed after a confirmed save edit')
            self.retention.warning = 'cleanup_failed'
            result['retention'] = {'deletedIds': [], 'warning': 'cleanup_failed'}
        return result

    def _staged_path(self):
        return self.store.ensure_storage_root() / 'staged-restore.json'

    def _staged_applying_paths(self):
        root = self.store.ensure_storage_root()
        return sorted(root.glob('.staged-restore-applying-*.json'))

    def _ensure_data_root(self):
        return self.store.ensure_storage_root()

    def _recovery_paths(self):
        root = self.store.ensure_storage_root()
        transactions = root / 'transactions'
        if not transactions.exists() and not transactions.is_symlink():
            return []
        if transactions.is_symlink() or not transactions.is_dir():
            raise SaveSnapshotError('Save transaction storage path is unsafe.')
        root_resolved = root.resolve(strict=False)
        transactions_resolved = transactions.resolve(strict=False)
        if transactions_resolved.parent != root_resolved:
            raise SaveSnapshotError('Save transaction storage escaped its data root.')

        paths = []
        for candidate in sorted(transactions.glob('.rollback-*')):
            if candidate.is_symlink() or not candidate.is_dir():
                continue
            resolved = candidate.resolve(strict=False)
            if resolved.parent != transactions_resolved:
                continue
            paths.append(str(resolved))
        return paths

    def _write_staged(self, payload):
        path = self._staged_path()
        self._ensure_data_root()
        fd, temp_name = tempfile.mkstemp(prefix='.staged-restore-', suffix='.json', dir=str(path.parent))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='') as handle:
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
                handle.write('\n')
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            try:
                Path(temp_name).unlink()
            except FileNotFoundError:
                pass

    def _quarantine_staged(self, path):
        stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
        destination = path.with_name('{}.corrupt-{}-{}'.format(path.name, stamp, uuid.uuid4().hex[:8]))
        try:
            os.replace(path, destination)
            return destination
        except OSError:
            return None

    def _read_staged_marker(self, path):
        if path.is_symlink() or not path.is_file():
            raise ValueError('Staged restore marker is unsafe.')
        payload = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(payload, dict):
            raise ValueError('Staged restore marker must be an object.')
        snapshot_id = payload.get('snapshotId')
        preserve_current = payload.get('preserveCurrent')
        staged_at = payload.get('stagedAt')
        if not isinstance(snapshot_id, str) or not snapshot_id:
            raise ValueError('Staged restore snapshot ID is invalid.')
        if type(preserve_current) is not bool:
            raise ValueError('Staged restore preserveCurrent is invalid.')
        if not isinstance(staged_at, str) or not staged_at or len(staged_at) > 128:
            raise ValueError('Staged restore timestamp is invalid.')
        self.store.load_verified_snapshot(snapshot_id)
        return {
            'snapshotId': snapshot_id,
            'preserveCurrent': preserve_current,
            'stagedAt': staged_at,
        }

    def pending_restore(self):
        self._require_supported()
        applying = self._staged_applying_paths()
        if applying:
            # An applying marker survived a process loss. The save mutation may
            # have not started, partially completed, rolled back, or committed;
            # never infer an outcome or replay it automatically.
            try:
                pending = self._read_staged_marker(applying[0])
            except Exception:
                logging.exception('Staged restore claim remains indeterminate; its intent is unavailable')
                pending = {}
            pending['indeterminate'] = True
            pending['indeterminateCount'] = len(applying)
            return pending

        path = self._staged_path()
        if not path.exists() and not path.is_symlink():
            return None
        try:
            pending = self._read_staged_marker(path)
            pending['indeterminate'] = False
            return pending
        except OSError:
            raise
        except (ValueError, SaveSnapshotError) as error:
            if isinstance(error.__cause__, OSError):
                raise error.__cause__ from error
            quarantined = self._quarantine_staged(path)
            if quarantined is None and (path.exists() or path.is_symlink()):
                raise RuntimeError('Corrupt staged restore marker could not be quarantined.') from error
            return None

    def _stage(self, snapshot_id, preserve_current):
        if not self.spec.staged_restore:
            raise SaveStagedUnavailableError('This game cannot stage restore until exit.')
        if self._staged_applying_paths():
            raise SaveStagedIndeterminateError(
                'A previous staged restore was interrupted; inspect the save state and clear it before staging another restore.'
            )
        self.store.load_verified_snapshot(snapshot_id)
        payload = {
            'snapshotId': snapshot_id,
            'preserveCurrent': preserve_current,
            'stagedAt': datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
        }
        self._write_staged(payload)
        return {'staged': True, **payload}

    def recovery_paths(self):
        """Return validated terminal rollback evidence without enumerating snapshots."""
        self._require_supported()
        return tuple(self._recovery_paths())

    def list_state(self):
        self._require_supported()
        snapshots = self.store.list_snapshots()
        recovery_paths = self._recovery_paths()
        return {
            'snapshots': snapshots,
            'pendingRestore': self.pending_restore(),
            'recoveryPaths': recovery_paths,
            **self.retention.state(snapshots, recovery_paths),
        }

    def configure_retention(self, max_count, max_bytes):
        self._require_supported()
        return self.retention.configure(max_count, max_bytes)

    def protect(self, snapshot_id, protected):
        self._require_supported()
        return self.store.protect_snapshot(snapshot_id, protected)

    def backup(self, display_name=None):
        self._require_supported()
        running = self._running()
        if running and not self.spec.hot_backup:
            raise SaveBusyError('Game is running and live backup is disabled.')
        return self.store.create_snapshot(
            self._resolve,
            hot=running,
            display_name=display_name,
            origin="manual",
            describe=self._snapshot_naming if self.provider is not None else None,
        )

    def rename(self, snapshot_id, display_name):
        self._require_supported()
        return self.store.rename_snapshot(snapshot_id, display_name)

    def delete(self, snapshot_id):
        self._require_supported()
        pending = self.pending_restore()
        if pending is not None and pending.get('indeterminate'):
            raise ValueError('Backups cannot be deleted while a staged restore outcome is unconfirmed.')
        if pending is not None and pending['snapshotId'] == snapshot_id:
            raise ValueError('Pending restore snapshot cannot be deleted.')
        return self.store.delete_snapshot(snapshot_id)

    def folder(self, snapshot_id=None):
        self._require_supported()
        if snapshot_id is not None:
            return self.store.snapshot_folder(snapshot_id)
        self.store._ensure_parent()
        return str(self.store.snapshots.resolve())

    def restore(self, snapshot_id, preserve_current=True):
        self._require_supported()
        if type(preserve_current) is not bool:
            raise ValueError('preserveCurrent must be boolean.')
        self.store.load_verified_snapshot(snapshot_id)
        running = self._running()
        if running and self.spec.restore_policy == 'stoppedOnly':
            return self._stage(snapshot_id, preserve_current)

        try:
            return self._transaction().restore(
                snapshot_id,
                preserve_current=preserve_current,
                target_running=running,
            )
        except SaveBusyError as error:
            running_now = running or self._running()
            if running_now:
                if self.spec.staged_restore:
                    return self._stage(snapshot_id, preserve_current)
                raise SaveStagedUnavailableError('Save files are busy and staged restore is unavailable.') from error
            raise

    def cancel_staged(self):
        self._require_supported()
        paths = [self._staged_path(), *self._staged_applying_paths()]
        cancelled = False
        for path in paths:
            if path.exists() or path.is_symlink():
                path.unlink()
                cancelled = True
        return {'cancelled': cancelled}

    def apply_staged(self):
        self._require_supported()
        pending = self.pending_restore()
        if pending is None:
            return {'applied': False}
        if pending.get('indeterminate'):
            return {'applied': False, 'indeterminate': True}
        if self._running():
            raise SaveBusyError('Game is still running.')

        path = self._staged_path()
        claimed = path.with_name('.staged-restore-applying-{}.json'.format(uuid.uuid4().hex))
        os.replace(path, claimed)
        try:
            result = self._transaction().restore(
                pending['snapshotId'],
                preserve_current=pending['preserveCurrent'],
                target_running=False,
            )
        except SaveRestorePreparationInterrupted as error:
            try:
                os.replace(claimed, path)
            except OSError:
                logging.exception('Failed to restore staged marker after rollback-copy interruption: %s', claimed)
            if isinstance(error.__cause__, KeyboardInterrupt):
                raise error.__cause__
            raise
        except SaveRollbackError:
            # Rollback has explicitly failed, so the real-save outcome is not
            # proven. Keep the applying claim visible as indeterminate; turning
            # it back into an ordinary pending marker could auto-replay it.
            logging.error('Staged restore rollback failed; preserving indeterminate claim: %s', claimed)
            raise
        except BaseException as error:
            if not isinstance(error, Exception):
                # SIGTERM is surfaced as KeyboardInterrupt by the backend
                # process. A control-flow interruption can itself occur during
                # rollback, so fail closed instead of assuming rollback finished.
                logging.error('Staged restore interrupted; preserving indeterminate claim: %s', claimed)
                raise
            # Ordinary exceptions from a transaction whose outcome is known may
            # restore the instruction to pending for a later explicit/automatic retry.
            try:
                os.replace(claimed, path)
            except OSError:
                logging.exception('Failed to restore staged marker after restore failure: %s', claimed)
            raise

        applied = claimed.with_name(claimed.name.replace('.staged-restore-applying-', '.staged-restore-applied-', 1))
        try:
            os.replace(claimed, applied)
        except OSError:
            # The restore committed but acknowledgement was not made durable.
            # Leave the applying marker in place so the next process fails
            # closed instead of guessing that replay is safe.
            logging.exception('Failed to acknowledge committed staged restore: %s', claimed)
            return {'applied': True, 'snapshotId': pending['snapshotId'], 'restore': result}
        try:
            applied.unlink(missing_ok=True)
        except OSError:
            logging.warning('Applied staged restore marker cleanup deferred: %s', applied)
        return {'applied': True, 'snapshotId': pending['snapshotId'], 'restore': result}
