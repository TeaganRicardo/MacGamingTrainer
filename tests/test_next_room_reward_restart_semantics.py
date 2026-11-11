"""Retired Hades II global next-room intent cannot survive or be re-armed."""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2 import preparation
from games.hades2.command_contract import command_metadata
from games.hades2.preferences import (
    DESIRED_STATE_SCHEMA_VERSION,
    Hades2PreferenceStore,
    normalize_persisted_desired,
)
from games.hades2.profile_service import Hades2ProfileService
from runtime_revision_support import runtime_revision

assert DESIRED_STATE_SCHEMA_VERSION == 12
for old_version in (3, 4, 11, 12):
    normalized = normalize_persisted_desired(
        {
            "schemaVersion": old_version,
            "nextRoomReward": "WeaponUpgrade",
            "nextRoomRewardToken": "legacy-pending-token",
            "nextOccurrenceTarget": "npc:Nemesis",
            "nextOccurrenceToken": "occurrence-token",
        },
        old_version,
    )
    for key in (
        "nextRoomReward", "nextRoomRewardToken",
        "nextOccurrenceTarget", "nextOccurrenceToken",
    ):
        assert key not in normalized, (old_version, key, normalized)

lua = (ROOT / "Backend/games/hades2/runtime/hades.lua").read_text(encoding="utf-8")
assert runtime_revision(lua) >= 127
assert 'command == "set_next_room_reward"' not in lua
assert "M.nextRoomReward" not in lua
assert "nextRoomRewardToken" not in lua
assert 'command == "apply_world_exit"' in lua
assert 'command == "cancel_world_exit"' in lua

commands = {row["name"] for row in command_metadata()}
assert "set_next_room_reward_desired" not in commands
assert "set_next_room_reward_once" not in commands
assert {"apply_world_exit", "cancel_world_exit"} <= commands

old_data = preparation.DATA
try:
    preparation.DATA = Path(tempfile.mkdtemp(prefix="mgt-retired-next-room-"))
    store = Hades2PreferenceStore(preparation.DATA / "desired-state.json")
    store.save(dict(
        Hades2PreferenceStore.defaults(),
        nextRoomReward="WeaponUpgrade",
        nextRoomRewardToken="must-drop",
    ))
    persisted = json.loads((preparation.DATA / "desired-state.json").read_text(encoding="utf-8"))
    assert persisted["schemaVersion"] == 12
    assert "nextRoomReward" not in persisted
    assert "nextRoomRewardToken" not in persisted

    profiles = Hades2ProfileService(preparation.DATA / "profiles")
    profiles.save(
        "current",
        dict(
            Hades2PreferenceStore.defaults(),
            nextRoomReward="MaxHealthDrop",
            nextRoomRewardToken="must-drop-profile",
        ),
    )
    desired = profiles.load("current")["desired"]
    assert "nextRoomReward" not in desired
    assert "nextRoomRewardToken" not in desired

    legacy_profile = profiles.path("legacy")
    legacy_profile.write_text(json.dumps({
        "schemaVersion": 6,
        "desiredSchemaVersion": 11,
        "name": "legacy",
        "updatedAt": "2026-11-09T00:00:00Z",
        "desired": dict(
            Hades2PreferenceStore.defaults(),
            nextRoomReward="WeaponUpgrade",
            nextRoomRewardToken="old",
        ),
    }), encoding="utf-8")
    legacy = profiles.load("legacy")["desired"]
    assert "nextRoomReward" not in legacy
    assert "nextRoomRewardToken" not in legacy
finally:
    preparation.DATA = old_data

print("next_room_reward_retired_semantics_ok")
