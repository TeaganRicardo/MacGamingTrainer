import copy
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
sys.path.insert(0, str(ROOT / "tests"))

from core.adapter import AdapterError
from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter
from games.hades2.desired_reconciliation import DesiredReconciliationOutcome
from games.hades2.preferences import Hades2PreferenceStore
from hades2_resident_session_fakes import FakeResidentSession, FakeTimeWarpController


def observed_runtime_with_locks():
    return {
        "status": "ready",
        "scene": "run",
        "capabilities": {"setFeature": True},
        "desiredFeatures": {},
        "activeFeatures": {},
        "dormantFeatures": {},
        "featureSupport": {},
        "featureErrors": {},
        "boonRarity": {
            "target": "Epic",
            "multiplier": 100.0,
            "forceLegendary": False,
            "forceDuo": False,
        },
        "gatheringProbabilities": {},
        "chaosGateProbability": None,
        "stats": {
            "grasp": {"locked": True, "target": 30, "value": 30},
            "enemyHealth": {"locked": True, "target": 175, "value": 175},
        },
        "healthLocked": True,
        "health": 120,
        "maxHealth": 160,
        "manaLocked": True,
        "mana": 50,
        "maxMana": 90,
        "armorLocked": True,
        "armor": 25,
        "moneyLocked": True,
        "money": 999,
        "resources": [
            {"id": "MetaCurrency", "locked": True, "count": 12},
            {"id": "Bones", "locked": True, "count": 5},
        ],
        "rerollsLocked": True,
        "rerolls": 7,
        "elements": [
            {"id": "Fire", "locked": True, "count": 8},
            {"id": "Water", "locked": True, "count": 4},
        ],
        "nextRoomReward": None,
    }


class RecordingReconciler:
    def __init__(self, fail_once=False):
        self.calls = []
        self.fail_once = fail_once

    def reconcile(self, desired, observed, *, force_full=False):
        self.calls.append({
            "desired": copy.deepcopy(desired),
            "observed": copy.deepcopy(observed),
            "force_full": bool(force_full),
        })
        if self.fail_once:
            self.fail_once = False
            raise AdapterError(
                "lua_error",
                "simulated known resident reconciliation failure",
            )
        return DesiredReconciliationOutcome(
            reply=None,
            confirmed=True,
            mismatches=(),
        )


def make_adapter(prefix, runtime=None):
    preparation.DATA = Path(tempfile.mkdtemp(prefix=prefix))
    runtime = runtime or FakeResidentSession(observed_runtime_with_locks(), pid=777)
    adapter = Hades2Adapter(
        resident_session=runtime,
        time_warp_controller=FakeTimeWarpController(),
    )
    adapter.state.update(connected=True, pid=runtime.pid, status="ready", scene="run")
    return runtime, adapter


# Profile replacement must hand the reconciler the real runtime observation
# captured before the replacement desired snapshot is projected into Adapter
# state. Per-family lock planning is owned and tested by the reconciler itself.
runtime, adapter = make_adapter("mgt-profile-reconcile-")
reconciler = RecordingReconciler()
adapter.desired_reconciler = reconciler

desired = Hades2PreferenceStore.defaults()
desired.update({
    "statLocks": {"enemyHealth": 200},
    "vitalLocks": {"mana": {"current": 40, "max": 90}},
    "resourceLocks": {"MetaCurrency": 20},
    "rerollsLock": None,
    "elementLocks": {"Fire": 9},
})
adapter.profile_service.save("partial-locks", desired)

result = adapter.load_profile("partial-locks")
assert result["loadedProfile"] == "partial-locks"
assert len(reconciler.calls) == 1
call = reconciler.calls[0]
assert call["force_full"] is True
observed = call["observed"]
assert observed["stats"]["grasp"]["locked"] is True
assert observed["stats"]["enemyHealth"]["target"] == 175
assert observed["healthLocked"] is True
assert observed["armorLocked"] is True
assert observed["moneyLocked"] is True
assert next(row for row in observed["resources"] if row["id"] == "Bones")["locked"] is True
assert observed["rerollsLocked"] is True
assert next(row for row in observed["elements"] if row["id"] == "Water")["locked"] is True

# The desired state given to reconciliation is the replacement Profile, not a
# runtime-adopted snapshot. Successful semantic confirmation clears pending.
assert call["desired"]["statLocks"] == {"enemyHealth": 200}
assert call["desired"]["vitalLocks"] == {"mana": {"current": 40, "max": 90}}
assert call["desired"]["resourceLocks"] == {"MetaCurrency": 20}
assert call["desired"]["elementLocks"] == {"Fire": 9}
assert adapter.preference_dirty is False


# Offline Profile load remains pending. The next explicit status observation is
# the point where reconciliation receives a fresh runtime snapshot.
offline_runtime, offline = make_adapter("mgt-profile-reconcile-offline-")
offline_runtime.live = False
offline.state.update(connected=False, status="disconnected")
offline_reconciler = RecordingReconciler()
offline.desired_reconciler = offline_reconciler
offline.profile_service.save("offline-no-locks", Hades2PreferenceStore.defaults())

offline.load_profile("offline-no-locks")
assert offline.preference_dirty is True
assert offline_reconciler.calls == []

offline_runtime.live = True
offline.state.update(connected=True, pid=offline_runtime.pid, status="ready")
offline.execute("status", {})
assert len(offline_reconciler.calls) == 1
assert offline_reconciler.calls[0]["observed"]["moneyLocked"] is True
assert offline.preference_dirty is False


# A failed live Profile reconciliation must not make Adapter trust its projected
# desired UI state as runtime truth. Loading the same Profile again re-observes
# the resident and supplies the still-locked runtime snapshot a second time.
retry_runtime, retry = make_adapter("mgt-profile-reconcile-retry-")
retry_reconciler = RecordingReconciler(fail_once=True)
retry.desired_reconciler = retry_reconciler
retry.profile_service.save("retry-unlocked", Hades2PreferenceStore.defaults())

try:
    retry.load_profile("retry-unlocked")
except AdapterError as error:
    assert error.code == "lua_error"
else:
    raise AssertionError("expected first Profile reconciliation to fail")

assert retry.preference_dirty is True
assert len(retry_reconciler.calls) == 1
assert retry_reconciler.calls[0]["observed"]["healthLocked"] is True
# Projection may show the requested Profile after failure, but it is never used
# as confirmation evidence.
assert retry.state["healthLocked"] is False

second = retry.load_profile("retry-unlocked")
assert second["loadedProfile"] == "retry-unlocked"
assert len(retry_reconciler.calls) == 2
assert retry_reconciler.calls[1]["observed"]["healthLocked"] is True
assert retry_reconciler.calls[1]["observed"]["moneyLocked"] is True
assert retry.preference_dirty is False

print("profile_lock_reconciliation_ok")
