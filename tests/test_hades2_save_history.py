"""Player history projection and typed edits share the real entity/stage seam."""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
from games.hades2.save_document import LuaTable
from games.hades2.save_workspace import Hades2SaveWorkspace


def table(mapping):
    return LuaTable(0, len(mapping), list(mapping.items()))


names_fixture = tempfile.TemporaryDirectory(prefix="mgt-history-labels-")
for language, boon, fish in (("en", "Historic Boon", "Silver Carp"), ("zh-CN", "旧日祝福", "银鲤")):
    (Path(names_fixture.name) / ("Names." + language + ".sjson")).write_text(
        'Id = "UnknownHistoricBoon" DisplayName = "' + boon + '"\n'
        'Id = "KnownBoon" DisplayName = "' + boon + '"\n'
        'Id = "UnknownFish" DisplayName = "' + fish + '"\n', encoding="utf-8")


def workspace(state, game_path=names_fixture.name):
    state.update({"Resources": table({}), "Flags": table({})})
    root = table({"GameState": table(state), "CurrentRun": table({})})
    session = SimpleNamespace(document=SimpleNamespace(lua_state=root), relative_path="Profile1.sav")
    return Hades2SaveWorkspace(session, "Profile1", game_path=game_path), root


w, root = workspace({
    "RunHistory": table({
        1: table({"RunResult": 2, "GameplayTime": 123.5, "EndingRoomName": "F_Boss01",
                  "ShrinePointsCache": 4, "TraitCache": table({"UnknownHistoricBoon": 1})}),
        2: table({"RunResult": 3, "GameplayTime": 98.25, "ShrinePointsCache": 12}),
    }),
    "LifetimeTraitStats": table({
        "UnknownHistoricBoon": table({"UseCount": 5, "ClearCount": 2,
            "ClearCountUnderworld": 1, "ClearCountSurface": 1,
            "FastestTimeUnderworld": 123.5, "FastestTimeSurface": 98.25,
            "HighestShrinePointsUnderworld": 4, "HighestShrinePointsSurface": 12,
            "UnknownFutureMeasure": 999}),
    }),
    "FishingSuccesses": 7, "FishingSuccessesManual": 4,
    "FishingSuccessesFamiliar": 3, "FishingFails": 2,
    "ExorcismSuccesses": 9, "ExorcismFails": 1,
    "HarvestSuccesses": 12,
    "FishCaught": table({"UnknownFish": 3}),
})
page = w.query(domain="entities", scope="records", language="en", limit=100)
groups = {g["id"]: g for g in page["entities"]}
assert "history:run:1" in groups, "completed runs are missing from the player-history workflow"
assert "history:run:2" in groups
assert "history:trait:UnknownHistoricBoon" in groups
assert "history:gathering:fishing" in groups
assert all(r["editable"] and r["mutationKinds"]
           for g in groups.values() if g["id"].startswith("history:") for r in g["items"])
run = {r["rawId"]: r for r in groups["history:run:1"]["items"]}
assert run["RunResult"]["value"] == 2
assert run["RunResult"]["choiceNames"]["2"] == "Underworld · Failed"
assert run["GameplayTime"]["value"] == 123.5
assert "seconds" in run["GameplayTime"]["name"]
assert run["EndingRoomName"]["value"] == "F_Boss01"
assert run["trait:UnknownHistoricBoon"]["path"] == ["GameState", "RunHistory", 1, "TraitCache", "UnknownHistoricBoon"]
assert all(r.get("reason") and r.get("reasonCode") == "editable" for r in run.values())
trait = {r["rawId"]: r for r in groups["history:trait:UnknownHistoricBoon"]["items"]}
assert trait["UseCount"]["value"] == 5 and trait["ClearCountSurface"]["value"] == 1
assert trait["HighestShrinePointsSurface"]["value"] == 12
assert "UnknownFutureMeasure" not in trait, "an unproven measure borrowed semantic authority"
# Deliberate raw-identity search finds unknown records, without presenting the
# internal identifier as the routine entity title.
found = w.query(domain="entities", scope="records", search="UnknownHistoricBoon", language="zh-CN")
assert any(g["id"] == "history:trait:UnknownHistoricBoon" for g in found["entities"])
assert all("UnknownHistoricBoon" not in g["name"] for g in found["entities"])
assert not any(k.startswith("_") for g in page["entities"] for r in g["items"] for k in r)
# Entity paging never slices a run's physical fields across result pages.
small = w.query(domain="entities", scope="records", language="en", limit=1)
assert len(small["entities"]) == 1 and small["hasMore"]
assert small["entities"][0]["items"] == groups[small["entities"][0]["id"]]["items"]
for language, needle in (("en", "Underworld"), ("zh-CN", "Underworld"),
                         ("en", "未通关"), ("zh-CN", "冥界")):
    result = w.query(domain="entities", scope="records", search=needle, language=language)
    assert any(g["id"] == "history:run:1" for g in result["entities"]), "displayed run outcome is not searchable"
