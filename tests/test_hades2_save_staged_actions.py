"""Staged Save actions remain editable while linked effects are recomputed."""
import struct
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.adapter import GameAdapter, GameAdapterContext
from core.module_manifest import SaveManagementSpec, SaveRootSpec
from core.protocol import JsonlRequestRouter
from core.save_service import CoreSaveService
from games.hades2.save_document import Hades2SaveDocument, Hades2SaveHeader, LuaTable
from games.hades2.save_provider import Hades2SaveProvider
from games.hades2.save_edit import Hades2SaveEditSession
from games.hades2.save_workspace import Hades2SaveWorkspace
from games.hades2.command_contract import Hades2CommandContract


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
ARCANA_CACHE_EFFECTS = {
    "linked:arcanaCache:MetaUpgradeUnlockedCountCache",
    "linked:arcanaCache:MetaUpgradeMaxLevelCountCache",
    "linked:arcanaCache:MetaUpgradeCostCache",
    "linked:arcanaCache:MaxMetaUpgradeCostCache",
}
saves, workspace = environment("basic", state)
workspace.stage("card:ChanneledCast:Unlocked", "set", False)
workspace.stage("interaction:NPC_Hecate_01", "set", 4)
workspace.stage("resource:MetaCurrency", "set", 50)
review = workspace.review(language="en")
assert review["actionCount"] == 3
assert review["effectCount"] == 6
assert review["physicalChangeCount"] == 9
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
} | ARCANA_CACHE_EFFECTS
zh_arcana = workspace.review(language="zh-CN")["actions"][0]["effects"]
assert any(effect["name"].endswith("已装备") for effect in zh_arcana)
assert any(effect["name"].endswith("等级") for effect in zh_arcana)

# Remove only the middle requested action. Surviving requested actions and
# their dependent effects are recomputed from authoritative staged intent.
review = workspace.unstage("interaction:NPC_Hecate_01", language="en")
assert review["actionCount"] == 2
assert [action["entryId"] for action in review["actions"]] == [
    "card:ChanneledCast:Unlocked", "resource:MetaCurrency",
]
assert review["effectCount"] == 6

# Restaging an existing action revises it in place rather than adding another
# user action, even after unrelated query/browse work.
workspace.query(domain="entities", scope="resources", search="", language="en")
review = workspace.stage("resource:MetaCurrency", "set", 75, language="en")
assert review["actionCount"] == 2
assert review["actions"][1]["entryId"] == "resource:MetaCurrency"
assert review["actions"][1]["after"] == 75
assert review["physicalChangeCount"] == 8
assert {row["id"] for row in review["changes"]} == {
    "card:ChanneledCast:Unlocked",
    "resource:MetaCurrency",
    "linked:card:ChanneledCast:Equipped",
    "linked:card:ChanneledCast:Level",
} | ARCANA_CACHE_EFFECTS

# Cancel clears the requested-action set without touching the loaded source;
# re-staging reconstructs the same linked projection from intent, not cached diff.
cancelled = workspace.cancel(language="en")
assert cancelled["actionCount"] == 0
assert cancelled["physicalChangeCount"] == 0
assert workspace.document.lua_state["GameState"]["Resources"]["MetaCurrency"] == 10
workspace.stage("card:ChanneledCast:Unlocked", "set", False, language="en")
review = workspace.stage("resource:MetaCurrency", "set", 75, language="en")
assert review["actionCount"] == 2
assert review["effectCount"] == 6
assert review["physicalChangeCount"] == 8

# Applying the remaining two requested actions crosses the Save transaction
# exactly once and clears the action basket.
result = workspace.apply()
assert result["changeCount"] == 2
assert workspace.review(language="en")["actionCount"] == 0
installed = Hades2SaveDocument.load(saves / "Profile1.sav").lua_state["GameState"]
assert installed["Resources"]["MetaCurrency"] == 75
card = installed["MetaUpgradeState"]["ChanneledCast"]
assert card.get("Unlocked") is None and card.get("Equipped") is None and card["Level"] == 1

