"""Arcana equipment intents retain native grid, automatic cards and caches."""
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


def rejects(call):
    try:
        call()
    except ValueError:
        return
    raise AssertionError("conflicting Arcana intents were accepted")


with tempfile.TemporaryDirectory(prefix="mgt-arcana-equipment-") as temporary:
    base = Path(temporary)
    saves = base / "saves"
    saves.mkdir()
    game_state = table({
        "Resources": table({}), "Flags": table({}),
        "MetaUpgradeState": table({
            "ChanneledCast": table({"Level": 1}),
            "FutureCard": table({"Level": 19, "Unknown": "preserve"}),
        }),
        "FutureProgression": table({"owner": "unchanged"}),
    })
    document = Hades2SaveDocument(Hades2SaveHeader(
        game_version=0x12, save_flags=0, timestamp=1, location="Crossroads",
        completed_runs=1, accumulated_meta_points=0, active_shrine_points=0,
        meta_upgrade_level=0, cosmetics_points=0, easy_mode=0, hard_mode=0,
        notable_lua_data=("GameState", "CurrentRun"), map_name="Hub_Main", next_map_name="F_Opening01",
    ), [table({"GameState": game_state, "CurrentRun": table({"Sentinel": "unchanged"})})])
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
        provider_loader=lambda _target: Hades2SaveProvider(game_path=base / "no-game"))
    editor = Hades2SaveWorkspace.open(service)
    rows = {row["id"]: row for row in editor.query(domain="progression", language="en", limit=200)["items"]}
    assert rows["card:ChanneledCast:Equipped"]["editable"], "reliable native equipment Boolean is read-only"
    original = path.read_bytes()
    editor.stage("card:ChanneledCast:Equipped", "set", True)
    assert path.read_bytes() == original
    review = editor.review(language="en")
    assert "linked:card:ChanneledCast:Unlocked" in {row["id"] for row in review["changes"]}
    layout_effect = next((row for row in review["changes"]
                          if row["id"] == "linked:arcanaCache:MetaUpgradeCardLayout"), None)
    assert layout_effect is not None, "review hides the newly created native Arcana layout"
    assert layout_effect["before"] is None
    assert layout_effect["after"]["luaType"] == "table"
    assert len(layout_effect["after"]["entries"]) == 5
    assert layout_effect["name"] == "Arcana card layout"
    editor.apply()
    saved = Hades2SaveDocument.load(path).lua_state
    assert saved["GameState"]["MetaUpgradeState"]["ChanneledCast"]["Unlocked"] is True
    assert saved["GameState"]["MetaUpgradeState"]["ChanneledCast"]["Equipped"] is True
    assert saved["GameState"]["MetaUpgradeCostCache"] == 1
    assert saved["GameState"]["FutureProgression"]["owner"] == "unchanged"
    assert saved["GameState"]["MetaUpgradeState"]["FutureCard"]["Unknown"] == "preserve"
    assert saved["CurrentRun"]["Sentinel"] == "unchanged"

    # Enabling the native five-cost automatic card supplies the smallest
    # deterministic set of manual prerequisites and enough purchased Grasp.
    editor = Hades2SaveWorkspace.open(service)
    editor.stage("card:MaxHealthPerRoom:Equipped", "set", True)
    effects = {row["id"]: row for row in editor.review(language="en")["changes"]}
    for name in ("LowManaDamageBonus", "CastCount", "LastStand", "ManaOverTime"):
        assert effects["linked:card:" + name + ":Equipped"]["after"] is True
        assert effects["linked:card:" + name + ":Unlocked"]["after"] is True
    assert effects["linked:arcanaCache:MetaUpgradeLimitLevel"]["after"] == 3
    assert effects["linked:arcanaCache:MaxMetaUpgradeCostCache"]["after"] == 16
    editor.apply()
    saved = Hades2SaveDocument.load(path).lua_state["GameState"]
    assert saved["MetaUpgradeState"]["MaxHealthPerRoom"]["Equipped"] is True
    assert saved["MetaUpgradeCostCache"] == 15
    editor = Hades2SaveWorkspace.open(service)
    editor.stage("card:MaxHealthPerRoom:Equipped", "set", False)
    effects = {row["id"]: row for row in editor.review()["changes"]}
    assert effects["linked:card:ManaOverTime:Equipped"]["after"] is False
    editor.apply()
    saved = Hades2SaveDocument.load(path).lua_state["GameState"]
    assert saved["MetaUpgradeState"]["MaxHealthPerRoom"].get("Equipped") is None
    assert saved["MetaUpgradeState"]["ManaOverTime"]["Unlocked"] is True
    assert saved["MetaUpgradeLimitLevel"] == 3, "automatic teardown revoked purchased capacity"

    editor = Hades2SaveWorkspace.open(service)
    equipment = {row["id"]: row for row in editor.query(domain="weapons", language="en", limit=200)["items"]}
    assert equipment["weapon:WeaponStaffSwing"]["editable"], "starter ownership is arbitrarily read-only"
    assert equipment["familiarUpgrade:FrogHealthBonus"]["editable"], "missing native owner cannot be created"
    assert "aspectSelection:WeaponDagger" in equipment, "missing parent hides legal selection intent"
    editor.stage("aspectSelection:WeaponDagger", "setEnum", "DaggerBlockAspect")
    editor.stage("familiarSelected:FrogFamiliar", "set", True)
    editor.stage("tool:ToolPickaxe", "set", 2)
    editor.stage("weapon:WeaponStaffSwing", "set", True)
    effects = {row["id"] for row in editor.review()["changes"]}
    assert {"linked:weapon:WeaponDagger", "linked:aspect:DaggerBlockAspect",
            "linked:familiar:FrogFamiliar"}.issubset(effects)
    editor.apply()
    saved = Hades2SaveDocument.load(path).lua_state["GameState"]
    assert saved["LastWeaponUpgradeName"]["WeaponDagger"] == "DaggerBlockAspect"
    assert saved["WeaponsUnlocked"]["DaggerBlockAspect"] is True
    assert saved["EquippedFamiliar"] == "FrogFamiliar"
    assert saved["FamiliarsUnlocked"]["FrogFamiliar"] is True
    editor = Hades2SaveWorkspace.open(service)
    editor.stage("aspect:DaggerBackstabAspect", "set", 0)
    editor.stage("weapon:WeaponStaffSwing", "set", False)
    assert "linked:weapon:WeaponDagger" in {row["id"] for row in editor.review()["changes"]}
    editor.apply()
    saved = Hades2SaveDocument.load(path).lua_state["GameState"]
    assert saved["WeaponsUnlocked"].get("WeaponStaffSwing") is None
    assert saved["WeaponsUnlocked"].get("WeaponDagger") is None
    assert saved["LastWeaponUpgradeName"].get("WeaponDagger") is None
    assert saved["WorldUpgradesAdded"]["WeaponDagger"] is True

    def reset(cards, layout=None):
        fixture = copy.deepcopy(document)
        fixture.lua_state["GameState"]["MetaUpgradeState"] = table(cards)
        if layout is not None:
            fixture.lua_state["GameState"]["MetaUpgradeCardLayout"] = table({
                i: table(dict(enumerate(row, 1))) for i, row in enumerate(layout, 1)
            })
        path.write_bytes(fixture.to_bytes())
        return Hades2SaveWorkspace.open(service)

    # Worked current-build requirements fix every automatic rule and the
    # deterministic tie-break independently of table iteration order.
    for automatic, selected in (
        ("SorceryRegenUpgrade", {"MagicCrit"}),
        ("BonusRarity", {"ChanneledCast"}),
        ("CardDraw", {"ChanneledCast"}),
        ("TradeOff", {"DoorReroll", "StartingGold", "ScreenReroll"}),
        ("EpicRarityBoost", {"CastBuff", "BonusHealth", "BonusDodge", "ManaOverTime", "MagicCrit"}),
    ):
        editor = reset({})
        editor.stage("card:" + automatic + ":Equipped", "set", True)
        editor.apply()
        saved = Hades2SaveDocument.load(path).lua_state["GameState"]
        actual = {name for name, card in saved["MetaUpgradeState"].entries()
                  if card.get("Equipped") is True}
        assert actual == selected | {automatic}, (automatic, actual)

    # An automatic neighbor enables a full row on the second snapshot pass.
    editor = reset({
        **{name: table({"Unlocked": True, "Level": 1, "Equipped": True})
           for name in ("ChanneledCast", "HealthRegen", "LowManaDamageBonus")},
        "SorceryRegenUpgrade": table({"Unlocked": True, "Level": 1}),
        "EpicRarityBoost": table({"Unlocked": True, "Level": 1}),
    })
    editor.stage("card:CastCount:Equipped", "set", True)
    effects = {row["id"] for row in editor.review()["changes"]}
    assert {"linked:card:SorceryRegenUpgrade:Equipped", "linked:card:EpicRarityBoost:Equipped"}.issubset(effects)
    editor.apply()
    saved = Hades2SaveDocument.load(path).lua_state["GameState"]
    assert saved["MetaUpgradeState"]["EpicRarityBoost"]["Equipped"] is True

    # Moving the neighbor card changes which prerequisite is cheapest.
    layout = [
        ["ChanneledCast", "HealthRegen", "LowManaDamageBonus", "CastCount", "MaxHealthPerRoom"],
        ["CastBuff", "BonusHealth", "BonusDodge", "ManaOverTime", "MagicCrit"],
        ["SprintShield", "LastStand", "SorceryRegenUpgrade", "StatusVulnerability", "ChanneledBlock"],
        ["DoorReroll", "StartingGold", "MetaToRunUpgrade", "RarityBoost", "BonusRarity"],
        ["TradeOff", "ScreenReroll", "LowHealthBonus", "EpicRarityBoost", "CardDraw"],
    ]
    editor = reset({}, layout)
    editor.stage("card:SorceryRegenUpgrade:Equipped", "set", True)
    editor.apply()
    saved = Hades2SaveDocument.load(path).lua_state["GameState"]
    assert saved["MetaUpgradeState"]["BonusDodge"]["Equipped"] is True
    assert saved["MetaUpgradeCardLayout"][3][3] == "SorceryRegenUpgrade"

    editor = reset({name: table({"Unlocked": True, "Level": 1, "Equipped": True})
                    for name in ("ManaOverTime", "StatusVulnerability", "StartingGold", "RarityBoost")})
    for name in ("ManaOverTime", "StatusVulnerability", "StartingGold", "RarityBoost"):
        editor.stage("card:" + name + ":Equipped", "set", False)
    rejects(lambda: editor.stage("card:MaxHealthPerRoom:Equipped", "set", True))
    assert editor.review()["actionCount"] == 4, "conflict replaced explicit choices or lost the basket"

    # Desired ranks repair native tier gaps/mirrors instead of making a reliable
    # membership owner read-only. Existing historical and future data survive.
    fixture = copy.deepcopy(document)
    state = fixture.lua_state["GameState"]
    state["WeaponsUnlocked"] = table({"DaggerBlockAspect": True, "DaggerBlockAspect4": True,
                                      "ToolPickaxe2": True, "FutureWeapon": True})
    state["WorldUpgrades"] = table({"FrogHealthBonus2": True, "FutureUpgrade": True})
    state["WorldUpgradesAdded"] = table({"FutureUpgrade": True})
    state["LastWeaponUpgradeName"] = table({"WeaponDagger": "FutureAspect"})
    state["FamiliarsUnlocked"] = table({"FutureFamiliar": True})
    state["EquippedFamiliar"] = "FutureFamiliar"
    state["FamiliarUpgrades"] = table({"FrogHealthBonus3": True, "FutureFamiliarUpgrade": True})
    path.write_bytes(fixture.to_bytes())
    editor = Hades2SaveWorkspace.open(service)
    editor.stage("aspectSelection:WeaponDagger", "setEnum", "DaggerBlockAspect")
    editor.stage("tool:ToolPickaxe", "set", 1)
    editor.stage("familiarUpgrade:FrogHealthBonus", "set", 2)
    editor.stage("familiarSelected:FrogFamiliar", "set", True)
    editor.apply()
    state = Hades2SaveDocument.load(path).lua_state["GameState"]
    for key in ("DaggerBlockAspect", "DaggerBlockAspect2", "WeaponDagger", "ToolPickaxe"):
        assert state["WeaponsUnlocked"][key] is True
        assert state["WorldUpgrades"][key] is True
    assert state["WeaponsUnlocked"].get("DaggerBlockAspect4") is None
    assert state["WeaponsUnlocked"].get("ToolPickaxe2") is None
    assert state["WorldUpgradesAdded"]["DaggerBlockAspect4"] is True
    assert state["WorldUpgradesAdded"]["ToolPickaxe2"] is True
    assert state["WorldUpgradesAdded"]["FrogHealthBonus3"] is True
    assert state["FamiliarUpgrades"].get("FrogHealthBonus3") is None
    for key in ("FrogHealthBonus", "FrogHealthBonus2"):
        assert state["FamiliarUpgrades"][key] is True
        assert state["WorldUpgrades"][key] is True
        assert state["WorldUpgradesAdded"][key] is True
    assert state["WeaponsUnlocked"]["FutureWeapon"] is True
    assert state["FamiliarsUnlocked"]["FutureFamiliar"] is True
    assert state["FamiliarUpgrades"]["FutureFamiliarUpgrade"] is True

    editor = reset({"MagicCrit": table({"Unlocked": True, "Level": 1, "Equipped": True})})
    editor.stage("card:MagicCrit:Equipped", "set", False)
    editor.stage("card:SorceryRegenUpgrade:Equipped", "set", True)
    editor.apply()
    state = Hades2SaveDocument.load(path).lua_state["GameState"]
    assert state["MetaUpgradeState"]["MagicCrit"].get("Equipped") is None
    assert state["MetaUpgradeState"]["CastCount"]["Equipped"] is True

    # Equal selection counts prefer existing unlocks before spending additional
    # progression, even when the already unlocked alternative has a higher cost.
    editor = reset({"ManaOverTime": table({"Unlocked": True, "Level": 1})})
    editor.stage("card:SorceryRegenUpgrade:Equipped", "set", True)
    editor.apply()
    state = Hades2SaveDocument.load(path).lua_state["GameState"]
    assert state["MetaUpgradeState"]["ManaOverTime"]["Equipped"] is True
    assert "MagicCrit" not in state["MetaUpgradeState"]

    # A purchased level has no native grid dependency when its card is already
    # unlocked. Do not make an unrelated unreadable layout block that edit.
    fixture = copy.deepcopy(document)
    state = fixture.lua_state["GameState"]
    state["MetaUpgradeState"]["ChanneledCast"]["Unlocked"] = True
    state["MetaUpgradeCardLayout"] = True
    path.write_bytes(fixture.to_bytes())
    editor = Hades2SaveWorkspace.open(service)
    editor.stage("card:ChanneledCast:Level", "set", 3)
    editor.stage("card:FutureCard:Level", "set", 20)
    editor.apply()
    state = Hades2SaveDocument.load(path).lua_state["GameState"]
    assert state["MetaUpgradeCardLayout"] is True
    assert state["MetaUpgradeState"]["FutureCard"]["Level"] == 20
    assert state["MetaUpgradeState"]["FutureCard"]["Unknown"] == "preserve"

    fixture = copy.deepcopy(document)
    fixture.lua_state["GameState"]["MetaUpgradeState"]["ChanneledCast"]["AdjacencyBonuses"] = table({
        "CustomMultiplier": 2, "UnknownBonus": "preserve"})
    path.write_bytes(fixture.to_bytes())
    editor = Hades2SaveWorkspace.open(service)
    editor.stage("card:ChanneledCast:Equipped", "set", True)
    adjacency = next(row for row in editor.review(language="en")["changes"]
                     if row["id"] == "linked:arcanaCache:AdjacencyBonuses:ChanneledCast")
    assert adjacency["before"] == 2 and adjacency["after"] is None
    assert "Adjacency multiplier" in adjacency["name"]
    editor.apply()
    bonuses = Hades2SaveDocument.load(path).lua_state["GameState"]["MetaUpgradeState"]["ChanneledCast"]["AdjacencyBonuses"]
    assert bonuses.get("CustomMultiplier") is None and bonuses["UnknownBonus"] == "preserve"

    fixture = copy.deepcopy(document)
    fixture.lua_state["GameState"].pop("MetaUpgradeState", None)
    path.write_bytes(fixture.to_bytes())
    editor = Hades2SaveWorkspace.open(service)
    missing = editor.query(domain="entities", scope="growth", search="BonusHealth", language="en")
    assert any(group["id"] == "arcana:BonusHealth" for group in missing["entities"])
    editor.stage("card:BonusHealth:Level", "set", 2)
    editor.apply()
    state = Hades2SaveDocument.load(path).lua_state["GameState"]
    assert state["MetaUpgradeState"]["BonusHealth"]["Level"] == 2
    assert state["MetaUpgradeState"]["BonusHealth"]["Unlocked"] is True

    fixture = copy.deepcopy(document)
    fixture.lua_state["GameState"]["MetaUpgradeState"]["ChanneledCast"]["Level"] = table({"bad": "shape"})
    fixture.lua_state["GameState"]["MetaUpgradeUnlockedCountCache"] = table({"invalid": "projection"})
    path.write_bytes(fixture.to_bytes())
    editor = Hades2SaveWorkspace.open(service)
    known = next(row for row in editor.query(domain="progression", limit=200)["items"]
                 if row["id"] == "card:ChanneledCast:Level")
    assert known["editable"] and known["value"] is None
    editor.stage("card:ChanneledCast:Level", "set", 2)
    effect = next(row for row in editor.review()["changes"]
                  if row["id"] == "linked:arcanaCache:MetaUpgradeUnlockedCountCache")
    assert effect["before"]["luaType"] == "table" and effect["beforeDisplay"]
    editor.apply()
    assert Hades2SaveDocument.load(path).lua_state["GameState"]["MetaUpgradeState"]["ChanneledCast"]["Level"] == 2

    fixture = copy.deepcopy(document)
    state = fixture.lua_state["GameState"]
    state["MetaUpgradeState"]["FutureCard"] = table({"Level": "opaque-v1", "Unlocked": 2.5,
                                                       "Unknown": "preserve"})
    path.write_bytes(fixture.to_bytes())
    editor = Hades2SaveWorkspace.open(service)
    unknown = {row["id"]: row for row in editor.query(domain="progression", language="en", limit=200)["items"]}
    assert "card:FutureCard:Equipped" not in unknown, "unknown metadata invented an absent field"
    assert unknown["card:FutureCard:Level"]["valueType"] == "string"
    assert unknown["card:FutureCard:Unlocked"]["valueType"] == "number"
    assert unknown["card:FutureCard:Level"]["warning"], "unknown impact warning missing"
    editor.stage("card:FutureCard:Level", "set", "opaque-v2")
    editor.stage("card:FutureCard:Unlocked", "set", -1.25)
    editor.apply()
    state = Hades2SaveDocument.load(path).lua_state["GameState"]
    assert state["MetaUpgradeState"]["FutureCard"]["Level"] == "opaque-v2"
    assert state["MetaUpgradeState"]["FutureCard"]["Unlocked"] == -1.25
    assert state["MetaUpgradeState"]["FutureCard"].get("Equipped") is None
    assert state.get("MetaUpgradeCostCache") is None, "unknown metadata invented derived state"

    # Familiar purchases use Lua truth, unlike weapon upgrade key counting.
    # A stored false membership must not hide an explicit first-rank purchase.
    for membership, before, desired in ((False, 0, 1), (0, 1, 2), ("", 1, 2)):
        fixture = copy.deepcopy(document)
        fixture.lua_state["GameState"]["FamiliarsUnlocked"] = table({"FrogFamiliar": True})
        fixture.lua_state["GameState"]["FamiliarUpgrades"] = table({
            "FrogHealthBonus": membership, "FutureFamiliarUpgrade": "preserve"})
        path.write_bytes(fixture.to_bytes())
        editor = Hades2SaveWorkspace.open(service)
        row = next(row for row in editor.query(domain="weapons", limit=200)["items"]
                   if row["id"] == "familiarUpgrade:FrogHealthBonus")
        assert row["value"] == before, (membership, row["value"])
        assert editor.stage(row["id"], "set", desired)["actionCount"] == 1
        editor.apply()
        saved = Hades2SaveDocument.load(path).lua_state
        assert saved["GameState"]["FamiliarUpgrades"]["FrogHealthBonus"] is True
        assert saved["GameState"]["FamiliarUpgrades"]["FutureFamiliarUpgrade"] == "preserve"
        assert saved["CurrentRun"]["Sentinel"] == "unchanged"
        reopened = Hades2SaveWorkspace.open(service)
        row = next(row for row in reopened.query(domain="weapons", limit=200)["items"]
                   if row["id"] == "familiarUpgrade:FrogHealthBonus")
        assert row["value"] == desired

print("Arcana native equipment Save journey: PASS")
