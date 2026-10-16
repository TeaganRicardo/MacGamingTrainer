import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.module_manifest import SaveManagementSpec, SaveRootSpec
from core.save_service import CoreSaveService
from games.hades2.save_document import Hades2SaveDocument, Hades2SaveHeader, LuaTable
from games.hades2.save_provider import Hades2SaveProvider
from games.hades2.save_workspace import Hades2SaveWorkspace


def _table(values):
    return LuaTable(0, len(values), list(values.items()))


def _save_bytes(timestamp, meta_currency, marker):
    game_state = _table({
        "Resources": _table({"MetaCurrency": float(meta_currency)}),
        "GameplayTime": 100.0,
        "TotalTime": 200.0,
        "TotalRequiredEnemyKills": 300.0,
        "UnknownFutureField": _table({"Marker": marker}),
    })
    root = _table({"GameState": game_state, "CurrentRun": _table({})})
    header = Hades2SaveHeader(
        game_version=0x12,
        save_flags=0,
        timestamp=timestamp,
        location="Crossroads",
        completed_runs=12,
        accumulated_meta_points=34,
        active_shrine_points=5,
        meta_upgrade_level=20,
        cosmetics_points=7,
        easy_mode=0,
        hard_mode=0,
        notable_lua_data=("GameState", "CurrentRun"),
        map_name="Hub_Main",
        next_map_name="F_Opening01",
    )
    return Hades2SaveDocument(header, [root]).to_bytes()


def _active_profile(name):
    raw = name.encode("utf-8")
    return b"SGB1" + struct.pack("<I", len(raw)) + raw


base_directory = tempfile.TemporaryDirectory(prefix="mgt-managed-backup-editor-")
base = Path(base_directory.name)
saves = base / "saves"
saves.mkdir(parents=True)
(saves / "activeProfile").write_bytes(_active_profile("Profile2"))
(saves / "Profile1.sav").write_bytes(_save_bytes(100, 1, "profile-one"))
(saves / "Profile2.sav").write_bytes(_save_bytes(200, 20, "managed-backup-source"))
(saves / "Profile3.sav").write_bytes(_save_bytes(300, 3, "profile-three"))

spec = SaveManagementSpec(
    roots=(SaveRootSpec("main", str(saves), ("Profile*.sav", "activeProfile", "saveinfo")),),
    provider="games.hades2.save_provider:Hades2SaveProvider",
    hot_backup=True,
    restore_policy="hotPreferred",
    staged_restore=True,
)
service = CoreSaveService(
    "hades2",
    spec,
    base / "data",
    lambda: False,
    provider_loader=lambda _target: Hades2SaveProvider(),
)

backup = service.backup()
snapshot_id = backup["id"]
snapshot_folder = Path(service.folder(snapshot_id))
source_path = snapshot_folder / "files" / "main" / "Profile2.sav"
source_before = source_path.read_bytes()

# The backup captured Profile2 as its selected source version. Live selection
# has since moved elsewhere, so the physical Profile2 target is non-active.
(saves / "activeProfile").write_bytes(_active_profile("Profile1"))
(saves / "Profile2.sav").write_bytes(_save_bytes(400, 400, "newer-before-open"))

workspace = Hades2SaveWorkspace.open(service, snapshot_id=snapshot_id)
summary = workspace.summary()
assert summary["profile"] == "Profile2"
assert summary["source"] == {
    "kind": "managedBackup",
    "snapshotId": snapshot_id,
    "rootId": "main",
    "relativePath": "Profile2.sav",
}
assert summary["target"] == {
    "rootId": "main",
    "relativePath": "Profile2.sav",
}

source_state = workspace.document.lua_state["GameState"]
assert source_state["Resources"]["MetaCurrency"] == 20.0
assert source_state["UnknownFutureField"]["Marker"] == "managed-backup-source"
workspace.stage("resource:MetaCurrency", "set", 77)

# Neither an active-profile switch nor a still-newer target version rebases the
# already-open static edit session.
(saves / "activeProfile").write_bytes(_active_profile("Profile3"))
(saves / "Profile2.sav").write_bytes(_save_bytes(500, 500, "newer-after-open"))
result = workspace.apply()
assert result["previousSnapshotId"]

