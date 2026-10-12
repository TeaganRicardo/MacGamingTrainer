import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
sys.path.insert(0, str(ROOT / "tests"))

from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter
from hades2_resident_session_fakes import FakeResidentSession, FakeTimeWarpController


# Regression: the resident is attached and compatible in Hero-less Crossroads,
# but its aggregate combat 'ready' predicate is false. Stored session intent
# must replay without trying to write the missing Hero's stats/vitals or a
# future-room one-shot in that scene.
with tempfile.TemporaryDirectory(prefix="mgt-scene-owner-replay-") as temporary:
    preparation.DATA = Path(temporary)
    waiting = {
        "status": "waiting",
        "scene": "crossroads",
        "capabilities": {
            "setFeature": True,
            "setHealth": False,
            "setMana": False,
            "setArmor": False,
            "setResource": True,
            "setRerolls": False,
            "setSpellCharge": False,
            "setStats": True,
            "setElements": False,
        },
        "statAvailable": {"moveSpeed": False},
        "desiredFeatures": {},
        "activeFeatures": {},
        "dormantFeatures": {},
        "featureErrors": {},
        "stats": {},
        "resources": [],
        "elements": [],
    }
    resident = FakeResidentSession(payload=waiting)
    adapter = Hades2Adapter(
        resident_session=resident,
        time_warp_controller=FakeTimeWarpController(),
    )
    adapter.preferences = adapter._default_preferences()
    adapter.preferences.update(
        damageEnabled=True,
        infiniteAmmo=True,
        statLocks={"moveSpeed": 150},
        vitalLocks={"health": {"current": 40, "max": 100}},
        rerollsLock=2,
        nextRoomReward="WeaponUpgrade",
        nextRoomRewardToken="room-owner-token",
    )
    adapter.preference_initialized = True
    adapter.preference_dirty = True
    observed = adapter.execute("status", {})
    batches = [call["batch"] for call in resident.calls if call["kind"] == "reconcile"]
    assert len(batches) == 1, "Hero-less Crossroads skipped durable resident replay"
    batch = batches[0]
    assert ("set_feature", {"feature": "damageEnabled", "value": True}) in batch
    assert ("set_feature", {"feature": "infiniteAmmo", "value": True}) in batch
    unsafe = {"set_stat", "set_vital", "lock_vital", "set_rerolls", "lock_rerolls",
              "set_element", "lock_element", "set_next_room_reward", "set_next_occurrence"}
    assert not (unsafe & {command for command, _ in batch}), (
        "missing owner sent unsafe replay mutations to the resident"
    )
    assert adapter.preference_dirty, "unavailable Hero-owned locks were discarded"
    assert adapter.preferences["statLocks"]["moveSpeed"] == 150
    assert observed["status"] == "waiting"

print("hades2_scene_owner_replay_ok")