# A direct Arcana level intent owns the same physical field as the unlock
# action's implicit reset. Do not show that field twice; removing the direct
# intent must restore the linked effect from the pinned source.
arcana_overlap_state = {
    "MetaUpgradeState": table({
        "ChanneledCast": table({"Unlocked": True, "Equipped": True, "Level": 2.0}),
    }),
    "ObjectivesCompleted": table({}),
    "CompletedObjectiveSets": table({}),
}
_, arcana_overlap = environment("arcana-overlap", arcana_overlap_state)
arcana_overlap.stage("card:ChanneledCast:Unlocked", "set", False, language="en")
overlap_review = arcana_overlap.stage("card:ChanneledCast:Level", "set", 1, language="en")
assert overlap_review["actionCount"] == 2
assert overlap_review["effectCount"] == 5
assert overlap_review["physicalChangeCount"] == 7
assert {row["id"] for row in overlap_review["changes"]} == {
    "card:ChanneledCast:Unlocked",
    "card:ChanneledCast:Level",
    "linked:card:ChanneledCast:Equipped",
} | ARCANA_CACHE_EFFECTS
assert len({row["id"] for row in overlap_review["changes"]}) == 7
overlap_review = arcana_overlap.unstage("card:ChanneledCast:Level", language="en")
assert overlap_review["actionCount"] == 1
assert overlap_review["effectCount"] == 6
assert overlap_review["physicalChangeCount"] == 7
assert {row["id"] for row in overlap_review["changes"]} == {
    "card:ChanneledCast:Unlocked",
    "linked:card:ChanneledCast:Equipped",
    "linked:card:ChanneledCast:Level",
} | ARCANA_CACHE_EFFECTS

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
assert first["actions"][0]["effects"][0]["name"] == "Equipped Familiar"
assert first["actions"][0]["effects"][0]["afterDisplay"] == "None"
zh_familiar_effect = equipment.review(language="zh-CN")["actions"][0]["effects"][0]
assert zh_familiar_effect["name"] == "当前魔宠"
assert zh_familiar_effect["afterDisplay"] == "不携带"
second = equipment.stage("familiarSelection", "setEnum", "", language="en")
assert second["actionCount"] == 2
assert second["effectCount"] == 0
assert second["actions"][1]["choiceNames"][""] == "None"
assert equipment.review(language="zh-CN")["actions"][1]["choiceNames"][""] == "不携带"
third = equipment.unstage("familiarSelection", language="en")
assert third["actionCount"] == 1
assert third["effectCount"] == 1
assert third["actions"][0]["effects"][0]["id"] == "linked:familiarSelection"


# Known-invalid combined intent is rejected at the same Hades batch-validation
# seam used by Apply. The previously valid action survives the rejected edit.
owned = {
    "WeaponDagger", "DaggerBlockAspect", "DaggerBlockAspect2",
}
conflict_state = {
    "WeaponsUnlocked": table({key: True for key in owned}),
    "WorldUpgrades": table({key: True for key in owned}),
    "WorldUpgradesAdded": table({key: True for key in owned}),
    "LastWeaponUpgradeName": table({"WeaponDagger": "DaggerBlockAspect"}),
    "FamiliarsUnlocked": table({}),
}
_, conflict = environment("conflict", conflict_state)
first = conflict.stage("weapon:WeaponDagger", "set", False, language="en")
assert first["actionCount"] == 1
try:
    conflict.stage("aspect:DaggerBlockAspect", "set", 4, language="en")
except ValueError as error:
    assert "conflict" in str(error).lower() or "owned" in str(error).lower(), error
else:
    raise AssertionError("known-invalid combined staged actions were accepted")
survivors = conflict.review(language="en")
assert survivors["actionCount"] == 1
assert survivors["actions"][0]["entryId"] == "weapon:WeaponDagger"

# A source-known but read-only relationship record never becomes a requested
# action merely because it is visible in the entity/search projection.
gift_npc = LuaTable(1, 1, [(1.0, "GiftPoints"), ("GiftPoints", 1.0)])
read_only_state = {
    "NPCInteractions": table({"NPC_Hecate_01": 1.0}),
    "SpecialInteractRecord": table({}),
    "GiftRecord": table({"Hecate": gift_npc}),
    "GiftResourceRecord": table({"GiftPoints": 1.0}),
    "MetaUpgradeState": table({}),
    "ObjectivesCompleted": table({}),
    "CompletedObjectiveSets": table({}),
}
_, read_only = environment("read-only", read_only_state)
gift_rows = read_only.query(domain="relationships", language="en")["items"]
gift = next(row for row in gift_rows if row["id"] == "gift:Hecate:GiftPoints")
assert gift["editable"] is False
try:
    read_only.stage("gift:Hecate:GiftPoints", "set", 0, language="en")