installed = Hades2SaveDocument.load(saves / "Profile2.sav").lua_state["GameState"]
assert installed["Resources"]["MetaCurrency"] == 77.0
assert installed["UnknownFutureField"]["Marker"] == "managed-backup-source"

# Opening/editing a managed backup never mutates the backup itself.
assert source_path.read_bytes() == source_before
listed = {row["id"]: row for row in service.list_state()["snapshots"]}
assert listed[snapshot_id]["valid"] is True

print("hades2_managed_backup_save_editor_ok")
base_directory.cleanup()

# Exercise the game command boundary, the same workspace, and the real Core
# transaction. Runtime transport/preferences remain isolated in this fixture.
import json
import os
import core.save_restore as restore_module
from core.save_restore import SaveRestoreError, SaveRollbackError
from core.save_snapshots import SaveSnapshotError
from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter
from games.hades2.command_contract import Hades2CommandContract


def identity(path, root="main"):
    return {"rootId": root, "relativePath": path}


def environment(folder):
    root = folder / "saves"
    root.mkdir()
    (root / "activeProfile").write_bytes(_active_profile("Profile2"))
    for index in range(1, 4):
        (root / f"Profile{index}.sav").write_bytes(_save_bytes(index * 100, index * 10, f"source-{index}"))
    (root / "Profile2_Temp.sav").write_bytes(_save_bytes(210, 21, "temp-source"))
    (root / "Profile2_Archive.sav").write_bytes(_save_bytes(220, 22, "variant-source"))
    (root / "Profile2.v.sav").write_bytes(b"validation-marker")
    (root / "Profile7_Invalid.sav").write_bytes(b"not a structured save")
    state = {"running": False}
    spec = SaveManagementSpec(
        roots=(SaveRootSpec("main", str(root), ("Profile*.sav", "activeProfile")),),
        provider="games.hades2.save_provider:Hades2SaveProvider", hot_backup=True,
        restore_policy="hotPreferred", staged_restore=True,
    )
    service = CoreSaveService("hades2", spec, folder / "data", lambda: state["running"],
        provider_loader=lambda _: Hades2SaveProvider(game_path=folder / "AbsentGame.app"))
    prior_data = preparation.DATA
    preparation.DATA = folder / "preferences"
    try:
        adapter = Hades2Adapter(transport=object(), time_warp_controller=object())
    finally:
        preparation.DATA = prior_data
    adapter.bind_save_service(service)
    return root, service, state, adapter


def request(adapter, command, **params):
    return json.loads(json.dumps(adapter.command_contract.dispatch(
        command, json.loads(json.dumps(params)), "fixture-request")))


def contents(folder):
    return {str(path.relative_to(folder)): path.read_bytes() for path in folder.rglob("*") if path.is_file()}


def resource(path):
    return Hades2SaveDocument.load(path).lua_state["GameState"]["Resources"]["MetaCurrency"]


