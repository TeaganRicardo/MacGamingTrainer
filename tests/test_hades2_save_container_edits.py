"""Container fields and every extra luabins value use real staged Save writes."""
import copy
import json
import math
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
from games.hades2.command_contract import Hades2CommandContract
from games.hades2 import save_advanced


def table(items):
    items = list(items.items()) if isinstance(items, dict) else list(items)
    return LuaTable(0, len(items), items)


def node(kind, value):
    return {"luaType": kind, "value": value}


class SaveContainerEditTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mgt-save-container-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        saves = self.base / "saves"
        saves.mkdir()
        self.path = saves / "Profile1.sav"
        header = Hades2SaveHeader(0x12, 7, 18446744073709551615, "Crossroads", 1, 2, 3, 4, 5, 0, 0,
                                 ("GameState", "CurrentRun"), "Hub_Main", "F_Opening01")
        main = table({"GameState": table({"Resources": table({"MetaCurrency": 3}),
                                         "saveContainer": "a real native Lua key"}),
                      "header": "native header key", "payload": "native payload key", "\udcff": table({"ByteChild": True})})
        self.path.write_bytes(Hades2SaveDocument(header, [main, 12.5, table({"Child": "original"}), None]).to_bytes())
        self.original = self.path.read_bytes()
        spec = SaveManagementSpec((SaveRootSpec("main", str(saves), ("Profile*.sav",)),),
                                  None, True, "stoppedOnly", True)
        self.service = CoreSaveService("hades2", spec, self.base / "data", lambda: False)
        self.editor = Hades2SaveWorkspace.open(self.service,
            source={"rootId": "main", "relativePath": "Profile1.sav"},
            target={"rootId": "main", "relativePath": "Profile1.sav"})

    def rows(self, path=()):
        return self.editor.query(domain="advanced", path=list(path), language="en", limit=200)["items"]

    def namespace(self, name):
        return next(row for row in self.rows() if row["path"] == [{"saveContainer": name}])

    def field(self, name):
        return next(row for row in self.rows(self.namespace("header")["path"]) if row["rawId"] == name)

    def test_header_scalars_keep_uint64_precision_through_review_apply_and_reopen(self):
        stamp = self.field("timestamp")
        self.assertTrue(stamp["editable"], "the codec-supported header is not writable")
        self.assertEqual(stamp["value"], "18446744073709551615")
        self.editor.stage(stamp["id"], "set", "18446744073709551614")
        for key, value in (("save_flags", 65535), ("completed_runs", 4294967295),
                           ("easy_mode", 255), ("location", "  未知地点  ")):
            self.editor.stage(self.field(key)["id"], "set", value)
        self.assertEqual(self.path.read_bytes(), self.original)
        review = self.editor.review()
        action = next(row for row in review["actions"] if row["entryId"] == stamp["id"])
        self.assertEqual(action["typedAfter"], node("string", "18446744073709551614"))
        result = self.editor.apply()
        self.assertTrue(result["applied"])
        self.service.store.load_verified_snapshot(result["previousSnapshotId"])
        reopened = Hades2SaveDocument.load(self.path)
        self.assertEqual(reopened.header.timestamp, 18446744073709551614)
        self.assertEqual(reopened.header.completed_runs, 4294967295)
        self.assertEqual(reopened.header.easy_mode, 255)
        self.assertEqual(reopened.header.location, "  未知地点  ")
        self.assertEqual(reopened.lua_values[1], 12.5)
        self.assertEqual(reopened.lua_values[2]["Child"], "original")
        self.assertEqual(reopened.lua_state["header"], "native header key")

    def test_container_paths_cross_real_command_validation_and_never_alias_native_keys(self):
        editor = self.editor
        class Adapter:
            def validate_save_workspace(self, identifier):
                assert identifier == editor.identifier
            def detail_save_editor(self, params):
                return editor.investigate(params["entryId"], params["language"])
            def query_save_editor(self, params):
                return editor.query(**{key: params[key] for key in ("domain", "path", "language")})
        contract = Hades2CommandContract(Adapter())
        result = contract.dispatch("save_editor_query", {"workspaceId": editor.identifier,
            "domain": "advanced", "path": [{"saveContainer": "header"}], "language": "en"}, "header-query")
        self.assertTrue(any(row["rawId"] == "timestamp" for row in result["items"]))
        detail = contract.dispatch("save_editor_detail", {"workspaceId": editor.identifier,
            "entryId": self.namespace("payload")["id"], "language": "en"}, "payload-detail")
        self.assertEqual(detail["typedValue"]["luaType"], "table")
        native = next(row for row in self.rows() if row["path"] == ["header"])
        self.editor.stage(native["id"], "set", "native changed")
        self.editor.stage(self.field("location")["id"], "set", "header changed")
        self.editor.apply()
        reopened = Hades2SaveDocument.load(self.path)
        self.assertEqual(reopened.lua_state["header"], "native changed")
        self.assertEqual(reopened.header.location, "header changed")
        byte_rows = self.rows([{"luaType": "string", "encoding": "base64", "value": "/w=="}])
        self.assertEqual(byte_rows[0]["rawId"], "ByteChild")
        for bad in ([{"saveContainer": "Header"}], [{"saveContainer": "header", "luaType": "string"}],
                    [{"saveContainer": "payload", "index": 1}]):
            with self.assertRaises(ValueError):
                self.rows(bad)

    def test_extra_root_values_and_main_root_members_keep_canonical_actions(self):
        extra = self.namespace("payload")
        values = self.rows(extra["path"])
        self.editor.stage(values[0]["id"], "set", node("boolean", False))
        child = self.rows(values[1]["path"])[0]
        self.editor.stage(child["id"], "set", "edited")
        self.editor.stage(values[2]["id"], "set", {"luaType": "table", "entries": [{"key": node("string", "nested"), "value": node("number", 8)}]})
        main = self.namespace("main")
        self.assertNotIn("childCount", main, "main structure row duplicated child navigation")
        self.editor.stage(main["id"], "addMembership", {"key": node("string", "NewRoot"), "value": node("string", "new")})
        review = self.editor.review()
        action = next(row for row in review["actions"] if row["rawId"] == "NewRoot")
        self.assertTrue(action["entryId"].startswith("advanced:"), "main root member received a namespace alias")
        self.editor.stage(action["entryId"], "set", node("string", "revised"))
        self.assertEqual(self.path.read_bytes(), self.original)
        self.editor.apply()
        reopened = Hades2SaveDocument.load(self.path)
        self.assertIs(reopened.lua_values[1], False)
        self.assertEqual(reopened.lua_values[2]["Child"], "edited")
        self.assertEqual(reopened.lua_values[3]["nested"], 8)
        self.assertEqual(reopened.lua_state["NewRoot"], "revised")
        self.assertEqual(reopened.header.timestamp, 18446744073709551615)

    def test_format_transitions_show_conditional_header_field_changes(self):
        version = self.field("game_version")
        review = self.editor.stage(version["id"], "set", 0x11)
        effect = next(row for row in review["changes"] if row["id"] == "linked:save-container:cosmetics_points")
        self.assertEqual((effect["before"], effect["after"]), (5, None))
        self.editor.apply()
        self.assertIsNone(Hades2SaveDocument.load(self.path).header.cosmetics_points)
        self.assertFalse(any(row["rawId"] == "cosmetics_points" for row in self.rows(self.namespace("header")["path"])))
        review = self.editor.stage(self.field("game_version")["id"], "set", 0x12)
        self.assertTrue(any(row["id"] == "linked:save-container:cosmetics_points" and row["after"] == 0
                            for row in review["changes"]))
        self.editor.apply()
        self.assertEqual(Hades2SaveDocument.load(self.path).header.cosmetics_points, 0)
        self.editor.stage(self.field("cosmetics_points")["id"], "set", 17)
        with self.assertRaises(ValueError):
            self.editor.stage(self.field("game_version")["id"], "set", 0x11)
        self.assertEqual(self.editor.review()["actionCount"], 1)
        self.editor.apply()
        self.assertEqual(Hades2SaveDocument.load(self.path).header.cosmetics_points, 17)

    def test_real_codec_limits_reject_before_apply_and_retain_acknowledged_changes(self):
        self.editor.stage(self.field("location")["id"], "set", "retained")
        for name, values in (("save_flags", (-1, 65536, 1.5, True)),
                             ("completed_runs", (-1, 4294967296)), ("easy_mode", (-1, 256)),
                             ("game_version", (0x10, 0x13)),
                             ("timestamp", ("-1", "18446744073709551616", "1.2", "12x")),
                             ("location", ("x" * (1024 * 1024 + 1),))):
            for value in values:
                with self.assertRaises(ValueError, msg=(name, str(value)[:30])):
                    self.editor.stage(self.field(name)["id"], "set", value)
                self.assertEqual(self.editor.review()["actionCount"], 1)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.editor.apply()
        self.assertEqual(Hades2SaveDocument.load(self.path).header.location, "retained")

    def test_header_and_payload_structures_support_membership_and_independent_namespaces(self):
        names = self.field("notable_lua_data")
        self.editor.stage(names["id"], "addMembership", {"key": node("number", 3), "value": node("string", "Future")})
        extra = self.namespace("payload")
        self.editor.stage(extra["id"], "addMembership", {"key": node("number", 4),
            "value": {"luaType": "string", "encoding": "base64", "value": "AP8="}})
        self.editor.apply()
        reopened = Hades2SaveDocument.load(self.path)
        self.assertEqual(reopened.header.notable_lua_data, ("GameState", "CurrentRun", "Future"))
        self.assertEqual(reopened.lua_values[4].encode("utf8", "surrogateescape"), b"\x00\xff")
        self.editor.stage(self.field("notable_lua_data")["id"], "removeMembership", {"key": node("number", 1)})
        values = self.rows(self.namespace("payload")["path"])
        self.editor.stage(values[0]["id"], "unset")
        self.editor.apply()
        reopened = Hades2SaveDocument.load(self.path)
        self.assertEqual(reopened.header.notable_lua_data, ("CurrentRun", "Future"))
        self.assertEqual(len(reopened.lua_values), 4)
        self.assertEqual(reopened.lua_values[1]["Child"], "original")
        self.assertIsNone(reopened.lua_values[2])

    def test_complete_batch_overlap_detection_covers_root_fields_and_index_shifts(self):
        header = self.namespace("header")
        replacement = self.editor.investigate(header["id"], "en")["typedValue"]
        self.editor.stage(self.field("location")["id"], "set", "first")
        with self.assertRaisesRegex(ValueError, "overlap"):
            replacement["entries"][3]["value"] = node("string", "root change")
            self.editor.stage(header["id"], "set", replacement)
        self.assertEqual(self.editor.review()["actionCount"], 1)
        self.editor.cancel()
        extra = self.namespace("payload")
        values = self.rows(extra["path"])
        self.editor.stage(self.rows(values[1]["path"])[0]["id"], "set", "child")
        for parent in (extra, values[1]):
            with self.assertRaisesRegex(ValueError, "overlap"):
                self.editor.stage(parent["id"], "set", {"luaType": "table", "entries": []})
        with self.assertRaisesRegex(ValueError, "overlap"):
            self.editor.stage(values[0]["id"], "unset")
        self.assertEqual(self.editor.review()["actionCount"], 1)
        self.editor.cancel()
        main = self.namespace("main")
        root = self.editor.investigate(main["id"], "en")["typedValue"]
        root["entries"].append({"key": node("string", "Other"), "value": node("boolean", True)})
        root["hashSize"] += 1
        self.editor.stage("resource:MetaCurrency", "set", 9)
        with self.assertRaisesRegex(ValueError, "same Lua path"):
            self.editor.stage(main["id"], "set", root)
        self.assertEqual(self.editor.review()["actionCount"], 1)

    def test_main_root_can_be_replaced_or_repair_missing_gamestate_without_aliases(self):
        main = self.namespace("main")
        replacement = {"luaType": "table", "entries": [{"key": node("string", "Preserved"), "value": node("boolean", True)}]}
        self.editor.stage(main["id"], "set", replacement)
        self.editor.apply()
        self.assertTrue(Hades2SaveDocument.load(self.path).lua_state["Preserved"])
        main = self.namespace("main")
        self.editor.stage(main["id"], "addMembership", {"key": node("string", "GameState"),
            "value": {"luaType": "table", "entries": []}})
        self.editor.apply()
        reopened = Hades2SaveDocument.load(self.path)
        self.assertIsInstance(reopened.lua_state["GameState"], LuaTable)
        self.assertTrue(reopened.lua_state["Preserved"])
        with self.assertRaises(ValueError):
            self.editor.stage(self.namespace("main")["id"], "set", node("number", 8))

    def test_header_root_does_not_silently_discard_explicit_conditional_field(self):
        root = self.namespace("header")
        replacement = self.editor.investigate(root["id"], "en")["typedValue"]
        version = next(entry for entry in replacement["entries"] if entry["key"]["value"] == "game_version")
        version["value"] = node("number", 0x11)
        with self.assertRaises(ValueError):
            self.editor.stage(root["id"], "set", replacement)
        self.assertEqual(self.editor.review()["actionCount"], 0)
        replacement["entries"] = [entry for entry in replacement["entries"] if entry["key"]["value"] != "cosmetics_points"]
        replacement["hashSize"] -= 1
        self.editor.stage(root["id"], "set", replacement)
        self.editor.apply()
        self.assertEqual(Hades2SaveDocument.load(self.path).header.game_version, 0x11)

    def test_explicit_nonfinite_encoding_crosses_codec_and_finite_json(self):
        document = Hades2SaveDocument.load(self.path)
        document.lua_state["Nonfinite"] = float("inf")
        document.lua_values[1] = float("nan")
        self.path.write_bytes(document.to_bytes())
        self.editor = Hades2SaveWorkspace.open(self.service,
            source={"rootId": "main", "relativePath": "Profile1.sav"},
            target={"rootId": "main", "relativePath": "Profile1.sav"})
        existing = next(row for row in self.rows() if row["rawId"] == "Nonfinite")
        self.assertTrue(existing["editable"], "codec-supported nonfinite value is policy-read-only")
        self.assertEqual(existing["typedValue"], {"luaType": "number", "encoding": "nonfinite", "value": "inf"})
        self.editor.stage(existing["id"], "set", 6.25)
        payload = self.rows(self.namespace("payload")["path"])[0]
        nonfinite = {"luaType": "number", "encoding": "nonfinite", "value": "-inf"}
        self.editor.stage(payload["id"], "set", nonfinite)
        self.editor.stage(self.namespace("main")["id"], "addMembership", {
            "key": node("string", "NewNan"), "value": {**nonfinite, "value": "nan"}})
        json.dumps(self.editor.review(), allow_nan=False)
        self.editor.apply()
        reopened = Hades2SaveDocument.load(self.path)
        self.assertEqual(reopened.lua_state["Nonfinite"], 6.25)
        self.assertEqual(reopened.lua_values[1], -float("inf"))
        self.assertTrue(math.isnan(reopened.lua_state["NewNan"]))
        nan_row = next(row for row in self.rows() if row["rawId"] == "NewNan")
        self.editor.stage(nan_row["id"], "set", {**nonfinite, "value": "nan"})
        self.assertEqual(self.editor.review()["actionCount"], 0, "typed NaN comparison is unstable")
        self.editor.stage(nan_row["id"], "unset")
        self.editor.apply()
        self.assertNotIn("NewNan", Hades2SaveDocument.load(self.path).lua_state)

    def test_transport_wrappers_preserve_the_actual_codec_depth_boundary(self):
        deep = 1
        for _ in range(128):
            deep = table({"Child": deep})
        extra = self.namespace("payload")
        replacement = self.editor.investigate(extra["id"], "en")["typedValue"]
        replacement["entries"][0]["value"] = save_advanced.typed_value(deep)
        self.editor.stage(extra["id"], "set", replacement)
        self.editor.apply()
        path = [{"saveContainer": "payload"}, 1, *(["Child"] * 127)]
        leaf = self.rows(path)[0]
        self.assertEqual(len(leaf["path"]), 130)
        self.editor.stage(leaf["id"], "set", 2)
        self.editor.apply()
        after = Hades2SaveDocument.load(self.path).lua_values[1]
        for _ in range(128):
            after = after["Child"]
        self.assertEqual(after, 2)
        invalid = table({"Child": deep})
        replacement["entries"][0]["value"] = save_advanced.typed_value(invalid)
        with self.assertRaises(ValueError):
            self.editor.stage(self.namespace("payload")["id"], "set", replacement)
        self.assertEqual(self.editor.review()["actionCount"], 0)


if __name__ == "__main__":
    unittest.main()
