import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2 import preparation as prep
from games.hades2.adapter import Hades2Adapter
from games.hades2.error_presentation import Hades2PresentationError
from games.hades2.preferences import Hades2PreferenceStore
from core.process_time_warp import ProcessTimeWarpError

base = Path(tempfile.mkdtemp(prefix="mgt-time-warp-hades-"))
prep.DATA = base
prep.GAME = base / "Hades II.app"
prep.SAVES = base / "Saves"
prep.official_display_names = lambda ids, language="zh-CN": {}

assert Hades2PreferenceStore.normalize({"gameSpeed": 0.0})["gameSpeed"] == 0.0
assert Hades2PreferenceStore.normalize({"gameSpeed": 10.0})["gameSpeed"] == 10.0
assert Hades2PreferenceStore.normalize({"gameSpeed": -0.1})["gameSpeed"] == 1.0
assert Hades2PreferenceStore.normalize({"gameSpeed": 10.1})["gameSpeed"] == 1.0


class FakeTransport:
    def __init__(self):
        self.pid = 4242
        self.live = True
        self.last_duration = 0.001
        self.sources = []

    def alive(self):
        return self.live

    def execute(self, source, *, expression_timeout_seconds=None):
        self.sources.append(source)
        return json.dumps({
            "status": "ready",
            "scene": "run",
            "capabilities": {"setFeature": True},
            "featureSupport": {},
            "desiredFeatures": {},
            "activeFeatures": {},
            "dormantFeatures": {},
            "featureErrors": {},
            "damageMultiplier": 2.0,
            "moneyMultiplier": 2.0,
            "resourceMultiplier": 2.0,
            "boonRarity": {
                "target": "Epic",
                "multiplier": 100.0,
                "forceLegendary": False,
                "forceDuo": False,
            },
            "nextRoomReward": None,
            "stats": {},
            "resources": [],
            "elements": [],
            "boons": [],
            "rewards": [],
        })


class FakeTimeWarp:
    def __init__(self):
        self.speed = 1.0

    def set_speed(self, speed):
        self.speed = float(speed)
        return self.speed

    def reset(self):
        self.speed = 1.0
        return self.speed


transport = FakeTransport()
adapter = Hades2Adapter(transport=transport)
adapter.time_warp = FakeTimeWarp()
adapter.preference_initialized = True
adapter.preference_dirty = False
adapter._runtime_bootstrapped = True
adapter.state.update(connected=True, status="waiting", scene="loading", capabilities={"setFeature": False})

# A status-only runtime observation must retain the Core-owned Time Warp
# capability/active projection even though it deliberately skips durable
# Hades desired-state projection.
adapter._time_warp_speed = 2.0
observed = adapter.observe_runtime()
assert observed["featureSupport"]["gameSpeed"] is True
assert observed["activeFeatures"]["gameSpeed"] is True
adapter._time_warp_speed = 1.0
transport.sources.clear()

state = adapter.dispatch("set_desired", {"feature": "gameSpeed", "value": 0.0}, "speed-freeze")
assert state["gameSpeed"] == 0.0
assert state["activeFeatures"]["gameSpeed"] is True
assert adapter.time_warp.speed == 0.0
assert transport.sources == [], "process Time Warp unexpectedly crossed the Lua boundary"

try:
    adapter.dispatch("set_desired", {"feature": "gameSpeed", "value": 10.1}, "speed-invalid")
except Hades2PresentationError as error:
    # Out-of-range input is rejected with a language-neutral presentation key.
    assert error.presentation == "hades2.error.gameSpeedRange", error.presentation
else:
    raise AssertionError("gameSpeed > 10 was accepted")

state = adapter.dispatch("set_desired", {"feature": "gameSpeed", "value": 1.0}, "speed-reset")
assert state["gameSpeed"] == 1.0
assert state["activeFeatures"]["gameSpeed"] is False
assert adapter.time_warp.speed == 1.0

# Before the new Lua generation is known, persist the desired factor but avoid
# layering Time Warp over a possible resident r40 Lua speed implementation.
adapter._runtime_bootstrapped = False
adapter.preference_dirty = False
state = adapter.dispatch("set_desired", {"feature": "gameSpeed", "value": 2.0}, "speed-pending")
assert state["gameSpeed"] == 2.0
assert adapter.time_warp.speed == 1.0
assert state["activeFeatures"]["gameSpeed"] is False
assert adapter.preference_dirty is True

# Once the r41 generation is established, speed applies even in a non-ready
# scene; Lua-only desired state remains pending until the scene is ready.
adapter._runtime_bootstrapped = True
adapter.state["status"] = "waiting"
state = adapter._replay_preferences(force_full=True)
assert adapter.time_warp.speed == 2.0
assert state["activeFeatures"]["gameSpeed"] is True
assert adapter.preference_dirty is True
assert transport.sources == []

# In a ready scene, the rest of the profile still replays through Lua, but the
# Lua batch must not carry process-owned gameSpeed.
adapter.state["status"] = "ready"
state = adapter._replay_preferences(force_full=True)
assert transport.sources
assert "gameSpeed" not in transport.sources[-1]
assert adapter.time_warp.speed == 2.0
assert state["gameSpeed"] == 2.0
assert adapter.preference_dirty is False

# Full teardown restores only the trainer process factor to 1x while retaining
# the existing Lua cleanup path for all other Hades runtime features.
state = adapter.execute("disable_all", {})
assert adapter.time_warp.speed == 1.0
assert state["gameSpeed"] == 1.0
assert state["activeFeatures"]["gameSpeed"] is False


class FailingTimeWarp:
    def set_speed(self, speed):
        raise ProcessTimeWarpError(
            "time_warp_set_failed",
            "host.timeWarp.error.setFailed",
            arguments=(-7,),
            diagnostic="synthetic driver failure",
        )

    def reset(self):
        return 1.0


# Drive the real Hades desired-state path. The adapter deliberately keeps the
# failed desired value pending, but the observable failure is now a structured
# Host presentation token rather than raw localized copy in featureErrors.
failing = Hades2Adapter(transport=FakeTransport())
failing.time_warp = FailingTimeWarp()
failing.preference_initialized = True
failing.preference_dirty = False
failing._runtime_bootstrapped = True
failing.state.update(connected=True, status="ready", scene="run", capabilities={"setFeature": True})
failed_state = failing.dispatch("set_desired", {"feature": "gameSpeed", "value": 2.0}, "speed-fails")
assert "gameSpeed" not in failed_state.get("featureErrors", {}), failed_state.get("featureErrors")
presentation = failed_state["featureErrorPresentations"]["gameSpeed"]
assert presentation == {
    "presentation": "host.timeWarp.error.setFailed",
    "arguments": [-7],
}, presentation

print("process_time_warp_hades_integration_ok")