with tempfile.TemporaryDirectory(prefix="mgt-backup-selection-") as temporary:
    folder = Path(temporary)
    saves, service, state, adapter = environment(folder)
    stamp = 1_700_000_000_000_000_000
    os.utime(saves / "Profile2.sav", ns=(stamp, stamp))
    os.utime(saves / "Profile2.v.sav", ns=(stamp + 100, stamp + 100))
    backup = service.backup()
    snapshot = backup["id"]
    snapshot_folder = Path(service.folder(snapshot))
    preserved = contents(snapshot_folder)
    inventory = request(adapter, "save_editor_inventory", snapshotId=snapshot)
    assert inventory["defaultSource"] == identity("Profile2_Temp.sav")
    sources = {row["relativePath"] for row in inventory["sources"]}
    assert "Profile2_Archive.sav" in sources and "Profile7_Invalid.sav" not in sources
    assert not {"activeProfile", "Profile2.v.sav"} & sources
    assert identity("Profile3.sav") in [{k: row[k] for k in ("rootId", "relativePath")} for row in inventory["targets"]]

    # Temp and extra codec-supported variants use the same workspace/commands.
    for source, expected in (("Profile2_Temp.sav", 21), ("Profile2_Archive.sav", 22)):
        opened = request(adapter, "save_editor_open", snapshotId=snapshot,
            source=identity(source), target=identity("Profile1.sav"))
        assert opened["source"]["relativePath"] == source and opened["target"] == identity("Profile1.sav")
        owner = opened["workspaceId"]
        request(adapter, "save_editor_stage", workspaceId=owner, entryId="resource:MetaCurrency", operation="set", value=expected + 1)
        request(adapter, "save_editor_apply", workspaceId=owner)
        assert resource(saves / "Profile1.sav") == expected + 1
    assert contents(snapshot_folder) == preserved

    opened = request(adapter, "save_editor_open", snapshotId=snapshot,
        source=identity("Profile2.sav"), target=identity("Profile1.sav"))
    owner = opened["workspaceId"]
    source_sha = opened["sourceSHA256"]
    (saves / "activeProfile").write_bytes(_active_profile("Profile3"))
    (saves / "Profile1.sav").write_bytes(_save_bytes(500, 500, "new-target-one"))
    (saves / "Profile3.sav").write_bytes(_save_bytes(600, 600, "new-target-three"))

    # Browsing, staging, reviewing and cancelling never read the source again.
    original_sources, original_read = service.source_files, service.read_source_file
    def no_reparse(*args, **kwargs):
        raise AssertionError("a pinned document was silently read again")
    service.source_files = service.read_source_file = no_reparse
    rows = request(adapter, "save_editor_query", workspaceId=owner, domain="resources")["items"]
    assert next(row for row in rows if row["rawId"] == "MetaCurrency")["value"] == 20
    request(adapter, "save_editor_stage", workspaceId=owner, entryId="resource:MetaCurrency", operation="set", value=77)
    assert request(adapter, "save_editor_review", workspaceId=owner)["changes"][0]["before"] == 20
    request(adapter, "save_editor_cancel", workspaceId=owner)
    assert adapter.save_workspace.document.lua_state["GameState"]["Resources"]["MetaCurrency"] == 20
    request(adapter, "save_editor_stage", workspaceId=owner, entryId="resource:MetaCurrency", operation="set", value=88)
    selected = request(adapter, "save_editor_target", workspaceId=owner, target=identity("Profile3.sav"))
    assert selected["workspaceId"] == owner and selected["sourceSHA256"] == source_sha
    assert selected["source"] == opened["source"] and selected["pendingCount"] == 1
    result = request(adapter, "save_editor_apply", workspaceId=owner)
    assert resource(saves / "Profile3.sav") == 88 and resource(saves / "Profile1.sav") == 500
    installed = Hades2SaveDocument.load(saves / "Profile3.sav")
    assert installed.lua_state["GameState"]["UnknownFutureField"]["Marker"] == "source-2"
    installed.lua_state["GameState"]["Resources"]["MetaCurrency"] = 20
    assert installed.to_bytes() == preserved["files/main/Profile2.sav"], "unknown payload/header bytes were lost"
    previous = service.store.load_verified_snapshot(result["previousSnapshotId"])
    assert resource(previous["root"] / "files/main/Profile3.sav") == 600
    assert contents(snapshot_folder) == preserved
    service.source_files, service.read_source_file = original_sources, original_read

    # A different explicit source owns later commands; the prior view cannot
    # stage or apply into it even though semantic entry IDs happen to match.
    newer = request(adapter, "save_editor_open", source=identity("Profile1.sav"), target=identity("Profile3.sav"))
    for command, params in (("save_editor_stage", {"entryId": "resource:MetaCurrency", "operation": "set", "value": 999}),
                            ("save_editor_apply", {})):
        try:
            request(adapter, command, workspaceId=owner, **params)
        except Exception as error:
            assert "no longer selected" in str(getattr(error, "diagnostic", None) or error)
        else:
            raise AssertionError("departed frontend adopted a different document")
    assert newer["workspaceId"] != owner and adapter.save_workspace.review()["count"] == 0


