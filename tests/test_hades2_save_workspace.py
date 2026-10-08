import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.module_manifest import SaveManagementSpec, SaveRootSpec
from core.save_restore import SaveBusyError
from core.save_service import CoreSaveService
from games.hades2.save_document import Hades2SaveDocument, Hades2SaveHeader, LuaTable
from games.hades2.save_provider import Hades2SaveProvider
from games.hades2.save_workspace import Hades2SaveWorkspace


def _table(values):
    return LuaTable(0, len(values), list(values.items()))


def _save_bytes(timestamp, resources=None, stats=None, extra=None):
    game_state = {
        "Resources": _table(resources or {"MetaCurrency": 123.0}),
        "GameplayTime": 123.5,
        "TotalTime": 456.25,
        "TotalRequiredEnemyKills": 789.0,
        "UnknownFutureField": _table(extra or {"KeepMe": "yes"}),
    }
    if stats is not None:
        game_state.update(stats)
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


def _environment(name, *, include_temp=False, running=False, resources=None, stats=None, extra=None):
    base = Path(tempfile.mkdtemp(prefix="mgt-save-workspace-")) / name
    saves = base / "saves"
    saves.mkdir(parents=True)
    (saves / "activeProfile").write_bytes(_active_profile())
    (saves / "Profile1.sav").write_bytes(
        _save_bytes(100, resources=resources, stats=stats, extra=extra)
    )
    if include_temp:
        (saves / "Profile1_Temp.sav").write_bytes(
            _save_bytes(200, resources=resources, stats=stats, extra=extra)
        )
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

# Only independently understood persistent scalar statistics are writable.
# These three identities are owned by current RunLogic / CombatLogic; cache
# fields and arbitrary numeric GameState entries stay outside the descriptor set.
stats = workspace.query(domain="playerStats", offset=0, limit=10, language="en")
assert stats["total"] == 3
by_id = {row["rawId"]: row for row in stats["items"]}
assert set(by_id) == {"GameplayTime", "TotalTime", "TotalRequiredEnemyKills"}
assert by_id["GameplayTime"]["value"] == 123.5
assert by_id["GameplayTime"]["valueType"] == "number"
assert by_id["GameplayTime"]["constraints"] == {"min": 0, "integer": False}
assert by_id["TotalTime"]["value"] == 456.25
assert by_id["TotalRequiredEnemyKills"]["value"] == 789
assert by_id["TotalRequiredEnemyKills"]["valueType"] == "integer"
assert by_id["TotalRequiredEnemyKills"]["constraints"] == {
    "min": 0,
    "max": 9007199254740991,
    "integer": True,
}
assert all(row["editable"] is True for row in stats["items"])
assert all(row["mutationKinds"] == ["set"] for row in stats["items"])

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

# Staging stores typed mutation intent only. The source document stays pinned
# and untouched until one explicit batch Apply crosses the recoverable seam.
original_meta = workspace.document.lua_state["GameState"]["Resources"]["MetaCurrency"]
original_gameplay_time = workspace.document.lua_state["GameState"]["GameplayTime"]
workspace.stage("resource:MetaCurrency", "set", 500)
workspace.stage("resource:GiftPoints", "set", 20)
workspace.stage("playerStat:GameplayTime", "set", 900.5)
assert workspace.document.lua_state["GameState"]["Resources"]["MetaCurrency"] == original_meta
assert workspace.document.lua_state["GameState"]["GameplayTime"] == original_gameplay_time
review = workspace.review()
assert review["count"] == 3
assert review["changes"] == [
    {
        "id": "resource:MetaCurrency",
        "domain": "resources",
        "rawId": "MetaCurrency",
        "operation": "set",
        "before": 123,
        "after": 500,
    },
    {
        "id": "resource:GiftPoints",
        "domain": "resources",
        "rawId": "GiftPoints",
        "operation": "set",
        "before": 9,
        "after": 20,
    },
    {
        "id": "playerStat:GameplayTime",
        "domain": "playerStats",
        "rawId": "GameplayTime",
        "operation": "set",
        "before": 123.5,
        "after": 900.5,
    },
]
workspace.cancel()
assert workspace.review() == {"count": 0, "changes": []}

for entry_id, operation, value in (
    ("resource:MetaCurrency", "set", -1),
    ("resource:MetaCurrency", "set", 1_000_000),
    ("resource:MetaCurrency", "set", 1.5),
    ("resource:MetaCurrency", "unset", None),
    ("playerStat:GameplayTime", "set", -1),
    ("playerStat:GameplayTime", "set", float("inf")),
    ("playerStat:TotalRequiredEnemyKills", "set", 1.5),
    ("playerStat:TotalRequiredEnemyKills", "set", 9_007_199_254_740_992),
    ("playerStat:GameplayTime", "unset", None),
    ("playerStat:UnknownCounter", "set", 1),
    ("advanced:GameState/UnknownFutureField/Item0000", "set", 9),
):
    try:
        workspace.stage(entry_id, operation, value)
    except ValueError:
        pass
    else:
        raise AssertionError("unsupported Save Editor mutation was accepted")

# Version-pinned sessions may be prepared while Hades is running, but Apply
# is cold-only. A newer game-authored save is intentionally preserved as the
# recovery snapshot, then replaced by the edited originally-read document.
_base, pinned_saves, pinned_service = _environment(
    "pinned",
    running=True,
    resources={"MetaCurrency": 123.0, "GiftPoints": 9.0},
    extra={"KeepMe": "A"},
)
pinned = Hades2SaveWorkspace.open(pinned_service)
pinned.stage("resource:MetaCurrency", "set", 500)
pinned.stage("playerStat:GameplayTime", "set", 900.5)
try:
    pinned.apply()
except SaveBusyError:
    pass
else:
    raise AssertionError("running Save Editor apply was not refused")
assert pinned.review()["count"] == 2

newer = _save_bytes(
    300,
    resources={"MetaCurrency": 777.0, "GiftPoints": 88.0},
    stats={"GameplayTime": 3333.0},
    extra={"KeepMe": "B"},
)
pinned_path = pinned_saves / "Profile1.sav"
pinned_path.write_bytes(newer)
pinned_service.target_running_probe = lambda: False
applied = pinned.apply()
assert applied["applied"] is True
assert applied["previousSnapshotId"]
assert pinned.review() == {"count": 0, "changes": []}

installed = Hades2SaveDocument.load(pinned_path)
assert installed.lua_state["GameState"]["Resources"]["MetaCurrency"] == 500.0
assert installed.lua_state["GameState"]["Resources"]["GiftPoints"] == 9.0
assert installed.lua_state["GameState"]["GameplayTime"] == 900.5
assert installed.lua_state["GameState"]["UnknownFutureField"]["KeepMe"] == "A"
previous = pinned_service.store.load_verified_snapshot(applied["previousSnapshotId"])
assert (previous["root"] / "files/main/Profile1.sav").read_bytes() == newer

print("hades2_save_workspace_ok")
