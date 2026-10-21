"""Generic verified file reads and captured physical replacement identities."""
import os
import resource
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
from core.module_manifest import SaveManagementSpec, SaveRootSpec
from core.save_resolution import ResolvedSaveFile, SaveResolutionError
import core.save_resolution as resolution_module
from core.save_service import CoreSaveService
from core.save_snapshots import SaveSnapshotError
import core.save_restore as restore_module
from core.save_restore import SaveRestoreError, SaveRollbackError


with tempfile.TemporaryDirectory(prefix="mgt-generic-source-") as temporary:
    folder = Path(temporary)
    saves = folder / "saves"
    saves.mkdir()
    target = saves / "slot.dat"
    target.write_bytes(b"original opaque game bytes")
    spec = SaveManagementSpec(roots=(SaveRootSpec("files", str(saves), ("*.dat",)),),
        provider=None, hot_backup=False, restore_policy="stoppedOnly", staged_restore=False)
    service = CoreSaveService("independent-game", spec, folder / "data", lambda: False)
    snapshot = service.backup()["id"]
    source, raw = service.read_source_file("files", "slot.dat", snapshot)
    assert raw == b"original opaque game bytes"
    assert (source.root_id, source.relative_path) == ("files", "slot.dat")
    assert service.source_files(snapshot) == (source,)
    target.write_bytes(b"a newer live version")
    assert service.read_source_file("files", "slot.dat")[1] == b"a newer live version"
    assert service.read_source_file("files", "slot.dat", snapshot)[1] == raw
    for root_id, relative in (("unknown", "slot.dat"), ("files", "../slot.dat")):
        for snapshot_id in (None, snapshot):
            try:
                service.read_source_file(root_id, relative, snapshot_id)
            except (SaveResolutionError, SaveSnapshotError):
                pass
            else:
                raise AssertionError("unowned source identity was accepted")

    # A read made after manifest validation still has to match that manifest.
    original_verify = service.store._read_manifest
    def changed_after_verify(root):
        manifest = original_verify(root)
        (root / "files/files/slot.dat").write_bytes(b"changed between verification and read")
        return manifest
    service.store._read_manifest = changed_after_verify
    try:
        service.read_source_file("files", "slot.dat", snapshot)
    except SaveSnapshotError:
        pass
    else:
        raise AssertionError("unverified source bytes escaped the owner")
    service.store._read_manifest = original_verify

with tempfile.TemporaryDirectory(prefix="mgt-physical-target-") as temporary:
    folder = Path(temporary)
    saves = folder / "saves"
    saves.mkdir()
    original_directory = saves / "selected"
    other_directory = saves / "other"
    original_directory.mkdir()
    other_directory.mkdir()
    target = original_directory / "slot.dat"
    target.write_bytes(b"selected original")
    other = other_directory / "slot.dat"
    other.write_bytes(b"other physical target")
    spec = SaveManagementSpec(roots=(SaveRootSpec("files", str(saves), ("selected/*.dat",)),),
        provider=None, hot_backup=False, restore_policy="stoppedOnly", staged_restore=False)
    service = CoreSaveService("independent-game", spec, folder / "data", lambda: False)
    captured = service.resolved_files()[0].source_path.resolve()
    prepared = folder / "prepared.dat"
    prepared.write_bytes(b"edited fixed document")
    replacement = ResolvedSaveFile("files", "selected/slot.dat", prepared)
    # Replacing content and inode at the same physical path is an intended write.
    incoming = folder / "new.dat"
    incoming.write_bytes(b"new target version")
    incoming.replace(target)
    result = service.replace_files((replacement,), expected_paths={('files', 'selected/slot.dat'): captured})
    assert result['replaced'] and target.read_bytes() == b"edited fixed document"
    before = service.store.load_verified_snapshot(result['previousSnapshotId'])
    assert (before['root'] / "files/files/selected/slot.dat").read_bytes() == b"new target version"

    # A parent alias would retain root/relative identity while redirecting the
    # physical file. Do not normalize the captured expected path a second time.
    original_directory.rename(saves / "departed")
    original_directory.symlink_to(other_directory, target_is_directory=True)
    try:
        service.replace_files((replacement,), expected_paths={('files', 'selected/slot.dat'): captured})
    except SaveRestoreError:
        pass
    else:
        raise AssertionError("fixed identity followed a replacement parent alias")
    assert other.read_bytes() == b"other physical target"
    assert (saves / "departed/slot.dat").read_bytes() == b"edited fixed document"

