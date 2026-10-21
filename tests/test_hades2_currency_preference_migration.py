"""Currency modes and retired garden intent survive only valid migrations."""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter
from games.hades2.preferences import Hades2PreferenceStore, normalize_persisted_desired
from games.hades2.profile_service import Hades2ProfileService
from hades2_resident_session_fakes import FakeResidentSession, FakeTimeWarpController

old = normalize_persisted_desired({
    "gardenQoL": True, "infiniteMoney": True, "infiniteRerolls": True,
    "resourceLocks": {"Money": 25}, "rerollsLock": 3,
}, 9)
assert "gardenQoL" not in old
assert not old["infiniteMoney"] and not old["infiniteRerolls"]
assert old["resourceLocks"] == {"Money": 25} and old["rerollsLock"] == 3

current = Hades2PreferenceStore.normalize({
    "infiniteMoney": True, "infiniteRerolls": True,
    "resourceLocks": {"Money": 25, "Ore": 7}, "rerollsLock": 3,
})
assert current["resourceLocks"] == {"Ore": 7} and current["rerollsLock"] is None

with tempfile.TemporaryDirectory(prefix="mgt-currency-preferences-") as temporary:
    original_data = preparation.DATA
    preparation.DATA = Path(temporary)
    try:
        session = FakeResidentSession()
        session.detach()
        adapter = Hades2Adapter(resident_session=session, time_warp_controller=FakeTimeWarpController())
        adapter.preferences["resourceLocks"] = {"Money": 25, "Ore": 7}
        adapter.preferences["rerollsLock"] = 3
        adapter.dispatch("set_desired", {"feature": "infiniteMoney", "value": True}, "gold-mode")
        adapter.dispatch("set_desired", {"feature": "infiniteRerolls", "value": True}, "reroll-mode")
        assert adapter.preferences["resourceLocks"] == {"Ore": 7}
        assert adapter.preferences["rerollsLock"] is None
        reopened = Hades2Adapter(resident_session=session, time_warp_controller=FakeTimeWarpController())
        assert reopened.preferences["infiniteMoney"] and reopened.preferences["infiniteRerolls"]
        assert reopened.preferences["resourceLocks"] == {"Ore": 7}
        assert reopened.preferences["rerollsLock"] is None
        assert session.calls == [], "detached preferences must not execute a game mutation"

        service = Hades2ProfileService(Path(temporary) / "profiles")
        custom_chord = {"keyCode": 5, "modifiers": 6144, "keyLabel": "G"}
        service.save("currency", current, {"_layoutVersion": 1,
            "infiniteHealth": custom_chord, "gardenQoL": custom_chord})
        loaded = service.load("currency")
        assert loaded["desired"]["infiniteMoney"] and loaded["desired"]["infiniteRerolls"]
        assert loaded["shortcuts"] == {"_layoutVersion": 1, "infiniteHealth": custom_chord}
        serialized = json.loads(service.path("currency").read_text())
        assert "gardenQoL" not in serialized["desired"] and "gardenQoL" not in serialized["shortcuts"]
        assert "mature_garden" not in serialized["desired"], "garden mutation must not become replayable intent"
    finally:
        preparation.DATA = original_data
print("hades2_currency_preference_migration_ok")
