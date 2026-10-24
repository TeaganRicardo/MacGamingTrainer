"""Save-only JSONL bootstrap for the native player-journey fixture.

All Save dispatch, workspaces, codec and transactions are production owners.
The fixture replaces only runtime startup and the physical roots/probe, so it
cannot construct a game transport or inspect a real process/save installation.
"""
import argparse
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

from core.adapter import GameAdapter, GameAdapterContext
from core.module_manifest import SaveManagementSpec, SaveRootSpec
from core.protocol import JsonlRequestRouter
from games.hades2.adapter import Hades2Adapter
from games.hades2.command_contract import Hades2CommandContract
from games.hades2.save_document import Hades2SaveDocument, Hades2SaveHeader, LuaTable
from games.hades2.save_provider import Hades2SaveProvider


def table(values):
    return LuaTable(0, len(values), list(values.items()))


def document(amount, marker):
    state = table({
        "Resources": table({"MetaCurrency": float(amount), "GiftPoints": 2.0}),
        "GameplayTime": 100.0, "TotalTime": 200.0, "TotalRequiredEnemyKills": 3.0,
        "NPCInteractions": table({"NPC_Hecate_01": 1.0}),
        "SpecialInteractRecord": table({}), "GiftRecord": table({}),
        "GiftResourceRecord": table({}), "QuestStatus": table({"QuestHelpDora": "Unlocked"}),
        "ObjectivesCompleted": table({}), "CompletedObjectiveSets": table({}),
        "MetaUpgradeState": table({
            "ChanneledCast": table({"Unlocked": True, "Equipped": True, "Level": 2.0}),
        }),
        "WeaponsUnlocked": table({}), "WorldUpgrades": table({}),
        "WorldUpgradesAdded": table({}), "LastWeaponUpgradeName": table({}),
        "FamiliarsUnlocked": table({"HoundFamiliar": True}),
        "EquippedFamiliar": "HoundFamiliar",
        "UnknownFutureField": table({"Marker": marker}),
        "AdvancedFixture": table({
            "Number": 4.5, "Boolean": True, "Text": "initial", "Empty": "initial", "Removed": 99.0,
            "Binary": "\udcff\x00", "Nil": None,
            "Members": LuaTable(0, 4, [(True, "boolean key"), (1.0, "numeric key"), ("1", "string key"), ("\udcff", "binary key")]),
        }),
    })
    if os.environ.get("MGT_SAVE_JOURNEY_RECORDS") == "1":
        state["RunHistory"] = table({1.0: table({
            "RunResult": 2.0, "EndingRoomName": "F_Boss01", "ActiveBounty": "Initial bounty",
            "GameplayTime": 12.5, "ShrinePointsCache": 4.0, "TraitCache": table({}),
        })})
        state["FishingSuccesses"] = 9.0
        state["QuestStatus"] = table({"QuestHelpDora": "Unlocked", "QuestUnlockMoros": "Complete"})
        state["QuestsViewed"] = table({"QuestHelpDora": False})
        state["QuestsCompleted"] = table({"QuestHelpDora": False})
        state["TextLinesRecord"] = table({"UnverifiedScene": False})
        state["TextLinesChoiceRecord"] = table({"UnverifiedScene": " Choice A "})
        state["SpeechRecord"] = table({"/VO/Unknown_0001": 3.0, "/VO/Legacy_0001": True})
        state["GiftRecord"] = table({"Hecate": table({1.0: "GiftPoints", "GiftPoints": 7.0}),
                                     "Odysseus": table({"GiftPoints": 3.0})})
        state["GiftResourceRecord"] = table({"GiftPoints": 11.0})
        state["GiftTextLinesOrderRecord"] = table({"Hecate": table({1.0: "OriginalGiftLine"})})
        state["LifetimeResourcesGained"] = table({"GiftPoints": 100.0})
        state["NPCInteractions"]["FutureNPC"] = " exact observed value "
    header = Hades2SaveHeader(
        game_version=0x12, save_flags=0, timestamp=100, location="Crossroads",
        completed_runs=1, accumulated_meta_points=0, active_shrine_points=0,
        meta_upgrade_level=0, cosmetics_points=0, easy_mode=0, hard_mode=0,
        notable_lua_data=("GameState", "CurrentRun"),
        map_name="Hub_Main", next_map_name="F_Opening01",
    )
    current = table({"RunResult": 2.0, "GameplayTime": 999.0})
    if os.environ.get("MGT_SAVE_JOURNEY_RECORDS") == "1":
        current["ResourcesGained"] = table({"GiftPoints": 4.0})
        current["GiftRecord"] = table({"Hecate": table({"GiftPoints": 1.0})})
        current["GiftResourceRecord"] = table({"GiftPoints": 1.0})
    values = [table({"GameState": state, "CurrentRun": current})]
    if os.environ.get("MGT_SAVE_CONTAINER_FIXTURE") == "1":
        header.timestamp = 18446744073709551615
        values.extend([12.5, table({"Child": "original"}), None,
            LuaTable(0, 2, [(float("inf"), table({"Nested": "original"})), ("UniqueSibling", "original")])])
    return Hades2SaveDocument(header, values).to_bytes()


