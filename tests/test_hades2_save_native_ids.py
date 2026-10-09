"""The pinned native Save identity generator must remain executable/reproducible."""

import hashlib
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
        'StoryResetData =\n{\n  TextLines =\n  {\n    "HecatePostTrueEnding01",\n    -- "CommentedOutLine",\n    --[=[\n    "BlockCommentedLine",\n    ]=]\n    "HecatePostEpilogue01", -- active native line\n    "HecatePostTrueEnding01",\n  },\n  Unrelated =\n  {\n    "NotAResetTarget",\n  },\n}\n',
        encoding="utf-8",
    )
    (scripts / "NPCData_Hecate.lua").write_text(
        'UnitSetData.NPC_Hecate =\n{\n\tNPC_Hecate_01 =\n\t{\n\t},\n'
        '\tNPC_Giftable =\n\t{\n\t},\n}\n',
        encoding="utf-8",
    )
    native_sources = {path: path.read_bytes() for path in scripts.glob("*.lua")}
    expected = {
        "QUEST_IDS": frozenset({"QuestExample"}),
        "RESOURCE_IDS": frozenset({"DreamPoints"}),
        "NPC_INTERACTION_IDS": frozenset({"NPC_Hecate_01"}),
        "OBJECTIVE_IDS": frozenset({"GiftPrompt", "WeaponCast"}),
        "STORY_RESET_TEXT_IDS": frozenset({"HecatePostTrueEnding01", "HecatePostEpilogue01"}),
    }
    # The shipped native scripts have CRLF line endings. Every family must
    # regenerate identically from LF, CRLF and CR inputs, with raw-byte hashes.
    for newline in (b"\n", b"\r\n", b"\r"):
        for path, original in native_sources.items():
            path.write_bytes(original.replace(b"\n", newline))
        generated = subprocess.check_output(
            [sys.executable, str(ROOT / "Tools/generate_hades_save_ids.py"),
             str(scripts)], text=True,
        )
        namespace = {}
        exec(compile(generated, "<native-save-identity-catalog>", "exec"), namespace)
        for name, ids in expected.items():
            assert namespace[name] == ids, (name, newline)
        for name in ("QuestData.lua", "ResourceData.lua", "ObjectiveData.lua", "StoryResetData.lua"):
            raw_sha = hashlib.sha256((scripts / name).read_bytes()).hexdigest()
            assert f"{name} SHA-256 {raw_sha}" in generated, (name, newline)

print("hades2_save_native_ids_ok")