with tempfile.TemporaryDirectory(prefix="mgt-same-path-directory-replacement-") as temporary:
    folder = Path(temporary)
    saves = folder / "saves"
    selected = saves / "selected"
    selected.mkdir(parents=True)
    target = selected / "slot.dat"
    baseline = b"baseline bytes in selected directory"
    candidate = b"replacement bytes"
    target.write_bytes(baseline)
    spec = SaveManagementSpec(roots=(SaveRootSpec("files", str(saves), ("selected/*.dat",)),),
        provider=None, hot_backup=False, restore_policy="stoppedOnly", staged_restore=False)
    service = CoreSaveService("same-path-directory-replacement", spec, folder / "data", lambda: False)
    prepared = folder / "prepared.dat"
    prepared.write_bytes(candidate)
    replacement = ResolvedSaveFile("files", "selected/slot.dat", prepared)
    departed = saves / "departed"
    real_verify_target_paths = restore_module.SaveRestoreTransaction._verify_target_paths
    swapped = [False]

    def replace_directory_at_transaction_boundary(transaction, expected_paths):
        if not swapped[0]:
            # Reuse the exact pathname with a different directory inode. The
            # current path already contains candidate bytes, so content checks
            # alone cannot reveal that the captured descriptor belongs elsewhere.
            selected.rename(departed)
            selected.mkdir()
            (selected / "slot.dat").write_bytes(candidate)
            swapped[0] = True
        return real_verify_target_paths(transaction, expected_paths)

    restore_module.SaveRestoreTransaction._verify_target_paths = replace_directory_at_transaction_boundary
    try:
        try:
            service.replace_files((replacement,))
        except SaveRestoreError:
            pass
        else:
            raise AssertionError("same-path physical directory replacement was accepted")
    finally:
        restore_module.SaveRestoreTransaction._verify_target_paths = real_verify_target_paths
    assert swapped[0], "directory replacement did not reach the transaction boundary"
    assert (departed / "slot.dat").read_bytes() == baseline
    assert (selected / "slot.dat").read_bytes() == candidate
    assert not list((service.store.ensure_storage_root() / "transactions").glob(".rollback-*"))

with tempfile.TemporaryDirectory(prefix="mgt-directory-write-race-") as temporary:
    folder = Path(temporary)
    saves = folder / "saves"
    selected, other = saves / "selected", saves / "other"
    selected.mkdir(parents=True)
    other.mkdir()
    target, unselected = selected / "slot.dat", other / "slot.dat"
    baseline = b"latest selected bytes before Apply"
    target.write_bytes(baseline)
    unselected.write_bytes(b"unselected directory must never be touched")
    spec = SaveManagementSpec(roots=(SaveRootSpec("files", str(saves), ("selected/*.dat",)),),
        provider=None, hot_backup=False, restore_policy="stoppedOnly", staged_restore=False)
    service = CoreSaveService("directory-race", spec, folder / "data", lambda: False)
    prepared = folder / "prepared.dat"
    prepared.write_bytes(b"fixed edited source")
    replacement = ResolvedSaveFile("files", "selected/slot.dat", prepared)
    captured = target.resolve()
    real_replace = restore_module.os.replace
    redirected = False

    def redirect_at_mutation(source, destination, **options):
        global redirected
        if Path(destination).name == "slot.dat" and not redirected:
            redirected = True
            selected.rename(saves / "departed")
            selected.symlink_to(other, target_is_directory=True)
        return real_replace(source, destination, **options)

    restore_module.os.replace = redirect_at_mutation
    try:
        try:
            service.replace_files((replacement,), expected_paths={('files', 'selected/slot.dat'): captured})
        except SaveRollbackError as error:
            recovery = Path(error.recovery_path)
        else:
            raise AssertionError("late directory redirection reported a successful write/rollback")
    finally:
        restore_module.os.replace = real_replace
    assert redirected, "directory race did not reach the actual mutation boundary"
    assert unselected.read_bytes() == b"unselected directory must never be touched"
    assert (saves / "departed/slot.dat").read_bytes() == baseline
    assert (recovery / "files/files/selected/slot.dat").read_bytes() == baseline
    assert str(recovery.resolve()) in service.list_state()["recoveryPaths"]
    assert prepared.read_bytes() == b"fixed edited source"

