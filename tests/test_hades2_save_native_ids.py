"""The pinned native Save identity generator must remain executable/reproducible."""

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.save_native_ids import (
    QUEST_IDS, RESOURCE_IDS, NPC_INTERACTION_IDS, OBJECTIVE_IDS,
    STORY_RESET_TEXT_IDS,
)

assert "QuestHelpOdysseus" in QUEST_IDS
assert "DreamPoints" in RESOURCE_IDS
assert "NPC_Hecate_01" in NPC_INTERACTION_IDS
assert "NPC_Nemesis_01" in NPC_INTERACTION_IDS
assert "WeaponCast" in OBJECTIVE_IDS
assert "GiftPrompt" in OBJECTIVE_IDS
assert not ({"FutureUnit", "NPC_Giftable"} & NPC_INTERACTION_IDS)
assert "UnknownObjective" not in OBJECTIVE_IDS
assert "HecatePostTrueEnding01" in STORY_RESET_TEXT_IDS
assert "UnverifiedScene" not in STORY_RESET_TEXT_IDS

with tempfile.TemporaryDirectory(prefix="mgt-native-save-ids-") as temp:
    scripts = Path(temp)
    (scripts / "QuestData.lua").write_text(
        'QuestOrderData =\n{\n\t"QuestExample",\n}\n', encoding="utf-8"
    )
    (scripts / "ResourceData.lua").write_text(
        'ResourceData =\n{\n\tBaseResource =\n\t{\n\t},\n'
        '\tDreamPoints =\n\t{\n\t},\n\tMoney =\n\t{\n\t\tRunResource = true,\n\t},\n}\nResourceDisplayOrderData =\n{\n}\n',
        encoding="utf-8",
    )
    (scripts / "ObjectiveData.lua").write_text(
        'ObjectiveData =\n{\n\tGiftPrompt = {},\n}\n'
        'ObjectiveSetData =\n{\n\tFCastTutorial =\n\t{\n\t\tObjectives =\n'
        '\t\t{\n\t\t\t{\n\t\t\t\t"WeaponCast",\n\t\t\t}\n\t\t},\n\t},\n}\n',
        encoding="utf-8",
    )
    (scripts / "StoryResetData.lua").write_text(
        'StoryResetData =\n{\n  TextLines =\n  {\n    "HecatePostTrueEnding01",\n    -- "CommentedOutLine",\n    "HecatePostEpilogue01",\n    "HecatePostTrueEnding01",\n  },\n}\n',
        encoding="utf-8",
    )
    (scripts / "NPCData_Hecate.lua").write_text(
        'UnitSetData.NPC_Hecate =\n{\n\tNPC_Hecate_01 =\n\t{\n\t},\n'
        '\tNPC_Giftable =\n\t{\n\t},\n}\n',
        encoding="utf-8",
    )
    generated = subprocess.check_output(
        [sys.executable, str(ROOT / "Tools/generate_hades_save_ids.py"),
         str(scripts)], text=True,
    )
    namespace = {}
    exec(compile(generated, "<native-save-identity-catalog>", "exec"), namespace)
    assert namespace["QUEST_IDS"] == frozenset({"QuestExample"})
    assert namespace["RESOURCE_IDS"] == frozenset({"DreamPoints"})
    assert namespace["NPC_INTERACTION_IDS"] == frozenset({"NPC_Hecate_01"})
    assert namespace["OBJECTIVE_IDS"] == frozenset({"GiftPrompt", "WeaponCast"})
    assert namespace["STORY_RESET_TEXT_IDS"] == frozenset({"HecatePostTrueEnding01", "HecatePostEpilogue01"})

print("hades2_save_native_ids_ok")
