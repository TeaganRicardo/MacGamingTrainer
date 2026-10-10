import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.save_document import Hades2SaveDocument, Hades2SaveHeader, LuaTable
from games.hades2.save_workspace import Hades2SaveWorkspace


def table(values):
    return LuaTable(0, len(values), list(values.items()))


def document():
    unknown = {
        "MysteryCounter": 7.0,
        "Nested": table({"OpaqueThing": "kept"}),
        "DuplicateOwner": LuaTable(0, 2, [
            ("SameKey", 1.0),
            ("SameKey", 2.0),
        ]),
        "DuplicateContainers": LuaTable(0, 2, [
            ("Twin", table({"DeepNeedle": 1.0})),
            ("Twin", table({"DeepNeedle": 2.0})),
        ]),
    }
    unknown.update({
        "BulkItem{:03d}".format(index): float(index)
        for index in range(240)
    })
    state = table({
        "Resources": table({"MetaCurrency": 123.0}),
        "Flags": table({"HasPinnedAnyBoon": True}),
        "TextLinesRecord": table({}),
        "TextLinesChoiceRecord": table({}),
        "GiftTextLinesOrderRecord": table({}),
        "QuestStatus": table({"QuestHelpDora": "CashedOut"}),
        "WeaponsUnlocked": table({"WeaponStaffSwing": True}),
        "WorldUpgrades": table({}),
        "WorldUpgradesAdded": table({}),
        "LastWeaponUpgradeName": table({}),
        "UnknownFutureField": table(unknown),
    })
    root = table({"GameState": state, "CurrentRun": table({})})
    header = Hades2SaveHeader(
        game_version=0x12,
        save_flags=0,
        timestamp=100,
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
    return Hades2SaveDocument(header, [root])


class Session:
    relative_path = "Profile1.sav"

    def __init__(self):
        self.document = document()


with tempfile.TemporaryDirectory(prefix="mgt-save-discovery-") as td:
    game = Path(td) / "Hades II.app"
    text = game / "Contents/Resources/Content/Game/Text"
    (text / "en").mkdir(parents=True)
    (text / "zh-CN").mkdir(parents=True)
    (text / "en" / "Resources.en.sjson").write_text(
        'Texts = { { Id = "MetaCurrency", DisplayName = "Ashes", }, '
        '{ Id = "QuestHelpOdysseus", DisplayName = "The Wanderer\'s Task", }, }',
        encoding="utf-8",
    )
    (text / "zh-CN" / "Resources.zh-CN.sjson").write_text(
        'Texts = { { Id = "MetaCurrency", DisplayName = "灰烬", }, '
        '{ Id = "QuestHelpOdysseus", DisplayName = "流浪者的使命", }, }',
        encoding="utf-8",
    )

    workspace = Hades2SaveWorkspace(Session(), "Profile1", game_path=game)

    # Discovery is one cross-domain public seam. The player does not have to
    # know that MetaCurrency belongs to Resources before searching for it.
    english = workspace.query(domain="discover", search="Ashes", language="en")
    assert english["domain"] == "discover"
    resource = next(item for item in english["items"] if item["id"] == "resource:MetaCurrency")
    assert resource["state"] == "observed"
    assert resource["editable"] is True
    assert resource["reasonCode"] == "editable"

    # Both official languages remain searchable regardless of active UI language.
    chinese_alias = workspace.query(domain="discover", search="灰烬", language="en")
    assert any(item["id"] == "resource:MetaCurrency" for item in chinese_alias["items"])

    # A known semantic identity stays recognizable when its physical owner is
    # ambiguous or malformed. The failed identity becomes read-only without
    # hiding unrelated valid entries from the same semantic domain.
    ambiguous_session = Session()
    ambiguous_state = ambiguous_session.document.lua_state["GameState"]
    ambiguous_state["Resources"] = LuaTable(0, 3, [
        ("MetaCurrency", 123.0),
        ("MetaCurrency", 456.0),
        ("GiftPoints", 2.0),
    ])
    ambiguous_workspace = Hades2SaveWorkspace(
        ambiguous_session, "Profile1", game_path=game
    )
    ambiguous_known = ambiguous_workspace.query(
        domain="discover", search="Ashes", language="en"
    )
    ambiguous_resource = next(
        item for item in ambiguous_known["items"]
        if item["id"] == "resource:MetaCurrency"
    )
    assert ambiguous_resource["state"] == "ambiguous"
    assert ambiguous_resource["editable"] is False
    assert ambiguous_resource["reasonCode"] == "ambiguousOwner"
    assert any(
        item["id"] == "resource:MetaCurrency"
        for item in ambiguous_workspace.query(
            domain="discover", search="灰烬", language="en"
        )["items"]
    )
    safe_sibling = ambiguous_workspace.query(
        domain="discover", search="GiftPoints", language="en"
    )
    sibling = next(
        item for item in safe_sibling["items"]
        if item["id"] == "resource:GiftPoints"
    )
    assert sibling["domain"] == "resources"
    assert sibling["editable"] is True

    malformed_session = Session()
    malformed_state = malformed_session.document.lua_state["GameState"]
    malformed_state["Resources"] = table({
        "MetaCurrency": "corrupt",
        "GiftPoints": 2.0,
    })
    malformed_workspace = Hades2SaveWorkspace(
        malformed_session, "Profile1", game_path=game
    )
    malformed_known = malformed_workspace.query(
        domain="discover", search="Ashes", language="en"
    )
    malformed_resource = next(
        item for item in malformed_known["items"]
        if item["id"] == "resource:MetaCurrency"
    )
    assert malformed_resource["state"] == "unsupported"
    assert malformed_resource["editable"] is False
    assert malformed_resource["reasonCode"] == "unsupportedOwner"
    unsupported_only = malformed_workspace.query(
        domain="discover",
        search="Ashes",
        language="en",
        stateFilter="unsupported",
    )
    assert [item["id"] for item in unsupported_only["items"]] == [
        "resource:MetaCurrency"
    ]

    flag_session = Session()
    flag_state = flag_session.document.lua_state["GameState"]
    flag_state["Flags"] = LuaTable(0, 3, [
        ("HasPinnedAnyBoon", True),
        ("HasPinnedAnyBoon", False),
        ("HasShuffledMusicPlayer", True),
    ])
    flag_workspace = Hades2SaveWorkspace(
        flag_session, "Profile1", game_path=game
    )
    bad_flag = next(
        item for item in flag_workspace.query(
            domain="discover", search="Has pinned a boon", language="en"
        )["items"]
        if item["id"] == "flag:HasPinnedAnyBoon"
    )
    assert bad_flag["state"] == "ambiguous"
    assert bad_flag["editable"] is False
    good_flag = next(
        item for item in flag_workspace.query(
            domain="discover",
            search="Has shuffled the music player",
            language="en",
        )["items"]
        if item["id"] == "flag:HasShuffledMusicPlayer"
    )
    assert good_flag["state"] == "observed"
    assert good_flag["editable"] is True

    relationship_session = Session()
    relationship_state = relationship_session.document.lua_state["GameState"]
    relationship_state["NPCInteractions"] = table({
        "NPC_Nemesis_01": "bad",
        "NPC_Hecate_01": 2.0,
    })
    relationship_workspace = Hades2SaveWorkspace(
        relationship_session, "Profile1", game_path=game
    )
    bad_relationship = next(
        item for item in relationship_workspace.query(
            domain="discover", search="NPC_Nemesis_01", language="en"
        )["items"]
        if item["id"] == "interaction:NPC_Nemesis_01"
    )
    assert bad_relationship["state"] == "unsupported"
    assert bad_relationship["editable"] is False
    good_relationship = next(
        item for item in relationship_workspace.query(
            domain="discover", search="NPC_Hecate_01", language="en"
        )["items"]
        if item["id"] == "interaction:NPC_Hecate_01"
    )
    assert good_relationship["state"] == "observed"
    assert good_relationship["editable"] is True

    arcana_session = Session()
    arcana_state = arcana_session.document.lua_state["GameState"]
    arcana_state["MetaUpgradeState"] = LuaTable(0, 3, [
        ("ChanneledCast", table({"Unlocked": True, "Level": 1.0})),
        ("ChanneledCast", table({"Unlocked": False, "Level": 2.0})),
        ("HealthRegen", table({"Unlocked": True, "Level": 1.0})),
    ])
    arcana_workspace = Hades2SaveWorkspace(
        arcana_session, "Profile1", game_path=game
    )
    bad_arcana = next(
        item for item in arcana_workspace.query(
            domain="discover", search="ChanneledCast", language="en"
        )["items"]
        if item["id"] == "card:ChanneledCast:Level"
    )
    assert bad_arcana["state"] == "ambiguous"
    assert bad_arcana["editable"] is False
    good_arcana = next(
        item for item in arcana_workspace.query(
            domain="discover", search="HealthRegen", language="en"
        )["items"]
        if item["id"] == "card:HealthRegen:Level"
    )
    assert good_arcana["state"] == "observed"
    assert good_arcana["editable"] is True

    weapon_session = Session()
    weapon_state = weapon_session.document.lua_state["GameState"]
    weapon_state["WeaponsUnlocked"] = LuaTable(0, 3, [
        ("WeaponStaffSwing", True),
        ("WeaponDagger", True),
        ("WeaponDagger", False),
    ])
    weapon_workspace = Hades2SaveWorkspace(
        weapon_session, "Profile1", game_path=game
    )
    bad_weapon = next(
        item for item in weapon_workspace.query(
            domain="discover", search="WeaponDagger", language="en"
        )["items"]
        if item["id"] == "weapon:WeaponDagger"
    )
    assert bad_weapon["state"] == "ambiguous"
    assert bad_weapon["editable"] is False
    good_weapon = next(
        item for item in weapon_workspace.query(
            domain="discover", search="WeaponTorch", language="en"
        )["items"]
        if item["id"] == "weapon:WeaponTorch"
    )
    assert good_weapon["state"] == "absent"
    assert good_weapon["editable"] is True

    # A source-owned identity can be discoverable even when no value is present.
    absent = workspace.query(
        domain="discover",
        search="HasUsedWeaponShopNavigation",
        language="en",
    )
    flag = next(item for item in absent["items"] if item["id"] == "flag:HasUsedWeaponShopNavigation")
    assert flag["state"] == "absent"
    assert flag["editable"] is True
    assert flag["reasonCode"] == "editableAbsent"

    claimed = workspace.query(
        domain="discover",
        search="QuestHelpDora",
        language="en",
    )
    claimed_quest = next(item for item in claimed["items"] if item["id"] == "quest:QuestHelpDora")
    assert claimed_quest["state"] == "observed"
    assert claimed_quest["editable"] is False
    assert claimed_quest["reasonCode"] == "rewardClaimed"

    starter = workspace.query(
        domain="discover",
        search="WeaponStaffSwing",
        language="en",
    )
    starter_weapon = next(item for item in starter["items"] if item["id"] == "weapon:WeaponStaffSwing")
    assert starter_weapon["editable"] is False
    assert starter_weapon["reasonCode"] == "starterWeapon"

    # Compound semantic owners must report the semantic state, not merely the
    # presence of the row's display path. The default Staff aspect is owned by
    # its base weapon even when no separate BaseStaffAspect key exists.
    compound = workspace.query(
        domain="discover",
        search="BaseStaffAspect",
        language="en",
    )
    base_aspect = next(item for item in compound["items"] if item["id"] == "aspect:BaseStaffAspect")
    assert base_aspect["value"] == 1
    assert base_aspect["state"] == "observed"

    absent_only = workspace.query(
        domain="discover",
        search="HasUsedWeaponShopNavigation",
        language="en",
        stateFilter="absent",
    )
    assert absent_only["items"]
    assert all(item["state"] == "absent" for item in absent_only["items"])
    assert workspace.query(
        domain="discover",
        search="HasUsedWeaponShopNavigation",
        language="en",
        stateFilter="observed",
    )["total"] == 0

    concept = workspace.query(
        domain="discover",
        search="Weapon aspects",
        language="en",
    )
    assert any(item["id"] == "aspect:BaseStaffAspect" for item in concept["items"])

    ambiguous = workspace.query(
        domain="discover",
        search="SameKey",
        language="en",
    )
    duplicate = next(item for item in ambiguous["items"] if item["rawId"] == "SameKey")
    assert duplicate["state"] == "ambiguous"
    assert duplicate["editable"] is False
    assert duplicate["reasonCode"] == "ambiguousRaw"
    assert duplicate["pathAmbiguous"] is True

    # Ambiguity on a parent container must propagate to descendants reached by
    # raw discovery. Those descendants need distinct physical identities and
    # must never advertise an exact Advanced path that cannot be resolved.
    deep = workspace.query(
        domain="discover",
        search="DeepNeedle",
        language="en",
    )["items"]
    assert len(deep) == 2
    assert len({item["id"] for item in deep}) == 2
    assert all(item["state"] == "ambiguous" for item in deep)
    assert all(item["reasonCode"] == "ambiguousRaw" for item in deep)
    assert all(item["pathAmbiguous"] is True for item in deep)

    # Unknown data is searchable without granting write authority and keeps the
    # exact Advanced path needed to inspect it.
    unknown = workspace.query(domain="discover", search="MysteryCounter", language="en")
    mystery = next(item for item in unknown["items"] if item["rawId"] == "MysteryCounter")
    assert mystery["domain"] == "advanced"
    assert mystery["state"] == "unknown"
    assert mystery["editable"] is False
    assert mystery["reasonCode"] == "unknownRaw"
    assert mystery["path"] == ["GameState", "UnknownFutureField", "MysteryCounter"]

    # Global discovery still pages large unknown result sets at the Workspace
    # boundary instead of requiring the frontend to receive the raw tree.
    bulk = workspace.query(
        domain="discover",
        search="BulkItem",
        offset=100,
        limit=50,
        language="en",
    )
    assert bulk["total"] == 240
    assert len(bulk["items"]) == 50
    assert bulk["items"][0]["rawId"] == "BulkItem100"
    assert all(item["domain"] == "advanced" for item in bulk["items"])

    # Empty discovery is useful but does not dump every absent/unknown identity.
    default = workspace.query(domain="discover", search="", language="en")
    assert all(item["state"] == "observed" for item in default["items"])
    assert not any(item["rawId"] == "HasUsedWeaponShopNavigation" for item in default["items"])
    assert not any(item["rawId"] == "MysteryCounter" for item in default["items"])

    # Native catalogs can identify absent content without inventing write
    # authority. The same entry remains searchable by either official language.
    missing_quest = workspace.query(
        domain="discover",
        search="流浪者的使命",
        language="en",
    )
    quest = next(item for item in missing_quest["items"] if item["id"] == "quest:QuestHelpOdysseus")
    assert quest["state"] == "absent"
    assert quest["editable"] is False
    assert quest["reasonCode"] == "knownAbsent"

    coverage = {item["id"]: item for item in workspace.summary()["coverage"]}
    assert set(coverage) == {
        "resources", "playerHistory", "narrative", "relationships",
        "progression", "equipment", "unknown",
    }
    assert coverage["resources"] == {
        "id": "resources",
        "discoverability": "supported",
        "understanding": "supported",
        "write": "supported",
        "reasonCode": "verifiedDescriptors",
    }
    assert coverage["playerHistory"]["discoverability"] == "partial"
    assert coverage["playerHistory"]["write"] == "partial"
    assert coverage["unknown"]["discoverability"] == "supported"
    assert coverage["unknown"]["understanding"] == "readOnly"
    assert coverage["unknown"]["write"] == "readOnly"

print("hades2_save_discovery_ok")
