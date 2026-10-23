"""Bound only confirmed automatic pre-edit copies; preserve explicit recovery."""
import json
import logging
import os
from pathlib import Path
import tempfile

from .save_snapshots import SaveSnapshotError

DEFAULT_MAX_COUNT = 20
DEFAULT_MAX_BYTES = 256 * 1024 * 1024
_MAX_SAFE_INTEGER = 9_007_199_254_740_991


class SaveBackupRetention:
    def __init__(self, store):
        self.store = store
        self.warning = ''

    @property
    def policy_path(self):
        return self.store.ensure_storage_root() / 'automatic-backup-policy.json'

    @staticmethod
    def _validate(max_count, max_bytes):
        if type(max_count) is not int or not 1 <= max_count <= 10000:
            raise ValueError('Automatic backup count must be between 1 and 10000.')
        if type(max_bytes) is not int or not 1 <= max_bytes <= _MAX_SAFE_INTEGER:
            raise ValueError('Automatic backup byte budget is invalid.')
        return {'maxCount': max_count, 'maxBytes': max_bytes}

    def policy(self):
        path = self.policy_path
        if not path.exists() and not path.is_symlink():
            return self._validate(DEFAULT_MAX_COUNT, DEFAULT_MAX_BYTES), True
        try:
            if path.is_symlink() or not path.is_file():
                raise ValueError('Unsafe automatic backup policy.')
            payload = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(payload, dict) or payload.get('schemaVersion') != 1:
                raise ValueError('Invalid automatic backup policy.')
            return self._validate(payload.get('maxCount'), payload.get('maxBytes')), True
        except (OSError, ValueError):
            # Invalid settings must not silently authorize default deletion.
            return self._validate(DEFAULT_MAX_COUNT, DEFAULT_MAX_BYTES), False

    def configure(self, max_count, max_bytes):
        policy = self._validate(max_count, max_bytes)
        path = self.policy_path
        if path.is_symlink():
            raise SaveSnapshotError('Automatic backup policy cannot be a symbolic link.')
        descriptor, temporary = tempfile.mkstemp(prefix='.retention-', suffix='.json', dir=str(path.parent))
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
                json.dump({'schemaVersion': 1, **policy}, handle, sort_keys=True)
                handle.write('\n')
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        self.warning = ''
        # Changing policy is non-destructive. The next confirmed successful
        # edit and verified new backup provide the cleanup checkpoint.
        return policy

    @staticmethod
    def eligible(row):
        return (row['valid'] and row['origin'] == 'automaticPreEdit'
                and row['retentionEligible'] and not row['protected'])

    def state(self, rows, recovery_paths):
        policy, valid = self.policy()
        eligible = [row for row in rows if self.eligible(row)]
        sizes_known = all(row['storageBytes'] is not None for row in eligible)
        eligible_bytes = sum(row['storageBytes'] or 0 for row in eligible)
        usage = {'snapshotCount': len(rows), 'snapshotBytes': sum(row['storageBytes'] or 0 for row in rows),
                 'unknownSnapshotSizes': sum(row['storageBytes'] is None for row in rows)}
        for key, selected in (
            ('automatic', [row for row in rows if self.eligible(row)]),
            ('protected', [row for row in rows if row['origin'] == 'automaticPreEdit' and not self.eligible(row)]),
            ('manual', [row for row in rows if row['origin'] in ('manual', 'preRestore')]),
            ('unclassified', [row for row in rows if row['origin'] == 'unclassified']),
        ):
            usage[key + 'Count'] = len(selected)
            usage[key + 'Bytes'] = sum(row['storageBytes'] or 0 for row in selected)
        recovery_sizes = [self.store.storage_bytes(path) for path in recovery_paths]
        usage.update(recoveryCount=len(recovery_paths), recoveryBytes=sum(size or 0 for size in recovery_sizes),
                     unknownRecoverySizes=sum(size is None for size in recovery_sizes))
        return {
            'retention': {**policy, 'minimumCount': 1, 'policyValid': valid,
                          'overBudget': len(eligible) > policy['maxCount'] or eligible_bytes > policy['maxBytes'],
                          'usageComplete': sizes_known,
                          'warning': 'policy_invalid' if not valid else self.warning},
            'storageUsage': usage,
        }

    def after_successful_edit(self, replacement_id, pinned_ids=(), recovery_pending=False):
        """Never let post-commit retention failure change the edit's result."""
        deleted = []
        self.warning = ''
        try:
            # Hash verification precedes eligibility and every possible eviction.
            self.store.confirm_pre_edit(replacement_id)
            policy, valid = self.policy()
            if not valid:
                self.warning = 'policy_invalid'
            elif recovery_pending:
                self.warning = 'recovery_pending'
            else:
                inventory = self.store.list_snapshots()
                if not any(row['id'] == replacement_id and row['valid'] for row in inventory):
                    raise SaveSnapshotError('The verified replacement backup is unavailable.')
                rows = [row for row in inventory if self.eligible(row)]
                if any(row['storageBytes'] is None for row in rows):
                    self.warning = 'usage_unavailable'
                else:
                    # IDs contain random suffixes; use explicit creation order.
                    rows.sort(key=lambda row: (int(row['createdAtNs']), row['id']))
                    keep = set(pinned_ids) | {replacement_id}
                    count = len(rows)
                    total = sum(row['storageBytes'] for row in rows)
                    for row in rows:
                        if count <= policy['maxCount'] and total <= policy['maxBytes']:
                            break
                        if row['id'] in keep or count <= 1:
                            continue
                        self.store.delete_snapshot(row['id'])
                        deleted.append(row['id'])
                        count -= 1
                        total -= row['storageBytes']
        except Exception:
            logging.exception('Automatic backup cleanup failed after a confirmed save edit')
            self.warning = 'cleanup_failed'
        return {'deletedIds': deleted, 'warning': self.warning}