with tempfile.TemporaryDirectory(prefix="mgt-directory-validation-race-") as temporary:
    folder = Path(temporary)
    saves = folder / "saves"
    selected, other = saves / "selected", saves / "other"
    selected.mkdir(parents=True)
    other.mkdir()
    target, unselected = selected / "slot.dat", other / "slot.dat"
    target.write_bytes(b"latest pre-write baseline")
    candidate = b"identical candidate bytes in different physical directories"
    unselected.write_bytes(candidate)
    prepared = folder / "prepared.dat"
    prepared.write_bytes(candidate)
    spec = SaveManagementSpec(roots=(SaveRootSpec("files", str(saves), ("selected/*.dat",)),),
        provider=None, hot_backup=False, restore_policy="stoppedOnly", staged_restore=False)
    service = CoreSaveService("validation-race", spec, folder / "data", lambda: False)
    captured = target.resolve()
    verified = False

    def redirect_after_validating_installed_bytes():
        global verified
        assert target.read_bytes() == candidate
        verified = True
        selected.rename(saves / "departed")
        selected.symlink_to(other, target_is_directory=True)

    try:
        service.replace_files((ResolvedSaveFile("files", "selected/slot.dat", prepared),),
            expected_paths={('files', 'selected/slot.dat'): captured},
            post_install_verify=redirect_after_validating_installed_bytes)
    except SaveRollbackError as error:
        recovery = Path(error.recovery_path)
    else:
        raise AssertionError("matching content hid a physical target change during validation")
    assert verified
    assert unselected.read_bytes() == candidate
    assert (saves / "departed/slot.dat").read_bytes() == b"latest pre-write baseline"
    assert (recovery / "files/files/selected/slot.dat").read_bytes() == b"latest pre-write baseline"
    assert str(recovery.resolve()) in service.list_state()["recoveryPaths"]

with tempfile.TemporaryDirectory(prefix="mgt-save-directory-budget-") as temporary:
    folder = Path(temporary)
    saves = folder / "saves"
    saves.mkdir()
    for index in range(64):
        (saves / f"slot-{index}.dat").write_bytes(f"original-{index}".encode())
    spec = SaveManagementSpec(roots=(SaveRootSpec("files", str(saves), ("*.dat",)),),
        provider=None, hot_backup=False, restore_policy="stoppedOnly", staged_restore=False)
    service = CoreSaveService("many-files-one-directory", spec, folder / "data", lambda: False)
    snapshot = service.backup()["id"]
    for path in saves.iterdir():
        path.write_bytes(b"newer contents")
    limits = resource.getrlimit(resource.RLIMIT_NOFILE)
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (32, limits[1]))
        result = service.restore(snapshot, preserve_current=False)
    finally:
        resource.setrlimit(resource.RLIMIT_NOFILE, limits)
    assert result["restored"] is True
    assert all((saves / f"slot-{index}.dat").read_bytes() == f"original-{index}".encode() for index in range(64))

