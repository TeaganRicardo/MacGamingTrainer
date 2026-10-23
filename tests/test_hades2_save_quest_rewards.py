"""Explicit offline rewards survive the complete temporary Save transaction."""
import hashlib
import unittest
from unittest.mock import patch
from test_hades2_save_relationship_transactions import SaveTransactionFixture, table
from games.hades2.save_document import Hades2SaveDocument
from games.hades2.save_investigation import NativeDialogueInvestigation
from games.hades2.save_native_ids import QUEST_IDS


class QuestRewardTests(SaveTransactionFixture):
    # Reuse only the real Core/codec fixture, not its unrelated test methods.
    def setUp(self):
        super().setUp()
        self.scripts = self.base / "sources/Scripts"
        self.scripts.mkdir(parents=True)
        (self.base / "sources/Text").mkdir()
        self.quest_source = '''QuestData = {
          RewardParent = { RewardResourceName = "GiftPoints", RewardResourceAmount = 3 },
          QuestHelpDora = { InheritFrom = { "RewardParent" } },
          QuestUnlockMoros = { RewardResourceName = "GiftPoints", RewardResourceAmount = 5 },
          QuestCatchFish = { RewardResourceName = "MetaCurrency", RewardResourceAmount = 7 },
        }'''
        files = {"StoryResetData.lua": 'StoryResetData = { TextLines = {} }',
                 "QuestData.lua": self.quest_source,
                 "ResourceData.lua": '''ResourceData = {
                    BaseResource = {},
                    GiftPoints = { InheritFrom = { "BaseResource" }, OnAddedFunctionName = "OnGiftPointsAdded" },
                    MetaCurrency = { InheritFrom = { "BaseResource" }, IgnoreAsLastResourceGained = true },
                 }''', "ResourceLogic.lua": "-- verified reward mutation owner fixture\n",
                 "QuestLogLogic.lua": "-- verified claim owner fixture\n"}
        for filename, content in files.items():
            (self.scripts / filename).write_text(content)
        self.state["QuestStatus"] = table({"QuestHelpDora": "Complete", "QuestUnlockMoros": "Unlocked"})
        self.state["QuestsCompleted"] = table({"QuestHelpDora": True})
        self.state["LifetimeResourcesGained"] = table({"GiftPoints": 100})
        self.current["ResourcesGained"] = table({"GiftPoints": 4})
        self.current["KeepRun"] = "unchanged"
        self.write()
        self.work = self.open()

    def open(self):
        work = super().open()
        if hasattr(self, "scripts"):
            work._game_path = str(self.base)
            work._investigation = NativeDialogueInvestigation(self.base,
                expected_hash=hashlib.sha256((self.scripts / "StoryResetData.lua").read_bytes()).hexdigest())
            work._investigation.reward_owner_hashes = {name: hashlib.sha256((self.scripts / name).read_bytes()).hexdigest()
                for name in ("ResourceLogic.lua", "QuestLogLogic.lua", "ResourceData.lua")}
        return work

    def test_explicit_claim_grants_all_saved_native_effects_and_reopens(self):
        original = self.path.read_bytes()
        claim = next(row for row in self.work.query(domain="quests", search="QuestHelpDora", language="en")["items"]
                     if row["id"] == "questClaim:QuestHelpDora")
        self.assertIn("× 3", claim.get("warning", ""))
        self.assertIn("Active objective prompts are preserved", claim.get("warning", ""))
        self.assertIn("no game presentation", claim.get("warning", ""))
        staged = self.work.stage("questClaim:QuestHelpDora", "set", True)
        self.assertEqual(staged["actionCount"], 1)
        paths = {tuple(item["path"]) for item in staged["changes"] if item.get("path")}
        self.assertIn(("GameState", "LifetimeResourcesGained", "GiftPoints"), paths)
        self.assertIn(("CurrentRun", "ResourcesGained", "GiftPoints"), paths)
        self.assertEqual(self.path.read_bytes(), original)
        result = self.work.apply()
        saved = self.open().document.lua_state
        self.assertEqual(saved["GameState"]["Resources"]["GiftPoints"], 23)
        self.assertEqual(saved["GameState"]["LifetimeResourcesGained"]["GiftPoints"], 103)
        self.assertEqual(saved["CurrentRun"]["ResourcesGained"]["GiftPoints"], 7)
        self.assertEqual(saved["GameState"]["UnviewedLastResourceGained"], "GiftPoints")
        self.assertEqual(saved["GameState"]["QuestStatus"]["QuestHelpDora"], "CashedOut")
        self.assertIs(saved["GameState"]["QuestsCompleted"]["QuestHelpDora"], True)
        self.assertEqual(saved["CurrentRun"]["KeepRun"], "unchanged")
        before = self.service.store.load_verified_snapshot(result["previousSnapshotId"])
        self.assertEqual((before["root"] / "files/main/Profile1.sav").read_bytes(), original)
        self.assertEqual(self.open().stage("questClaim:QuestHelpDora", "set", True)["actionCount"], 0)


    def test_combined_rewards_revise_cancel_and_direct_status_do_not_grant(self):
        self.work.stage("questClaim:QuestHelpDora", "set", True)
        self.work.stage("questClaim:QuestUnlockMoros", "set", True)
        effects = self.work.review()["changes"]
        inventory = next(item for item in effects if item.get("path") == ["GameState", "Resources", "GiftPoints"])
        self.assertEqual(inventory["after"], 28)
        self.work.stage("questClaim:QuestHelpDora", "set", False)
        self.assertEqual(self.work.review()["actionCount"], 1)
        self.work.unstage("questClaim:QuestUnlockMoros")
        self.work.stage("quest:QuestHelpDora", "setEnum", "CashedOut")
        self.work.stage("questClaim:QuestCatchFish", "set", True)
        self.work.apply()
        saved = self.open().document.lua_state
        self.assertEqual(saved["GameState"]["Resources"]["GiftPoints"], 20)
        self.assertEqual(saved["GameState"]["Resources"]["MetaCurrency"], 7)
        self.assertEqual(saved["CurrentRun"]["ResourcesGained"]["MetaCurrency"], 7)
        self.assertIsNone(saved["GameState"].get("UnviewedLastResourceGained"))

    def test_explicit_overlaps_including_source_equal_values_are_rejected(self):
        self.work.stage("questClaim:QuestHelpDora", "set", True)
        for identifier, operation, value in (
            ("resource:GiftPoints", "set", 20),
            ("resource:GiftPoints", "set", 90),
            ("quest:QuestHelpDora", "setEnum", "Complete"),
            ("questObservation:QuestsCompleted:QuestHelpDora", "set", False),
        ):
            with self.assertRaises(ValueError, msg=identifier):
                self.work.stage(identifier, operation, value)
        advanced = next(row for row in self.work.query(domain="advanced", path=["GameState", "QuestsCompleted"])["items"]
                        if row["rawId"] == "QuestHelpDora")
        with self.assertRaises(ValueError):
            self.work.stage(advanced["id"], "set", True)
        self.assertEqual(self.work.review()["actionCount"], 1)

    def test_changed_reward_evidence_and_positive_legacy_callback_are_explicit(self):
        self.work.stage("questClaim:QuestHelpDora", "set", True)
        (self.scripts / "QuestData.lua").write_text(self.quest_source.replace("Amount = 3", "Amount = 9"))
        with self.assertRaisesRegex(ValueError, "source has changed"):
            self.work.apply()
        self.assertEqual(Hades2SaveDocument.load(self.path).lua_state["GameState"]["Resources"]["GiftPoints"], 20)
        self.assertEqual(self.work.unstage("questClaim:QuestHelpDora")["actionCount"], 0)
        self.current["Hero"] = table({"Traits": table({1: table({"GiftPointHealthMultiplier": 5})})})
        self.write(); self.work = self.open()
        with self.assertRaisesRegex(ValueError, "processed native health-trait"):
            self.work.stage("questClaim:QuestHelpDora", "set", True)
        self.work.stage("resource:GiftPoints", "set", 25)
        self.work.stage("quest:QuestHelpDora", "setEnum", "CashedOut")
        self.work.apply()
        self.assertEqual(self.open().document.lua_state["GameState"]["Resources"]["GiftPoints"], 25)

    def test_same_resource_rewards_merge_and_missing_owners_are_created(self):
        for key in ("Resources", "LifetimeResourcesGained", "QuestsCompleted"):
            self.state.pop(key)
        self.current.pop("ResourcesGained")
        self.write(); self.work = self.open()
        self.work.stage("questClaim:QuestUnlockMoros", "set", True)
        self.work.stage("questClaim:QuestHelpDora", "set", True)
        self.work.apply()
        saved = self.open().document.lua_state
        self.assertEqual(saved["GameState"]["Resources"]["GiftPoints"], 8)
        self.assertEqual(saved["GameState"]["LifetimeResourcesGained"]["GiftPoints"], 8)
        self.assertEqual(saved["CurrentRun"]["ResourcesGained"]["GiftPoints"], 8)
        self.assertIs(saved["GameState"]["QuestsCompleted"]["QuestUnlockMoros"], True)

    def test_callback_trait_input_cannot_be_changed_behind_pending_reward(self):
        self.current["Hero"] = table({"Traits": table({})})
        self.write(); self.work = self.open()
        self.work.stage("questClaim:QuestHelpDora", "set", True)
        trait_row = next(row for row in self.work.query(domain="advanced", path=["CurrentRun", "Hero"])["items"]
                         if row["rawId"] == "Traits")
        with self.assertRaises(ValueError):
            self.work.stage(trait_row["id"], "set", {"luaType": "table", "entries": [
                {"key": {"luaType": "number", "value": 1}, "value": {"luaType": "table", "entries": [
                    {"key": {"luaType": "string", "value": "GiftPointHealthMultiplier"},
                     "value": {"luaType": "number", "value": 5}}]}}]})
        self.assertEqual(self.work.review()["actionCount"], 1)

    def test_ambiguous_native_reward_field_blocks_only_explicit_claim(self):
        source = self.quest_source.replace('RewardResourceAmount = 3',
            'RewardResourceAmount = 3, RewardResourceAmount = 8')
        (self.scripts / "QuestData.lua").write_text(source)
        with self.assertRaisesRegex(ValueError, "duplicat"):
            self.work.stage("questClaim:QuestHelpDora", "set", True)
        self.work.stage("questClaim:QuestCatchFish", "set", True)
        self.work.stage("quest:QuestHelpDora", "setEnum", "Complete")
        self.assertEqual(self.work.review()["actionCount"], 1)

    def test_mixed_workflows_keep_the_original_source_and_explicit_target(self):
        self.state["MetaUpgradeState"] = table({})
        self.state["Flags"]["FutureFlag"] = False
        self.write(); self.work = self.open()
        original_source = self.path.read_bytes()
        target = self.saves / "Profile2.sav"
        target.write_bytes(original_source)
        self.work.set_target({"rootId": "main", "relativePath": target.name})
        # Neither a new source version nor a later target version may silently
        # replace the originally opened document's requested values.
        changed_source = Hades2SaveDocument.load(self.path)
        changed_source.lua_state["GameState"]["KeepUnknown"] = "external source"
        self.path.write_bytes(changed_source.to_bytes())
        later_source = self.path.read_bytes()
        changed_target = Hades2SaveDocument.load(target)
        changed_target.lua_state["GameState"]["KeepUnknown"] = "external target"
        target.write_bytes(changed_target.to_bytes())
        previous_target = target.read_bytes()
        edits = (
            ("questClaim:QuestHelpDora", "set", True),
            ("gift:Hecate:GiftPoints", "set", 10),
            ("history:gathering:fishing:FishingFails", "set", 12),
            ("card:ChanneledCast:Level", "set", 2),
            ("familiarSelected:FrogFamiliar", "set", True),
            ("resource:MetaCurrency", "set", 200),
            ("flag:FutureFlag", "set", True),
            ("dialogue:A", "set", False),
        )
        for identity, operation, value in edits:
            self.work.stage(identity, operation, value)
        raw = next(row for row in self.work.query(domain="advanced", path=["GameState"])["items"]
                   if row["rawId"] == "KeepUnknown")
        self.work.stage(raw["id"], "set", "requested raw value")
        stamp = next(row for row in self.work.query(domain="advanced", path=[{"saveContainer": "header"}])["items"]
                     if row["rawId"] == "timestamp")
        self.work.stage(stamp["id"], "set", "101")
        review = self.work.review()
        self.assertEqual(review["actionCount"], 10)
        effects = {row["id"] for row in review["changes"]}
        self.assertIn("linked:giftTotal:GiftPoints", effects)
        self.assertIn("linked:arcanaCache:MetaUpgradeCardLayout", effects)
        self.assertEqual(target.read_bytes(), previous_target)
        result = self.work.apply()
        installed = Hades2SaveDocument.load(target)
        self.assertEqual(installed.header.timestamp, 101)
        saved = installed.lua_state
        state = saved["GameState"]
        self.assertEqual(self.path.read_bytes(), later_source)
        self.assertEqual(state["KeepUnknown"], "requested raw value")
        self.assertEqual(state["QuestStatus"]["QuestHelpDora"], "CashedOut")
        self.assertEqual(state["Resources"]["GiftPoints"], 23)
        self.assertEqual(state["GiftRecord"]["Hecate"]["GiftPoints"], 10)
        self.assertEqual(state["GiftResourceRecord"]["GiftPoints"], 14)
        self.assertEqual(state["FishingFails"], 12)
        self.assertEqual(state["MetaUpgradeState"]["ChanneledCast"]["Level"], 2)
        self.assertTrue(state["MetaUpgradeState"]["ChanneledCast"]["Unlocked"])
        self.assertEqual(state["EquippedFamiliar"], "FrogFamiliar")
        self.assertTrue(state["FamiliarsUnlocked"]["FrogFamiliar"])
        self.assertEqual(state["Resources"]["MetaCurrency"], 200)
        self.assertTrue(state["Flags"]["FutureFlag"])
        self.assertIs(state["TextLinesRecord"]["A"], False)
        self.assertEqual(saved["CurrentRun"]["ResourcesGained"]["GiftPoints"], 7)
        self.assertEqual(saved["CurrentRun"]["GiftRecord"]["Hecate"]["GiftPoints"], 1)
        backup = self.service.store.load_verified_snapshot(result["previousSnapshotId"])
        self.assertEqual((backup["root"] / "files/main/Profile2.sav").read_bytes(), previous_target)
        self.assertEqual(self.work.review()["actionCount"], 0)

    def test_unrelated_container_edits_coexist_with_each_transaction_in_either_order(self):
        from games.hades2 import save_advanced
        for identity, value in (("questClaim:QuestHelpDora", True), ("gift:Hecate:GiftPoints", 10)):
            for reverse in (False, True):
                with self.subTest(identity=identity, reverse=reverse):
                    self.write(); self.work = self.open()
                    stamp = next(row for row in self.work.query(domain="advanced", path=[{"saveContainer": "header"}])["items"]
                                 if row["rawId"] == "timestamp")
                    payload = next(row for row in self.work.query(domain="advanced")["items"]
                                   if row["path"] == [{"saveContainer": "payload"}])
                    edits = [(identity, "set", value), (stamp["id"], "set", "101"),
                             (payload["id"], "set", save_advanced.typed_value(table({1: 9.25})))]
                    for entry, operation, after in reversed(edits) if reverse else edits:
                        self.work.stage(entry, operation, after)
                    self.assertEqual(self.work.review()["actionCount"], 3)
                    self.work.apply()
                    saved = Hades2SaveDocument.load(self.path)
                    self.assertEqual(saved.header.timestamp, 101)
                    self.assertEqual(saved.lua_values[1:], [9.25])
                    if identity.startswith("questClaim:"):
                        self.assertEqual(saved.lua_state["GameState"]["Resources"]["GiftPoints"], 23)
                        self.assertEqual(saved.lua_state["GameState"]["QuestStatus"]["QuestHelpDora"], "CashedOut")
                    else:
                        self.assertEqual(saved.lua_state["GameState"]["GiftRecord"]["Hecate"]["GiftPoints"], 10)
                        self.assertEqual(saved.lua_state["GameState"]["GiftResourceRecord"]["GiftPoints"], 14)

    def test_one_browse_uses_one_source_capture_for_all_reward_rows(self):
        (self.scripts / "QuestData.lua").write_text("QuestData = {\n" + "\n".join(
            name + ' = { RewardResourceName = "GiftPoints", RewardResourceAmount = 3 },'
            for name in sorted(QUEST_IDS)) + "\n}")
        source = self.work._investigation
        with patch.object(source, "_refresh", wraps=source._refresh) as refresh:
            rows = self.work.query(domain="quests", search="Quest", language="en")["items"]
        self.assertEqual(sum(row["id"].startswith("questClaim:") for row in rows), len(QUEST_IDS))
        self.assertEqual(refresh.call_count, 1, "each reward row rescans the same native tree")
        self.work.stage("questClaim:QuestHelpDora", "set", True)
        path = self.scripts / "QuestData.lua"
        path.write_text(path.read_text().replace("Amount = 3", "Amount = 9"))
        with self.assertRaisesRegex(ValueError, "source has changed"):
            self.work.apply()

if __name__ == "__main__":
    unittest.main()