class SaveOnlyAdapter(Hades2Adapter):
    def __init__(self, context):
        # Deliberately skip Hades runtime/debugger initialization. Inherited
        # Save methods still use the real command/workspace/service owners.
        GameAdapter.__init__(self, context)
        self.command_contract = Hades2CommandContract(self)
        self.save_workspaces = {}

    def dispatch(self, command, params, request_id):
        if not command.startswith("save_editor_"):
            raise AssertionError("native Save fixture attempted a non-Save command")
        return self.command_contract.dispatch(command, params, request_id)

    def metadata(self):
        return GameAdapter.metadata(self)

    def reply_replayed(self):
        pass

    def close(self):
        self.save_workspaces.clear()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", required=True)
    args = parser.parse_args()
    base = Path(os.environ["MGT_SAVE_JOURNEY_FIXTURE"]).resolve()
    if not (base / ".fixture-owned").is_file():
        raise RuntimeError("native Save fixture requires its disposable root marker")
    saves = base / "saves"
    saves.mkdir()
    original = document(10, "fixed-source")
    target = document(900, "initial-target")
    (saves / "Profile1.sav").write_bytes(original)
    (saves / "Profile2.sav").write_bytes(target)
    (base / "source-original.sav").write_bytes(original)
    (base / "target-newer.sav").write_bytes(document(999, "external-newer-target"))
    profile = b"Profile1"
    (saves / "activeProfile").write_bytes(b"SGB1" + struct.pack("<I", len(profile)) + profile)
    (base / "initial.json").write_text(json.dumps({
        "sourceSHA256": hashlib.sha256(original).hexdigest(),
        "targetSHA256": hashlib.sha256(target).hexdigest(),
    }))
    # Authored localization fixtures exercise the production installed-text
    # reader. They are not evidence of text in a user's installed game build.
    text_root = base / "native-game/Contents/Resources/Content/Game/Text"
    text_root.mkdir(parents=True)
    for language, names in {
        "en": {"MetaCurrency": "Ashes", "GiftPoints": "Nectar",
               "ChanneledCast": "Sorceress", "NPC_Hecate_01": "Hecate",
               "HoundFamiliar": "Hecuba"},
        "zh-CN": {"MetaCurrency": "灰烬", "GiftPoints": "花蜜",
                  "ChanneledCast": "女巫", "NPC_Hecate_01": "赫卡忒",
                  "HoundFamiliar": "赫卡柏"},
    }.items():
        (text_root / f"Journey.{language}.sjson").write_text("\n".join(
            "{ Id = " + json.dumps(identifier) + " DisplayName = "
            + json.dumps(name, ensure_ascii=False) + " }"
            for identifier, name in names.items()
        ))
    if os.environ.get("MGT_SAVE_JOURNEY_RECORDS") == "1":
        scripts = base / "native-game/Contents/Resources/Content/Scripts"
        scripts.mkdir(parents=True)
        (scripts / "NPCData_Hecate.lua").write_text('''UnitSetData = {
 NPC_Hecate_01 = {
  InteractTextLineSets = {
   UnverifiedScene = {
    { Cue = "/VO/Unknown_0001", Text = "Integer speech fixture" },
   },
   HecateJourney01 = {
  { Cue = "/VO/Unknown_0001", Text = "Integer speech fixture" },
  { Cue = "/VO/Legacy_0001", Text = "Boolean speech fixture" },
   }
  }
 }
}''')
        reset = b'StoryResetData = { TextLines = { "HecateJourney01" } }'
        (scripts / "StoryResetData.lua").write_bytes(reset)
        (scripts / "QuestData.lua").write_text('''QuestData = {
 QuestUnlockMoros = { RewardResourceName = "GiftPoints", RewardResourceAmount = 3 },
}''')
        (scripts / "ResourceData.lua").write_text('''ResourceData = {
 GiftPoints = { OnAddedFunctionName = "OnGiftPointsAdded" },
}''')
        (scripts / "ResourceLogic.lua").write_text("-- authored reward mutation owner fixture\n")
        (scripts / "QuestLogLogic.lua").write_text("-- authored claim mutation owner fixture\n")
        # The authored text corpus has its own exact fixture digest. Keep the
        # production source scanner/parser; this proves contextual controls,
        # not compatibility with an installed supported game's source set.
        from games.hades2 import save_workspace
        investigation_type = save_workspace.NativeDialogueInvestigation
        checksum = hashlib.sha256(reset).hexdigest()
        def fixture_investigation(path):
            finding = investigation_type(path, expected_hash=checksum)
            finding.reward_owner_hashes = {name: hashlib.sha256((scripts / name).read_bytes()).hexdigest()
                for name in ("ResourceLogic.lua", "QuestLogLogic.lua", "ResourceData.lua")}
            return finding
        save_workspace.NativeDialogueInvestigation = fixture_investigation
        for language in ("en", "zh-CN"):
            directory = text_root / language
            directory.mkdir()
            (directory / f"Journey.{language}.sjson").write_text('''{ Texts = [
 { Id = "Unknown_0001" DisplayName = "Integer speech fixture" Event = "HecateJourney01" }
 { Id = "Legacy_0001" DisplayName = "Boolean speech fixture" Event = "HecateJourney01" }
] }''')
    module = Path(sys.modules[Hades2Adapter.__module__].__file__).parent
    protocol = json.loads((module / "module.json").read_text())["protocolVersion"]
    spec = SaveManagementSpec(
        roots=(SaveRootSpec("main", str(saves), ("Profile*.sav", "activeProfile")),),
        provider="games.hades2.save_provider:Hades2SaveProvider",
        hot_backup=True, restore_policy="hotPreferred", staged_restore=True,
    )
    adapter = SaveOnlyAdapter(GameAdapterContext(
        game_id=args.game, display_name="Hades II", module_protocol_version=protocol,
        module_dir=module, public_metadata={"protocolVersion": protocol},
        save_management=spec,
    ))
    router = JsonlRequestRouter(adapter, save_data_root=base / "data",
                                target_running_probe=lambda: False)
    # Source lookups remain contained in this temporary game tree. An authored
    # corpus may explain context; it cannot inspect an installed game tree.
    router.save_service.provider = Hades2SaveProvider(game_path=base / "native-game")
    for raw in sys.stdin:
        request = json.loads(raw)
        with (base / "commands.jsonl").open("a") as log:
            log.write(json.dumps(request) + "\n")
        print(router.handle_encoded(request), flush=True)
    adapter.close()


if __name__ == "__main__":
    main()
