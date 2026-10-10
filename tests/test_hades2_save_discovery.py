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
    state = table({
        "Resources": table({"MetaCurrency": 123.0}),
        "Flags": table({"HasPinnedAnyBoon": True}),
        "TextLinesRecord": table({}),
        "TextLinesChoiceRecord": table({}),
        "GiftTextLinesOrderRecord": table({}),
        "QuestStatus": table({}),
        "UnknownFutureField": table({
            "MysteryCounter": 7.0,
            "Nested": table({"OpaqueThing": "kept"}),
        }),
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

    # Unknown data is searchable without granting write authority and keeps the
    # exact Advanced path needed to inspect it.
    unknown = workspace.query(domain="discover", search="MysteryCounter", language="en")
    mystery = next(item for item in unknown["items"] if item["rawId"] == "MysteryCounter")
    assert mystery["domain"] == "advanced"
    assert mystery["state"] == "unknown"
    assert mystery["editable"] is False
    assert mystery["reasonCode"] == "unknownRaw"
    assert mystery["path"] == ["GameState", "UnknownFutureField", "MysteryCounter"]

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
