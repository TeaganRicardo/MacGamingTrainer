"""Hades entity queries and native-owner mutations on isolated in-memory Save data."""
import hashlib
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.save_document import LuaTable
from games.hades2.save_investigation import NativeDialogueInvestigation
from games.hades2.save_workspace import Hades2SaveWorkspace
from games.hades2.command_contract import _save_editor_query


def table(mapping):
    return LuaTable(0, len(mapping), list(mapping.items()))


state = table({
    "Resources": table({"MetaCurrency": 123, "GiftPoints": 0}),
    "GameplayTime": 10.0, "TotalTime": 20.0,
    "TotalRequiredEnemyKills": 0,
    "NPCInteractions": table({"NPC_Nemesis_01": 3}),
    "MetaUpgradeState": table({
        "ChanneledCast": table({"Unlocked": True, "Level": 2, "Equipped": False}),
    }),
    "Flags": table({}),
    "TextLinesRecord": table({}),
    "TextLinesChoiceRecord": table({}),
    "GiftTextLinesOrderRecord": table({}),
})
root = table({"GameState": state, "CurrentRun": table({})})
session = SimpleNamespace(document=SimpleNamespace(lua_state=root), relative_path="Profile1.sav")
workspace = Hades2SaveWorkspace(session, "Profile1", game_path="/nonexistent/mgt-test-game")

all_page = workspace.query(domain="entities", language="en", limit=200)
assert all_page["scope"] == "all" and all_page["total"] >= 3
assert any(group["id"] == "entry:resource:MetaCurrency" for group in all_page["entities"])
assert all(len(group["items"]) > 0 for group in all_page["entities"])
assert all(not any(k.startswith("_") for k in row)
           for group in all_page["entities"] for row in group["items"])

# The native Arcana state has multiple independent mutations on one entity.
arcana = workspace.query(domain="entities", scope="growth",
                         search="ChanneledCast", language="en", limit=1)
assert arcana["total"] == 1
assert arcana["entities"][0]["id"] == "arcana:ChanneledCast"
fields = arcana["entities"][0]["items"]
assert {row["id"] for row in fields} == {
    "card:ChanneledCast:Unlocked", "card:ChanneledCast:Level", "card:ChanneledCast:Equipped",
}
assert all(row["editable"] and row["mutationKinds"] == ["set"]
           for row in fields)
# Read-only query never changes the pinned original Save.
assert root["GameState"]["MetaUpgradeState"]["ChanneledCast"]["Level"] == 2
workspace.stage("card:ChanneledCast:Level", "set", 3)
assert root["GameState"]["MetaUpgradeState"]["ChanneledCast"]["Level"] == 2
assert workspace.review()["actionCount"] == 1
assert workspace.review()["changes"][0]["after"] == 3
workspace.cancel()

# Stable native person identity, including the official NPC_ scene variant.
people = workspace.query(domain="entities", scope="story",
                         search="Nemesis", language="zh-CN", limit=10)
assert any(group["id"] == "person:Nemesis" and
           any(row["id"] == "interaction:NPC_Nemesis_01" for row in group["items"])
           for group in people["entities"])

# Players may deliberately find a missing, native-authorized resource.
missing = workspace.query(domain="entities", scope="resources",
                          search="GiftPoints", language="en")
assert any(group["id"] == "entry:resource:GiftPoints" and group["items"][0]["value"] == 0 for group in missing["entities"])
assert not any(row["rawId"] == "GiftPoints"
               for group in workspace.query(domain="entities", scope="resources")["entities"]
               for row in group["items"])

# Scope is validated at command and workspace seams, not quietly reinterpreted.
assert _save_editor_query({"domain": "entities", "scope": "growth", "search": "ChanneledCast"})["scope"] == "growth"
for invalid in ("future", "", 5, None):
    try:
        _save_editor_query({"domain": "entities", "scope": invalid})
    except (ValueError, TypeError):
        pass
    else:
        raise AssertionError("unknown browse scope was accepted")
# A real source-verified scene can attach its recorded physical dialogue field
# to the same NPC as interaction history. Unverified IDs cannot borrow identity.
state["TextLinesRecord"]["NemesisPostTrueEnding01"] = True
with tempfile.TemporaryDirectory(prefix="mgt-entity-source-") as directory:
    game = Path(directory)
    scripts = game / "sources/Scripts"
    english = game / "sources/Text/en"
    scripts.mkdir(parents=True)
    english.mkdir(parents=True)
    reset = scripts / "StoryResetData.lua"
    reset.write_text('StoryResetData = { TextLines = { "NemesisPostTrueEnding01" } }')
    (scripts / "NPCData_Nemesis.lua").write_text('''UnitSetData = {
      NPC_Nemesis_01 = { InteractTextLineSets = {
        NemesisPostTrueEnding01 = { { Cue = "/VO/Nemesis_0407", Text = "I remember this" } },
      } },
    }''')
    (english / "_NPCData_Nemesis.en.sjson").write_text('''{ Texts = [
      { Id = "NPC_Nemesis_01" DisplayName = "Nemesis" }
      { Id = "Nemesis_0407" DisplayName = "I remember this" Event = "NemesisPostTrueEnding01" }
    ] }''')
    workspace._investigation = NativeDialogueInvestigation(
        game, expected_hash=hashlib.sha256(reset.read_bytes()).hexdigest())
    linked = workspace.query(domain="entities", scope="story",
                             search="Nemesis", language="en", limit=1)
    assert workspace._investigation.native["status"] == "available"
    assert linked["total"] >= 1
    person = next(group for group in linked["entities"] if group["id"] == "person:Nemesis")
    assert {"interaction:NPC_Nemesis_01", "dialogue:NemesisPostTrueEnding01"}.issubset(
                {row["id"] for row in person["items"]})
    assert all("NemesisPostTrueEnding01" not in row["name"] for row in person["items"]
               if row["domain"] in ("dialogue", "investigate"))
    scene = next(row for row in person["items"] if row["id"] == "dialogue:NemesisPostTrueEnding01")
    assert scene["editable"] and scene["content"] == ["I remember this"]
    assert not any(row["domain"] == "investigate" for row in person["items"])

print("Hades source-owned entity query and staging contract: PASS")
