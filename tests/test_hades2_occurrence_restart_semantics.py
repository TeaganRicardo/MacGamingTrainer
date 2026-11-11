"""Regression contract: Hades II named occurrences are live one-shots."""
import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
sys.path.insert(0, str(ROOT / "tests"))

from core.adapter import AdapterError
from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter
from games.hades2.preferences import Hades2PreferenceStore
from games.hades2.profile_service import Hades2ProfileService
from games.hades2.schema import MULTIPLIERS, TOGGLES, default_boon_rarity
from hades2_resident_session_fakes import FakeResidentSession, FakeTimeWarpController


def status_payload(target=None, token=None, consumed_token=None):
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
        "nextRoomReward": None,
        "nextOccurrenceTarget": target,
        "runtimeDiagnostics": {
            "nextOccurrenceToken": token,
            "lastConsumedNextOccurrenceToken": consumed_token,
        },
    }
    for key in MULTIPLIERS:
        if key != "gameSpeed":
            payload[key] = defaults[key]
    return payload


def handle_occurrence(resident, record):
    if record["kind"] == "reconcile":
        assert all(command != "set_next_occurrence" for command, _ in record["batch"]), (
            "a runtime occurrence leaked into desired replay"
        )
    if record["kind"] == "mutate" and record["command"] == "set_next_occurrence":
        target = record["params"]["target"]
        token = record["params"]["token"]
        assert token is None or isinstance(token, str) and token.startswith("one-shot-")
        resident.payload["nextOccurrenceTarget"] = target
        resident.payload["runtimeDiagnostics"]["nextOccurrenceToken"] = token
    return copy.deepcopy(resident.payload)


old_data = preparation.DATA
try:
    preparation.DATA = Path(tempfile.mkdtemp(prefix="mgt-occurrence-one-shot-"))
    desired_path = preparation.DATA / "desired-state.json"
    desired_path.write_text(json.dumps({
        "schemaVersion": 11,
        "nextOccurrenceTarget": "npc:Nemesis",
        "nextOccurrenceToken": "stale-occurrence",
    }), encoding="utf-8")

    resident = FakeResidentSession(status_payload(), handler=handle_occurrence, pid=4242)
    adapter = Hades2Adapter(
        resident_session=resident, time_warp_controller=FakeTimeWarpController()
    )
    assert adapter.preference_initialized
    assert "nextOccurrenceTarget" not in adapter.preferences
    assert "nextOccurrenceToken" not in adapter.preferences
    adapter.state.update(connected=True, pid=4242, capabilities={"setFeature": True})

    observed = adapter.execute("status", {})
    assert observed["nextOccurrenceTarget"] is None
    assert not any(
        command == "set_next_occurrence"
        for call in resident.calls if call["kind"] == "reconcile"
        for command, params in call["batch"]
    )

    armed = adapter.dispatch(
        "set_next_occurrence_once", {"target": "npc:Nemesis"}, "occurrence-1"
    )
    assert armed["nextOccurrenceTarget"] == "npc:Nemesis"
    mutate = [call for call in resident.calls if call["kind"] == "mutate"]
    first_token = mutate[-1]["params"]["token"]
    assert first_token.startswith("one-shot-")
    assert "nextOccurrenceTarget" not in adapter.preferences
    assert "nextOccurrenceToken" not in adapter.preferences

    adapter.set_next_occurrence_once("npc:Nemesis", "occurrence-1")
    assert resident.calls[-1]["params"]["token"] == first_token
    adapter.set_next_occurrence_once("npc:Nemesis", "occurrence-2")
    assert resident.calls[-1]["params"]["token"] != first_token

    resident.payload["nextOccurrenceTarget"] = None
    resident.payload["runtimeDiagnostics"]["lastConsumedNextOccurrenceToken"] = (
        resident.payload["runtimeDiagnostics"]["nextOccurrenceToken"]
    )
    resident.payload["runtimeDiagnostics"]["nextOccurrenceToken"] = None
    state = adapter.execute("status", {})
    assert state["nextOccurrenceTarget"] is None
    assert "nextOccurrenceTarget" not in adapter.preferences

    adapter.set_next_occurrence_once("npc:Echo", "occurrence-3")
    adapter.set_next_occurrence_once(None, "occurrence-cancel")
    assert resident.payload["nextOccurrenceTarget"] is None
    assert resident.payload["runtimeDiagnostics"]["nextOccurrenceToken"] is None

    # Persistence and Profile boundaries defensively strip retired fields.
    adapter.preference_store.save(dict(
        adapter.preferences,
        nextOccurrenceTarget="npc:Nemesis",
        nextOccurrenceToken="should-drop",
    ))
    persisted = json.loads(desired_path.read_text(encoding="utf-8"))
    assert persisted["schemaVersion"] == 12
    assert "nextOccurrenceTarget" not in persisted
    assert "nextOccurrenceToken" not in persisted

    profiles = Hades2ProfileService(preparation.DATA / "profiles")
    profiles.save("current", dict(adapter.preferences, nextOccurrenceTarget="npc:Nemesis"))
    assert "nextOccurrenceTarget" not in profiles.load("current")["desired"]
    adapter.load_profile("current")
    assert not any(
        command == "set_next_occurrence"
        for call in resident.calls if call["kind"] == "reconcile"
        for command, params in call["batch"]
    )

    restarted = Hades2Adapter(
        resident_session=resident, time_warp_controller=FakeTimeWarpController()
    )
    restarted.state.update(connected=True, pid=4242, capabilities={"setFeature": True})
    restarted.execute("status", {})
    assert resident.payload["nextOccurrenceTarget"] is None
    assert "nextOccurrenceTarget" not in restarted.preferences

    def unknown_handler(session, record):
        if record["command"] == "set_next_occurrence":
            return AdapterError("outcome_unknown", "uncertain occurrence")
        return handle_occurrence(session, record)

    resident.handler = unknown_handler
    try:
        restarted.set_next_occurrence_once("npc:Nemesis", "unknown-occurrence")
    except AdapterError as error:
        assert error.code == "outcome_unknown"
    else:
        raise AssertionError("uncertain occurrence was treated as success")
    assert "nextOccurrenceTarget" not in restarted.preferences
finally:
    preparation.DATA = old_data

print("hades2_occurrence_one_shot_semantics_ok")
