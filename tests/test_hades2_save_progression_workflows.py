"""Permanent entity journeys use native linked owners on temporary Save files."""
import copy
import struct
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.module_manifest import SaveManagementSpec, SaveRootSpec
from core.save_service import CoreSaveService
from games.hades2.save_document import Hades2SaveDocument, Hades2SaveHeader, LuaTable
from games.hades2.save_provider import Hades2SaveProvider
from games.hades2.save_workspace import Hades2SaveWorkspace


def table(values):
    return LuaTable(0, len(values), list(values.items()))


def rejects(work):
    try:
        work()
    except ValueError:
        return
    raise AssertionError("unsupported progression mutation was accepted")


def entity(workspace, identity, search):
    page = workspace.query(domain="entities", scope="growth", search=search,
                           language="en", limit=200)
    return next(item for item in page["entities"] if item["id"] == identity)


with tempfile.TemporaryDirectory(prefix="mgt-permanent-entities-") as directory:
    base = Path(directory)
    saves = base / "saves"
    saves.mkdir()
    game = base / "game"
    labels = {
        "en": {"FrogFamiliar": "Frinos", "FrogHealthBonus": "Life Bond",
               "ToolPickaxe": "Crescent Pick", "ChanneledCast": "The Sorceress"},
        "zh-CN": {"FrogFamiliar": "弗利诺斯", "FrogHealthBonus": "生命纽带",
                  "ToolPickaxe": "月牙镐", "ChanneledCast": "女术士"},
    }
    for language, names in labels.items():
        text = game / language / ("Fixture." + language + ".sjson")
        text.parent.mkdir(parents=True)
        text.write_text("\n".join(
            '{{ Id = "{}" DisplayName = "{}" }}'.format(key, value)
            for key, value in names.items()
        ))
    state = table({
        "Resources": table({"FamiliarPoints": 9}),
        "GameplayTime": 1.0, "TotalTime": 2.0, "TotalRequiredEnemyKills": 0,
        "WeaponsUnlocked": table({"WeaponStaffSwing": True, "ToolPickaxe": True}),
        "WorldUpgrades": table({"ToolPickaxe": True, "FutureUpgrade": True}),
        "WorldUpgradesAdded": table({"ToolPickaxe": True, "FutureUpgrade": True}),
        "LastWeaponUpgradeName": table({}),
        "FamiliarsUnlocked": table({"RavenFamiliar": True}),
        "EquippedFamiliar": "RavenFamiliar",
        "FamiliarUpgrades": table({"FutureFamiliarUpgrade": True}),
        "MetaUpgradeState": table({
            "ChanneledCast": table({"Unlocked": True, "Level": 2, "Equipped": True}),
        }),
        "MetaUpgradeUnlockedCountCache": 1,
        "MetaUpgradeMaxLevelCountCache": 0,
        "MetaUpgradeCostCache": 1,
    })
    current_run = table({"UnchangedRuntimeOwner": table({"Familiar": "RavenFamiliar"})})
    document = Hades2SaveDocument(Hades2SaveHeader(
        game_version=0x12, save_flags=0, timestamp=1, location="Crossroads",
        completed_runs=1, accumulated_meta_points=0, active_shrine_points=0,
        meta_upgrade_level=0, cosmetics_points=0, easy_mode=0, hard_mode=0,
        notable_lua_data=("GameState", "CurrentRun"), map_name="Hub_Main", next_map_name="F_Opening01",
    ), [table({"GameState": state, "CurrentRun": current_run})])
    path = saves / "Profile1.sav"
    path.write_bytes(document.to_bytes())
    profile = b"Profile1"
    (saves / "activeProfile").write_bytes(b"SGB1" + struct.pack("<I", len(profile)) + profile)
    spec = SaveManagementSpec(
        roots=(SaveRootSpec("main", str(saves), ("Profile*.sav", "activeProfile")),),
        provider="games.hades2.save_provider:Hades2SaveProvider", hot_backup=True,
        restore_policy="hotPreferred", staged_restore=True,
    )
    service = CoreSaveService("hades2", spec, base / "data", lambda: False,
                              provider_loader=lambda _target: Hades2SaveProvider(game_path=game))
    workspace = Hades2SaveWorkspace.open(service)
    original = path.read_bytes()
    frog = entity(workspace, "familiar:FrogFamiliar", "Frinos")
    fields = {row["id"]: row for row in frog["items"]}
    assert "familiarUpgrade:FrogHealthBonus" in fields, "native Familiar upgrade rank is missing"
    assert fields["familiarUpgrade:FrogHealthBonus"]["value"] == 0
    assert fields["familiarUpgrade:FrogHealthBonus"]["constraints"] == {"min": 0, "max": 3, "integer": True}
    assert fields["familiarUpgrade:FrogHealthBonus"]["name"] == "Life Bond · Purchased rank"
    assert fields["familiarSelected:FrogFamiliar"]["value"] is False
    assert "familiarSelection" not in fields, "entity repeats the global selection action"
    chinese = workspace.query(domain="entities", scope="growth", search="生命纽带", language="zh-CN")
    assert chinese["entities"][0]["name"] == "弗利诺斯"
    tool = entity(workspace, "tool:ToolPickaxe", "Crescent Pick")
    access = next(row for row in tool["items"] if row["id"] == "toolSelection:ToolPickaxe")
    assert access["value"] is True and access["editable"] is False
    assert access["blockReasonCode"] == "noIndependentToolSelection"
    card = entity(workspace, "arcana:ChanneledCast", "The Sorceress")
    equipped = next(row for row in card["items"] if row["id"] == "card:ChanneledCast:Equipped")
    assert equipped["value"] is True and equipped["editable"] is False
    assert equipped["blockReasonCode"] == "arcanaEquipmentGridOwned"

    workspace.stage("familiarUpgrade:FrogHealthBonus", "set", 3)
    workspace.stage("familiarSelected:FrogFamiliar", "set", True)
    workspace.stage("tool:ToolPickaxe", "set", 2)
    workspace.stage("card:ChanneledCast:Level", "set", 3)
    assert path.read_bytes() == original, "staging wrote the pinned Save"
    review = workspace.review()
    assert "linked:familiar:FrogFamiliar" in {row["id"] for row in review["changes"]}
    assert "linked:familiarSelection" not in {row["id"] for row in review["changes"]}
    assert next(row for row in review["changes"]
                if row["id"] == "linked:arcanaCache:MetaUpgradeMaxLevelCountCache")["after"] == 1
    workspace.apply()
    installed = Hades2SaveDocument.load(path).lua_state
    saved = installed["GameState"]
    for key in ("FrogHealthBonus", "FrogHealthBonus2", "FrogHealthBonus3"):
        for field in ("FamiliarUpgrades", "WorldUpgrades", "WorldUpgradesAdded"):
            assert saved[field][key] is True
    assert saved["FamiliarsUnlocked"]["FrogFamiliar"] is True
    assert saved["EquippedFamiliar"] == "FrogFamiliar"
    assert saved["WeaponsUnlocked"]["ToolPickaxe2"] is True
    assert saved["MetaUpgradeState"]["ChanneledCast"]["Level"] == 3
    assert saved["MetaUpgradeUnlockedCountCache"] == 1
    assert saved["MetaUpgradeMaxLevelCountCache"] == 1, "Arcana purchase left native progress cache stale"
    assert saved["MetaUpgradeCostCache"] == 1
    assert saved["FamiliarUpgrades"]["FutureFamiliarUpgrade"] is True
    assert installed["CurrentRun"]["UnchangedRuntimeOwner"]["Familiar"] == "RavenFamiliar"

    reopened = Hades2SaveWorkspace.open(service)
    reopened.stage("familiarUpgrade:FrogHealthBonus", "set", 1)
    reopened.apply()
    saved = Hades2SaveDocument.load(path).lua_state["GameState"]
    assert saved["FamiliarUpgrades"].get("FrogHealthBonus2") is None
    assert saved["WorldUpgrades"].get("FrogHealthBonus3") is None
    assert saved["WorldUpgradesAdded"]["FrogHealthBonus3"] is True, "downgrade erased purchase history"

    revoked = Hades2SaveWorkspace.open(service)
    revoked.stage("familiar:FrogFamiliar", "set", False)
    effects = {row["id"] for row in revoked.review()["changes"]}
    assert "linked:familiarUpgrade:FrogHealthBonus" in effects
    assert "linked:familiarSelection" in effects
    revoked.apply()
    saved = Hades2SaveDocument.load(path).lua_state["GameState"]
    assert saved.get("EquippedFamiliar") is None
    assert saved["FamiliarUpgrades"].get("FrogHealthBonus") is None
    assert saved["WorldUpgradesAdded"]["FrogHealthBonus"] is True
    assert saved["FamiliarUpgrades"]["FutureFamiliarUpgrade"] is True

    invalid = Hades2SaveWorkspace.open(service)
    rejects(lambda: invalid.stage("familiarUpgrade:FrogHealthBonus", "set", 4))
    try:
        invalid.stage("familiarSelected:FrogFamiliar", "set", True)
    except ValueError as error:
        assert "Frinos" in " ".join(getattr(error, "arguments", ())), error
    else:
        raise AssertionError("selection of a locked Familiar was accepted")
    rejects(lambda: invalid.stage("toolSelection:ToolPickaxe", "set", False))
    rejects(lambda: invalid.stage("card:ChanneledCast:Equipped", "set", False))
    assert invalid.review()["actionCount"] == 0
    discovery = invalid.query(domain="discover", search="FutureFamiliarUpgrade", language="en")
    assert discovery["items"] and all(not row["editable"] for row in discovery["items"])

    def inspection(root):
        session = SimpleNamespace(document=SimpleNamespace(lua_state=root), relative_path="Profile1.sav")
        return Hades2SaveWorkspace(session, "Profile1", game_path=game)

    # Native automatic-card equipment depends on the complete saved loadout.
    # An equipped manual-card revoke must not advertise a partial linked write.
    root = copy.deepcopy(Hades2SaveDocument.load(path).lua_state)
    root["GameState"]["MetaUpgradeState"]["MaxHealthPerRoom"] = table({
        "Unlocked": True, "Level": 1, "Equipped": True,
    })
    editor = inspection(root)
    card_rows = {row["id"]: row for row in editor.query(domain="progression")["items"]}
    for identity in ("card:ChanneledCast:Unlocked", "card:MaxHealthPerRoom:Unlocked"):
        assert card_rows[identity]["editable"] is False, identity
        assert card_rows[identity]["blockReasonCode"] == "arcanaUnlockLoadoutOwned"
        rejects(lambda: editor.stage(identity, "set", False))
    assert card_rows["card:ChanneledCast:Level"]["editable"] is True
    assert card_rows["card:MaxHealthPerRoom:Level"]["editable"] is True

    # The same automatic owner does not prevent changing an unequipped manual
    # card's progression: native requirements depend on equipped costs/grid.
    root["GameState"]["MetaUpgradeState"]["ChanneledCast"].pop("Equipped", None)
    editor = inspection(root)
    card_rows = {row["id"]: row for row in editor.query(domain="progression")["items"]}
    assert card_rows["card:ChanneledCast:Unlocked"]["editable"] is True
    editor.stage("card:ChanneledCast:Unlocked", "set", False)

    # Cache deltas retain opaque contribution; no unrelated card is rebuilt.
    root = copy.deepcopy(Hades2SaveDocument.load(path).lua_state)
    owner = root["GameState"]
    owner["MetaUpgradeState"]["FutureCard"] = table({"Level": 19, "Equipped": True})
    owner["MetaUpgradeUnlockedCountCache"] = 7
    owner["MetaUpgradeMaxLevelCountCache"] = 9
    owner["MetaUpgradeCostCache"] = 11
    editor = inspection(root)
    editor.stage("card:ChanneledCast:Unlocked", "set", False)
    effects = {row["rawId"]: row for row in editor.review()["changes"]
               if row["id"].startswith("linked:arcanaCache:")}
    assert {key: row["after"] for key, row in effects.items()} == {
        "MetaUpgradeUnlockedCountCache": 6,
        "MetaUpgradeMaxLevelCountCache": 8,
        "MetaUpgradeCostCache": 10,
    }
    assert owner["MetaUpgradeState"]["FutureCard"]["Level"] == 19
    assert owner["MetaUpgradeMaxLevelCountCache"] == 9
    for cache in tuple(effects):
        owner.pop(cache, None)
    editor = inspection(root)
    editor.stage("card:ChanneledCast:Level", "set", 2)
    assert not any(row["id"].startswith("linked:arcanaCache:")
                   for row in editor.review()["changes"]), "absent native caches were synthesized"

    for case in ("malformed", "duplicate", "underflow"):
        root = copy.deepcopy(Hades2SaveDocument.load(path).lua_state)
        owner = root["GameState"]
        if case == "malformed":
            owner["MetaUpgradeMaxLevelCountCache"] = "one"
        elif case == "duplicate":
            entries = list(owner.entries()) + [("MetaUpgradeMaxLevelCountCache", 2)]
            owner = LuaTable(0, len(entries), entries)
            root["GameState"] = owner
        else:
            owner["MetaUpgradeMaxLevelCountCache"] = 0
        editor = inspection(root)
        row = next(row for row in editor.query(domain="progression")["items"]
                   if row["id"] == "card:ChanneledCast:Level")
        assert row["editable"] is False, case
        assert row["blockReasonCode"] == ("ambiguousOwner" if case == "duplicate"
                                           else "arcanaProgressionCacheUnsupported")
        rejects(lambda: editor.stage("card:ChanneledCast:Level", "set", 2))

    # Each linked owner must be uniquely typed, contiguous and consistent.
    # Unknown upgrades remain untouched while unsafe known records are inspectable.
    for case in ("missing", "malformed", "gap", "mirror", "duplicate"):
        root = copy.deepcopy(Hades2SaveDocument.load(path).lua_state)
        owner = root["GameState"]
        owner["FamiliarsUnlocked"]["FrogFamiliar"] = True
        if case == "missing":
            owner.pop("FamiliarUpgrades", None)
        elif case == "malformed":
            owner["FamiliarUpgrades"] = True
        elif case == "gap":
            owner["FamiliarUpgrades"]["FrogHealthBonus2"] = True
            owner["WorldUpgrades"]["FrogHealthBonus2"] = True
        elif case == "mirror":
            owner["FamiliarUpgrades"]["FrogHealthBonus"] = True
        else:
            owner["FamiliarUpgrades"] = LuaTable(0, 2, [
                ("FrogHealthBonus", True), ("FrogHealthBonus", False),
            ])
        editor = inspection(root)
        row = next(row for row in editor.query(domain="weapons", language="en")["items"]
                   if row["id"] == "familiarUpgrade:FrogHealthBonus")
        assert row["editable"] is False, case
        assert row["mutationKinds"] == [], case
        expected = ("missingFamiliarUpgradeOwner" if case == "missing"
                    else "ambiguousOwner" if case == "duplicate"
                    else "familiarUpgradeOwnerUnsupported")
        assert row["blockReasonCode"] == expected, (case, row)
        rejects(lambda: editor.stage("familiarUpgrade:FrogHealthBonus", "set", 3))
        assert editor.review()["actionCount"] == 0
        if case == "missing":
            discovered = next(row for row in editor.query(
                domain="discover", search="FrogHealthBonus", language="en"
            )["items"] if row["id"] == "familiarUpgrade:FrogHealthBonus")
            assert discovered["reasonCode"] == expected
            assert "lacks its Familiar upgrade owner" in discovered["reason"]

    # A staged batch is a set of intents: rank acquisition and parent revocation
    # must report the same contradiction regardless of the click order.
    for actions in (
        (("familiarUpgrade:FrogHealthBonus", 3), ("familiar:FrogFamiliar", False)),
        (("familiar:FrogFamiliar", False), ("familiarUpgrade:FrogHealthBonus", 3)),
    ):
        root = copy.deepcopy(Hades2SaveDocument.load(path).lua_state)
        root["GameState"]["FamiliarsUnlocked"]["FrogFamiliar"] = True
        editor = inspection(root)
        editor.stage(actions[0][0], "set", actions[0][1])
        rejects(lambda: editor.stage(actions[1][0], "set", actions[1][1]))
        assert editor.review()["actionCount"] == 1

    # Saved Familiar linkage can make a tool available without a purchased tool.
    root = copy.deepcopy(Hades2SaveDocument.load(path).lua_state)
    root["GameState"]["WeaponsUnlocked"].pop("ToolPickaxe", None)
    root["GameState"]["WeaponsUnlocked"].pop("ToolPickaxe2", None)
    root["GameState"]["EquippedFamiliar"] = "RavenFamiliar"
    editor = inspection(root)
    tool_rows = {row["id"]: row for row in entity(editor, "tool:ToolPickaxe", "Crescent Pick")["items"]}
    assert tool_rows["tool:ToolPickaxe"]["value"] == 0
    assert tool_rows["toolSelection:ToolPickaxe"]["value"] is True
    root["GameState"].pop("EquippedFamiliar", None)
    assert next(row for row in editor.query(domain="weapons")["items"]
                if row["id"] == "toolSelection:ToolPickaxe")["value"] is False

    # The safe manual-card revocation path updates all observed native caches
    # through Stage -> review -> Apply -> reopen, including its linked reset.
    editor = Hades2SaveWorkspace.open(service)
    editor.stage("card:ChanneledCast:Unlocked", "set", False)
    editor.apply()
    saved = Hades2SaveDocument.load(path).lua_state["GameState"]
    assert saved["MetaUpgradeState"]["ChanneledCast"]["Level"] == 1
    assert saved["MetaUpgradeState"]["ChanneledCast"].get("Equipped") is None
    assert all(saved[cache] == 0 for cache in (
        "MetaUpgradeUnlockedCountCache", "MetaUpgradeMaxLevelCountCache", "MetaUpgradeCostCache",
    ))

print("Hades permanent progression entity journeys: PASS")
