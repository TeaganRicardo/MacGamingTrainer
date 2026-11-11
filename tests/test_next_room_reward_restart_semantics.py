"""Regression contract: Hades II reward overrides are live one-shots.

An old persisted reward must never be re-armed by restart, Profile load,
reconciliation or an unknown-outcome transport failure.
"""
import copy
import json
import sys
import tempfile
from pathlib import Path

from runtime_revision_support import runtime_revision

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
sys.path.insert(0, str(ROOT / "tests"))

from core.adapter import AdapterError
from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter
from games.hades2.preferences import (
    DESIRED_STATE_SCHEMA_VERSION,
    Hades2PreferenceStore,
    normalize_persisted_desired,
)
from games.hades2.profile_service import Hades2ProfileService
from games.hades2.schema import MULTIPLIERS, TOGGLES, default_boon_rarity
from hades2_resident_session_fakes import FakeResidentSession, FakeTimeWarpController

assert DESIRED_STATE_SCHEMA_VERSION == 12
for old_version in (3, 4, 11, 12):
    legacy = {
        "schemaVersion": old_version,
        "nextRoomReward": "WeaponUpgrade",
        "nextRoomRewardToken": "legacy-pending-token",
        "nextOccurrenceTarget": "npc:Nemesis",
        "nextOccurrenceToken": "occurrence-token",
    }
    normalized = normalize_persisted_desired(legacy, old_version)
    assert "nextRoomReward" not in normalized, old_version
    assert "nextRoomRewardToken" not in normalized, old_version
    assert "nextOccurrenceTarget" not in normalized, old_version
    assert "nextOccurrenceToken" not in normalized, old_version

lua = (ROOT / "Backend/games/hades2/runtime/hades.lua").read_text()
assert runtime_revision(lua) >= 42
assert "M.nextRoomRewardToken == rewardToken" in lua
assert "M.lastConsumedNextRoomRewardToken = rewardToken" in lua
assert "M.nextRoomReward = nil" in lua
assert "M.nextRoomRewardToken = nil" in lua
assert "params.token" in lua


def status_payload(reward=None, token=None, consumed_token=None):
    defaults = Hades2PreferenceStore.defaults()
    payload = {
        "status": "ready",
        "scene": "run",
        "capabilities": {"setFeature": True},
        "desiredFeatures": {key: bool(defaults[key]) for key in TOGGLES},
        "activeFeatures": {key: False for key in TOGGLES},
        "dormantFeatures": {},
        "featureErrors": {},
        "boonRarity": default_boon_rarity(),
        "gatheringProbabilities": {},
        "chaosGateProbability": None,
        "stats": {},
        "resources": [],
        "elements": [],
        "healthLocked": False,
        "manaLocked": False,
        "armorLocked": False,
        "moneyLocked": False,
        "rerollsLocked": False,
        "nextRoomReward": reward,
        "nextOccurrenceTarget": None,
        "runtimeDiagnostics": {
            "nextRoomRewardToken": token,
            "lastConsumedNextRoomRewardToken": consumed_token,
        },
    }
    for key in MULTIPLIERS:
        if key != "gameSpeed":
            payload[key] = defaults[key]
    return payload


def handle_reward(resident, record):
    if record["kind"] == "reconcile":
        assert all(command != "set_next_room_reward" for command, _ in record["batch"]), (
            "a runtime one-shot leaked into desired replay"
        )
    if record["kind"] == "mutate" and record["command"] == "set_next_room_reward":
        reward = record["params"]["reward"]
        token = record["params"]["token"]
        assert token is None or isinstance(token, str) and token.startswith("one-shot-")
        resident.payload["nextRoomReward"] = reward
        resident.payload["runtimeDiagnostics"]["nextRoomRewardToken"] = token
    return copy.deepcopy(resident.payload)


