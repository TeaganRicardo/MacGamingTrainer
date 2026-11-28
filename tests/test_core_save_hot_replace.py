import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.module_manifest import SaveManagementSpec, SaveRootSpec
from core import save_restore
from core.save_resolution import ResolvedSaveFile
from core.save_restore import SaveBusyError, SaveRestoreError, SaveRollbackError
from core.save_service import CoreSaveService


def make_service(folder, running_probe):
    saves = folder / "saves"
    saves.mkdir()
    current = saves / "Profile1.sav"
    current.write_bytes(b"current")
    spec = SaveManagementSpec(
        roots=(SaveRootSpec("main", str(saves), ("*.sav",)),),
        provider=None,
        hot_backup=True,
        restore_policy="hotPreferred",
        staged_restore=True,
    )
    service = CoreSaveService("example", spec, folder / "data", running_probe)
    return service, current


def replacement(folder, payload=b"edited"):
    staged = folder / "replacement.sav"
    staged.write_bytes(payload)
    return ResolvedSaveFile("main", "Profile1.sav", staged)


# Core remains cold by default. A game-owned caller must opt into a running
# replacement explicitly.
with tempfile.TemporaryDirectory(prefix="mgt-core-hot-replace-") as temporary:
    folder = Path(temporary)
    service, current = make_service(folder, lambda: True)
    row = replacement(folder)

    try:
        service.replace_files((row,), expected_paths={("main", "Profile1.sav"): current.resolve()})
    except SaveBusyError:
        pass
    else:
        raise AssertionError("running replacement bypassed the default cold policy")
    assert current.read_bytes() == b"current"
    assert service.list_state()["snapshots"] == []

    result = service.replace_files(
        (row,),
        expected_paths={("main", "Profile1.sav"): current.resolve()},
        allow_running=True,
    )
    assert result["replaced"] is True
    assert result["hot"] is True
    assert current.read_bytes() == b"edited"
    previous = service.store.load_verified_snapshot(result["previousSnapshotId"])
    assert (previous["root"] / "files/main/Profile1.sav").read_bytes() == b"current"


# Opting into hot capability does not turn a cold transaction into a hot one
# after preparation has begun. If the game launches between the service probe
# and mutation, the transaction fails closed.
class LaunchProbe:
    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.calls >= 2


with tempfile.TemporaryDirectory(prefix="mgt-core-hot-launch-race-") as temporary:
    folder = Path(temporary)
    probe = LaunchProbe()
    service, current = make_service(folder, probe)
    row = replacement(folder)
    try:
        service.replace_files(
            (row,),
            expected_paths={("main", "Profile1.sav"): current.resolve()},
            allow_running=True,
        )
    except SaveBusyError:
        pass
    else:
        raise AssertionError("cold replacement silently changed transaction mode after game launch")
    assert current.read_bytes() == b"current"
    assert service.list_state()["snapshots"] == []


# A running writer that rewrites the target after installation keeps its
# newer version live. The verified pre-write state is still in the snapshot.
with tempfile.TemporaryDirectory(prefix="mgt-core-hot-write-race-") as temporary:
    folder = Path(temporary)
    service, current = make_service(folder, lambda: True)
    row = replacement(folder)

    def game_rewrites_after_install():
        current.write_bytes(b"game-race")

    try:
        service.replace_files(
            (row,),
            post_install_verify=game_rewrites_after_install,
            expected_paths={("main", "Profile1.sav"): current.resolve()},
            allow_running=True,
        )
    except SaveRestoreError:
        pass
    else:
        raise AssertionError("hot replacement reported success after a concurrent target rewrite")
    assert current.read_bytes() == b"game-race"
    assert len(service.list_state()["snapshots"]) == 1
    assert not service.recovery_paths()

# The game can hold the pre-swap inode open. Keep it through the normal hot
# verification window and detect a write through that already-open handle.
with tempfile.TemporaryDirectory(prefix="mgt-core-hot-open-writer-") as temporary:
    folder = Path(temporary)
    service, current = make_service(folder, lambda: True)
    row = replacement(folder)
    live_inode = current.stat().st_ino
    with current.open("r+b") as writer:

        def game_finishes_write(_delay):
            writer.write(b"finished-open-write")
            writer.truncate()
            writer.flush()
            os.fsync(writer.fileno())

        with patch.object(save_restore.time, "sleep", side_effect=game_finishes_write):
            try:
                service.replace_files((row,), allow_running=True)
            except SaveRestoreError as error:
                assert "newer live save was preserved" in str(error)
            else:
                raise AssertionError("hot commit discarded a write to the displaced inode")
    assert current.read_bytes() == b"finished-open-write"
    assert current.stat().st_ino == live_inode
    assert not service.recovery_paths()


