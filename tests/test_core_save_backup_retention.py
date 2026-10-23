"""Automatic retention exercises real Core transactions in temporary trees."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from core.module_manifest import SaveManagementSpec, SaveRootSpec
from core.save_resolution import ResolvedSaveFile
from core.save_restore import SaveRestoreError, SaveRollbackError
from core.save_service import CoreSaveService


class BackupRetentionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='mgt-preedit-retention-')
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name).resolve()
        self.saves = self.folder / 'saves'
        self.saves.mkdir()
        self.target = self.saves / 'Profile1.sav'
        self.target.write_bytes(b'original')
        self.running = False
        self.spec = SaveManagementSpec(
            roots=(SaveRootSpec('main', str(self.saves), ('*.sav',)),), provider=None,
            hot_backup=True, restore_policy='stoppedOnly', staged_restore=True,
        )
        self.service = CoreSaveService('fixture', self.spec, self.folder / 'data', lambda: self.running)

    def edit(self, value, verifier=None):
        source = self.folder / 'replacement.sav'
        source.write_bytes(value)
        return self.service.replace_files((ResolvedSaveFile('main', 'Profile1.sav', source),),
                                          post_install_verify=verifier)

    def rows(self):
        return {row['id']: row for row in self.service.list_state()['snapshots']}

    def configure(self, count=1, size=1024 * 1024):
        return self.service.configure_retention(count, size)

    def test_repeated_successful_edits_are_bounded(self):
        # Original RED: these 22 successful edits left 22 pre-edit snapshots.
        for index in range(22):
            result = self.edit(f'edited-{index}'.encode())
        rows = self.rows()
        self.assertEqual(len(rows), 20)
        self.assertIn(result['previousSnapshotId'], rows)
        self.assertTrue(all(row['origin'] == 'automaticPreEdit' and row['retentionEligible'] for row in rows.values()))
        backup = self.service.store.load_verified_snapshot(result['previousSnapshotId'])
        self.assertEqual((backup['root'] / 'files/main/Profile1.sav').read_bytes(), b'edited-20')

    def test_configuring_policy_is_persistent_and_non_destructive(self):
        for value in (b'a', b'b', b'c'):
            self.edit(value)
        self.configure()
        self.assertEqual(len(self.rows()), 3)
        reloaded = CoreSaveService('fixture', self.spec, self.folder / 'data', lambda: False)
        self.assertEqual(reloaded.list_state()['retention']['maxCount'], 1)
        self.edit(b'd')
        self.assertEqual(len(self.rows()), 1)
        for count, size in ((0, 10), (True, 10), (1, 0), (1, False)):
            with self.assertRaises(ValueError):
                self.service.configure_retention(count, size)
        self.assertEqual(reloaded.list_state()['retention']['maxCount'], 1)

    def test_origin_does_not_follow_name_and_legacy_is_never_reclassified(self):
        manual = self.service.store.create_snapshot(self.service._resolve, describe=lambda files, stamp: (
            'Before edit', [], {'en': {'name': 'Before edit', 'details': []}}))
        self.assertTrue(manual['automaticName'])
        legacy = self.service.backup()
        manifest_path = Path(legacy['path']) / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        for field in ('origin', 'protected', 'retentionEligible', 'createdAtNs'):
            manifest.pop(field)
        manifest_path.write_text(json.dumps(manifest))
        auto = self.edit(b'a')['previousSnapshotId']
        renamed = self.service.rename(auto, 'Keep this recovery point')
        self.assertEqual(renamed['origin'], 'automaticPreEdit')
        self.assertTrue(renamed['protected'])
        self.configure()
        for value in (b'b', b'c', b'd'):
            newest = self.edit(value)['previousSnapshotId']
        rows = self.rows()
        self.assertEqual(set(rows), {manual['id'], legacy['id'], auto, newest})
        self.assertEqual(rows[legacy['id']]['origin'], 'unclassified')
        self.assertEqual(rows[manual['id']]['origin'], 'manual')
        self.service.protect(auto, False)  # explicit return to automatic cleanup
        self.edit(b'e')
        self.assertNotIn(auto, self.rows())

    def test_byte_budget_keeps_verified_newest_recovery_floor(self):
        self.configure(size=1)
        self.edit(b'a')
        last = self.edit(b'b')['previousSnapshotId']
        state = self.service.list_state()
        self.assertEqual(len(state['snapshots']), 1)
        self.assertEqual(state['snapshots'][0]['id'], last)
        self.assertTrue(state['retention']['overBudget'])
        self.assertGreater(state['storageUsage']['automaticBytes'], 1)
        self.service.store.load_verified_snapshot(last)

    def test_pending_restore_input_is_not_evicted(self):
        self.configure()
        pinned = self.edit(b'a')['previousSnapshotId']
        self.running = True
        staged = self.service.restore(pinned)
        self.assertTrue(staged['staged'])
        self.running = False
        latest = self.edit(b'b')['previousSnapshotId']
        self.assertEqual(set(self.rows()), {pinned, latest})
        self.assertTrue(self.service.list_state()['retention']['overBudget'])
        # An interrupted staged transaction makes the cleanup checkpoint unsafe.
        marker = self.service._staged_path()
        marker.rename(marker.parent / '.staged-restore-applying-fixture.json')
        next_result = self.edit(b'c')
        self.assertEqual(next_result['retention']['warning'], 'recovery_pending')
        self.assertEqual(len(self.rows()), 3)

    def test_failed_apply_backup_stays_outside_later_eviction(self):
        self.configure()
        def rejected():
            raise ValueError('synthetic post-install rejection')
        with self.assertRaises(SaveRestoreError):
            self.edit(b'rejected', rejected)
        failed = next(iter(self.rows()))
        self.assertFalse(self.rows()[failed]['retentionEligible'])
        self.assertEqual(self.target.read_bytes(), b'original')
        for value in (b'a', b'b', b'c'):
            latest = self.edit(value)['previousSnapshotId']
        self.assertEqual(set(self.rows()), {failed, latest})

    def test_interruption_and_rollback_failure_preserve_recovery(self):
        self.configure()
        def interrupted():
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.edit(b'interrupted', interrupted)
        interrupted_id = next(iter(self.rows()))
        transaction = self.service._transaction()
        with mock.patch.object(self.service, '_transaction', return_value=transaction), \
             mock.patch.object(transaction, '_install_entries', side_effect=OSError('synthetic disk failure')):
            with self.assertRaises(SaveRollbackError):
                self.edit(b'failed')
        recovery = self.service._recovery_paths()
        self.assertTrue(recovery)
        before = set(self.rows())
        result = self.edit(b'success')
        self.assertTrue(result['replaced'])
        self.assertEqual(result['retention']['warning'], 'recovery_pending')
        self.assertTrue(before <= set(self.rows()))
        self.assertIn(interrupted_id, self.rows())
        self.assertEqual(self.service._recovery_paths(), recovery)

    def test_cleanup_failure_does_not_fail_or_roll_back_successful_apply(self):
        self.configure()
        self.edit(b'a')
        with mock.patch.object(self.service.store, 'delete_snapshot', side_effect=OSError('cannot remove backup')):
            result = self.edit(b'b')
        self.assertTrue(result['replaced'])
        self.assertEqual(self.target.read_bytes(), b'b')
        self.assertEqual(result['retention']['warning'], 'cleanup_failed')
        self.assertEqual(len(self.rows()), 2)
        self.assertEqual(self.service.list_state()['retention']['warning'], 'cleanup_failed')
        self.assertEqual(self.service._recovery_paths(), [])

    def test_unverified_replacement_cannot_authorize_eviction(self):
        self.configure()
        self.edit(b'a')
        original = self.service.store.confirm_pre_edit
        def corrupt_then_confirm(snapshot_id):
            path = self.service.store._path_for_id(snapshot_id) / 'files/main/Profile1.sav'
            path.write_bytes(b'corrupt backup')
            return original(snapshot_id)
        with mock.patch.object(self.service.store, 'confirm_pre_edit', side_effect=corrupt_then_confirm):
            result = self.edit(b'b')
        self.assertTrue(result['replaced'])
        self.assertEqual(result['retention']['warning'], 'cleanup_failed')
        self.assertEqual(len(self.rows()), 2)

    def test_inventory_measures_actual_files_including_invalid_copies(self):
        backup = self.service.backup()
        folder = Path(backup['path'])
        (folder / 'files/main/Profile1.sav').write_bytes(b'larger corrupt payload')
        (folder / 'extra').write_bytes(b'additional bytes')
        outside = self.folder / 'outside'
        outside.write_bytes(b'x' * 10000)
        (folder / 'link').symlink_to(outside)
        row = self.rows()[backup['id']]
        expected = sum(path.lstat().st_size for path in folder.rglob('*') if path.is_file() or path.is_symlink())
        self.assertFalse(row['valid'])
        self.assertEqual(row['origin'], 'unclassified')
        self.assertEqual(row['storageBytes'], expected)
        self.assertEqual(self.service.list_state()['storageUsage']['snapshotBytes'], expected)
        self.assertLess(expected, 10000)

    def test_explicit_name_protects_an_automatic_copy(self):
        named = self.service.store.create_snapshot(self.service._resolve, origin='automaticPreEdit', display_name='Keep')
        self.service.store.confirm_pre_edit(named['id'])
        self.configure()
        self.edit(b'a')
        self.edit(b'b')
        self.assertIn(named['id'], self.rows())
        self.assertTrue(self.rows()[named['id']]['protected'])

    def test_unknown_size_pauses_cleanup_and_is_not_reported_as_zero(self):
        self.configure()
        self.edit(b'a')
        real_size = self.service.store.storage_bytes
        def unreadable(root):
            return None if Path(root).parent == self.service.store.snapshots else real_size(root)
        with mock.patch.object(self.service.store, 'storage_bytes', side_effect=unreadable):
            result = self.edit(b'b')
            state = self.service.list_state()
        self.assertEqual(result['retention']['warning'], 'usage_unavailable')
        self.assertEqual(state['storageUsage']['unknownSnapshotSizes'], 2)
        self.assertFalse(state['retention']['usageComplete'])
        self.assertEqual(len(self.rows()), 2)

    def test_malformed_origin_stays_visible_without_becoming_evictable(self):
        backup = self.service.backup()
        path = Path(backup['path']) / 'manifest.json'
        manifest = json.loads(path.read_text())
        manifest['origin'] = ['automaticPreEdit']
        path.write_text(json.dumps(manifest))
        row = self.rows()[backup['id']]
        self.assertFalse(row['valid'])
        self.assertEqual(row['origin'], 'unclassified')

    def test_invalid_policy_cannot_authorize_default_cleanup(self):
        self.configure()
        self.edit(b'a')
        self.service.retention.policy_path.write_text('{invalid')
        result = self.edit(b'b')
        self.assertTrue(result['replaced'])
        self.assertEqual(len(self.rows()), 2)
        self.assertEqual(result['retention']['warning'], 'policy_invalid')
        self.assertFalse(self.service.list_state()['retention']['policyValid'])


if __name__ == '__main__':
    unittest.main()