with tempfile.TemporaryDirectory(prefix="mgt-source-read-identity-") as temporary:
    folder = Path(temporary)
    saves = folder / "saves"
    saves.mkdir()
    target = saves / "slot.dat"
    target.write_bytes(b"authorized regular source")
    other = folder / "unselected.dat"
    other.write_bytes(b"unselected fixture bytes")
    spec = SaveManagementSpec(roots=(SaveRootSpec("files", str(saves), ("*.dat",)),),
        provider=None, hot_backup=False, restore_policy="stoppedOnly", staged_restore=False)
    service = CoreSaveService("source-read-identity", spec, folder / "data", lambda: False)
    snapshot = service.backup()["id"]
    for snapshot_id in (None, snapshot):
        source_path = target if snapshot_id is None else Path(service.folder(snapshot)) / "files/files/slot.dat"
        real_open = resolution_module.os.open
        changed = False

        def redirect_source_before_open(path, flags, *args, **options):
            global changed
            if Path(path).name == "slot.dat" and not changed:
                changed = True
                source_path.unlink()
                source_path.symlink_to(other)
            return real_open(path, flags, *args, **options)

        resolution_module.os.open = redirect_source_before_open
        try:
            try:
                service.read_source_file("files", "slot.dat", snapshot_id)
            except (SaveResolutionError, SaveSnapshotError):
                pass
            else:
                raise AssertionError("source read followed a replacement symbolic link")
        finally:
            resolution_module.os.open = real_open
            source_path.unlink()
            source_path.write_bytes(b"authorized regular source")
        assert changed, "source identity case did not reach its actual open boundary"
        assert other.read_bytes() == b"unselected fixture bytes"

with tempfile.TemporaryDirectory(prefix="mgt-rollback-final-directory-") as temporary:
    folder = Path(temporary)
    saves = folder / "saves"
    selected, other = saves / "selected", saves / "other"
    selected.mkdir(parents=True)
    other.mkdir()
    target, unselected = selected / "slot.dat", other / "slot.dat"
    baseline = b"identical baseline bytes in distinct directories"
    target.write_bytes(baseline)
    unselected.write_bytes(baseline)
    prepared = folder / "prepared.dat"
    prepared.write_bytes(b"edited candidate")
    spec = SaveManagementSpec(roots=(SaveRootSpec("files", str(saves), ("selected/*.dat",)),),
        provider=None, hot_backup=False, restore_policy="stoppedOnly", staged_restore=False)
    service = CoreSaveService("rollback-final-directory", spec, folder / "data", lambda: False)
    captured = target.resolve()
    real_hash = restore_module._sha256
    rollback_requested = False
    changed = False

    def fail_after_install():
        global rollback_requested
        rollback_requested = True
        raise OSError("fixture requested rollback after install")

    def redirect_after_final_rollback_read(path):
        global changed
        digest = real_hash(path)
        if rollback_requested and not changed and Path(path) == target:
            assert target.read_bytes() == baseline
            changed = True
            selected.rename(saves / "departed")
            selected.symlink_to(other, target_is_directory=True)
        return digest

    restore_module._sha256 = redirect_after_final_rollback_read
    try:
        try:
            service.replace_files((ResolvedSaveFile("files", "selected/slot.dat", prepared),),
                expected_paths={('files', 'selected/slot.dat'): captured}, post_install_verify=fail_after_install)
        except SaveRollbackError as error:
            recovery = Path(error.recovery_path)
        else:
            raise AssertionError("rollback cleanup proceeded after its directory identity changed")
    finally:
        restore_module._sha256 = real_hash
    assert changed, "directory change did not reach the final rollback read"
    assert unselected.read_bytes() == baseline
    assert (saves / "departed/slot.dat").read_bytes() == baseline
    assert (recovery / "files/files/selected/slot.dat").read_bytes() == baseline
    assert str(recovery.resolve()) in service.list_state()["recoveryPaths"]

print("core_save_file_sources_ok")
