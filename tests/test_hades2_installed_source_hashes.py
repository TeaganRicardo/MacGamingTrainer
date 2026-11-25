"""Installed-source trust hashes come from the supported-build snapshot and fail closed.

Portable temporary fixtures only: no installed game, Save or source archive is read.
"""
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
sys.path.insert(0, str(ROOT / "Tools"))

from games.hades2 import config, save_advanced, save_native_ids, save_quest_rewards
from games.hades2.save_investigation import NativeDialogueInvestigation, supported_source_hashes
from supported_build import supported_reference_directory

NAME = "installed_source_hashes.json"
MANIFEST = json.loads((ROOT / "Backend/games/hades2/module.json").read_text(encoding="utf-8"))
SNAPSHOT = supported_reference_directory("hades2") / NAME
OWNERS = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["owners"]
STORY_HASH = OWNERS["storyReset"]["files"]["StoryResetData.lua"]
REWARD_HASHES = OWNERS["questRewardOwners"]["files"]


def expect_value_error(action, label):
    try:
        action()
    except ValueError:
        return
    raise AssertionError("unverifiable installed-source hashes were trusted: " + label)


def game_fixture(base, *, story_reset=True):
    scripts = base / "sources/Scripts"
    scripts.mkdir(parents=True)
    (base / "sources/Text").mkdir()
    files = {
        "QuestData.lua": 'QuestData = {\n  QuestCatchFish = { RewardResourceName = "MetaCurrency", RewardResourceAmount = 7 },\n}\n',
        "ResourceData.lua": "ResourceData = {\n  MetaCurrency = { IgnoreAsLastResourceGained = true },\n}\n",
        "ResourceLogic.lua": "-- reward mutation owner fixture\n",
        "QuestLogLogic.lua": "-- claim owner fixture\n",
    }
    if story_reset:
        files["StoryResetData.lua"] = "StoryResetData = { TextLines = {} }"
    for name, text in files.items():
        (scripts / name).write_text(text, encoding="utf-8")
    return scripts


# The packaged app carries the data only as a declared supportedBuild resource;
# development execution reads the same file from the module-declared snapshot.
declared = [item for item in MANIFEST["appResources"] if item["source"] == "@supportedBuild/" + NAME]
assert len(declared) == 1, declared
assert config.supported_reference_path(NAME) == SNAPSHOT.resolve()
with tempfile.TemporaryDirectory(prefix="mgt-source-hashes-bundle-") as temporary:
    resources = Path(temporary) / "Mac Gaming Trainer.app/Contents/Resources"
    module_file = resources / "Backend/games/hades2/config.py"
    module_file.parent.mkdir(parents=True)
    assert config.supported_reference_path(NAME, module_file) == (
        resources / "Modules" / "hades2" / declared[0]["destination"]
    ).resolve()
try:
    config.supported_reference_path("undeclared_reference.json")
except LookupError:
    pass
else:
    raise AssertionError("an undeclared reference file would be read outside the packaged resource set")

# Production defaults are the snapshot values. Feature consumers carry no
# supported-build digest literal and the generated ID registry no second copy.
assert dict(supported_source_hashes("storyReset")) == {"StoryResetData.lua": STORY_HASH}
assert dict(supported_source_hashes("questRewardOwners")) == REWARD_HASHES
for consumer in ("save_investigation.py", "save_quest_rewards.py"):
    source = (ROOT / "Backend/games/hades2" / consumer).read_text(encoding="utf-8")
    assert not re.search(r"\b[0-9a-f]{64}\b", source), consumer
generated = (ROOT / "Backend/games/hades2/save_native_ids.py").read_text(encoding="utf-8")
assert not hasattr(save_native_ids, "QUEST_REWARD_OWNER_SHA256")
assert STORY_HASH not in generated

