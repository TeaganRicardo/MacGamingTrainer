"""Typed Advanced edits cross the real codec and recoverable Core transaction."""
import copy
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
from games.hades2 import save_advanced
from games.hades2.command_contract import Hades2CommandContract


def table(entries):
    entries = list(entries.items()) if isinstance(entries, dict) else list(entries)
    return LuaTable(0, len(entries), entries)


def node(kind, value):
    return {"luaType": kind, "value": value}


class AdvancedSaveMutationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mgt-typed-advanced-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.saves = self.root / "saves"
        self.saves.mkdir()
        self.path = self.saves / "Profile1.sav"
        self.raw = table({"Boolean": True, "Number": 3.5, "String": " old ", "Nil": None,
                          "Members": table([(True, "bool"), (1.0, "number"), ("1", "string")]),
                          "Bytes": b"\xff\x00raw".decode("utf8", "surrogateescape"),
                          "Unknown": table({"Keep": "unchanged"})})
        state = table({"Resources": table({"MetaCurrency": 10.0}),
                       "MetaUpgradeState": table({"LowManaDamageBonus": table({"Unlocked": True, "Equipped": True, "Level": 2.0})}),
                       "MetaUpgradeCostCache": 2.0,
                       "Raw": self.raw})
        header = Hades2SaveHeader(0x12, 0, 123, "Crossroads", 1, 2, 3, 4, 5, 0, 0,
                                 ("GameState", "CurrentRun"), "Hub_Main", "F_Opening01")
        self.path.write_bytes(Hades2SaveDocument(header, [table({"GameState": state, "CurrentRun": table({})})]).to_bytes())
        spec = SaveManagementSpec((SaveRootSpec("main", str(self.saves), ("Profile*.sav",)),),
                                  None, True, "stoppedOnly", True)
        self.service = CoreSaveService("hades2", spec, self.root / "data", lambda: False)
        self.workspace = Hades2SaveWorkspace.open(self.service, source={"rootId": "main", "relativePath": "Profile1.sav"},
                                                  target={"rootId": "main", "relativePath": "Profile1.sav"})

    def rows(self, path=("GameState", "Raw")):
        return self.workspace.query(domain="advanced", path=list(path), language="en")["items"]

    def row(self, key, path=("GameState", "Raw")):
        return next(row for row in self.rows(path) if row["rawId"] == key)

    def test_unknown_scalars_are_writable_by_actual_type_then_apply_and_reopen(self):
        for key, value in (("Boolean", False), ("Number", -42.25), ("String", "  new value  ")):
            row = self.row(key)
            self.assertTrue(row["editable"], "Unique unknown scalar is technically writable, not read-only")
            self.assertIn("set", row["mutationKinds"])
            self.workspace.stage(row["id"], "set", value)
        self.assertEqual(self.workspace.document.lua_state["GameState"]["Raw"]["Number"], 3.5)
        self.assertEqual(self.workspace.review()["actionCount"], 3)
        result = self.workspace.apply()
        self.assertTrue(result["applied"])
        self.service.store.load_verified_snapshot(result["previousSnapshotId"])
        reopened = Hades2SaveDocument.load(self.path)
        raw = reopened.lua_state["GameState"]["Raw"]
        self.assertIs(raw["Boolean"], False)
        self.assertEqual(raw["Number"], -42.25)
        self.assertEqual(raw["String"], "  new value  ")
        self.assertEqual(raw["Unknown"]["Keep"], "unchanged")
        self.assertEqual(raw["Bytes"].encode("utf8", "surrogateescape"), b"\xff\x00raw")
        self.assertEqual(reopened.header.timestamp, 123)

    def test_derived_arcana_effects_conflict_with_raw_edits_in_both_staging_orders(self):
        cache = self.row("MetaUpgradeCostCache", path=("GameState",))
        card_id = "card:LowManaDamageBonus:Equipped"
        self.workspace.stage(cache["id"], "set", 10)
        with self.assertRaises(save_advanced.AdvancedMutationError):
            self.workspace.stage(card_id, "set", False)
        self.assertEqual([action["entryId"] for action in self.workspace.review()["actions"]], [cache["id"]])
        self.workspace.unstage(cache["id"])
        self.workspace.stage(card_id, "set", False)
        with self.assertRaises(save_advanced.AdvancedMutationError):
            self.workspace.stage(cache["id"], "set", 10)
        self.assertEqual([action["entryId"] for action in self.workspace.review()["actions"]], [card_id])
        self.workspace.apply()
        saved = Hades2SaveDocument.load(self.path).lua_state["GameState"]
        self.assertEqual(saved["MetaUpgradeCostCache"], 0)
        self.assertIsNone(saved["MetaUpgradeState"]["LowManaDamageBonus"].get("Equipped"))

    def test_members_have_independent_revisable_actions_and_real_key_types(self):
        members = self.row("Members")
        self.workspace.stage(members["id"], "addMembership", {"key": node("string", "New"), "value": node("number", 8)})
        self.workspace.stage(members["id"], "addMembership", {"key": node("boolean", False), "value": node("string", "false key")})
        review = self.workspace.review()
        self.assertEqual(review["actionCount"], 2)
        action = next(action for action in review["actions"] if action["rawId"] == "New")
        self.workspace.stage(action["entryId"], "set", node("number", 9))
        self.assertEqual(self.workspace.investigate(action["entryId"], "en")["typedValue"], node("number", 9))
        detail = self.workspace.investigate(members["id"], "en")
        self.assertEqual(save_advanced.value_from_typed(detail["typedValue"])["New"], 9)
        self.workspace.unstage(next(action["entryId"] for action in review["actions"] if action["rawId"] == "False"))
        self.workspace.stage(members["id"], "removeMembership", {"key": node("boolean", True)})
        self.workspace.apply()
        after = Hades2SaveDocument.load(self.path).lua_state["GameState"]["Raw"]["Members"]
        with self.assertRaises(KeyError):
            after[True]
        self.assertEqual(after[1.0], "number")
        self.assertEqual(after["1"], "string")
        self.assertEqual(after["New"], 9)

    def test_table_detail_and_binary_values_round_trip_without_reclassification(self):
        row = self.row("Members")
        self.assertNotIn("typedValue", row, "lazy table query serialized the whole subtree")
        detail = self.workspace.investigate(row["id"], "en")
        replacement = copy.deepcopy(detail["typedValue"])
        replacement["entries"].append({"key": node("string", "Nested"),
            "value": {"luaType": "table", "entries": [{"key": node("number", 2), "value": node("nil", None)}]}})
        replacement["hashSize"] += 1
        self.workspace.stage(row["id"], "set", replacement)
        review = self.workspace.review()
        self.assertEqual(review["actions"][0]["typedAfter"], save_advanced.typed_value(save_advanced.value_from_typed(replacement)))
        self.workspace.unstage(row["id"])
        binary = self.row("Bytes")
        self.assertEqual(binary["valueType"], "binary")
        self.assertIsNone(binary["value"])
        self.workspace.stage(binary["id"], "set", {"luaType": "string", "encoding": "base64", "value": "AP8="})
        self.workspace.stage(row["id"], "set", replacement)
        self.workspace.apply()
        raw = Hades2SaveDocument.load(self.path).lua_state["GameState"]["Raw"]
        self.assertEqual(raw["Bytes"].encode("utf8", "surrogateescape"), b"\x00\xff")
        self.assertIsNone(raw["Members"]["Nested"][2])

    def test_nil_set_and_field_delete_have_distinct_presence_and_revision(self):
        row = self.row("Nil")
        review = self.workspace.stage(row["id"], "unset")
        self.assertEqual(review["actionCount"], 1)
        self.assertFalse(review["actions"][0]["afterPresent"])
        self.workspace.stage(row["id"], "set", node("nil", None))
        self.assertEqual(self.workspace.review()["actionCount"], 0)
        self.workspace.stage(row["id"], "unset")
        self.workspace.apply()
        raw = Hades2SaveDocument.load(self.path).lua_state["GameState"]["Raw"]
        with self.assertRaises(KeyError):
            raw["Nil"]

    def test_duplicate_paths_are_specific_read_only_and_do_not_block_other_fields(self):
        raw = self.workspace.document.lua_state["GameState"]["Raw"]
        raw["Duplicates"] = table([("same", 1), ("same", 2)])
        rows = self.rows(("GameState", "Raw", "Duplicates"))
        self.assertTrue(all(not row["editable"] and row["readOnlyReason"] for row in rows))
        with self.assertRaises(ValueError):
            self.workspace.stage(rows[0]["id"], "set", 4)
        self.workspace.stage(self.row("Number")["id"], "set", 4)
        self.assertEqual(self.workspace.review()["actionCount"], 1)

    def test_wrong_types_nonfinite_and_overlapping_intents_preserve_basket(self):
        numeric = self.row("Number")
        for value in (float("nan"), float("inf"), True, "123", 9007199254740993):
            with self.assertRaises(ValueError):
                self.workspace.stage(numeric["id"], "set", value)
        self.workspace.stage(numeric["id"], "set", 5)
        with self.assertRaisesRegex(ValueError, "overlap"):
            self.workspace.stage(self.row("Raw", ("GameState",))["id"], "unset")
        self.assertEqual(self.workspace.review()["actionCount"], 1)
        self.workspace.cancel()
        self.workspace.stage("resource:MetaCurrency", "set", 20)
        raw_resource = self.row("MetaCurrency", ("GameState", "Resources"))
        with self.assertRaisesRegex(ValueError, "same Lua path"):
            self.workspace.stage(raw_resource["id"], "set", 30)
        self.assertEqual(self.workspace.review()["actionCount"], 1)

    def test_advanced_bypasses_semantic_whitelist_but_not_linked_action_conflicts(self):
        raw_resource = self.row("MetaCurrency", ("GameState", "Resources"))
        self.workspace.stage(raw_resource["id"], "set", -10)
        self.workspace.apply()
        self.assertEqual(Hades2SaveDocument.load(self.path).lua_state["GameState"]["Resources"]["MetaCurrency"], -10)
        self.workspace.stage("card:LowManaDamageBonus:Unlocked", "set", False)
        level = self.row("Level", ("GameState", "MetaUpgradeState", "LowManaDamageBonus"))
        with self.assertRaisesRegex(ValueError, "same Lua path"):
            self.workspace.stage(level["id"], "set", 3)
        self.assertEqual(self.workspace.review()["actionCount"], 1)

    def test_real_command_validation_accepts_typed_detail_and_long_unique_identity(self):
        workspace = self.workspace
        key = "LongUniqueKey" * 50
        workspace.document.lua_state["GameState"]["Raw"][key] = "text"
        entry = self.row(key)
        self.assertGreater(len(entry["id"]), 512)
        class Adapter:
            def validate_save_workspace(self, identifier):
                if identifier != workspace.identifier:
                    raise ValueError("different workspace")
            def detail_save_editor(self, params):
                return workspace.investigate(params["entryId"], params["language"])
            def stage_save_editor(self, params):
                return workspace.stage(params["entryId"], params["operation"], params.get("value"), params["language"])
        contract = Hades2CommandContract(Adapter())
        detail = contract.dispatch("save_editor_detail", {"workspaceId": workspace.identifier,
            "entryId": entry["id"], "language": "en"}, "typed-detail")
        self.assertEqual(detail["typedValue"], node("string", "text"))
        review = contract.dispatch("save_editor_stage", {"workspaceId": workspace.identifier,
            "entryId": entry["id"], "operation": "set", "value": "  exact  ", "language": "en"}, "typed-stage")
        self.assertEqual(review["actionCount"], 1)
        self.workspace.apply()
        self.assertEqual(Hades2SaveDocument.load(self.path).lua_state["GameState"]["Raw"][key], "  exact  ")

    def test_encoded_byte_keys_and_nonfinite_values_do_not_poison_other_rows(self):
        raw = self.workspace.document.lua_state["GameState"]["Raw"]
        byte_key = b"\xffkey".decode("utf8", "surrogateescape")
        raw[byte_key] = table({"Child": "old"})
        raw["BadNumber"] = float("inf")
        bad = self.row("BadNumber")
        self.assertTrue(bad["editable"])
        self.assertEqual(bad["typedValue"], {"luaType": "number", "encoding": "nonfinite", "value": "inf"})
        byte_row = self.row(save_advanced.display_key(byte_key))
        child = self.rows(byte_row["path"])[0]
        self.workspace.stage(child["id"], "set", "new")
        self.workspace.stage(self.row("String")["id"], "set", "other")
        self.workspace.apply()
        after = Hades2SaveDocument.load(self.path).lua_state["GameState"]["Raw"]
        self.assertEqual(after[byte_key]["Child"], "new")
        self.assertEqual(after["BadNumber"], float("inf"))

    def test_raw_table_and_type_changes_need_no_semantic_whitelist(self):
        state_row = self.row("GameState", ())
        self.workspace.stage(state_row["id"], "set", node("string", "explicit raw replacement"))
        self.workspace.apply()
        self.assertEqual(Hades2SaveDocument.load(self.path).lua_state["GameState"], "explicit raw replacement")

    def test_codec_depth_failure_is_rejected_before_replacing_acknowledged_intent(self):
        row = self.row("Number")
        self.workspace.stage(row["id"], "set", 7)
        deep = node("number", 1)
        for _ in range(128):
            deep = {"luaType": "table", "entries": [{"key": node("string", "Child"), "value": deep}]}
        with self.assertRaisesRegex(ValueError, "deep"):
            self.workspace.stage(row["id"], "set", deep)
        self.assertEqual(self.workspace.review()["actions"][0]["after"], 7)


if __name__ == "__main__":
    unittest.main()