except ValueError:
    pass
else:
    raise AssertionError("read-only gift history became a staged action")
assert read_only.review(language="en")["actionCount"] == 0

# If a previously staged physical owner becomes ambiguous, review fails closed
# without discarding that intent; the user can still explicitly remove it.
_, stale = environment("stale-owner", {})
stale.stage("playerStat:GameplayTime", "set", 333.0, language="en")
game_state = stale.document.lua_state["GameState"]
game_state._entries.append(("GameplayTime", 999.0))
game_state.hash_size += 1
try:
    stale.review(language="en")
except ValueError as error:
    assert "ambiguous" in str(error).lower(), error
else:
    raise AssertionError("stale/ambiguous staged owner was reviewed as valid")
assert len(stale._pending) == 1
assert stale.unstage("playerStat:GameplayTime", language="en")["actionCount"] == 0

# A transaction failure restores the loaded document projection and keeps the
# requested action available for inspection/retry; no failed Apply clears it.
failure_saves, failed_apply = environment("apply-failure", {})
failed_apply.stage("resource:MetaCurrency", "set", 42, language="en")
original_document = failed_apply.document
original_disk = (failure_saves / "Profile1.sav").read_bytes()
with patch.object(Hades2SaveEditSession, "apply", side_effect=RuntimeError("simulated apply failure")):
    try:
        failed_apply.apply()
    except RuntimeError:
        pass
    else:
        raise AssertionError("simulated Save transaction failure was swallowed")
assert failed_apply.document is original_document
assert failed_apply.review(language="en")["actionCount"] == 1
assert (failure_saves / "Profile1.sav").read_bytes() == original_disk


# The real JSONL route must preserve a Hades-owned actionable presentation key
# and the localized action labels when combined equipment validation rejects
# a staged operation. Generic host invalidRequest is not sufficient.
class SaveActionJSONLAdapter(GameAdapter):
    def __init__(self, workspace):
        super().__init__(GameAdapterContext(
            game_id="hades2",
            display_name="Hades II",
            module_protocol_version=15,
            module_dir=ROOT / "Backend/games/hades2",
            public_metadata={"protocolVersion": 15},
        ))
        self.workspace = workspace
        self.command_contract = Hades2CommandContract(self)

    def dispatch(self, command, params, request_id):
        return self.command_contract.dispatch(command, params, request_id)

    def validate_save_workspace(self, identifier):
        if identifier != self.workspace.identifier:
            raise ValueError("Save Editor document is no longer selected.")

    def stage_save_editor(self, params):
        return self.workspace.stage(
            params["entryId"], params["operation"], params.get("value"),
            language=params["language"],
        )

    def close(self):
        pass


jsonl_saves, jsonl_workspace = environment("jsonl-conflict", conflict_state)
equipment_rows = {
    row["id"]: row
    for row in jsonl_workspace.query(domain="weapons", language="en")["items"]
}
router_data = tempfile.TemporaryDirectory(prefix="mgt-save-action-jsonl-")
router = JsonlRequestRouter(
    SaveActionJSONLAdapter(jsonl_workspace),
    save_data_root=Path(router_data.name),
    target_running_probe=lambda: False,
)
try:
    first_reply = router.handle({
        "id": "stage-weapon",
        "command": "save_editor_stage",
        "params": {
            "workspaceId": jsonl_workspace.identifier,
            "entryId": "weapon:WeaponDagger",
            "operation": "set",
            "value": False,
            "language": "en",
        },
    })
    assert first_reply["ok"] is True, first_reply
    rejected = router.handle({
        "id": "stage-conflicting-aspect",
        "command": "save_editor_stage",
        "params": {
            "workspaceId": jsonl_workspace.identifier,
            "entryId": "aspect:DaggerBlockAspect",
            "operation": "set",
            "value": 4,
            "language": "en",
        },
    })
    assert rejected["ok"] is False, rejected
    error = rejected["error"]
    expected_keys = {
        "Save Editor equipment changes conflict.": "hades2.saveEditor.error.equipmentChangesConflict",
        "Save Editor locked weapon has acquired aspects.": "hades2.saveEditor.error.lockedWeaponHasAspects",
        "Save Editor unlocked weapon lacks default aspect.": "hades2.saveEditor.error.unlockedWeaponNeedsDefaultAspect",
        "Save Editor selected aspect is not purchased.": "hades2.saveEditor.error.selectedAspectNotPurchased",
    }
    assert expected_keys.get(error.get("diagnostic")) == error.get("presentation"), error
    assert error["code"] == "invalid_request", error
    assert len(error.get("arguments", [])) == 1, error
    labels = error["arguments"][0]
    for entry_id in ("weapon:WeaponDagger", "aspect:DaggerBlockAspect"):
        assert equipment_rows[entry_id]["name"] in labels, (entry_id, error)
    assert jsonl_workspace.review(language="en")["actionCount"] == 1