with tempfile.TemporaryDirectory(prefix="mgt-source-hashes-game-") as temporary:
    base = Path(temporary)
    scripts = game_fixture(base / "game")
    game_fixture(base / "no-reset", story_reset=False)

    # Default verification is unchanged: an installed StoryResetData.lua that
    # differs from the supported snapshot (or is absent) is not trusted.
    default = NativeDialogueInvestigation(base / "game")
    assert default.expected_hash == STORY_HASH
    assert default.native["status"] == "mismatch" and not default.native["quests"]
    assert default.native["sourceProvenance"]["expectedStoryResetSHA256"] == STORY_HASH
    assert default.native["sourceProvenance"]["storyResetVerification"] == "mismatch"
    missing = NativeDialogueInvestigation(base / "no-reset")
    assert missing.native["status"] == "missing"
    assert missing.native["sourceProvenance"]["storyResetVerification"] == "missing"

    # Quest reward owners: an installed capture differing from the snapshot is
    # refused; the snapshot digests are exactly what authorizes a grant.
    fixture_story = hashlib.sha256((scripts / "StoryResetData.lua").read_bytes()).hexdigest()
    investigation = NativeDialogueInvestigation(base / "game", expected_hash=fixture_story)
    assert investigation.native["status"] == "available"
    try:
        save_quest_rewards._reward(None, "QuestCatchFish", investigation)
    except save_advanced.AdvancedMutationError as error:
        assert "verified source capture" in str(error)
    else:
        raise AssertionError("unverified quest reward owners authorized a grant")
    verified = dict(investigation.native, scriptHashes={**investigation.native["scriptHashes"], **REWARD_HASHES})
    evidence = save_quest_rewards._reward(None, "QuestCatchFish", investigation, native=verified)
    assert (evidence["resource"], evidence["amount"], evidence["ignoreLast"]) == ("MetaCurrency", 7, True)

    # Each mutation owner is required, even if every declared hash matches.
    for omitted in ("QuestLogLogic.lua", "ResourceData.lua", "ResourceLogic.lua"):
        assert omitted in REWARD_HASHES
        incomplete = {name: digest for name, digest in REWARD_HASHES.items() if name != omitted}
        path = base / ("omitted-" + omitted + ".json")
        path.write_text(json.dumps({"owners": {"storyReset": OWNERS["storyReset"],
                                               "questRewardOwners": {"files": incomplete}}}), encoding="utf-8")
        captured = dict(verified, scriptHashes={name: digest for name, digest in verified["scriptHashes"].items()
                                                 if name != omitted})
        with patch.object(config, "supported_reference_path", lambda name, *args, _path=path: _path):
            try:
                save_quest_rewards._reward(None, "QuestCatchFish", investigation, native=captured)
            except save_advanced.AdvancedMutationError as error:
                assert "incomplete supported-build source hashes" in str(error)
            else:
                raise AssertionError("quest reward granted without required owner " + omitted)

    # Missing, malformed, empty or incomplete reference data never widens trust:
    # the investigation refuses to start and a reward grant is refused.
    invalid = {
        "missing": None,
        "malformed": "{not json",
        "no owners": json.dumps({"owners": {}}),
        "empty files": json.dumps({"owners": {"storyReset": {"files": {}}, "questRewardOwners": {"files": {}}}}),
        "bad digest": json.dumps({"owners": {"storyReset": {"files": {"StoryResetData.lua": "F" * 64}},
                                             "questRewardOwners": {"files": {"ResourceLogic.lua": "0" * 63}}}}),
        "absent owner": json.dumps({"owners": {"other": {"files": {"Other.lua": "0" * 64}}}}),
        "path in file name": json.dumps({"owners": {"storyReset": {"files": {"../StoryResetData.lua": "0" * 64}},
                                                    "questRewardOwners": {"files": {"ResourceLogic.lua": "0" * 64}}}}),
    }
    for label, text in invalid.items():
        path = base / ("invalid-" + label.replace(" ", "-") + ".json")
        if text is not None:
            path.write_text(text, encoding="utf-8")
        with patch.object(config, "supported_reference_path", lambda name, *args, _path=path: _path):
            expect_value_error(lambda: supported_source_hashes("questRewardOwners"), label)
            expect_value_error(lambda: NativeDialogueInvestigation(base / "game"), label + " (investigation)")
            try:
                save_quest_rewards._reward(None, "QuestCatchFish", investigation, native=verified)
            except save_advanced.AdvancedMutationError:
                pass
            else:
                raise AssertionError("quest reward granted without verified owner hashes: " + label)

print("hades2_installed_source_hashes_ok")
