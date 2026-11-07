"""Trainer-owned copies never inherit source locking flags; targets keep them."""
import os
from pathlib import Path
import stat
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
sys.path.insert(0, str(ROOT / "tests"))

from core.save_restore import SaveRestoreError
from test_core_structured_save_edit import CODEC, environment, open_session


class SaveMetadataTests(unittest.TestCase):
    def test_immutable_source_is_backed_up_and_locked_target_is_not_unlocked(self):
        with tempfile.TemporaryDirectory() as temporary:
            saves, service, original = environment(Path(temporary))
            target = saves / "Profile1.sav"
            os.chflags(target, stat.UF_IMMUTABLE)
            try:
                snapshot = service.backup()
                copy = Path(snapshot["path"]) / "files/main/Profile1.sav"
                self.assertEqual(copy.read_bytes(), original)
                self.assertFalse(copy.stat().st_flags & stat.UF_IMMUTABLE)
                session = open_session(service)
                session.document.value = 77
                with self.assertRaises(SaveRestoreError) as failure:
                    session.apply()
                self.assertEqual(failure.exception.code, "restore_failed")
                self.assertEqual(target.read_bytes(), original)
                self.assertTrue(target.stat().st_flags & stat.UF_IMMUTABLE)
                self.assertEqual(service.recovery_paths(), ())
                service.delete(snapshot["id"])
            finally:
                os.chflags(target, 0)
                # Reclaim only this fixture's old-implementation copies after RED.
                for path in Path(temporary).rglob("*"):
                    if not path.is_symlink():
                        os.chflags(path, 0)

    def test_stale_owned_stage_with_immutable_copy_is_reclaimed(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, service, _ = environment(Path(temporary))
            service.store._ensure_parent()
            stage = service.store.snapshots / ".snapshot-oldcopy"
            stage.mkdir()
            payload = stage / "payload"
            payload.write_bytes(b"old private staging")
            os.chflags(payload, stat.UF_IMMUTABLE)
            os.utime(stage, (time.time() - 172800,) * 2)
            try:
                service.store.list_snapshots()
                self.assertFalse(stage.exists())
            finally:
                if payload.exists():
                    os.chflags(payload, 0)


if __name__ == "__main__":
    unittest.main()