with tempfile.TemporaryDirectory(prefix="mgt-backup-recovery-") as temporary:
    folder = Path(temporary)
    saves, service, state, adapter = environment(folder)
    snapshot = service.backup()["id"]
    original_backup = contents(Path(service.folder(snapshot)))
    workspace = Hades2SaveWorkspace.open(service, snapshot_id=snapshot,
        source=identity("Profile2.sav"), target=identity("Profile3.sav"))
    workspace.stage("resource:MetaCurrency", "set", 91)
    latest = _save_bytes(700, 700, "latest-before-hot-write")
    (saves / "Profile3.sav").write_bytes(latest)
    state["running"] = True
    hot_result = workspace.apply()
    assert hot_result["hot"] is True
    assert hot_result["runtimeReloaded"] is False
    assert resource(saves / "Profile3.sav") == 91
    installed_hot = Hades2SaveDocument.load(saves / "Profile3.sav")
    assert installed_hot.lua_state["GameState"]["UnknownFutureField"]["Marker"] == "source-2"
    hot_previous = service.store.load_verified_snapshot(hot_result["previousSnapshotId"])
    assert (hot_previous["root"] / "files/main/Profile3.sav").read_bytes() == latest
    assert workspace.review()["count"] == 0
    state["running"] = False

    # Recovery behavior remains identical after the successful hot write. Open a
    # fresh pinned workspace so the failure cases below start from known intent.
    workspace = Hades2SaveWorkspace.open(service, snapshot_id=snapshot,
        source=identity("Profile2.sav"), target=identity("Profile3.sav"))
    workspace.stage("resource:MetaCurrency", "set", 92)
    post_hot = (saves / "Profile3.sav").read_bytes()

    original_install = restore_module.SaveRestoreTransaction._replace_file
    calls = [0]
    def fail_after_install(self, source, destination, digest, **options):
        calls[0] += 1
        original_install(self, source, destination, digest, **options)
        if calls[0] == 1:
            raise OSError("fixture failed after install")
    restore_module.SaveRestoreTransaction._replace_file = fail_after_install
    try:
        try:
            workspace.apply()
        except SaveRestoreError:
            pass
        else:
            raise AssertionError("failed install reported success")
    finally:
        restore_module.SaveRestoreTransaction._replace_file = original_install
    assert (saves / "Profile3.sav").read_bytes() == post_hot
    assert workspace.review()["count"] == 1
    assert workspace.document.lua_state["GameState"]["Resources"]["MetaCurrency"] == 20
    assert contents(Path(service.folder(snapshot))) == original_backup

    def fail_install_and_rollback(self, source, destination, digest, **options):
        if calls[0] > 0:
            calls[0] = 0
            original_install(self, source, destination, digest, **options)
        raise OSError("fixture cannot complete install or rollback")
    calls[0] = 1
    restore_module.SaveRestoreTransaction._replace_file = fail_install_and_rollback
    try:
        try:
            workspace.apply()
        except SaveRollbackError as error:
            recovery = Path(error.recovery_path)
        else:
            raise AssertionError("rollback failure reported success")
    finally:
        restore_module.SaveRestoreTransaction._replace_file = original_install
    assert recovery.is_dir() and (recovery / "files/main/Profile3.sav").read_bytes() == post_hot
    assert str(recovery.resolve()) in service.list_state()["recoveryPaths"]
    assert workspace.review()["count"] == 1 and contents(Path(service.folder(snapshot))) == original_backup


