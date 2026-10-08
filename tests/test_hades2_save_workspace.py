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


def _save_bytes(timestamp, resources=None, stats=None, extra=None, state=None):
    game_state = {
        "Resources": _table(resources or {"MetaCurrency": 123.0}),
        "GameplayTime": 123.5,
        "TotalTime": 456.25,
        "TotalRequiredEnemyKills": 789.0,
        "UnknownFutureField": _table(extra or {"KeepMe": "yes"}),
    }
    if stats is not None:
        game_state.update(stats)
    if state is not None:
        game_state.update(state)
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


def _environment(name, *, include_temp=False, running=False, resources=None, stats=None, extra=None, state=None):
    base = Path(tempfile.mkdtemp(prefix="mgt-save-workspace-")) / name
    saves = base / "saves"
    saves.mkdir(parents=True)
    (saves / "activeProfile").write_bytes(_active_profile())
    (saves / "Profile1.sav").write_bytes(
        _save_bytes(100, resources=resources, stats=stats, extra=extra, state=state)
    )
    if include_temp:
        (saves / "Profile1_Temp.sav").write_bytes(
            _save_bytes(200, resources=resources, stats=stats, extra=extra, state=state)
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

# Explicitly verified narrative records are editable; arbitrary GameState flags
# are not promoted to write access, and gift-tied lines remain immutable.
narrative_state = {
    "Flags": _table({
        "HasShuffledMusicPlayer": True,
        "UnsupportedHiddenFlag": True,
    }),
    "TextLinesRecord": _table({"NormalScene": True, "GiftLine": True}),
    "TextLinesChoiceRecord": _table({"NormalScene": "ChoiceA"}),
    "GiftTextLinesOrderRecord": _table({
        "Hecate": LuaTable(1, 0, [(1.0, "GiftLine")]),
    }),
    "QuestStatus": _table({"QuestA": "Unlocked", "QuestB": "CashedOut"}),
    "QuestsCompleted": _table({"QuestB": True}),
}
_base, narrative_saves, narrative_service = _environment("narrative", state=narrative_state)
narrative = Hades2SaveWorkspace.open(narrative_service)
flags = narrative.query(domain="flags", search="HasPinnedAnyBoon", language="en")
assert flags["total"] == 1
assert flags["items"][0]["value"] is False
assert flags["items"][0]["group"] == "Tutorial and presentation records"
dialogue = narrative.query(domain="dialogue", limit=10, language="zh-CN")
assert {row["rawId"] for row in dialogue["items"]} == {"NormalScene", "GiftLine"}
assert next(row for row in dialogue["items"] if row["rawId"] == "GiftLine")["editable"] is False
quests = narrative.query(domain="progression", limit=10, language="en")
assert quests["total"] == 2
assert next(row for row in quests["items"] if row["rawId"] == "QuestA")["choices"] == [
    "Unlocked", "Complete"
]
assert next(row for row in quests["items"] if row["rawId"] == "QuestB")["editable"] is False
for identity, action, value in (
    ("flag:UnsupportedHiddenFlag", "set", False),
    ("dialogue:GiftLine", "set", False),
    ("quest:QuestB", "setEnum", "Unlocked"),
    ("quest:QuestA", "setEnum", "CashedOut"),
    ("quest:QuestA", "set", "Complete"),
    ("flag:HasPinnedAnyBoon", "set", 1),
):
    try:
        narrative.stage(identity, action, value)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid narrative mutation accepted: " + identity)

narrative.stage("flag:HasPinnedAnyBoon", "set", True)
narrative.stage("flag:HasShuffledMusicPlayer", "set", False)
narrative.stage("dialogue:NormalScene", "set", False)
narrative.stage("quest:QuestA", "setEnum", "Complete")
changes = narrative.review()["changes"]
assert len(changes) == 6, changes  # four intents and two necessary linked effects
assert {row["id"] for row in changes if row["id"].startswith("linked:")} == {
    "linked:quest:QuestA", "linked:dialogue:NormalScene"
}
narrative.apply()
installed_narrative = Hades2SaveDocument.load(narrative_saves / "Profile1.sav")
game = installed_narrative.lua_state["GameState"]
assert game["Flags"]["HasPinnedAnyBoon"] is True
assert game["Flags"].get("HasShuffledMusicPlayer") is None
assert game["Flags"]["UnsupportedHiddenFlag"] is True
assert game["TextLinesRecord"].get("NormalScene") is None
assert game["TextLinesRecord"]["GiftLine"] is True
assert game["TextLinesChoiceRecord"].get("NormalScene") is None
assert game["QuestStatus"]["QuestA"] == "Complete"
assert game["QuestsCompleted"]["QuestA"] is True
assert game["QuestStatus"]["QuestB"] == "CashedOut"
assert game["UnknownFutureField"]["KeepMe"] == "yes"

# Relationship history has a native chronological array and a global
# gift-resource aggregate. A count edit must keep all three states coherent.
gift_npc = LuaTable(3, 2, [
    (1.0, "GiftPoints"), (2.0, "MedeaPoints"), (3.0, "GiftPoints"),
    ("GiftPoints", 2.0), ("MedeaPoints", 1.0),
])
long_term_state = {
    "NPCInteractions": _table({"Hecate": 2.0}),
    "GiftRecord": _table({"Hecate": gift_npc}),
    "GiftResourceRecord": _table({"GiftPoints": 5.0, "MedeaPoints": 1.0}),
    "MetaUpgradeState": _table({
        "ChanneledCast": _table({"Unlocked": True, "Equipped": True, "Level": 2.0}),
        "BonusHealth": _table({"Level": 1.0}),
        "UnknownHiddenCard": _table({"Unlocked": True, "Level": 17.0}),
    }),
    "ObjectivesCompleted": _table({"GiftPrompt": 2.0}),
    "CompletedObjectiveSets": _table({}),
}
_base, long_term_saves, long_term_service = _environment("long_term", state=long_term_state)
long_term = Hades2SaveWorkspace.open(long_term_service)
rels = long_term.query(domain="relationships", language="en")
assert {entry["id"] for entry in rels["items"]} == {
    "interaction:Hecate", "gift:Hecate:GiftPoints", "gift:Hecate:MedeaPoints"
}
assert all(row["editable"] for row in rels["items"])
progress = long_term.query(domain="progression", language="en")
assert {row["id"] for row in progress["items"]} == {
    "card:ChanneledCast:Unlocked", "card:ChanneledCast:Level",
    "card:BonusHealth:Unlocked", "card:BonusHealth:Level",
    "objective:GiftPrompt",
}
assert all(row["id"] != "card:UnknownHiddenCard:Level" for row in progress["items"])
for identity, value in (
    ("gift:Hecate:GiftPoints", -1),
    ("card:ChanneledCast:Level", 4),
    ("card:BonusHealth:Unlocked", 1),
    ("interaction:Hecate", True),
    ("objective:Unknown", 4),
):
    try:
        long_term.stage(identity, "set", value)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid long-term edit accepted: " + identity)

long_term.stage("interaction:Hecate", "set", 5)
long_term.stage("gift:Hecate:GiftPoints", "set", 3)
long_term.stage("card:ChanneledCast:Unlocked", "set", False)
long_term.stage("objective:GiftPrompt", "set", 3)
review = long_term.review()
assert review["count"] == 8, review
assert {item["id"] for item in review["changes"] if item["id"].startswith("linked:")} == {
    "linked:giftTotal:GiftPoints", "linked:giftOrder:Hecate",
    "linked:card:ChanneledCast:Equipped", "linked:card:ChanneledCast:Level"
}
long_term.apply()
edited = Hades2SaveDocument.load(long_term_saves / "Profile1.sav").lua_state["GameState"]
assert edited["NPCInteractions"]["Hecate"] == 5
record = edited["GiftRecord"]["Hecate"]
assert record["GiftPoints"] == 3
assert [value for key, value in record.entries() if type(key) is float] == [
    "GiftPoints", "MedeaPoints", "GiftPoints", "GiftPoints"
]
assert edited["GiftResourceRecord"]["GiftPoints"] == 6
arcana = edited["MetaUpgradeState"]["ChanneledCast"]
assert arcana.get("Unlocked") is None
assert arcana.get("Equipped") is None
assert arcana["Level"] == 1
assert edited["ObjectivesCompleted"]["GiftPrompt"] == 3
assert edited["MetaUpgradeState"]["UnknownHiddenCard"]["Level"] == 17
assert edited["UnknownFutureField"]["KeepMe"] == "yes"

# A later decrease retains the order of unrelated gift resources and removes
# only the newest matching entries; the global gift aggregate decreases too.
again = Hades2SaveWorkspace.open(long_term_service)
again.stage("gift:Hecate:GiftPoints", "set", 1)
again.apply()
edited = Hades2SaveDocument.load(long_term_saves / "Profile1.sav").lua_state["GameState"]
assert edited["GiftRecord"]["Hecate"]["GiftPoints"] == 1
assert [value for key, value in edited["GiftRecord"]["Hecate"].entries()
        if type(key) is float] == ["GiftPoints", "MedeaPoints"]
assert edited["GiftResourceRecord"]["GiftPoints"] == 4

# A card cannot be upgraded while locked, even when a batch also edits its
# unlocked state. Reject the whole candidate before crossing Core Save.
bad = Hades2SaveWorkspace.open(long_term_service)
bad.stage("card:BonusHealth:Level", "set", 2)
before_bad = (long_term_saves / "Profile1.sav").read_bytes()
try:
    bad.apply()
except ValueError:
    pass
else:
    raise AssertionError("upgrading locked Arcana was accepted")
assert (long_term_saves / "Profile1.sav").read_bytes() == before_bad
bad.cancel()
bad.stage("card:BonusHealth:Unlocked", "set", True)
bad.stage("card:BonusHealth:Level", "set", 2)
bad.apply()
edited = Hades2SaveDocument.load(long_term_saves / "Profile1.sav").lua_state["GameState"]
assert edited["MetaUpgradeState"]["BonusHealth"]["Unlocked"] is True
assert edited["MetaUpgradeState"]["BonusHealth"]["Level"] == 2

print("hades2_save_workspace_ok")
