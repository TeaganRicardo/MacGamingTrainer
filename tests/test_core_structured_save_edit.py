"""Core structured-edit lifecycle: pinning, validation, verified install and recovery."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.module_manifest import SaveManagementSpec, SaveRootSpec
from core.save_restore import SaveRestoreError, SaveRestoreTransaction, SaveRollbackError
from core.save_service import CoreSaveService
from core.structured_save_edit import StructuredSaveEditSession


class FixtureDocument:
    def __init__(self, value):
        self.value = value


class FixtureCodec:
    """A second-module-shaped codec; Core sees only structured encode/decode."""

    def encode(self, document):
        if not isinstance(document, FixtureDocument):
            raise TypeError("Expected a structured fixture document.")
        return json.dumps({"value": document.value}, separators=(",", ":")).encode("utf-8")

    def decode(self, payload):
        decoded = json.loads(payload.decode("utf-8"))
        if not isinstance(decoded, dict) or type(decoded.get("value")) is not int:
            raise ValueError("Malformed structured fixture document.")
        return FixtureDocument(decoded["value"])


CODEC = FixtureCodec()


def environment(base, *, two_files=False):
    saves = base / "saves"
    saves.mkdir(parents=True)
    original = CODEC.encode(FixtureDocument(10))
    (saves / "Profile1.sav").write_bytes(original)
    if two_files:
        (saves / "Profile2.sav").write_bytes(CODEC.encode(FixtureDocument(20)))
    spec = SaveManagementSpec(
        roots=(SaveRootSpec("main", str(saves), ("Profile*.sav",)),),
        provider=None,
        hot_backup=True,
        restore_policy="hotPreferred",
        staged_restore=True,
    )
    service = CoreSaveService("structured-fixture", spec, base / "data", lambda: False)
    return saves, service, original


def identity(path):
    return {"rootId": "main", "relativePath": path}


def open_session(service, *, target="Profile1.sav", version_pinned=False):
    return StructuredSaveEditSession.open(
        service,
        identity("Profile1.sav"),
        CODEC,
        target=identity(target) if target else None,
        version_pinned=version_pinned,
    )


def rejects(error_type, action):
    try:
        action()
    except error_type as error:
        return error
    raise AssertionError("An unverified structured edit reported success.")


def test_structured_edit_session_owns_the_complete_recoverable_lifecycle():
    with tempfile.TemporaryDirectory(prefix="mgt-core-structured-edit-") as temporary:
        base = Path(temporary)

        # A source can be opened without a write target. Apply remains
        # unavailable until a game adapter explicitly selects a physical target.
        saves, service, original = environment(base / "no-target")
        unbound = open_session(service, target=None)
        unbound.document.value = 19
        rejects(ValueError, unbound.apply)
        assert service.list_state()["snapshots"] == []
        unbound.set_target(identity("Profile1.sav"))
        unbound.apply()
        assert CODEC.decode((saves / "Profile1.sav").read_bytes()).value == 19

        # Source identity and source digest stay pinned while the rolling
        # baseline advances after each verified edit to an explicitly chosen target.
        saves, service, original = environment(base / "repeat", two_files=True)
        session = open_session(service, target="Profile2.sav", version_pinned=True)
        assert session.source_identity == identity("Profile1.sav")
        assert session.source_sha256 == hashlib.sha256(original).hexdigest()
        assert session.target == identity("Profile2.sav")
        first = CODEC.encode(FixtureDocument(21))
        session.document.value = 21
        first_result = session.apply()
        assert first_result["applied"] and first_result["replaced"]
        assert (saves / "Profile2.sav").read_bytes() == first
        assert (saves / "Profile1.sav").read_bytes() == original
        assert session.source_sha256 == hashlib.sha256(original).hexdigest()
        assert session.original_sha256 == hashlib.sha256(first).hexdigest()
        previous = service.store.load_verified_snapshot(first_result["previousSnapshotId"])
        assert (previous["root"] / "files/main/Profile2.sav").read_bytes() == CODEC.encode(FixtureDocument(20))

        second = CODEC.encode(FixtureDocument(22))
        session.document.value = 22
        second_result = session.apply()
        assert (saves / "Profile2.sav").read_bytes() == second
        assert session.original_sha256 == hashlib.sha256(second).hexdigest()
        snapshots = len(service.list_state()["snapshots"])
        rejects(ValueError, session.apply)
        assert len(service.list_state()["snapshots"]) == snapshots

        # An explicit target must be a currently declared physical save file.
        rejects(ValueError, lambda: session.set_target(identity("../outside.sav")))
        assert session.target == identity("Profile2.sav")

        # An unchanged edit, malformed structured candidate, or stale original
        # digest is rejected before any destructive transaction or backup.
        saves, service, original = environment(base / "unchanged")
        session = open_session(service)
        rejects(ValueError, session.apply)
        assert service.list_state()["snapshots"] == []
        session.document.value = "malformed"
        rejects(ValueError, session.apply)
        assert (saves / "Profile1.sav").read_bytes() == original
        assert service.list_state()["snapshots"] == []
        session.document = b"arbitrary bytes"
        rejects(TypeError, session.apply)
        assert (saves / "Profile1.sav").read_bytes() == original

        saves, service, original = environment(base / "stale")
        session = open_session(service)
        session.document.value = 11
        external = CODEC.encode(FixtureDocument(12))
        (saves / "Profile1.sav").write_bytes(external)
        rejects(SaveRestoreError, session.apply)
        assert (saves / "Profile1.sav").read_bytes() == external
        assert service.list_state()["snapshots"] == []
        assert session.original_sha256 == hashlib.sha256(original).hexdigest()

        # A failed install with a verified rollback remains retryable; the
        # original baseline advances only after the later confirmed success.
        saves, service, original = environment(base / "rollback-ok")
        session = open_session(service)
        session.document.value = 13
        real_replace = SaveRestoreTransaction._replace_file
        calls = []

        def fail_once_after_install(self, source, destination, digest, **options):
            if Path(destination) == (saves / "Profile1.sav").resolve():
                calls.append(str(destination))
                if len(calls) == 1:
                    real_replace(self, source, destination, digest, **options)
                    raise OSError("simulated lost install acknowledgement")
            return real_replace(self, source, destination, digest, **options)

        with patch.object(SaveRestoreTransaction, "_replace_file", fail_once_after_install):
            rejects(SaveRestoreError, session.apply)
        assert len(calls) == 2
        assert (saves / "Profile1.sav").read_bytes() == original
        assert session.recovery_path is None
        assert session.original_sha256 == hashlib.sha256(original).hexdigest()
        session.apply()
        assert CODEC.decode((saves / "Profile1.sav").read_bytes()).value == 13

        # A failed rollback preserves terminal recovery evidence and permanently
        # prevents this session from replaying the uncertain candidate.
        saves, service, original = environment(base / "rollback-failed")
        session = open_session(service)
        session.document.value = 14
        calls = []

        def fail_install_and_rollback(self, source, destination, digest, **options):
            if Path(destination) == (saves / "Profile1.sav").resolve():
                calls.append(str(destination))
                if len(calls) == 1:
                    real_replace(self, source, destination, digest, **options)
                    raise OSError("simulated lost install acknowledgement")
                raise OSError("simulated rollback failure")
            return real_replace(self, source, destination, digest, **options)

        with patch.object(SaveRestoreTransaction, "_replace_file", fail_install_and_rollback):
            failure = rejects(SaveRollbackError, session.apply)
            assert session.recovery_path == str(failure.recovery_path)
            assert session.recovery_unresolved is True
            rejects(ValueError, session.apply)
        assert len(calls) == 2
        recovery = Path(session.recovery_path)
        assert recovery.is_dir()
        assert (recovery / "files/main/Profile1.sav").read_bytes() == original
        assert str(recovery.resolve()) in service.list_state()["recoveryPaths"]

        # KeyboardInterrupt during rollback has no exception.recovery_path.
        # Core must discover the new retained recovery directory and lock the
        # same session rather than relying on the Hades I-only error attribute.
        saves, service, original = environment(base / "rollback-interrupted")
        session = open_session(service)
        session.document.value = 15
        calls = []

        def interrupt_rollback(self, source, destination, digest, **options):
            if Path(destination) == (saves / "Profile1.sav").resolve():
                calls.append(str(destination))
                if len(calls) == 1:
                    real_replace(self, source, destination, digest, **options)
                    raise OSError("simulated lost install acknowledgement")
                raise KeyboardInterrupt()
            return real_replace(self, source, destination, digest, **options)

        with patch.object(SaveRestoreTransaction, "_replace_file", interrupt_rollback):
            rejects(KeyboardInterrupt, session.apply)
            assert session.recovery_path is not None
            assert session.recovery_unresolved is True
            rejects(ValueError, session.apply)
        assert len(calls) == 2
        recovery = Path(session.recovery_path)
        assert recovery.is_dir()
        assert (recovery / "files/main/Profile1.sav").read_bytes() == original
        assert str(recovery.resolve()) in service.list_state()["recoveryPaths"]


if __name__ == "__main__":
    test_structured_edit_session_owns_the_complete_recoverable_lifecycle()
    print("core_structured_save_edit_ok")