# A replacement owns only its selected files. A different live profile may
# continue saving, including when a target failure requires rollback. The full
# pre-write snapshot remains available for deliberate whole-set restoration.
for target_race in (True, False):
    with tempfile.TemporaryDirectory(prefix="mgt-core-hot-selected-target-") as temporary:
        folder = Path(temporary)
        service, selected = make_service(folder, lambda: True)
        active = selected.with_name("Profile2.sav")
        active.write_bytes(b"active-before")
        row = replacement(folder)

        def concurrent_game_write():
            active.write_bytes(b"active-new-progress")
            if target_race:
                selected.write_bytes(b"selected-race")

        try:
            result = service.replace_files(
                (row,),
                post_install_verify=concurrent_game_write,
                expected_paths={("main", "Profile1.sav"): selected.resolve()},
                allow_running=True,
            )
        except SaveRestoreError:
            assert target_race, "an unrelated profile write aborted the selected replacement"
        else:
            assert not target_race and result["replaced"]
        assert active.read_bytes() == b"active-new-progress", "rollback overwrote an unselected profile"
        assert selected.read_bytes() == (b"selected-race" if target_race else b"edited")
        snapshot = service.store.load_verified_snapshot(service.list_state()["snapshots"][0]["id"])
        assert (snapshot["root"] / "files/main/Profile1.sav").read_bytes() == b"current"
        assert (snapshot["root"] / "files/main/Profile2.sav").read_bytes() == b"active-before"


# Publish after the final baseline read but before the native rename. Both
# normal entry points recover the exact displaced inode, including its mode.
for action in ("apply", "restore", "restore delete", "restore create"):
    with tempfile.TemporaryDirectory(prefix="mgt-core-hot-displaced-") as temporary:
        folder = Path(temporary)
        service, current = make_service(folder, lambda: True)
        sibling = current.with_name("Profile2.sav")
        sibling.write_bytes(b"unselected")
        if action == "apply":
            incoming = current
            row = replacement(folder)
        else:
            if action == "restore delete":
                incoming = current.with_name("obsolete.sav")
            elif action == "restore create":
                incoming = current.with_name("new-slot.sav")
                incoming.write_bytes(b"snapshot-only")
            else:
                incoming = current
            snapshot_id = service.backup()["id"]
            if action == "restore delete":
                incoming.write_bytes(b"obsolete")
            elif action == "restore create":
                incoming.unlink()
            current.write_bytes(b"present-before-restore")
        sibling_inode = sibling.stat().st_ino
        native = save_restore._rename_hot
        new_inode = []

        def game_saves_in_commit_window(source, destination, directory_fd, *, exchange=False):
            match = source == incoming.name if action == "restore delete" else destination == incoming.name
            if match and not new_inode:
                side = incoming.with_name("native.autosave")
                side.write_bytes(b"latest-save")
                side.chmod(0o640)
                os.replace(side, incoming)
                new_inode.append(incoming.stat().st_ino)
                assert incoming.read_bytes() == b"latest-save"
            return native(source, destination, directory_fd, exchange=exchange)

        with patch.object(save_restore, "_rename_hot", side_effect=game_saves_in_commit_window):
            try:
                if action == "apply":
                    service.replace_files((row,), allow_running=True)
                else:
                    service.restore(snapshot_id, preserve_current=action != "restore delete")
            except SaveRestoreError as error:
                assert not isinstance(error, SaveRollbackError), str(error)
            else:
                raise AssertionError("hot commit ignored a newer save")
        assert new_inode == [incoming.stat().st_ino]
        assert incoming.read_bytes() == b"latest-save"
        assert stat.S_IMODE(incoming.stat().st_mode) == 0o640
        assert sibling.stat().st_ino == sibling_inode
        assert sibling.read_bytes() == b"unselected"
        assert not service.recovery_paths()
        assert not list(incoming.parent.glob(".trainer-save-*"))


# If the game publishes again in the final rollback window, its bytes are
# retained under a name documented by the durable recovery journal.
with tempfile.TemporaryDirectory(prefix="mgt-core-hot-rollback-displaced-") as temporary:
    folder = Path(temporary)
    service, current = make_service(folder, lambda: True)
    row = replacement(folder)
    native = save_restore._rename_hot
    game_writes = []

    def game_saves_before_each_exchange(source, destination, directory_fd, *, exchange=False):
        if exchange and destination == current.name:
            side = current.with_name("native.autosave")
            payload = b"pre-install-save" if not game_writes else b"pre-rollback-save"
            side.write_bytes(payload)
            os.replace(side, current)
            game_writes.append(payload)
        return native(source, destination, directory_fd, exchange=exchange)

    with patch.object(save_restore, "_rename_hot", side_effect=game_saves_before_each_exchange):
        try:
            service.replace_files((row,), allow_running=True)
        except SaveRollbackError as error:
            recovery = Path(error.recovery_path)
        else:
            raise AssertionError("hot rollback did not report its retained competing save")
    assert game_writes == [b"pre-install-save", b"pre-rollback-save"]
    assert current.read_bytes() == b"pre-install-save"
    assert service.recovery_paths() == (str(recovery),)
    evidence = json.loads((recovery / "hot-files.json").read_text())
    assert "concurrently with rollback" in evidence["reason"]
    (held,) = evidence["files"]
    assert held["target"] == str(current.resolve())
    assert Path(held["holdingPath"]).read_bytes() == b"pre-rollback-save"


print("core_save_hot_replace_ok")
