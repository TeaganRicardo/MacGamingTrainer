"""Staged Save actions remain editable while linked effects are recomputed."""
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


def table(values):
    return LuaTable(0, len(values), list(values.items()))


def save_bytes(state):
    root = table({
        "GameState": table({
            "Resources": table({"MetaCurrency": 10.0, "GiftPoints": 2.0}),
            "GameplayTime": 100.0,
            "TotalTime": 200.0,
            "TotalRequiredEnemyKills": 3.0,
            "UnknownFutureField": table({"Keep": True}),
            **state,
        }),
        "CurrentRun": table({}),
    })
    header = Hades2SaveHeader(
        game_version=0x12, save_flags=0, timestamp=100,
        location="Crossroads", completed_runs=1, accumulated_meta_points=0,
        active_shrine_points=0, meta_upgrade_level=0, cosmetics_points=0,
        easy_mode=0, hard_mode=0, notable_lua_data=("GameState", "CurrentRun"),
        map_name="Hub_Main", next_map_name="F_Opening01",
    )
    return Hades2SaveDocument(header, [root]).to_bytes()


def environment(name, state):
    base = Path(tempfile.mkdtemp(prefix="mgt-save-actions-")) / name
    saves = base / "saves"
    saves.mkdir(parents=True)
    profile = b"Profile1"
    (saves / "activeProfile").write_bytes(b"SGB1" + struct.pack("<I", len(profile)) + profile)
    (saves / "Profile1.sav").write_bytes(save_bytes(state))
    spec = SaveManagementSpec(
        roots=(SaveRootSpec("main", str(saves), ("Profile*.sav", "activeProfile")),),
        provider="games.hades2.save_provider:Hades2SaveProvider",
        hot_backup=True, restore_policy="hotPreferred", staged_restore=True,
    )
    service = CoreSaveService(
        "hades2", spec, base / "data", lambda: False,
        provider_loader=lambda _target: Hades2SaveProvider(),
    )
    return saves, Hades2SaveWorkspace.open(service)


state = {
    "NPCInteractions": table({"NPC_Hecate_01": 1.0}),
    "SpecialInteractRecord": table({}),
    "GiftRecord": table({}),
    "GiftResourceRecord": table({}),
    "MetaUpgradeState": table({
        "ChanneledCast": table({"Unlocked": True, "Equipped": True, "Level": 2.0}),
    }),
    "ObjectivesCompleted": table({}),
    "CompletedObjectiveSets": table({}),
}
saves, workspace = environment("basic", state)
workspace.stage("card:ChanneledCast:Unlocked", "set", False)
workspace.stage("interaction:NPC_Hecate_01", "set", 4)
workspace.stage("resource:MetaCurrency", "set", 50)
review = workspace.review(language="en")
assert review["actionCount"] == 3
assert review["effectCount"] == 2
assert review["physicalChangeCount"] == 5
assert [action["entryId"] for action in review["actions"]] == [
    "card:ChanneledCast:Unlocked",
    "interaction:NPC_Hecate_01",
    "resource:MetaCurrency",
]
arcana = review["actions"][0]
assert arcana["entityId"] == "arcana:ChanneledCast"
assert arcana["name"]
assert arcana["valueType"] == "boolean"
assert {effect["id"] for effect in arcana["effects"]} == {
    "linked:card:ChanneledCast:Equipped",
    "linked:card:ChanneledCast:Level",
}

# Remove only the middle requested action. Surviving requested actions and
# their dependent effects are recomputed from authoritative staged intent.
review = workspace.unstage("interaction:NPC_Hecate_01", language="en")
assert review["actionCount"] == 2
assert [action["entryId"] for action in review["actions"]] == [
    "card:ChanneledCast:Unlocked", "resource:MetaCurrency",
]
assert review["effectCount"] == 2

# Restaging an existing action revises it in place rather than adding another
# user action, even after unrelated query/browse work.
workspace.query(domain="entities", scope="resources", search="", language="en")
review = workspace.stage("resource:MetaCurrency", "set", 75, language="en")
assert review["actionCount"] == 2
assert review["actions"][1]["entryId"] == "resource:MetaCurrency"
assert review["actions"][1]["after"] == 75

# Applying the remaining two requested actions crosses the Save transaction
# exactly once and clears the action basket.
result = workspace.apply()
assert result["changeCount"] == 2
assert workspace.review(language="en")["actionCount"] == 0
installed = Hades2SaveDocument.load(saves / "Profile1.sav").lua_state["GameState"]
assert installed["Resources"]["MetaCurrency"] == 75
card = installed["MetaUpgradeState"]["ChanneledCast"]
assert card.get("Unlocked") is None and card.get("Equipped") is None and card["Level"] == 1

# Overlapping direct/linked ownership must be recomputed rather than cached.
# Disabling the equipped familiar implies clearing the selection. Explicitly
# staging that same selection suppresses the linked effect; removing the direct
# selection action makes the linked effect reappear under the surviving action.
equipment_state = {
    "WeaponsUnlocked": table({}),
    "WorldUpgrades": table({}),
    "WorldUpgradesAdded": table({}),
    "LastWeaponUpgradeName": table({}),
    "FamiliarsUnlocked": table({"HoundFamiliar": True}),
    "EquippedFamiliar": "HoundFamiliar",
}
_, equipment = environment("overlap", equipment_state)
first = equipment.stage("familiar:HoundFamiliar", "set", False, language="en")
assert first["effectCount"] == 1
assert first["actions"][0]["effects"][0]["id"] == "linked:familiarSelection"
second = equipment.stage("familiarSelection", "setEnum", "", language="en")
assert second["actionCount"] == 2
assert second["effectCount"] == 0
third = equipment.unstage("familiarSelection", language="en")
assert third["actionCount"] == 1
assert third["effectCount"] == 1
assert third["actions"][0]["effects"][0]["id"] == "linked:familiarSelection"

print("hades2_save_staged_actions_ok")
