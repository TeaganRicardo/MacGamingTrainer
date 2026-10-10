import os
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


def _environment(name, *, include_temp=False, validation_age=None, running=False, resources=None, stats=None, extra=None, state=None):
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
    if validation_age:
        assert include_temp
        marker = saves / "Profile1.v.sav"
        marker.write_bytes(b"validation-marker")
        fixed = 1_700_000_000_000_000_000
        os.utime(saves / "Profile1.sav", ns=(fixed, fixed))
        stamp = fixed + (2_000_000_000 if validation_age == "new" else -2_000_000_000)
        os.utime(marker, ns=(stamp, stamp))
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

_base, _saves, service = _environment("run", include_temp=True, validation_age="new")
run = Hades2SaveWorkspace.open(service)
assert run.profile == "Profile1"
assert run.relative_path == "Profile1_Temp.sav"
_base, _saves, service = _environment("stale-temp", include_temp=True)
assert Hades2SaveWorkspace.open(service).relative_path == "Profile1.sav"
_base, _saves, service = _environment("old-validation", include_temp=True, validation_age="old")
assert Hades2SaveWorkspace.open(service).relative_path == "Profile1.sav"

# Resource queries are backend-filtered/paged and expose only descriptor-owned
# editability. The frontend never needs the whole save tree to search this domain.
resources = {
    "MetaCurrency": 123.0,
    "GiftPoints": 9.0,
    "CardUpgradePoints": 7.0,
    "UnmodeledCurrency": 6.0,
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
assert page["total"] >= 2
assert len(page["items"]) == 2
assert workspace.query(domain="resources", search="UnmodeledCurrency")["total"] == 0
by_resource = {row["rawId"]: row for row in workspace.query(
    domain="resources", limit=200, language="en"
)["items"]}
assert by_resource["GiftPoints"]["value"] == 9
assert by_resource["CardUpgradePoints"]["value"] == 7
# ResourceData.Money is marked RunResource; it is cleared at death and must
# never be represented as persistent inventory in the Save Editor.
assert "Money" not in by_resource
try:
    workspace.stage("resource:Money", "set", 123)
except ValueError:
    pass
else:
    raise AssertionError("run-only money became editable persistent inventory")
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
    ("resource:UnmodeledCurrency", "set", 500),
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
    "TextLinesRecord": _table({"HecatePostTrueEnding01": True, "GiftLine": True}),
    "TextLinesChoiceRecord": _table({"HecatePostTrueEnding01": "ChoiceA"}),
    "GiftTextLinesOrderRecord": _table({
        "Hecate": LuaTable(1, 0, [(1.0, "GiftLine")]),
    }),
    "QuestStatus": _table({"QuestHelpOdysseus": "Unlocked", "QuestHelpDora": "CashedOut", "QuestA": "Unlocked"}),
    "QuestsCompleted": _table({"QuestHelpDora": True}),
}
_base, narrative_saves, narrative_service = _environment("narrative", state=narrative_state)
# This native line also has recorded current-run counterparts. A reset must
# remove their observed choices/playback without altering RunHistory.
narrative_file = narrative_saves / "Profile1.sav"
narrative_document = Hades2SaveDocument.load(narrative_file)
run_records = narrative_document.lua_state["CurrentRun"]
run_records["TextLinesRecord"] = _table({"HecatePostTrueEnding01": True})
run_records["HubTextLinesRecord"] = _table({"HecatePostTrueEnding01": True})
run_records["TextLinesChoiceRecord"] = _table({"HecatePostTrueEnding01": "ChoiceA"})
run_records["CurrentRoom"] = _table({
    "TextLinesRecord": _table({"HecatePostTrueEnding01": True})
})
narrative_file.write_bytes(narrative_document.to_bytes())
narrative = Hades2SaveWorkspace.open(narrative_service)
flags = narrative.query(domain="flags", search="HasPinnedAnyBoon", language="en")
assert flags["total"] == 1
assert flags["items"][0]["value"] is False
assert flags["items"][0]["group"] == "Tutorial and presentation records"
dialogue = narrative.query(domain="dialogue", limit=10, language="zh-CN")
assert {row["rawId"] for row in dialogue["items"]} == {"HecatePostTrueEnding01", "GiftLine"}
assert next(row for row in dialogue["items"] if row["rawId"] == "GiftLine")["editable"] is False
quests = narrative.query(domain="progression", limit=10, language="en")
assert quests["total"] == 2  # unrecognized QuestA is not an editable game quest
assert next(row for row in quests["items"] if row["rawId"] == "QuestHelpOdysseus")["choices"] == [
    "Unlocked", "Complete"
]
assert next(row for row in quests["items"] if row["rawId"] == "QuestHelpDora")["editable"] is False
for identity, action, value in (
    ("flag:UnsupportedHiddenFlag", "set", False),
    ("dialogue:GiftLine", "set", False),
    ("quest:QuestHelpDora", "setEnum", "Unlocked"),
    ("quest:QuestHelpOdysseus", "setEnum", "CashedOut"),
    ("quest:QuestHelpOdysseus", "set", "Complete"),
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
narrative.stage("dialogue:HecatePostTrueEnding01", "set", False)
narrative.stage("quest:QuestHelpOdysseus", "setEnum", "Complete")
changes = narrative.review()["changes"]
assert len(changes) == 10, changes  # four intents, five dialogue owner links, quest history
assert {row["id"] for row in changes if row["id"].startswith("linked:")} == {
    "linked:dialogue:HecatePostTrueEnding01", "linked:quest:QuestHelpOdysseus",
    "linked:dialogue:CurrentRun.TextLinesRecord:HecatePostTrueEnding01",
    "linked:dialogue:CurrentRun.HubTextLinesRecord:HecatePostTrueEnding01",
    "linked:dialogue:CurrentRun.TextLinesChoiceRecord:HecatePostTrueEnding01",
    "linked:dialogue:CurrentRun.CurrentRoom.TextLinesRecord:HecatePostTrueEnding01",
}
narrative.apply()
installed_narrative = Hades2SaveDocument.load(narrative_saves / "Profile1.sav")
game = installed_narrative.lua_state["GameState"]
assert game["Flags"]["HasPinnedAnyBoon"] is True
assert game["Flags"].get("HasShuffledMusicPlayer") is None
assert game["Flags"]["UnsupportedHiddenFlag"] is True
assert game["TextLinesRecord"].get("HecatePostTrueEnding01") is None
assert game["TextLinesRecord"]["GiftLine"] is True
assert game["TextLinesChoiceRecord"].get("HecatePostTrueEnding01") is None
run_after = installed_narrative.lua_state["CurrentRun"]
assert run_after["TextLinesRecord"].get("HecatePostTrueEnding01") is None
assert run_after["HubTextLinesRecord"].get("HecatePostTrueEnding01") is None
assert run_after["TextLinesChoiceRecord"].get("HecatePostTrueEnding01") is None
assert run_after["CurrentRoom"]["TextLinesRecord"].get("HecatePostTrueEnding01") is None
assert game["QuestStatus"]["QuestHelpOdysseus"] == "Complete"
assert game["QuestsCompleted"]["QuestHelpOdysseus"] is True
assert game["QuestsCompleted"]["QuestHelpDora"] is True
assert game["QuestStatus"]["QuestHelpDora"] == "CashedOut"
assert game["QuestStatus"]["QuestA"] == "Unlocked"
assert game["UnknownFutureField"]["KeepMe"] == "yes"

# A valid cross-domain batch must be refused before touching disk if its
# dialogue ownership becomes ambiguous between staging and cold Apply.
duplicate_state = {
    "TextLinesRecord": _table({"HecatePostTrueEnding01": True}),
    "TextLinesChoiceRecord": _table({"HecatePostTrueEnding01": "ChoiceA"}),
    "GiftTextLinesOrderRecord": _table({"Hecate": LuaTable(0, 0, [])}),
}
_base, duplicated_saves, duplicated_service = _environment(
    "duplicate-dialogue-batch", state=duplicate_state
)
duplicated_path = duplicated_saves / "Profile1.sav"
duplicated = Hades2SaveWorkspace.open(duplicated_service)
duplicated.stage("resource:MetaCurrency", "set", 500)
duplicated.stage("dialogue:HecatePostTrueEnding01", "set", False)
before_ambiguous_apply = duplicated_path.read_bytes()
# Only in-memory source state changes. The actual save file remains untouched.
duplicated.document.lua_state["GameState"]["TextLinesChoiceRecord"] = LuaTable(
    0, 2, [
        ("HecatePostTrueEnding01", "ChoiceA"),
        ("HecatePostTrueEnding01", "ChoiceB"),
    ]
)
assert next(
    row for row in duplicated.query(domain="dialogue")["items"]
    if row["rawId"] == "HecatePostTrueEnding01"
)["editable"] is False
try:
    duplicated.review()
except ValueError:
    pass
else:
    raise AssertionError("ambiguous linked dialogue appeared in batch preview")
try:
    duplicated.apply()
except ValueError:
    pass
else:
    raise AssertionError("ambiguous cross-domain Save Editor batch was applied")
assert duplicated_path.read_bytes() == before_ambiguous_apply
assert duplicated.summary()["pendingCount"] == 2

# A physically parseable, duplicate-key save remains readable and byte-stable.
# Opening and rejecting a dialogue mutation must not normalize either record.
source_with_duplicates = Hades2SaveDocument.load(duplicated_path)
source_with_duplicates.lua_state["GameState"]["TextLinesChoiceRecord"] = LuaTable(
    0, 2, [
        ("HecatePostTrueEnding01", "ChoiceA"),
        ("HecatePostTrueEnding01", "ChoiceB"),
    ]
)
duplicated_path.write_bytes(source_with_duplicates.to_bytes())
original_duplicate_bytes = duplicated_path.read_bytes()
read_only_duplicate = Hades2SaveWorkspace.open(duplicated_service)
assert next(
    row for row in read_only_duplicate.query(domain="dialogue")["items"]
    if row["rawId"] == "HecatePostTrueEnding01"
)["editable"] is False
try:
    read_only_duplicate.stage("dialogue:HecatePostTrueEnding01", "set", False)
except ValueError:
    pass
else:
    raise AssertionError("physically duplicated dialogue was editable")
assert duplicated_path.read_bytes() == original_duplicate_bytes

# Relationship history has a native chronological array and a global
# gift-resource aggregate. A count edit must keep all three states coherent.
gift_npc = LuaTable(3, 2, [
    (1.0, "GiftPoints"), (2.0, "MedeaPoints"), (3.0, "GiftPoints"),
    ("GiftPoints", 2.0), ("MedeaPoints", 1.0),
])
long_term_state = {
    "Flags": _table({}),
    "TextLinesRecord": _table({}),
    "QuestStatus": _table({}),
    "NPCInteractions": _table({"NPC_Hecate_01": 2.0}),
    "SpecialInteractRecord": _table({"NPC_Hecate_01": 1.0}),
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
assert {
    "interaction:NPC_Hecate_01", "specialInteraction:NPC_Hecate_01",
    "gift:Hecate:GiftPoints", "gift:Hecate:MedeaPoints"
}.issubset({entry["id"] for entry in rels["items"]})
assert {"interaction:NPC_Hecate_01", "specialInteraction:NPC_Hecate_01"}.issubset({
    row["id"] for row in rels["items"] if row["editable"]
})
assert all(not row["editable"] for row in rels["items"] if row["id"].startswith("gift:"))
progress = long_term.query(domain="progression", language="en")
assert {
    "card:ChanneledCast:Unlocked", "card:ChanneledCast:Level",
    "card:BonusHealth:Unlocked", "card:BonusHealth:Level",
    "objective:GiftPrompt",
}.issubset({row["id"] for row in progress["items"]})
assert all(row["id"] != "card:UnknownHiddenCard:Level" for row in progress["items"])
for identity, value in (
    ("gift:Hecate:GiftPoints", 3),
    ("card:ChanneledCast:Level", 4),
    ("card:BonusHealth:Unlocked", 1),
    ("interaction:NPC_Hecate_01", True),
    ("objective:Unknown", 4),
):
    try:
        long_term.stage(identity, "set", value)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid long-term edit accepted: " + identity)

long_term.stage("interaction:NPC_Hecate_01", "set", 5)
long_term.stage("specialInteraction:NPC_Hecate_01", "set", 4)
long_term.stage("card:ChanneledCast:Unlocked", "set", False)
long_term.stage("objective:GiftPrompt", "set", 3)
review = long_term.review()
assert review["count"] == 6, review
assert {item["id"] for item in review["changes"] if item["id"].startswith("linked:")} == {
    "linked:card:ChanneledCast:Equipped", "linked:card:ChanneledCast:Level"
}
long_term.apply()
edited = Hades2SaveDocument.load(long_term_saves / "Profile1.sav").lua_state["GameState"]
assert edited["NPCInteractions"]["NPC_Hecate_01"] == 5
assert edited["SpecialInteractRecord"]["NPC_Hecate_01"] == 4
record = edited["GiftRecord"]["Hecate"]
assert record["GiftPoints"] == 2
assert [value for key, value in record.entries() if type(key) is float] == [
    "GiftPoints", "MedeaPoints", "GiftPoints"
]
assert edited["GiftResourceRecord"]["GiftPoints"] == 5
arcana = edited["MetaUpgradeState"]["ChanneledCast"]
assert arcana.get("Unlocked") is None
assert arcana.get("Equipped") is None
assert arcana["Level"] == 1
assert edited["ObjectivesCompleted"]["GiftPrompt"] == 3
assert edited["MetaUpgradeState"]["UnknownHiddenCard"]["Level"] == 17
assert edited["UnknownFutureField"]["KeepMe"] == "yes"

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

# Gift chronology must remain read-only even when counts look consistent.
# Numeric zero/one must not be accepted as Arcana boolean ownership.
malformed_gifts = LuaTable(2, 1, [
    (1.0, "GiftPoints"), (2.0, "MedeaPoints"), ("GiftPoints", 1.0),
])
malformed_state = {
    **long_term_state,
    "GiftRecord": _table({"Hecate": malformed_gifts}),
    "MetaUpgradeState": _table({
        "ChanneledCast": _table({"Unlocked": 1.0, "Level": 2.0}),
    }),
}
_base, _malformed_saves, malformed_service = _environment(
    "malformed_long_term", state=malformed_state
)
malformed = Hades2SaveWorkspace.open(malformed_service)
gift_rows = malformed.query(domain="relationships", language="en")["items"]
assert next(row for row in gift_rows if row["id"] == "gift:Hecate:GiftPoints")["editable"] is False
card_rows = malformed.query(domain="progression", language="en")["items"]
malformed_card = next(
    row for row in card_rows if row["id"] == "card:ChanneledCast:Level"
)
assert malformed_card["editable"] is False
assert malformed_card["ownerState"] == "unsupported"
assert malformed_card["blockReasonCode"] == "unsupportedOwner"
try:
    malformed.stage("card:ChanneledCast:Level", "set", 2)
except ValueError:
    pass
else:
    raise AssertionError("malformed Arcana owner became writable")

# Gift quantities need not equal gift-event count. No synthetic gifts or
# dialogue events may be manufactured when the two representations differ.
quantity_record = LuaTable(1, 1, [(1.0, "SuperGiftPoints"), ("SuperGiftPoints", 2.0)])
quantity_state = {**long_term_state, "GiftRecord": _table({"Hecate": quantity_record})}
_base, _quantity_saves, quantity_service = _environment("gift_quantity", state=quantity_state)
quantity_editor = Hades2SaveWorkspace.open(quantity_service)
quantity_row = next(r for r in quantity_editor.query(domain="relationships")["items"]
                    if r["id"] == "gift:Hecate:SuperGiftPoints")
assert quantity_row["value"] == 2 and not quantity_row["editable"]
try:
    quantity_editor.stage("gift:Hecate:SuperGiftPoints", "set", 3)
except ValueError:
    pass
else:
    raise AssertionError("synthetic gift history mutation accepted")

# Dialogue choices may be nested tables; review must be serializable and
# changing a quest must not require fictitious QuestsCompleted state.
import json
nested_state = {
    "Flags": _table({}), "TextLinesRecord": _table({"ChoiceScene": True}),
    "TextLinesChoiceRecord": _table({"ChoiceScene": _table({"ChoiceIndex": 2.0})}),
    "GiftTextLinesOrderRecord": _table({}),
    "QuestStatus": _table({"QuestC": "Unlocked"}),
}
_base, nested_saves, nested_service = _environment("nested-dialogue", state=nested_state)
nested_workspace = Hades2SaveWorkspace.open(nested_service)
try:
    nested_workspace.stage("dialogue:ChoiceScene", "set", False)
except ValueError:
    pass
else:
    raise AssertionError("unverified dialogue reset accepted")
assert nested_workspace.review() == {"count": 0, "changes": []}
json.dumps(nested_workspace.query(domain="dialogue")["items"])
nested_game = Hades2SaveDocument.load(nested_saves / "Profile1.sav").lua_state["GameState"]
assert nested_game["TextLinesChoiceRecord"]["ChoiceScene"]["ChoiceIndex"] == 2.0
assert nested_game["QuestStatus"]["QuestC"] == "Unlocked"

# WeaponsUnlocked is authoritative for ownership. Shop purchases also
# keep the two optional world-upgrade marker tables synchronized.
equipment_owned = {
    "WeaponDagger", "DaggerBlockAspect", "DaggerBlockAspect2", "ToolShovel"
}
equipment_state = {
    "WeaponsUnlocked": _table({key: True for key in equipment_owned}),
    "WorldUpgrades": _table({key: True for key in equipment_owned}),
    "WorldUpgradesAdded": _table({key: True for key in equipment_owned}),
    "LastWeaponUpgradeName": _table({"WeaponDagger": "DaggerBlockAspect"}),
    "FamiliarsUnlocked": _table({"HoundFamiliar": True}),
    "EquippedFamiliar": "HoundFamiliar",
}
_base, equipment_saves, equipment_service = _environment(
    "equipment", state=equipment_state
)
equipment = Hades2SaveWorkspace.open(equipment_service)
weapon_rows = equipment.query(domain="weapons", offset=0, limit=100, language="zh-CN")
by_id = {row["id"]: row for row in weapon_rows["items"]}
assert by_id["weapon:WeaponDagger"]["value"] is True
assert by_id["aspect:DaggerBlockAspect"]["value"] == 2
assert by_id["aspect:DaggerBackstabAspect"]["value"] == 1
assert by_id["aspect:DaggerBackstabAspect"]["editable"]
assert by_id["aspect:StaffClearCastAspect"]["value"] == 0
assert by_id["aspect:BaseStaffAspect"]["editable"] is False
assert by_id["aspectSelection:WeaponDagger"]["value"] == "DaggerBlockAspect"
assert "DaggerBackstabAspect" in by_id["aspectSelection:WeaponDagger"]["choices"]
assert by_id["aspectSelection:WeaponDagger"]["choiceNames"][""] == "默认形态"
assert by_id["tool:ToolShovel"]["value"] == 1
assert by_id["familiar:HoundFamiliar"]["value"] is True
assert by_id["familiarSelection"]["value"] == "HoundFamiliar"
assert "weapon:WeaponUnknown" not in by_id
assert all(row["domain"] == "weapons" for row in weapon_rows["items"])
for identity, operation, value in (
    ("aspect:DaggerBlockAspect", "set", 6),
    ("aspect:DaggerBlockAspect", "set", 2.5),
    ("tool:ToolShovel", "set", 3),
    ("familiar:HoundFamiliar", "set", 1),
    ("familiarSelection", "setEnum", "UnknownFamiliar"),
    ("aspectSelection:WeaponDagger", "setEnum", "WrongAspect"),
    ("weapon:WeaponUnknown", "set", True),
):
    try:
        equipment.stage(identity, operation, value)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid equipment edit accepted: " + identity)

equipment.stage("aspect:DaggerBlockAspect", "set", 4)
equipment.stage("tool:ToolShovel", "set", 2)
equipment.stage("familiar:CatFamiliar", "set", True)
equipment.stage("familiarSelection", "setEnum", "CatFamiliar")
review = equipment.review()
assert review["count"] == 4
equipment.apply()
installed_equipment = Hades2SaveDocument.load(equipment_saves / "Profile1.sav")
state = installed_equipment.lua_state["GameState"]
for table_name in ("WeaponsUnlocked", "WorldUpgrades", "WorldUpgradesAdded"):
    for key in ("DaggerBlockAspect3", "DaggerBlockAspect4", "ToolShovel2"):
        assert state[table_name][key] is True
    assert state[table_name].get("DaggerBlockAspect5") is None
assert state["LastWeaponUpgradeName"]["WeaponDagger"] == "DaggerBlockAspect"
assert state["FamiliarsUnlocked"]["CatFamiliar"] is True
assert state["EquippedFamiliar"] == "CatFamiliar"
assert state["UnknownFutureField"]["KeepMe"] == "yes"

# Turning off an owned aspect and familiar resets dependent selections; a
# downgrade removes later shop tiers from all three purchase-marker tables.
equipment_again = Hades2SaveWorkspace.open(equipment_service)
equipment_again.stage("aspect:DaggerBlockAspect", "set", 0)
equipment_again.stage("familiar:CatFamiliar", "set", False)
linked_ids = {row["id"] for row in equipment_again.review()["changes"]
              if row["id"].startswith("linked:")}
assert "linked:aspectSelection:WeaponDagger" in linked_ids
assert "linked:familiarSelection" in linked_ids
equipment_again.apply()
state = Hades2SaveDocument.load(equipment_saves / "Profile1.sav").lua_state["GameState"]
assert state["LastWeaponUpgradeName"].get("WeaponDagger") is None
assert state.get("EquippedFamiliar") is None
assert state["FamiliarsUnlocked"].get("CatFamiliar") is None
for table_name in ("WeaponsUnlocked", "WorldUpgrades", "WorldUpgradesAdded"):
    for tier in ("DaggerBlockAspect", "DaggerBlockAspect2",
                 "DaggerBlockAspect3", "DaggerBlockAspect4"):
        assert state[table_name].get(tier) is None

# A proposed selection of an unowned aspect is not silently installed. The
# entire batch fails before mutating the on-disk save.
bad_equipment = Hades2SaveWorkspace.open(equipment_service)
bad_equipment.stage("aspectSelection:WeaponDagger", "setEnum", "DaggerBlockAspect")
before_bad_equipment = (equipment_saves / "Profile1.sav").read_bytes()
try:
    bad_equipment.apply()
except ValueError:
    pass
else:
    raise AssertionError("unowned selected weapon aspect was accepted")
assert (equipment_saves / "Profile1.sav").read_bytes() == before_bad_equipment
bad_equipment.cancel()

# Compatible staged unlock and selection are committed together, without
# rewriting CurrentRun runtime mounted effects.
good_equipment = Hades2SaveWorkspace.open(equipment_service)
good_equipment.stage("aspect:DaggerBlockAspect", "set", 3)
good_equipment.stage("aspectSelection:WeaponDagger", "setEnum", "DaggerBlockAspect")
good_equipment.apply()
state = Hades2SaveDocument.load(equipment_saves / "Profile1.sav").lua_state["GameState"]
assert state["WeaponsUnlocked"]["DaggerBlockAspect3"] is True
assert state["LastWeaponUpgradeName"]["WeaponDagger"] == "DaggerBlockAspect"

# The parent weapon unlock and its purchased aspect cannot end in mutually
# contradictory states, regardless of staging order.
conflict = Hades2SaveWorkspace.open(equipment_service)
conflict.stage("weapon:WeaponDagger", "set", False)
conflict.stage("aspect:DaggerBlockAspect", "set", 4)
previous_save = (equipment_saves / "Profile1.sav").read_bytes()
try:
    conflict.apply()
except ValueError:
    pass
else:
    raise AssertionError("contradictory weapon/aspect batch was accepted")
assert (equipment_saves / "Profile1.sav").read_bytes() == previous_save


# Initial starting weapon state in CreateNewHero writes only WeaponsUnlocked.
# Missing world-upgrade mirrors must not hide or invalidate this weapon.
starter_state = {
    "WeaponsUnlocked": _table({"WeaponStaffSwing": True}),
    "WorldUpgrades": _table({}),
    "WorldUpgradesAdded": _table({}),
    "LastWeaponUpgradeName": _table({}),
}
_base, starter_saves, starter_service = _environment("starter-weapon", state=starter_state)
starter_editor = Hades2SaveWorkspace.open(starter_service)
starter_rows = {r["id"]: r for r in starter_editor.query(domain="weapons")["items"]}
assert starter_rows["weapon:WeaponStaffSwing"]["value"] is True
assert starter_rows["aspect:BaseStaffAspect"]["value"] == 1
assert starter_rows["weapon:WeaponStaffSwing"]["editable"] is False
assert starter_rows["aspect:StaffClearCastAspect"]["value"] == 0
starter_editor.stage("aspect:StaffClearCastAspect", "set", 2)
starter_editor.apply()
starter_written = Hades2SaveDocument.load(starter_saves / "Profile1.sav").lua_state["GameState"]
assert starter_written["WeaponsUnlocked"]["WeaponStaffSwing"] is True
assert starter_written["WeaponsUnlocked"]["StaffClearCastAspect2"] is True
assert starter_written["WorldUpgrades"]["StaffClearCastAspect2"] is True
assert starter_written["WorldUpgrades"].get("WeaponStaffSwing") is None


# Native quest lifecycle synchronizes completion history. Reversing an
# unclaimed quest also clears its completed-history gate without changing other
# quests or the original game's unrelated save state.
undo_quest = Hades2SaveWorkspace.open(narrative_service)
undo_quest.stage("quest:QuestHelpOdysseus", "setEnum", "Unlocked")
assert any(c["id"] == "linked:quest:QuestHelpOdysseus"
           for c in undo_quest.review()["changes"])
undo_quest.apply()
restored = Hades2SaveDocument.load(narrative_saves / "Profile1.sav").lua_state["GameState"]
assert restored["QuestStatus"]["QuestHelpOdysseus"] == "Unlocked"
assert restored["QuestsCompleted"].get("QuestHelpOdysseus") is None
assert restored["QuestsCompleted"]["QuestHelpDora"] is True
try:
    undo_quest.stage("quest:QuestA", "setEnum", "Complete")
except ValueError:
    pass
else:
    raise AssertionError("arbitrary stored QuestStatus key became writable")

# The real game writes free/default aspect unlock bits on visiting the Aspect
# shop. Revoking the parent weapon must remove the *recorded* free aspect too.
free_aspect_state = {
    "WeaponsUnlocked": _table({"WeaponDagger": True, "DaggerBackstabAspect": True}),
    "WorldUpgrades": _table({"WeaponDagger": True}),
    "WorldUpgradesAdded": _table({"WeaponDagger": True}),
    "LastWeaponUpgradeName": _table({}),
}
_base, free_saves, free_service = _environment("native-free-aspect", state=free_aspect_state)
free_editor = Hades2SaveWorkspace.open(free_service)
free_rows = {r["id"]: r for r in free_editor.query(domain="weapons")["items"]}
assert free_rows["aspect:DaggerBackstabAspect"]["value"] == 1
# The UI identity must distinguish the six forms sharing the same native title.
assert "WeaponDagger" in free_rows["aspect:DaggerBackstabAspect"]["name"]
free_editor.stage("weapon:WeaponDagger", "set", False)
free_editor.apply()
free_result = Hades2SaveDocument.load(free_saves / "Profile1.sav").lua_state["GameState"]
assert free_result["WeaponsUnlocked"].get("WeaponDagger") is None
assert free_result["WeaponsUnlocked"].get("DaggerBackstabAspect") is None
assert free_result["WorldUpgrades"].get("WeaponDagger") is None
assert free_result["UnknownFutureField"]["KeepMe"] == "yes"

# CompletedObjectiveSets uses set names; ObjectivesCompleted uses objective
# names. A coincidental identical key must not imply a linked historical state.
objective_state = {
    "QuestStatus": _table({}),
    "ObjectivesCompleted": _table({"WeaponCast": 2.0}),
    "CompletedObjectiveSets": _table({"FCastTutorial": True, "WeaponCast": True}),
}
_base, obj_saves, obj_service = _environment("native-objective-namespaces", state=objective_state)
obj_editor = Hades2SaveWorkspace.open(obj_service)
objective = next(x for x in obj_editor.query(domain="progression")["items"]
                 if x["id"] == "objective:WeaponCast")
assert objective["editable"] is True

# Overview is an advertised top-level domain, so it must be navigable and
# provide an actual structured summary rather than a permanent empty list.
assert Hades2SaveWorkspace.open(obj_service).query(domain="overview")["total"] >= 1


# GameState.Resources may omit a zero-valued native resource. That resource
# remains a valid writable identity even when not yet present in the save.
_base, sparse_saves, sparse_service = _environment(
    "sparse-resources", resources={"MetaCurrency": 1.0, "UnmodeledCurrency": 11.0}
)
sparse = Hades2SaveWorkspace.open(sparse_service)
all_rows = sparse.query(domain="resources", limit=200)["items"]
dream = next(row for row in all_rows if row["id"] == "resource:DreamPoints")
assert dream["value"] == 0 and dream["editable"] is True
assert not any(row["id"] == "resource:UnmodeledCurrency" for row in all_rows)
sparse.stage("resource:DreamPoints", "set", 7)
assert sparse.review()["changes"][0]["before"] == 0
sparse.apply()
sparse_state = Hades2SaveDocument.load(sparse_saves / "Profile1.sav").lua_state["GameState"]
assert sparse_state["Resources"]["DreamPoints"] == 7
assert sparse_state["Resources"]["UnmodeledCurrency"] == 11

# A rejected stage must not poison the mutation queue. Native malformed
# historical completion data must not be used for quest mutation.
malformed_history = {
    "QuestStatus": _table({"QuestHelpOdysseus": "Unlocked"}),
    "QuestsCompleted": _table({"QuestHelpOdysseus": 3.0}),
    "Flags": _table({}),
    "TextLinesRecord": _table({}),
}
_base, invalid_saves, invalid_service = _environment("bad-quest-history", state=malformed_history)
invalid_editor = Hades2SaveWorkspace.open(invalid_service)
try:
    invalid_editor.stage("quest:QuestHelpOdysseus", "setEnum", "Complete")
except ValueError:
    pass
else:
    raise AssertionError("malformed completed quest record became writable")
assert invalid_editor.review() == {"count": 0, "changes": []}
invalid_editor.stage("resource:MetaCurrency", "set", 17)
assert invalid_editor.review()["count"] == 1
invalid_editor.cancel()
assert invalid_editor.review() == {"count": 0, "changes": []}


# Native interaction keys are UnitSetData units, not localization/speaker
# names. The editor must be able to initialize a known but never met NPC from
# the native zero default without authorizing arbitrary future metadata keys.
identity_state = {
    "QuestStatus": _table({}),
    "NPCInteractions": _table({"NPC_Hecate_01": 3.0, "FutureUnit": 5.0}),
    "SpecialInteractRecord": _table({"NPC_Hecate_01": 1.0, "FutureUnit": 2.0}),
    "ObjectivesCompleted": _table({"WeaponCast": 2.0, "UnknownObjective": 4.0}),
}
_base, identity_saves, identity_service = _environment(
    "native-relationship-ids", state=identity_state
)
identity = Hades2SaveWorkspace.open(identity_service)
relationship_rows = {r["id"]: r for r in identity.query(
    domain="relationships", limit=200
)["items"]}
assert relationship_rows["interaction:NPC_Hecate_01"]["value"] == 3
assert relationship_rows["interaction:NPC_Nemesis_01"]["value"] == 0
assert relationship_rows["interaction:NPC_Nemesis_01"]["editable"] is True
assert "interaction:FutureUnit" not in relationship_rows
assert "specialInteraction:FutureUnit" not in relationship_rows
objective_rows = {r["id"]: r for r in identity.query(
    domain="progression", limit=200
)["items"]}
assert objective_rows["objective:WeaponCast"]["value"] == 2
assert "objective:UnknownObjective" not in objective_rows
identity.stage("interaction:NPC_Nemesis_01", "set", 1)
identity.stage("objective:WeaponCast", "set", 3)
identity.apply()
persisted = Hades2SaveDocument.load(identity_saves / "Profile1.sav").lua_state["GameState"]
assert persisted["NPCInteractions"]["NPC_Nemesis_01"] == 1
assert persisted["NPCInteractions"]["FutureUnit"] == 5
assert persisted["SpecialInteractRecord"]["FutureUnit"] == 2
assert persisted["ObjectivesCompleted"]["UnknownObjective"] == 4

# A linked narrative provenance failure must refuse a cross-domain apply.
invalid_owner_state = {
    "Flags": _table({}),
    "TextLinesRecord": _table({"HecatePostTrueEnding01": True}),
    "TextLinesChoiceRecord": _table({}),
    "GiftTextLinesOrderRecord": _table({}),
}
_base, refusal_saves, refusal_service = _environment("dialogue-refusal", state=invalid_owner_state)
refusal = Hades2SaveWorkspace.open(refusal_service)
refusal.stage("resource:MetaCurrency", "set", 99)
refusal.stage("dialogue:HecatePostTrueEnding01", "set", False)
source_bytes = (refusal_saves / "Profile1.sav").read_bytes()
refusal.document.lua_state["GameState"]["GiftTextLinesOrderRecord"] = "invalid"
try:
    refusal.apply()
except ValueError:
    pass
else:
    raise AssertionError("invalid narrative batch wrote to Core Save")
assert (refusal_saves / "Profile1.sav").read_bytes() == source_bytes




# Duplicate physical Lua keys remain inspectable and fail closed for the
# selected owned state, while a staged batch cannot write the original disk
# target after one previously staged owner becomes ambiguous.
_base, duplicate_saves, duplicate_service = _environment(
    "duplicate_pending_owner",
    resources={"MetaCurrency": 5.0, "GiftPoints": 7.0},
)
duplicate_editor = Hades2SaveWorkspace.open(duplicate_service)
duplicate_editor.stage("resource:MetaCurrency", "set", 50)
duplicate_editor.stage("playerStat:GameplayTime", "set", 300.0)
original_target = (duplicate_saves / "Profile1.sav").read_bytes()
game_state = duplicate_editor.document.lua_state["GameState"]
game_state._entries.append(("GameplayTime", 999.0))
game_state.hash_size += 1
for operation in (duplicate_editor.review, duplicate_editor.apply):
    try:
        operation()
    except ValueError as error:
        assert "ambiguous" in str(error).lower(), error
    else:
        raise AssertionError("duplicate staged owner was accepted")
assert (duplicate_saves / "Profile1.sav").read_bytes() == original_target
assert {change["id"] for change in duplicate_editor._pending.values()} == {
    "resource:MetaCurrency", "playerStat:GameplayTime",
}

# A duplicate physical key in unrelated future/unknown data is not grounds
# to prohibit a supported resource edit or discard any raw entries.
_base, preserved_saves, preserved_service = _environment("duplicate_unknown")
preserved = Hades2SaveWorkspace.open(preserved_service)
unknown = preserved.document.lua_state["GameState"]["UnknownFutureField"]
unknown._entries.append(("KeepMe", "other physical record"))
unknown.hash_size += 1
preserved.stage("resource:MetaCurrency", "set", 321)
preserved.apply()
installed = Hades2SaveDocument.load(preserved_saves / "Profile1.sav")
state = installed.lua_state["GameState"]
assert state["Resources"]["MetaCurrency"] == 321
assert [item for key, item in state["UnknownFutureField"].entries()
        if key == "KeepMe"] == ["yes", "other physical record"]

print("hades2_save_workspace_ok")
