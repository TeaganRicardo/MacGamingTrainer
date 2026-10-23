"""One quest's observed lifecycle and authored context in the entity journey."""
import hashlib
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
from games.hades2.save_document import LuaTable
from games.hades2.save_investigation import NativeDialogueInvestigation
from games.hades2.save_workspace import Hades2SaveWorkspace


def table(values):
    return LuaTable(0, len(values), list(values.items()))


with tempfile.TemporaryDirectory(prefix="mgt-quest-workflow-") as temporary:
    game = Path(temporary)
    scripts = game / "sources/Scripts"
    scripts.mkdir(parents=True)
    for language, name in (("en", "Doom's Herald"), ("zh-CN", "毁灭使者")):
        texts = game / "sources/Text" / language
        texts.mkdir(parents=True)
        (texts / ("HelpText." + language + ".sjson")).write_text(
            '{ Texts = [{ Id = "QuestUnlockMoros" DisplayName = "' + name + '" }'
            '{ Id = "NPC_Moros_01" DisplayName = "' + ('Moros' if language == 'en' else '摩罗斯') + '" }'
            '{ Id = "Moros" DisplayName = "' + ('Moros' if language == 'en' else '摩罗斯') + '" }'
            '{ Id = "Moros_0001" DisplayName = "' + ('We meet again' if language == 'en' else '我们又见面了') + '" }] }', encoding="utf-8")
    reset = b'StoryResetData = { TextLines = {} }'
    (scripts / "StoryResetData.lua").write_bytes(reset)
    (scripts / "QuestData.lua").write_text('''QuestData = {}
OverwriteTableKeys( QuestData, {
 DefaultQuestItem = { DebugOnly = true },
 QuestUnlockMoros = {
  InheritFrom = { "DefaultQuestItem" },
  UnlockGameStateRequirements = {{ PathTrue = { "GameState", "Flags", "QuestLogUnlocked" } }},
  CompleteGameStateRequirements = {{ OrRequirements = {
   { PathTrue = { "GameState", "TextLinesRecord", "MorosFirstMeeting" } },
   { NamedRequirements = { "DynamicNativeRequirement" } }
  } }},
  SetupEvents = {{ FunctionName = "OverwriteSelf", Args = {
   CompleteGameStateRequirements = {{ NamedRequirements = { "LaterStage" } }}
  } }},
  Nested = { QuestUnlockMoros = { CompleteGameStateRequirements = {} } },
 },
 QuestHelpDora = { CompleteGameStateRequirements = {} },
 QuestGiftNectar = { CompleteGameStateRequirements = {} },
 QuestCatchFish = { CompleteGameStateRequirements = {} },
})''', encoding="utf-8")
    (scripts / "NPCData_Moros.lua").write_text('''UnitSetData = {
 NPC_Moros_01 = {
  InteractTextLineSets = {
   MorosFirstMeeting = {
    { Cue = "/VO/Moros_0001", Text = "We meet again" },
   },
  },
 },
}''', encoding="utf-8")
    state = table({
        "Resources": table({}), "Flags": table({"QuestLogUnlocked": True}),
        "QuestStatus": table({"QuestUnlockMoros": "Unlocked", "QuestHelpDora": "CashedOut", "QuestGiftNectar": "Complete"}),
        "QuestsCompleted": table({"QuestGiftNectar": True}),
        "QuestsViewed": table({"QuestUnlockMoros": True}),
        "QuestsUpdated": table({"QuestUnlockMoros": False}),
        "PlayedQuestInterstitials": table({"QuestUnlockMoros": True}),
        "TextLinesRecord": table({"MorosFirstMeeting": True}),
        "SpeechRecord": table({"/VO/Moros_0001": 3}),
        "NPCInteractions": table({"NPC_Moros_01": 4}),
        "GiftRecord": table({"Moros": table({"GiftPoints": 2})}),
        "GiftResourceRecord": table({"GiftPoints": 2}),
        "GiftTextLinesOrderRecord": table({}), "TextLinesChoiceRecord": table({}),
    })
    root = table({"GameState": state, "CurrentRun": table({})})
    session = SimpleNamespace(document=SimpleNamespace(lua_state=root), relative_path="Profile1.sav")
    work = Hades2SaveWorkspace(session, "Profile1", game_path=str(game))
    work._investigation = NativeDialogueInvestigation(str(game), expected_hash=hashlib.sha256(reset).hexdigest())
    result = work.query(domain="entities", scope="story", search="毁灭使者", language="zh-CN")
    groups = {g["id"]: g for g in result["entities"]}
    assert "quest:QuestUnlockMoros" in groups, "quest lifecycle and context are not grouped as one subject"
    fields = {r["id"]: r for r in groups["quest:QuestUnlockMoros"]["items"]}
    assert fields["quest:QuestUnlockMoros"]["value"] == "Unlocked"
    assert fields["questObservation:QuestsViewed:QuestUnlockMoros"]["value"] is True
    assert fields["questObservation:QuestsUpdated:QuestUnlockMoros"]["value"] is False
    assert fields["questObservation:PlayedQuestInterstitials:QuestUnlockMoros"]["value"] is True
    context = fields["investigate:quest:QuestUnlockMoros"]
    assert context["domain"] == "investigate" and not context["editable"]
    detail = work.investigate(context["id"], language="en")
    assert detail["scene"] == "quest:QuestUnlockMoros" and not detail["canStage"]
    assert detail["futureEligibility"] == "unknown" and detail["sourceResolution"] == "resolved"
    assert len(detail["definitions"]) == 2  # direct owner plus explicitly named base
    conditions = repr(detail["definitions"])
    assert "UnlockGameStateRequirements" in conditions and "CompleteGameStateRequirements" in conditions
    assert "DynamicNativeRequirement" in conditions and "dynamic" in conditions
    assert "LaterStage" in conditions and "selected by native runtime" in conditions
    assert "recorded" in conditions and "QuestLogUnlocked" in conditions
    assert detail["sourceProvenance"]["buildVerification"] == "unverified"
    person = next(g for g in work.query(domain="entities", scope="story", search="摩罗斯", language="zh-CN")["entities"]
                  if g["id"] == "person:Moros")
    person_fields = {row["id"]: row for row in person["items"]}
    assert person["name"] == "摩罗斯"
    assert person_fields["interaction:NPC_Moros_01"]["value"] == 4
    assert person_fields["gift:Moros:GiftPoints"]["value"] == 2
    spoken = next(row for row in person["items"] if row["domain"] == "speechHistory")
    assert spoken["value"] == 3 and "我们又见面了" in spoken["name"] and spoken["editable"]
    assert any(row["domain"] == "investigate" for row in person["items"])
    # Each observed lifecycle remains distinguishable, including absent source
    # identities on deliberate search, without inventing a writable unlock.
    for name, expected in (("QuestHelpDora", "CashedOut"), ("QuestGiftNectar", "Complete"), ("QuestCatchFish", "absent")):
        page = work.query(domain="entities", scope="story", search=name, language="en")
        group = next(g for g in page["entities"] if g["id"] == "quest:" + name)
        row = next(r for r in group["items"] if r["id"] == "investigate:quest:" + name)
        assert row["value"] == expected
    # Existing quest action still owns its completion companion, rather than
    # treating presentation/voice history as independent edit controls.
    work.stage("quest:QuestUnlockMoros", "setEnum", "Complete")
    changes = work.review()
    assert changes["count"] >= 1
    assert state["QuestStatus"]["QuestUnlockMoros"] == "Unlocked", "staging changed the fixed source"
    linked = next(effect for effect in changes["changes"] if effect["id"] == "linked:quest:QuestUnlockMoros")
    assert linked["before"] is None and linked["after"] is True
    candidate = work._validated_review_state(work._pending.values())
    assert candidate.lua_state["GameState"]["QuestStatus"]["QuestUnlockMoros"] == "Complete"
    assert candidate.lua_state["GameState"]["QuestsCompleted"]["QuestUnlockMoros"] is True
    assert state["PlayedQuestInterstitials"]["QuestUnlockMoros"] is True
    # Duplicate presentation owners stay explicitly ambiguous and read-only.
    state["QuestsViewed"] = LuaTable(0, 2, [("QuestUnlockMoros", True), ("QuestUnlockMoros", False)])
    page = work.query(domain="entities", scope="story", search="QuestUnlockMoros", language="en")
    observation = next(r for g in page["entities"] for r in g["items"]
                       if r["id"] == "questObservation:QuestsViewed:QuestUnlockMoros")
    assert observation["value"] is None and observation["reasonCode"] == "ambiguousOwner"
    assert not observation["editable"] and work.investigate(context["id"], "en")["canStage"] is False
    state["SpeechRecord"] = LuaTable(0, 2, [("/VO/Moros_0001", 3), ("/VO/Moros_0001", 4)])
    page = work.query(domain="entities", scope="story", search="Moros", language="en")
    spoken = next(row for group in page["entities"] for row in group["items"] if row["domain"] == "speechHistory")
    assert spoken["value"] is None and spoken["reasonCode"] == "ambiguousOwner"
    # Detail binds to freshly captured bytes. Duplicate direct source owners
    # are unresolved; a nested look-alike never grants a quest definition.
    quest_source = scripts / "QuestData.lua"
    quest_source.write_text(quest_source.read_text() + '\nOverwriteTableKeys(QuestData, {\n QuestUnlockMoros = { CompleteGameStateRequirements = {} },\n})\n')
    unresolved = work.investigate(context["id"], "en")
    assert unresolved["sourceResolution"] == "unresolved" and unresolved["blockReasonCode"] == "questSourceUnresolved"
    assert unresolved["sourceIdentity"] != detail["sourceIdentity"]
    assert not unresolved["canStage"] and unresolved["stageID"] == ""
print("hades2_save_quest_workflow_ok")