old_data = preparation.DATA
try:
    preparation.DATA = Path(tempfile.mkdtemp(prefix="mgt-next-room-one-shot-"))
    path = preparation.DATA / "desired-state.json"
    path.write_text(json.dumps({
        "schemaVersion": 11,
        "nextRoomReward": "WeaponUpgrade",
        "nextRoomRewardToken": "stale-durable-reward",
    }), encoding="utf-8")

    resident = FakeResidentSession(status_payload(), handler=handle_reward, pid=4242)
    adapter = Hades2Adapter(
        resident_session=resident, time_warp_controller=FakeTimeWarpController()
    )
    assert adapter.preference_initialized
    assert "nextRoomReward" not in adapter.preferences
    assert "nextRoomRewardToken" not in adapter.preferences
    adapter.state.update(connected=True, pid=4242, capabilities={"setFeature": True})

    # Status and forced durable-state reconciliation must never re-arm
    # the retired reward, regardless of the old on-disk desired state.
    observed = adapter.execute("status", {})
    assert observed["nextRoomReward"] is None
    assert not any(call["command"] == "set_next_room_reward" for call in resident.calls)
    assert not any(
        command == "set_next_room_reward"
        for call in resident.calls if call["kind"] == "reconcile"
        for command, params in call["batch"]
    )

    # Explicit live commands arm the native owner once and keep the
    # selected reward out of the durable preferences and Profile schema.
    adapter.preference_dirty = False
    armed = adapter.dispatch("set_next_room_reward_once", {"reward": "WeaponUpgrade"}, "request-1")
    assert armed["nextRoomReward"] == "WeaponUpgrade"
    mutate_calls = [call for call in resident.calls if call["kind"] == "mutate"]
    assert len(mutate_calls) == 1
    first_token = mutate_calls[-1]["params"]["token"]
    assert "nextRoomReward" not in adapter.preferences
    assert "nextRoomRewardToken" not in adapter.preferences
    adapter.preference_store.save(dict(adapter.preferences, nextRoomReward="WeaponUpgrade",
                                       nextRoomRewardToken="unwanted-legacy-value"))
    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted["schemaVersion"] == 12
    assert "nextRoomReward" not in persisted and "nextRoomRewardToken" not in persisted

    # A duplicate Host request retains one native action identity; a new
    # deliberate request creates a new token.
    adapter.set_next_room_reward_once("WeaponUpgrade", "request-1")
    assert resident.calls[-1]["params"]["token"] == first_token
    adapter.set_next_room_reward_once("WeaponUpgrade", "request-2")
    assert resident.calls[-1]["params"]["token"] != first_token

    # Native room-start consumption is observed without making Host state
    # replayable. A later status/worker restart must stay disarmed.
    resident.payload["nextRoomReward"] = None
    resident.payload["runtimeDiagnostics"]["lastConsumedNextRoomRewardToken"] = (
        resident.payload["runtimeDiagnostics"]["nextRoomRewardToken"]
    )
    resident.payload["runtimeDiagnostics"]["nextRoomRewardToken"] = None
    state = adapter.execute("status", {})
    assert state["nextRoomReward"] is None
    assert "nextRoomReward" not in adapter.preferences

    adapter.set_next_room_reward_once("MaxHealthDrop", "request-3")
    adapter.set_next_room_reward_once(None, "cancel-request-1")
    assert resident.payload["nextRoomReward"] is None
    assert resident.payload["runtimeDiagnostics"]["nextRoomRewardToken"] is None

    # Historical Profiles and newly saved Profiles both omit the retired fields.
    profile_service = Hades2ProfileService(preparation.DATA / "profiles")
    profile_service.save("current", dict(adapter.preferences, nextRoomReward="MaxHealthDrop"))
    assert "nextRoomReward" not in profile_service.load("current")["desired"]
    legacy_profile = profile_service.path("legacy")
    legacy_profile.write_text(json.dumps({
        "schemaVersion": 6, "desiredSchemaVersion": 11,
        "name": "legacy", "updatedAt": "2026-11-09T00:00:00Z",
        "desired": dict(Hades2PreferenceStore.defaults(),
                        nextRoomReward="WeaponUpgrade", nextRoomRewardToken="old"),
    }), encoding="utf-8")
    assert "nextRoomReward" not in profile_service.load("legacy")["desired"]
    adapter.load_profile("legacy")
    assert not any(
        command == "set_next_room_reward"
        for call in resident.calls if call["kind"] == "reconcile"
        for command, params in call["batch"]
    )

    # Reconstructed backend against the same resident must not re-arm a
    # vanished one-shot or reinterpret the legacy token as new intent.
    restarted = Hades2Adapter(
        resident_session=resident, time_warp_controller=FakeTimeWarpController()
    )
    restarted.state.update(connected=True, pid=4242, capabilities={"setFeature": True})
    restarted.execute("status", {})
    assert resident.payload["nextRoomReward"] is None
    assert "nextRoomReward" not in restarted.preferences

    # On a transport unknown outcome, no durable state is installed and
    # later process/status observations can only read the resident.
    def unknown_handler(session, record):
        if record["command"] == "set_next_room_reward":
            return AdapterError("outcome_unknown", "uncertain one-shot")
        return handle_reward(session, record)

    resident.handler = unknown_handler
    try:
        restarted.set_next_room_reward_once("WeaponUpgrade", "unknown-request")
    except AdapterError as error:
        assert error.code == "outcome_unknown"
    else:
        raise AssertionError("one-shot transport ambiguity was treated as success")
    assert "nextRoomReward" not in restarted.preferences
    resident.handler = handle_reward
    restarted.execute("status", {})
    assert resident.payload["nextRoomReward"] is None
finally:
    preparation.DATA = old_data

print("next_room_reward_one_shot_semantics_ok")
