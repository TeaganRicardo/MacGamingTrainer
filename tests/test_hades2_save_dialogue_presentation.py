"""Recognizable scene ownership survives direct editing and Changes."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.save_document import LuaTable
from games.hades2.save_investigation import NativeDialogueInvestigation
from games.hades2.save_workspace import Hades2SaveWorkspace


def table(values):
    return LuaTable(0, len(values), list(values.items()))


class DialoguePresentationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mgt-dialogue-presentation-")
        self.addCleanup(self.temporary.cleanup)
        game = Path(self.temporary.name)
        scripts = game / "sources/Scripts"
        scripts.mkdir(parents=True)
        reset = b'StoryResetData = { TextLines = { "NemesisPostTrueEnding01" } }'
        (scripts / "StoryResetData.lua").write_bytes(reset)
        (scripts / "NPCData_Nemesis.lua").write_text('''UnitSetData = {
 NPC_Nemesis_01 = { InteractTextLineSets = {
  NemesisPostTrueEnding01 = { { Cue = "/VO/Nemesis_0407" } },
 } },
}''')
        for locale, person, line, voice in (
            ("en", "Nemesis", "I remember this", "A voice without a scene"),
            ("zh-CN", "涅墨西斯", "我记得这件事", "没有剧情记录的语音"),
        ):
            text = game / "sources/Text" / locale
            text.mkdir(parents=True)
            (text / ("Dialogue." + locale + ".sjson")).write_text('''{ Texts = [
 { Id = "NPC_Nemesis_01" DisplayName = "%s" }
 { Id = "Nemesis_0407" DisplayName = "%s" Event = "NemesisPostTrueEnding01" }
 { Id = "Nemesis_9999" DisplayName = "%s" Event = "NemesisVoiceOnly.VoiceLines" }
] }''' % (person, line, voice))
        self.root = table({"GameState": table({
            "Resources": table({}), "Flags": table({}),
            "TextLinesRecord": table({"NemesisPostTrueEnding01": True}),
            "TextLinesChoiceRecord": table({"NemesisPostTrueEnding01": "ChoiceA"}),
            "GiftTextLinesOrderRecord": table({}),
        }), "CurrentRun": table({"TextLinesRecord": table({"NemesisPostTrueEnding01": True})})})
        self.work = Hades2SaveWorkspace(SimpleNamespace(
            document=SimpleNamespace(lua_state=self.root), relative_path="Profile1.sav"
        ), "Profile1", game_path=str(game))
        self.work._investigation = NativeDialogueInvestigation(
            game, expected_hash=hashlib.sha256(reset).hexdigest())

    def rows(self):
        return {row["id"]: row for entity in self.work.query(
            domain="entities", scope="story", search="Nemesis", language="en"
        )["entities"] for row in entity["items"]}

    def test_voice_event_does_not_invent_a_playback_owner(self):
        self.assertNotIn("dialogue:NemesisVoiceOnly.VoiceLines", self.rows())

    def test_changes_keep_person_and_scene_content_in_both_languages(self):
        self.work.stage("dialogue:NemesisPostTrueEnding01", "set", False)
        for locale, person, line in (("en", "Nemesis", "I remember this"),
                                     ("zh-CN", "涅墨西斯", "我记得这件事")):
            action = self.work.review(locale)["actions"][0]
            self.assertEqual(action["entityName"], person)
            self.assertEqual(action["content"], [line])
            self.assertNotIn("NemesisPostTrueEnding01", action["name"])

    def test_native_reset_is_a_direct_action_and_clears_companions(self):
        reset = self.rows()["dialogueReset:NemesisPostTrueEnding01"]
        self.assertEqual(reset["mutationKinds"], ["set"])
        self.assertEqual(reset["choices"], [False])
        self.work.stage(reset["id"], "set", False)
        effects = self.work.review("en")["actions"][0]["effects"]
        self.assertEqual({effect["name"] for effect in effects}, {"Scene choice", "Current run · Played scene"})
        candidate = self.work._validated_review_state(self.work._pending.values()).lua_state
        self.assertIsNone(candidate["GameState"]["TextLinesRecord"].get("NemesisPostTrueEnding01"))
        self.assertIsNone(candidate["GameState"]["TextLinesChoiceRecord"].get("NemesisPostTrueEnding01"))
        self.assertIsNone(candidate["CurrentRun"]["TextLinesRecord"].get("NemesisPostTrueEnding01"))
        self.assertTrue(self.root["GameState"]["TextLinesRecord"]["NemesisPostTrueEnding01"])


if __name__ == "__main__":
    unittest.main()