finally:
    router.close()
    router_data.cleanup()


# The same invalid familiar-selection/unlock pair must yield the same
# action-specific error in either staging order, even with unrelated equipment
# work in the basket. The unrelated tool must not appear in the error labels.
def familiar_conflict_in_order(name, ordered_actions):
    familiar_state = {
        "WeaponsUnlocked": table({}),
        "WorldUpgrades": table({}),
        "WorldUpgradesAdded": table({}),
        "LastWeaponUpgradeName": table({}),
        "FamiliarsUnlocked": table({"CatFamiliar": True, "RavenFamiliar": True}),
        "EquippedFamiliar": "CatFamiliar",
    }
    _, familiar_workspace = environment("familiar-order-" + name, familiar_state)
    rows = {
        row["id"]: row
        for row in familiar_workspace.query(domain="weapons", language="en")["items"]
    }
    router_data = tempfile.TemporaryDirectory(prefix="mgt-familiar-order-jsonl-")
    router = JsonlRequestRouter(
        SaveActionJSONLAdapter(familiar_workspace),
        save_data_root=Path(router_data.name),
        target_running_probe=lambda: False,
    )

    def stage(index, entry_id, operation, value):
        return router.handle({
            "id": "{}-{}".format(name, index),
            "command": "save_editor_stage",
            "params": {
                "workspaceId": familiar_workspace.identifier,
                "entryId": entry_id,
                "operation": operation,
                "value": value,
                "language": "en",
            },
        })

    try:
        unrelated = stage(0, "tool:ToolFishingRod", "set", 2)
        assert unrelated["ok"] is True, unrelated
        for index, (entry_id, operation, value) in enumerate(ordered_actions, start=1):
            reply = stage(index, entry_id, operation, value)
            if index < len(ordered_actions):
                assert reply["ok"] is True, reply
                continue
            assert reply["ok"] is False, reply
            error = reply["error"]
            assert error["presentation"] == "hades2.saveEditor.error.equippedFamiliarMustBeUnlocked", error
            assert error["diagnostic"] == "Save Editor equipped familiar must be unlocked.", error
            assert len(error.get("arguments", [])) == 1, error
            labels = error["arguments"][0]
            assert rows["familiarSelection"]["name"] in labels, (rows, error)
            assert rows["familiar:RavenFamiliar"]["name"] in labels, (rows, error)
            assert rows["tool:ToolFishingRod"]["name"] not in labels, (rows, error)
            assert familiar_workspace.review(language="en")["actionCount"] == 2
            return error["presentation"], labels
    finally:
        router.close()
        router_data.cleanup()


selection_then_lock = familiar_conflict_in_order(
    "selection-first",
    [
        ("familiarSelection", "setEnum", "RavenFamiliar"),
        ("familiar:RavenFamiliar", "set", False),
    ],
)
lock_then_selection = familiar_conflict_in_order(
    "unlock-first",
    [
        ("familiar:RavenFamiliar", "set", False),
        ("familiarSelection", "setEnum", "RavenFamiliar"),
    ],
)
assert selection_then_lock == lock_then_selection, (
    selection_then_lock, lock_then_selection
)

print("hades2_save_staged_actions_ok")
