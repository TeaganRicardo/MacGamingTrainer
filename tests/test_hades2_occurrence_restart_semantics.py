"""Named occurrence World Actions survive only as live resident leases."""
import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
sys.path.insert(0, str(ROOT / "tests"))

from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter
from games.hades2.command_contract import command_metadata
from games.hades2.preferences import Hades2PreferenceStore
from games.hades2.profile_service import Hades2ProfileService
from games.hades2.schema import MULTIPLIERS, TOGGLES, default_boon_rarity
from hades2_resident_session_fakes import FakeResidentSession, FakeTimeWarpController


def status_payload(occurrence=None):
    defaults = Hades2PreferenceStore.defaults()
    payload = {
        "status": "ready",
        "scene": "run",
        "capabilities": {"setFeature": True, "worldActions": True},
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
        "worldActions": {"exits": [], **({"occurrence": occurrence} if occurrence else {})},
        "runtimeDiagnostics": {},
    }
    for key in MULTIPLIERS:
        if key != "gameSpeed":
            payload[key] = defaults[key]
    return payload


def handle_occurrence(resident, record):
    if record["kind"] == "reconcile":
        assert all(
            command not in ("apply_world_occurrence", "cancel_world_occurrence")
            for command, _ in record["batch"]
        ), "a World Action leaked into durable desired replay"
    if record["kind"] == "mutate" and record["command"] == "apply_world_occurrence":
        resident.payload["worldActions"]["occurrence"] = {
            "target": record["params"]["target"],
            "leaseToken": record["params"]["requestId"],
        }
    if record["kind"] == "mutate" and record["command"] == "cancel_world_occurrence":
        resident.payload["worldActions"].pop("occurrence", None)
    return copy.deepcopy(resident.payload)


old_data = preparation.DATA
try:
    preparation.DATA = Path(tempfile.mkdtemp(prefix="mgt-occurrence-world-action-"))
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
    adapter.state.update(
        connected=True, pid=4242,
        capabilities={"setFeature": True, "worldActions": True},
    )

    observed = adapter.execute("status", {})
    assert observed["worldActions"] == {"exits": []}
    assert not any(
        command in ("apply_world_occurrence", "cancel_world_occurrence")
        for call in resident.calls if call["kind"] == "reconcile"
        for command, params in call["batch"]
    )

    armed = adapter.dispatch(
        "apply_world_occurrence", {"target": "npc:Nemesis"}, "occurrence-1"
    )
    assert armed["worldActions"]["occurrence"] == {
        "target": "npc:Nemesis",
        "leaseToken": "occurrence-1",
    }
    assert "nextOccurrenceTarget" not in adapter.preferences
    assert "nextOccurrenceToken" not in adapter.preferences

    # A reconstructed Host observes the resident lease; it does not recreate it
    # from Preferences or Profile data.
    restarted = Hades2Adapter(
        resident_session=resident, time_warp_controller=FakeTimeWarpController()
    )
    restarted.state.update(
        connected=True, pid=4242,
        capabilities={"setFeature": True, "worldActions": True},
    )
    restarted_state = restarted.execute("status", {})
    assert restarted_state["worldActions"]["occurrence"]["leaseToken"] == "occurrence-1"
    assert "nextOccurrenceTarget" not in restarted.preferences

    # Simulate the native matching StartRoom/RecordEncounter consuming the lease.
    resident.payload["worldActions"].pop("occurrence", None)
    restarted.execute("status", {})
    assert "occurrence" not in resident.payload["worldActions"]

    # Persistence and Profile boundaries defensively strip retired fields, and a
    # Profile load cannot synthesize a new World Action after native consumption.
    restarted.preference_store.save(dict(
        restarted.preferences,
        nextOccurrenceTarget="npc:Nemesis",
        nextOccurrenceToken="should-drop",
    ))
    persisted = json.loads(desired_path.read_text(encoding="utf-8"))
    assert persisted["schemaVersion"] == 12
    assert "nextOccurrenceTarget" not in persisted
    assert "nextOccurrenceToken" not in persisted

    profiles = Hades2ProfileService(preparation.DATA / "profiles")
    profiles.save("current", dict(
        restarted.preferences,
        nextOccurrenceTarget="npc:Nemesis",
        nextOccurrenceToken="profile-legacy",
    ))
    assert "nextOccurrenceTarget" not in profiles.load("current")["desired"]
    before = len(resident.calls)
    restarted.load_profile("current")
    replay_calls = resident.calls[before:]
    assert not any(
        command in ("apply_world_occurrence", "cancel_world_occurrence")
        for call in replay_calls if call["kind"] == "reconcile"
        for command, params in call["batch"]
    )
    restarted.execute("status", {})
    assert "occurrence" not in resident.payload["worldActions"]

    # Explicit cancel is likewise a live action, not a durable state rewrite.
    restarted.dispatch(
        "apply_world_occurrence", {"target": "npc:Echo"}, "occurrence-2"
    )
    restarted.dispatch(
        "cancel_world_occurrence", {"leaseToken": "occurrence-2"}, "occurrence-cancel"
    )
    assert "occurrence" not in resident.payload["worldActions"]
    assert "nextOccurrenceTarget" not in restarted.preferences
finally:
    preparation.DATA = old_data

commands = {row["name"] for row in command_metadata()}
assert {"apply_world_occurrence", "cancel_world_occurrence"} <= commands
assert "set_next_occurrence_once" not in commands
assert "set_next_occurrence_desired" not in commands

runtime = (ROOT / "Backend/games/hades2/runtime/hades.lua").read_text(encoding="utf-8")
assert 'command == "set_next_occurrence"' not in runtime
assert 'command == "apply_world_occurrence"' in runtime
assert 'command == "cancel_world_occurrence"' in runtime

print("hades2_occurrence_world_action_restart_semantics_ok")
