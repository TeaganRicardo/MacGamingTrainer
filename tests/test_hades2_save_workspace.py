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


def _save_bytes(timestamp, resources=None, extra=None):
    game_state = {
        "Resources": _table(resources or {"MetaCurrency": 123.0}),
        "UnknownFutureField": _table(extra or {"KeepMe": "yes"}),
    }
    root = _table({"GameState": _table(game_state), "CurrentRun": _table({})})
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


def _active_profile(name="Profile1"):
    raw = name.encode("utf-8")
    return b"SGB1" + struct.pack("<I", len(raw)) + raw


def _environment(name, *, include_temp=False, running=False, resources=None, extra=None):
    base = Path(tempfile.mkdtemp(prefix="mgt-save-workspace-")) / name
    saves = base / "saves"
    saves.mkdir(parents=True)
    (saves / "activeProfile").write_bytes(_active_profile())
    (saves / "Profile1.sav").write_bytes(_save_bytes(100, resources=resources, extra=extra))
    if include_temp:
        (saves / "Profile1_Temp.sav").write_bytes(_save_bytes(200, resources=resources, extra=extra))
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
        lambda: running,
        provider_loader=lambda _target: Hades2SaveProvider(),
    )
    return base, saves, service


_base, _saves, service = _environment("hub")
hub = Hades2SaveWorkspace.open(service)
assert hub.profile == "Profile1"
assert hub.relative_path == "Profile1.sav"

_base, _saves, service = _environment("run", include_temp=True)
run = Hades2SaveWorkspace.open(service)
assert run.profile == "Profile1"
assert run.relative_path == "Profile1_Temp.sav"

# Resource queries are backend-filtered/paged and expose only descriptor-owned
# editability. The frontend never needs the whole save tree to search this domain.
resources = {
    "MetaCurrency": 123.0,
    "GiftPoints": 9.0,
    "CardUpgradePoints": 7.0,
}
extra = {"Item{:04d}".format(index): float(index) for index in range(1500)}
_base, _saves, service = _environment(
    "query",
    resources=resources,
    extra=extra,
)
workspace = Hades2SaveWorkspace.open(service)
page = workspace.query(domain="resources", search="Points", offset=0, limit=2, language="en")
assert page["domain"] == "resources"
assert page["total"] == 2
assert len(page["items"]) == 2
assert {row["rawId"] for row in page["items"]} == {"GiftPoints", "CardUpgradePoints"}
for row in page["items"]:
    assert row["editable"] is True
    assert row["mutationKinds"] == ["set"]
    assert row["valueType"] == "integer"
    assert row["constraints"] == {"min": 0, "max": 999999, "integer": True}

# Advanced browsing is lazy. Asking for one nested table returns only one page
# of its immediate children, and ungoverned values are read-only.
advanced = workspace.query(
    domain="advanced",
    path=["GameState", "UnknownFutureField"],
    offset=100,
    limit=25,
    language="en",
)
assert advanced["total"] == 1500
assert len(advanced["items"]) == 25
assert advanced["items"][0]["rawId"] == "Item0100"
assert all(row["editable"] is False for row in advanced["items"])
assert all(row["path"][:2] == ["GameState", "UnknownFutureField"] for row in advanced["items"])

print("hades2_save_workspace_ok")
