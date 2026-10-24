"""Save interaction counters use native actions and recognizable object owners."""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
from games.hades2.save_document import LuaTable
from games.hades2.save_workspace import Hades2SaveWorkspace


def table(values):
    return LuaTable(0, len(values), list(values.items()))


with tempfile.TemporaryDirectory(prefix="mgt-save-field-meanings-") as directory:
    game = Path(directory)
    for language, names in {
        "en": {"NPC_Hecate_01": "Hecate", "NPC_Apollo_Story_01": "Apollo",
               "FrogFamiliar": "Frinos", "Shrine": "Oath of the Unseen",
               "NPCUseTextSpecial": "Salute", "FamiliarUseTextSpecial": "Confide",
               "Objective_NemesisBet": "Win the wager", "DashStrike": "Dash-Strike",
               "Objective_WeaponStaffDash": "{$Keywords.DashStrike}{!Icons.ObjectiveSeparator}Press {RU} then {A2}",
               "Objective_WeaponStaffSwing5": "{!Icons.Omega} Attack{!Icons.ObjectiveSeparator}Hold {A2}"},
        "zh-CN": {"NPC_Hecate_01": "赫卡忒", "NPC_Apollo_Story_01": "阿波罗",
                  "FrogFamiliar": "弗利诺斯", "Shrine": "无形者之誓",
                  "NPCUseTextSpecial": "致意", "FamiliarUseTextSpecial": "倾诉",
                  "Objective_NemesisBet": "赢得赌约", "DashStrike": "突袭",
                  "Objective_WeaponStaffDash": "{$Keywords.DashStrike}{!Icons.ObjectiveSeparator}按 {RU} 后按 {A2}",
                  "Objective_WeaponStaffSwing5": "{!Icons.Omega} 攻击{!Icons.ObjectiveSeparator}长按 {A2}"},
    }.items():
        folder = game / "sources/Text" / language
        folder.mkdir(parents=True)
        (folder / ("Fields." + language + ".sjson")).write_text("\n".join(
            '{ Id = "' + key + '" DisplayName = "' + value + '" }'
            for key, value in names.items()), encoding="utf-8")
    state = table({"Resources": table({}), "Flags": table({}),
        "NPCInteractions": table({"NPC_Hecate_01": 3}),
        "SpecialInteractRecord": table({"NPC_Hecate_01": 4, "FrogFamiliar": 5, "Shrine": 1}),
        "ObjectivesCompleted": table({"NemesisBet": 2})})
    root = table({"GameState": state, "CurrentRun": table({})})
    session = SimpleNamespace(document=SimpleNamespace(lua_state=root), relative_path="Profile1.sav")
    workspace = Hades2SaveWorkspace(session, "Profile1", game_path=game)
    page = workspace.query(domain="entities", scope="story", search="Hecate Salute", language="en")
    assert page["total"] == 1, "the actual salute action cannot be found by its character and purpose"
    person = page["entities"][0]
    assert person["id"] == "person:Hecate"
    fields = {row["id"]: row for row in person["items"]}
    assert "Conversations" in fields["interaction:NPC_Hecate_01"]["name"]
    assert "Salute" in fields["specialInteraction:NPC_Hecate_01"]["name"]
    assert "Special interactions" not in str(fields)
    # Apollo's story object has no special handler. It must not acquire a
    # fabricated zero-valued salute just because it is a known NPC.
    apollo = workspace.query(domain="relationships", search="Apollo", language="en")
    assert all(row["id"] != "specialInteraction:NPC_Apollo_Story_01" for row in apollo["items"])
    familiar = workspace.query(domain="entities", search="弗利诺斯 倾诉", language="en")
    assert any(group["id"] == "familiar:FrogFamiliar" for group in familiar["entities"])
    shrine = workspace.query(domain="entities", search="Shrine", language="en")
    assert any("Fate" in row["name"]
               for group in shrine["entities"] for row in group["items"]
               if row["id"] == "specialInteraction:Shrine")
    objective = workspace.query(domain="entities", scope="records", search="赢得赌约", language="en")
    assert any(row["id"] == "objective:NemesisBet" for group in objective["entities"] for row in group["items"])
    for query, identity, label in (("突袭", "WeaponStaffDash", "Dash-Strike"),
                                    ("Ω 攻击", "WeaponStaffSwing5", "Ω Attack")):
        objective = workspace.query(domain="entities", scope="records", search=query, language="en")
        row = next(row for group in objective["entities"] for row in group["items"] if row["id"] == "objective:" + identity)
        assert row["name"] == "Objective completions · " + label
    owners = workspace.query(domain="relationships", language="en", limit=200)["items"]
    assert all("Recorded value" not in row["name"] and "Special interactions" not in row["name"] for row in owners)
    assert next(row for row in owners if row["id"] == "specialInteraction:HubGardenPlot")["entityName"] == "Soil Plots"
    # The renamed descriptor retains the exact writable field and staging path.
    workspace.stage("specialInteraction:NPC_Hecate_01", "set", 7)
    assert workspace.review()["actions"][0]["after"] == 7
    assert state["SpecialInteractRecord"]["NPC_Hecate_01"] == 4
    workspace.cancel()
    state["SpecialInteractRecord"]["FutureInteraction"] = "stored value"
    state["Flags"]["FutureFlag"] = True
    state["LifetimeTraitStats"] = table({"FutureTrait": table({"UseCount": 2})})
    for needle in ("FutureInteraction", "FutureFlag", "FutureTrait"):
        ordinary = workspace.query(domain="entities", search=needle, language="en")
        assert ordinary["total"] == 0, "unidentified data was given a misleading ordinary label"
    raw = workspace.query(domain="advanced", path=["GameState", "SpecialInteractRecord"], language="en")
    future = next(row for row in raw["items"] if row["rawId"] == "FutureInteraction")
    assert future["editable"] and future["value"] == "stored value"

print("save field native meaning, owner and bilingual action search: PASS")
