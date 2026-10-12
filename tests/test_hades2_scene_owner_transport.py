"""Ownerless durable replay through actual Adapter -> resident-session -> Lua 5.2."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
sys.path.insert(0, str(ROOT / "tests"))

from games.hades2 import preparation, resident_session
from games.hades2.adapter import Hades2Adapter
from games.hades2.resident_session import Hades2ResidentSession
from hades2_lua_observation_fixture import LuaObservationTransport
from hades2_resident_session_fakes import FakeTimeWarpController

previous_data = preparation.DATA
try:
    with tempfile.TemporaryDirectory(prefix="mgt-scene-owner-transport-") as temporary, \
         patch.object(resident_session, "localize_catalog", side_effect=lambda payload: payload):
        preparation.DATA = Path(temporary)
        native = LuaObservationTransport()
        try:
            # A genuinely bootstrapped resident initially has a live run.
            # Simulate a return to Hero-less Crossroads without resetting Lua.
            native.evaluate('__MacGamingTrainerV1.dispatch("disable_all", {includeCatalogs=false})')
            native.evaluate("""
              CalculateDamageMultipliers = function() return 1 end
              SetUnitProperty = function(args)
                if args.Property == "Speed" then lastSpeedWrite = args.Value end
              end
              priorRun = CurrentRun
              CurrentRun = nil
              CurrentHubRoom = {}
            """)
            adapter = Hades2Adapter(
                resident_session=Hades2ResidentSession(native, bootstrap=""),
                time_warp_controller=FakeTimeWarpController(),
            )
            adapter.preferences = adapter._default_preferences()
            adapter.preferences.update(
                damageEnabled=True,
                statLocks={"moveSpeed": 150},
                vitalLocks={"health": {"current": 60, "max": 100}},
                rerollsLock=4,
            )
            adapter.preference_initialized = True
            adapter.preference_dirty = True
            hub = adapter.execute("status", {"includeCatalogs": False})
            assert hub["scene"] == "crossroads"
            assert hub["activeFeatures"]["damageEnabled"] is True
            assert hub["residentDesiredLocks"]["statLocks"]["moveSpeed"] == 150
            assert hub["residentDesiredLocks"]["vitalLocks"]["health"]["current"] == 60
            assert hub["residentDesiredLocks"]["rerollsLock"] == 4
            assert adapter.preference_dirty, "absent Hero locks were falsely confirmed"
            assert native.execute("return tostring(CurrentRun)") == "nil"

            # The game creates a Hero without notifying Host or changing PID.
            # Resident UpdateTimers is the only recovery stimulus.
            native.evaluate("CurrentRun = priorRun; CurrentHubRoom = nil; UpdateTimers(0)")
            observed = adapter.observe_runtime()
            assert observed["scene"] == "run"
            assert observed["health"] == 60 and observed["maxHealth"] == 100
            assert observed["rerolls"] == 4 and observed["healthLocked"]
            assert observed["stats"]["moveSpeed"]["locked"] is True
            assert native.execute("return tostring(lastSpeedWrite)") == "1.5"
        finally:
            native.close()
finally:
    preparation.DATA = previous_data

print("hades2_scene_owner_transport_ok")
