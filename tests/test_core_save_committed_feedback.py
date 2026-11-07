"""Save receipts survive presentation and post-commit maintenance failures."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
sys.path.insert(0, str(ROOT / "tests"))

from core.save_snapshots import SaveNotFoundError, SaveSnapshotError
from core.save_restore import SaveRestoreError
from test_core_structured_save_edit import CODEC, environment, open_session


class SaveCommittedFeedbackTests(unittest.TestCase):
    def test_invalid_provider_presentation_does_not_block_verified_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            saves, service, original = environment(Path(temporary))
            descriptions = (
                ("bad/name", [], {}),
                ("Valid", ["bad\nline"], {}),
                ("Valid", [], {"en": {"name": "bad/name"}}),
            )
            for description in descriptions:
                with self.assertLogs(level="WARNING"):
                    row = service.store.create_snapshot(service.resolved_files, describe=lambda *_: description)
                self.assertEqual(row["nameDetails"], [])
                self.assertEqual(row["localizedPresentation"], {})
                self.assertEqual(row["namingWarning"], "provider_invalid")
                verified = service.store.load_verified_snapshot(row["id"])
                self.assertEqual((verified["root"] / "files/main/Profile1.sav").read_bytes(), original)
                self.assertEqual(service.list_state()["namingWarning"], "provider_invalid")
            with self.assertRaises(ValueError):
                service.backup("bad/name")
            self.assertEqual((saves / "Profile1.sav").read_bytes(), original)

    def test_invalid_provider_description_still_allows_automatic_preedit_copy(self):
        class Provider:
            def describe_snapshot(self, *_):
                return {"defaultName": "bad/name", "localizedPresentation": {"en": {"name": None}}}

        with tempfile.TemporaryDirectory() as temporary:
            saves, service, _ = environment(Path(temporary))
            service.provider = Provider()
            session = open_session(service)
            session.document.value = 77
            with self.assertLogs(level="WARNING"):
                result = session.apply()
            self.assertTrue(result["applied"])
            self.assertEqual(CODEC.load(saves / "Profile1.sav").value, 77)
            self.assertEqual(service.list_state()["namingWarning"], "provider_invalid")

    def test_cleanup_failure_keeps_receipt_and_rolling_baseline(self):
        with tempfile.TemporaryDirectory() as temporary:
            saves, service, original = environment(Path(temporary))
            session = open_session(service)
            session.document.value = 77
            real_temporary_directory = tempfile.TemporaryDirectory

            class FailingCleanup(real_temporary_directory):
                def cleanup(self):
                    super().cleanup()
                    raise OSError("injected staging cleanup failure")

            with patch("core.structured_save_edit.tempfile.TemporaryDirectory", FailingCleanup):
                with self.assertLogs(level="ERROR"):
                    result = session.apply()
            self.assertTrue(result["applied"])
            self.assertEqual(result["maintenanceWarning"], "staging_cleanup_failed")
            self.assertEqual(CODEC.load(saves / "Profile1.sav").value, 77)
            self.assertEqual(session.original_sha256, hashlib.sha256((saves / "Profile1.sav").read_bytes()).hexdigest())
            self.assertEqual(session.source_sha256, hashlib.sha256(original).hexdigest())
            session.document.value = 78
            self.assertTrue(session.apply()["applied"])
            self.assertEqual(CODEC.load(saves / "Profile1.sav").value, 78)

    def test_missing_snapshot_has_one_not_found_code_without_masking_corruption(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, service, _ = environment(Path(temporary))
            missing = "snap-20261107-000000-00000000"
            for operation in (service.store.load_verified_snapshot, service.store.snapshot_folder, service.store.delete_snapshot):
                with self.subTest(operation=operation), self.assertRaises(SaveNotFoundError):
                    operation(missing)
            with self.assertRaises(ValueError):
                service.store.load_verified_snapshot("../unsafe")
            snapshot = service.backup()
            (Path(snapshot["path"]) / "manifest.json").write_text("{}")
            with self.assertRaises(SaveSnapshotError) as failure:
                service.store.load_verified_snapshot(snapshot["id"])
            self.assertEqual(failure.exception.code, "snapshot_invalid")

    def test_cleanup_failure_does_not_replace_an_uncommitted_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            saves, service, original = environment(Path(temporary))
            session = open_session(service)
            session.document.value = 77
            real_directory = tempfile.TemporaryDirectory

            class FailingCleanup(real_directory):
                def cleanup(self):
                    super().cleanup()
                    raise OSError("injected staging cleanup failure")

            failure = SaveRestoreError("known failure before any replacement")
            with patch.object(service, "replace_files", side_effect=failure), patch(
                "core.structured_save_edit.tempfile.TemporaryDirectory", FailingCleanup
            ), self.assertLogs(level="ERROR"):
                with self.assertRaises(SaveRestoreError) as raised:
                    session.apply()
            self.assertIs(raised.exception, failure)
            self.assertEqual((saves / "Profile1.sav").read_bytes(), original)
            self.assertEqual(session.original_sha256, hashlib.sha256(original).hexdigest())


if __name__ == "__main__":
    unittest.main()
