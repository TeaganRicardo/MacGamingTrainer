import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
sys.path.insert(0, str(ROOT / "tests"))

from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter
from games.hades2.preferences import Hades2PreferenceStore, next_occurrence_consumed
from games.hades2.resident_session import ResidentMetrics, ResidentReply
from games.hades2.schema import MULTIPLIERS, TOGGLES, default_boon_rarity
from hades2_resident_session_fakes import FakeResidentSession, FakeTimeWarpController


def status_payload(*, target=None, token=None, consumed_token=None):
    defaults = Hades2PreferenceStore.defaults()
    payload = {
        "status": "ready",
        "scene": "run",
        "capabilities": {},
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


preferences = Hades2PreferenceStore.defaults()
preferences["nextOccurrenceTarget"] = "npc:Nemesis"
preferences["nextOccurrenceToken"] = "occurrence-token"

consumed = status_payload(target=None, consumed_token="occurrence-token")
assert next_occurrence_consumed(
    preferences, consumed, preference_dirty=True
) is True

not_delivered = status_payload(target=None, consumed_token=None)
assert next_occurrence_consumed(
    preferences, not_delivered, preference_dirty=True
) is False
assert next_occurrence_consumed(
    preferences, not_delivered, preference_dirty=False
) is True

sparse = status_payload(target=None, consumed_token=None)
sparse.pop("nextOccurrenceTarget")
assert next_occurrence_consumed(preferences, sparse, preference_dirty=False) is False
assert next_occurrence_consumed(preferences, sparse, preference_dirty=True) is False


class OccurrenceSession(FakeResidentSession):
    def __init__(self, payload):
        super().__init__(payload, pid=4242)
        self.state = self.payload

    def status(self, params=None):
        self.calls.append({
            "kind": "status",
            "command": "status",
            "params": dict(params or {}),
            "batch": None,
        })
        return ResidentReply(
            payload=json.loads(json.dumps(self.state)),
            metrics=ResidentMetrics(boundary_duration=0.001),
        )

    def reconcile(self, calls):
        calls = list(calls)
        self.calls.append({
            "kind": "reconcile",
            "command": "replay_preferences",
            "params": {},
            "batch": json.loads(json.dumps(calls)),
        })
        for command, params in calls:
            if command != "set_next_occurrence":
                raise AssertionError(
                    "unexpected reconciliation during occurrence test: " + command
                )
            self.state["nextOccurrenceTarget"] = params.get("target")
            diagnostics = self.state.setdefault("runtimeDiagnostics", {})
            if params.get("target") is None:
                diagnostics.pop("nextOccurrenceToken", None)
            else:
                diagnostics["nextOccurrenceToken"] = params.get("token")
        return ResidentReply(
            payload=json.loads(json.dumps(self.state)),
            metrics=ResidentMetrics(boundary_duration=0.001),
        )


old_data = preparation.DATA
try:
    preparation.DATA = Path(tempfile.mkdtemp(prefix="mgt-occurrence-consumed-"))
    consumed_session = OccurrenceSession(
        status_payload(target=None, consumed_token="occurrence-token")
    )
    consumed_adapter = Hades2Adapter(
        resident_session=consumed_session,
        time_warp_controller=FakeTimeWarpController(),
    )
    consumed_adapter.preferences = consumed_adapter._default_preferences()
    consumed_adapter.preferences["nextOccurrenceTarget"] = "npc:Nemesis"
    consumed_adapter.preferences["nextOccurrenceToken"] = "occurrence-token"
    consumed_adapter.preference_store.save(consumed_adapter.preferences)
    consumed_adapter.preference_initialized = True
    consumed_adapter.preference_dirty = True

    state = consumed_adapter.execute("status", {})
    assert consumed_adapter.preferences["nextOccurrenceTarget"] is None
    assert consumed_adapter.preferences["nextOccurrenceToken"] is None
    assert state["nextOccurrenceTarget"] is None
    assert [call["kind"] for call in consumed_session.calls] == ["status"]
    persisted = json.loads(
        (preparation.DATA / "desired-state.json").read_text(encoding="utf-8")
    )
    assert persisted["nextOccurrenceTarget"] is None
    assert persisted["nextOccurrenceToken"] is None

    preparation.DATA = Path(tempfile.mkdtemp(prefix="mgt-occurrence-redeliver-"))
    pending_session = OccurrenceSession(
        status_payload(target=None, consumed_token=None)
    )
    pending_adapter = Hades2Adapter(
        resident_session=pending_session,
        time_warp_controller=FakeTimeWarpController(),
    )
    pending_adapter.preferences = pending_adapter._default_preferences()
    pending_adapter.preferences["nextOccurrenceTarget"] = "npc:Nemesis"
    pending_adapter.preferences["nextOccurrenceToken"] = "occurrence-token"
    pending_adapter.preference_store.save(pending_adapter.preferences)
    pending_adapter.preference_initialized = True
    pending_adapter.preference_dirty = True

    state = pending_adapter.execute("status", {})
    assert [call["kind"] for call in pending_session.calls] == [
        "status",
        "reconcile",
    ]
    occurrence_calls = [
        params
        for command, params in pending_session.calls[-1]["batch"]
        if command == "set_next_occurrence"
    ]
    assert occurrence_calls == [
        {"target": "npc:Nemesis", "token": "occurrence-token"}
    ]
    assert pending_adapter.preferences["nextOccurrenceTarget"] == "npc:Nemesis"
    assert pending_adapter.preferences["nextOccurrenceToken"] == "occurrence-token"
    assert state["nextOccurrenceTarget"] == "npc:Nemesis"

    preparation.DATA = Path(tempfile.mkdtemp(prefix="mgt-occurrence-arm-"))
    armed_session = OccurrenceSession(status_payload())
    armed_adapter = Hades2Adapter(
        resident_session=armed_session,
        time_warp_controller=FakeTimeWarpController(),
    )
    armed_adapter.state.update(status="ready", scene="run")
    result = armed_adapter.set_next_occurrence_desired("npc:Nemesis")
    token = armed_adapter.preferences["nextOccurrenceToken"]
    assert isinstance(token, str) and token.startswith("next-occurrence-")
    mutate = [
        call for call in armed_session.calls
        if call["kind"] == "mutate" and call["command"] == "set_next_occurrence"
    ]
    assert len(mutate) == 1
    assert mutate[0]["params"] == {
        "target": "npc:Nemesis",
        "token": token,
    }
    persisted = json.loads(
        (preparation.DATA / "desired-state.json").read_text(encoding="utf-8")
    )
    assert persisted["nextOccurrenceTarget"] == "npc:Nemesis"
    assert persisted["nextOccurrenceToken"] == token
    assert result["nextOccurrenceTarget"] == "npc:Nemesis"

    armed_adapter.save_profile("Occurrence")
    saved_token = armed_adapter.preferences["nextOccurrenceToken"]
    armed_adapter.set_next_occurrence_desired("npc:Echo")
    assert armed_adapter.preferences["nextOccurrenceToken"] != saved_token
    armed_adapter.state["connected"] = False
    loaded = armed_adapter.load_profile("Occurrence")
    loaded_token = armed_adapter.preferences["nextOccurrenceToken"]
    assert loaded["nextOccurrenceTarget"] == "npc:Nemesis"
    assert isinstance(loaded_token, str) and loaded_token.startswith("profile-occurrence-")
    assert loaded_token != saved_token
finally:
    preparation.DATA = old_data

print("hades2_occurrence_restart_semantics_ok")
