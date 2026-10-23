"""Stored gift quantities are editable without synthesizing gift events."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
from core.module_manifest import SaveManagementSpec, SaveRootSpec
from core.save_service import CoreSaveService
from games.hades2.save_document import Hades2SaveDocument, Hades2SaveHeader, LuaTable
from games.hades2.save_workspace import Hades2SaveWorkspace


def table(items):
    items = list(items.items()) if isinstance(items, dict) else list(items)
    return LuaTable(0, len(items), items)


class SaveTransactionFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mgt-gift-counts-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.saves = self.base / "saves"; self.saves.mkdir()
        self.path = self.saves / "Profile1.sav"
        self.state = table({"Resources": table({"GiftPoints": 20}), "Flags": table({}),
            "GiftRecord": table({"Hecate": table([(1, "GiftPoints"), ("GiftPoints", 7), ("FutureGift", 2)]),
                                 "Odysseus": table({"GiftPoints": 3})}),
            "GiftResourceRecord": table({"GiftPoints": 11, "FutureGift": 2}),
            "GiftTextLinesOrderRecord": table({"Hecate": table({1: "A", 2: "B"})}),
            "TextLinesRecord": table({"A": True}), "KeepUnknown": "yes"})
        self.current = table({"GiftRecord": table({"Hecate": table({"GiftPoints": 1})}),
                              "GiftResourceRecord": table({"GiftPoints": 1})})
        self.write()
        spec = SaveManagementSpec((SaveRootSpec("main", str(self.saves), ("Profile*.sav",)),), None, True, "stoppedOnly", True)
        self.service = CoreSaveService("hades2", spec, self.base / "data", lambda: False)
        self.work = self.open()

    def write(self):
        header = Hades2SaveHeader(0x12, 0, 100, "Crossroads", 1, 0, 0, 0, 0, 0, 0,
                                 ("GameState", "CurrentRun"), "Hub_Main", "F_Opening01")
        self.path.write_bytes(Hades2SaveDocument(header, [table({"GameState": self.state, "CurrentRun": self.current})]).to_bytes())

    def open(self):
        target = {"rootId": "main", "relativePath": "Profile1.sav"}
        return Hades2SaveWorkspace.open(self.service, source=target, target=target)


class GiftTransactionTests(SaveTransactionFixture):
    def test_existing_quantity_is_editable_despite_nonmatching_event_order(self):
        row = next(row for row in self.work.query(domain="relationships", language="en", search="Hecate")["items"]
                   if row["id"] == "gift:Hecate:GiftPoints")
        self.assertTrue(row["editable"], "a reliable stored quantity is blocked by unproven order coupling")
        self.assertIn("without replaying a gift", row.get("warning", ""))
        original = self.path.read_bytes()
        self.work.stage(row["id"], "set", 12)
        self.work.stage("gift:Odysseus:GiftPoints", "set", 1)
        review = self.work.review()
        self.assertEqual(review["actionCount"], 2)
        total = next(effect for effect in review["changes"] if effect["id"] == "linked:giftTotal:GiftPoints")
        self.assertEqual((total["before"], total["after"]), (11, 14))
        self.work.stage(row["id"], "set", 10)
        self.work.unstage("gift:Odysseus:GiftPoints")
        self.assertEqual(next(effect for effect in self.work.review()["changes"] if effect["id"] == total["id"])["after"], 14)
        self.assertEqual(self.path.read_bytes(), original)
        result = self.work.apply()
        saved = Hades2SaveDocument.load(self.path).lua_state
        self.assertEqual(saved["GameState"]["GiftRecord"]["Hecate"]["GiftPoints"], 10)
        self.assertEqual(saved["GameState"]["GiftResourceRecord"]["GiftPoints"], 14)
        self.assertEqual(saved["GameState"]["GiftRecord"]["Hecate"][1], "GiftPoints")
        self.assertEqual(saved["GameState"]["GiftTextLinesOrderRecord"]["Hecate"][2], "B")
        self.assertEqual(saved["GameState"]["Resources"]["GiftPoints"], 20)
        self.assertEqual(saved["CurrentRun"]["GiftResourceRecord"]["GiftPoints"], 1)
        before = self.service.store.load_verified_snapshot(result["previousSnapshotId"])
        self.assertEqual((before["root"] / "files/main/Profile1.sav").read_bytes(), original)
        self.assertEqual(self.open().review()["actionCount"], 0)

    def test_missing_aggregate_is_rebuilt_from_all_reliable_people_and_unknown_resources(self):
        self.state.pop("GiftResourceRecord")
        self.write(); self.work = self.open()
        self.work.stage("gift:Hecate:GiftPoints", "set", 8)
        self.work.stage("gift:Odysseus:GiftPoints", "set", 4)
        self.work.stage("gift:Hecate:FutureGift", "set", 5)
        self.work.apply()
        saved = Hades2SaveDocument.load(self.path).lua_state["GameState"]
        self.assertEqual(saved["GiftResourceRecord"]["GiftPoints"], 12)
        self.assertEqual(saved["GiftResourceRecord"]["FutureGift"], 5)

    def test_multiple_deltas_are_combined_before_range_validation(self):
        self.state["GiftResourceRecord"]["GiftPoints"] = 3
        self.write(); self.work = self.open()
        self.work.stage("gift:Odysseus:GiftPoints", "set", 8)
        self.work.stage("gift:Hecate:GiftPoints", "set", 2)
        self.work.apply()
        self.assertEqual(Hades2SaveDocument.load(self.path).lua_state["GameState"]["GiftResourceRecord"]["GiftPoints"], 3)

    def test_ambiguity_is_scoped_to_actual_required_owner(self):
        self.state["GiftRecord"]["Hecate"] = table([("GiftPoints", 7), ("GiftPoints", 9), ("FutureGift", 2)])
        self.write(); self.work = self.open()
        rows = {row["id"]: row for row in self.work.query(domain="relationships", search="Hecate")["items"]}
        self.assertFalse(rows["gift:Hecate:GiftPoints"]["editable"])
        self.assertTrue(rows["gift:Hecate:FutureGift"]["editable"])
        self.work.stage("gift:Hecate:FutureGift", "set", 3)
        with self.assertRaises(ValueError):
            self.work.stage("gift:Hecate:GiftPoints", "set", 4)
        self.work.apply()
        saved = Hades2SaveDocument.load(self.path).lua_state["GameState"]
        self.assertEqual([value for key, value in saved["GiftRecord"]["Hecate"].entries() if key == "GiftPoints"], [7, 9])
        self.assertEqual(saved["GiftResourceRecord"]["FutureGift"], 3)

    def test_bad_values_and_explicit_aggregate_overlaps_preserve_intent(self):
        self.work.stage("gift:Hecate:GiftPoints", "set", 8)
        for value in (-1, 1.5, True, float("inf")):
            with self.assertRaises(ValueError):
                self.work.stage("gift:Hecate:GiftPoints", "set", value)
        aggregate = next(row for row in self.work.query(domain="advanced", path=["GameState", "GiftResourceRecord"])["items"]
                         if row["rawId"] == "GiftPoints")
        with self.assertRaises(ValueError):
            self.work.stage(aggregate["id"], "set", 99)
        with self.assertRaises(ValueError):
            self.work.stage(aggregate["id"], "set", 11)
        self.assertEqual(self.work.review()["actionCount"], 1)

    def test_missing_interaction_owners_are_created_and_observed_unknown_counts_are_writable(self):
        self.work.stage("interaction:NPC_Dora_01", "set", 4)
        self.work.stage("specialInteraction:NPC_Dora_01", "set", 2)
        self.work.stage("objective:OpenInventory", "set", 6)
        self.work.apply()
        saved = self.open().document.lua_state["GameState"]
        self.assertEqual(saved["NPCInteractions"]["NPC_Dora_01"], 4)
        self.assertEqual(saved["SpecialInteractRecord"]["NPC_Dora_01"], 2)
        self.assertEqual(saved["ObjectivesCompleted"]["OpenInventory"], 6)
        saved["NPCInteractions"]["FutureNPC"] = 8
        changed = Hades2SaveDocument.load(self.path)
        changed.lua_state["GameState"] = saved
        self.path.write_bytes(changed.to_bytes())
        self.work = self.open()
        self.work.stage("interaction:FutureNPC", "set", 10)
        self.work.apply()
        self.assertEqual(self.open().document.lua_state["GameState"]["NPCInteractions"]["FutureNPC"], 10)

    def test_unknown_observed_interaction_values_use_their_actual_scalar_type(self):
        self.state["NPCInteractions"] = table({"FutureFraction": -2.5, "FutureString": " original "})
        self.state["SpecialInteractRecord"] = table({"FutureBoolean": True})
        self.write(); self.work = self.open()
        unknown = next(row for row in self.work.query(domain="relationships", search="FutureString", language="en")["items"]
                       if row["id"] == "interaction:FutureString")
        self.assertIn("not catalogued", unknown.get("warning", ""))
        self.work.stage("interaction:FutureFraction", "set", -3.25)
        self.work.stage("interaction:FutureString", "set", " ")
        self.work.stage("specialInteraction:FutureBoolean", "set", False)
        self.work.apply()
        saved = self.open().document.lua_state["GameState"]
        self.assertEqual(saved["NPCInteractions"]["FutureFraction"], -3.25)
        self.assertEqual(saved["NPCInteractions"]["FutureString"], " ")
        self.assertIs(saved["SpecialInteractRecord"]["FutureBoolean"], False)

    def test_aggregate_reconstruction_owns_all_contributing_quantity_inputs(self):
        self.state.pop("GiftResourceRecord")
        self.write(); self.work = self.open()
        self.work.stage("gift:Hecate:GiftPoints", "set", 8)
        other = next(row for row in self.work.query(domain="advanced", path=["GameState", "GiftRecord", "Odysseus"])["items"]
                     if row["rawId"] == "GiftPoints")
        with self.assertRaises(ValueError):
            self.work.stage(other["id"], "set", 20)
        self.assertEqual(self.work.review()["actionCount"], 1)


if __name__ == "__main__":
    unittest.main()