unknown, _ = workspace({"RunHistory": table({1: table({"RunResult": 777})})})
assert any(g["id"] == "history:run:1" for g in unknown.query(
    domain="entities", scope="records", search="777", language="en")["entities"])
entry = run["GameplayTime"]
w.stage(entry["id"], "set", 11.5)
assert w.review()["actionCount"] == 1
w.cancel()
assert w.review()["count"] == 0
assert root["GameState"]["LifetimeTraitStats"]["UnknownHistoricBoon"]["UnknownFutureMeasure"] == 999
assert root["GameState"]["RunHistory"][1]["GameplayTime"] == 123.5

empty, _ = workspace({})
default = next(row for group in empty.query(domain="entities", scope="records", language="en")["entities"]
               for row in group["items"] if row["rawId"] == "FishingFails")
assert default["editable"] and default["beforePresent"] is False and default["value"] == 0
zero, _ = workspace({"FishingFails": 0})
assert any(g["id"] == "history:gathering:fishing" for g in zero.query(
    domain="entities", scope="records", language="en")["entities"])
# An unsupported/ambiguous owner is visible as a read-only limitation. It does
# not break other domains, discard original bytes, or promote unknown fields.
malformed, saved = workspace({"RunHistory": table({1: "not a run"}), "FishingFails": 2})
unavailable = malformed.query(domain="entities", scope="records", language="en")
assert any(g["id"] == "history:unavailable:RunHistory" for g in unavailable["entities"])
assert saved["GameState"]["RunHistory"][1] == "not a run"
assert any(g["id"] == "history:gathering:fishing" for g in unavailable["entities"])

# Literal duplicate keys have no unique native owner. Do not present two
# seemingly authoritative controls with the same physical path and row ID.
duplicates = LuaTable(0, 2, [("KnownBoon", 1), ("KnownBoon", 2)])
for field, value, unavailable_owner in (
    ("RunHistory", table({1: table({"RunResult": 1, "TraitCache": duplicates})}), "RunHistory"),
    ("FishCaught", duplicates, "FishCaught"),
):
    duplicate, document = workspace({field: value})
    duplicate_page = duplicate.query(domain="entities", scope="records", language="en")
    duplicate_rows = [row for group in duplicate_page["entities"] for row in group["items"]
                      if row["path"][-1] == "KnownBoon"]
    assert duplicate_rows and all(not row["editable"] and row["reasonCode"] == "ambiguousHistoryPath"
                                  for row in duplicate_rows)
    if field == "RunHistory":
        result_row = next(row for group in duplicate_page["entities"] for row in group["items"]
                          if row["rawId"] == "RunResult")
        assert result_row["editable"], "one ambiguous trait hid an unrelated unique result"
    assert document["GameState"][field] is value

with tempfile.TemporaryDirectory(prefix="mgt-history-names-") as temporary:
    source = Path(temporary)
    for language, boon, fish in (("en", "Divine Strike", "Silver Carp"),
                                ("zh-CN", "神圣攻击", "银鲤")):
        (source / ("History." + language + ".sjson")).write_text(
            'Id = "KnownBoon" DisplayName = "' + boon + '"\n'
            'Id = "KnownFish" DisplayName = "' + fish + '"\n', encoding="utf-8")
    named, _ = workspace({
        "RunHistory": table({1: table({"RunResult": 1, "TraitCache": table({"KnownBoon": 2})})}),
        "LifetimeTraitStats": table({"KnownBoon": table({"UseCount": 3})}),
        "FishCaught": table({"KnownFish": 1}),
    }, game_path=str(source))
    for language, boon, fish in (("en", "Divine Strike", "Silver Carp"),
                                ("zh-CN", "神圣攻击", "银鲤")):
        values = named.query(domain="entities", scope="records", language=language, limit=100)["entities"]
        by_id = {group["id"]: group for group in values}
        assert boon in by_id["history:trait:KnownBoon"]["name"]
        row = next(row for row in by_id["history:run:1"]["items"] if row["rawId"] == "trait:KnownBoon")
        assert boon in row["name"] and row["englishName"] == "Trait · Divine Strike"
        assert by_id["history:collection:FishCaught"]["items"][0]["name"] == fish
print("hades2_save_history_ok")