with tempfile.TemporaryDirectory(prefix="mgt-backup-identity-") as temporary:
    folder = Path(temporary)
    saves, service, state, adapter = environment(folder)
    snapshot = service.backup()["id"]
    workspace = Hades2SaveWorkspace.open(service, snapshot_id=snapshot,
        source=identity("Profile2.sav"), target=identity("Profile3.sav"))
    workspace.stage("resource:MetaCurrency", "set", 92)
    # A changed contained backup also cannot silently rebase the open document;
    # it is rejected only if the user explicitly opens that source again.
    source_path = Path(service.folder(snapshot)) / "files/main/Profile2.sav"
    source_path.write_bytes(_save_bytes(800, 800, "tampered-source"))
    assert workspace.review()["changes"][0]["before"] == 20
    try:
        Hades2SaveWorkspace.open(service, snapshot_id=snapshot)
    except SaveSnapshotError:
        pass
    else:
        raise AssertionError("unverified backup became a new document")
    workspace.apply()
    assert resource(saves / "Profile3.sav") == 92

    # Root/path identity is fixed, content/inode changes are allowed. Rebinding
    # a provider root to a different physical directory must not redirect Apply.
    workspace.stage("resource:MetaCurrency", "set", 93)
    other = folder / "other"
    other.mkdir()
    (other / "Profile3.sav").write_bytes(_save_bytes(900, 900, "other-container"))
    service.spec = SaveManagementSpec(roots=(SaveRootSpec("main", str(other), ("Profile*.sav",)),),
        provider="games.hades2.save_provider:Hades2SaveProvider", hot_backup=True,
        restore_policy="hotPreferred", staged_restore=True)
    try:
        workspace.apply()
    except SaveRestoreError:
        pass
    else:
        raise AssertionError("fixed target silently followed a changed root")
    assert resource(other / "Profile3.sav") == 900 and resource(saves / "Profile3.sav") == 92
    assert workspace.review()["count"] == 1

with tempfile.TemporaryDirectory(prefix="mgt-backup-multiple-roots-") as temporary:
    folder = Path(temporary)
    roots = {name: folder / name for name in ("first", "second")}
    for name, root in roots.items():
        root.mkdir()
        (root / "activeProfile").write_bytes(_active_profile("Profile2"))
        (root / "Profile1.sav").write_bytes(_save_bytes(100, 10, name + "-one"))
        (root / "Profile2.sav").write_bytes(_save_bytes(200, 20 if name == "first" else 90, name + "-two"))
    spec = SaveManagementSpec(
        roots=tuple(SaveRootSpec(name, str(path), ("Profile*.sav", "activeProfile")) for name, path in roots.items()),
        provider="games.hades2.save_provider:Hades2SaveProvider", hot_backup=False,
        restore_policy="stoppedOnly", staged_restore=False,
    )
    service = CoreSaveService("hades2", spec, folder / "data", lambda: False,
        provider_loader=lambda _: Hades2SaveProvider(game_path=folder / "AbsentGame.app"))
    snapshot = service.backup()["id"]
    preserved = contents(Path(service.folder(snapshot)))
    assert Hades2SaveWorkspace.inventory(service, snapshot)["defaultSource"] is None
    try:
        Hades2SaveWorkspace.open(service, snapshot_id=snapshot)
    except ValueError:
        pass
    else:
        raise AssertionError("two root identities silently collapsed into one active source")
    workspace = Hades2SaveWorkspace.open(service, snapshot_id=snapshot,
        source=identity("Profile2.sav", "second"))
    assert workspace.summary()["target"] is None
    assert workspace.document.lua_state["GameState"]["Resources"]["MetaCurrency"] == 90
    workspace.stage("resource:MetaCurrency", "set", 91)
    try:
        workspace.apply()
    except ValueError as error:
        assert "explicitly selected" in str(error)
    else:
        raise AssertionError("explicit source silently chose a target without user selection")
    assert workspace.review()["count"] == 1
    workspace.set_target(identity("Profile1.sav", "first"))
    workspace.apply()
    assert resource(roots["first"] / "Profile1.sav") == 91
    assert resource(roots["second"] / "Profile1.sav") == 10
    assert resource(roots["second"] / "Profile2.sav") == 90
    assert Hades2SaveDocument.load(roots["first"] / "Profile1.sav").lua_state["GameState"]["UnknownFutureField"]["Marker"] == "second-two"
    assert contents(Path(service.folder(snapshot))) == preserved

print("hades2_managed_backup_source_target_and_recovery_ok")
