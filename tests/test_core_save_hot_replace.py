import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.module_manifest import SaveManagementSpec, SaveRootSpec
from core.save_resolution import ResolvedSaveFile
from core.save_restore import SaveBusyError, SaveRestoreError
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


# A running writer that changes the target after installation cannot be
# reported as success. The transaction restores its captured pre-write state;
# if rollback itself ever fails, the existing transaction layer preserves the
# contained recovery directory.
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
    assert current.read_bytes() == b"current"
    assert len(service.list_state()["snapshots"]) == 1


print("core_save_hot_replace_ok")
