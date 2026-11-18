"""Hades II Vow of Time: native balance, lock scope and durable replay."""
import sys
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
sys.path.insert(0, str(ROOT / "tests"))

from games.hades2.command_contract import Hades2CommandContract
from games.hades2.desired_reconciliation import Hades2DesiredStateReconciler
from games.hades2.preferences import Hades2PreferenceStore
from lua_runtime_support import require_lua52

class Probe:
    def execute(self, command, params):
        return command, params

contract = Hades2CommandContract(Probe())
for seconds in (0, 1, 300, 999999):
    command, params = contract.dispatch(
        "set_counter", {"counter": "biomeTime", "value": seconds}, "biome-time-test"
    )
    assert command == "set_counter"
    assert params == {"counter": "biomeTime", "value": seconds}
for invalid in (-1, 0.25, 1000000, True, float("inf"), "360"):
    try:
        contract.dispatch("set_counter", {"counter": "biomeTime", "value": invalid}, "biome-invalid")
    except Exception:
        pass
    else:
        raise AssertionError(("invalid seconds accepted", invalid))
for locked in (True, False):
    command, params = contract.dispatch("lock_biome_time", {"locked": locked}, "lock-biome-test")
    assert command == "lock_biome_time" and params == {"locked": locked}
for invalid in (0, 1, None, "true"):
    try:
        contract.dispatch("lock_biome_time", {"locked": invalid}, "bad-lock")
    except Exception:
        pass
    else:
        raise AssertionError(("invalid lock accepted", invalid))

assert Hades2PreferenceStore.defaults()["biomeTimerFrozen"] is False
assert Hades2PreferenceStore.normalize({"biomeTimerFrozen": True})["biomeTimerFrozen"] is True
assert Hades2PreferenceStore.normalize({"biomeTimerFrozen": 1})["biomeTimerFrozen"] is False

from games.hades2.adapter import Hades2Adapter, clear_active
shadow = Hades2Adapter.__new__(Hades2Adapter)
shadow.state = {"biomeTime": 150, "biomeTimeLocked": False}
shadow._time_warp_speed = None
shadow._time_warp_error = None
shadow.preferences = Hades2PreferenceStore.normalize({"biomeTimerFrozen": True})
shadow._overlay_preferences()
assert shadow.state["biomeTimeLocked"] is True
clear_active(shadow.state, preserve_desired=True)
assert shadow.state["biomeTime"] is None and shadow.state["biomeTimeLocked"] is False
shadow._overlay_preferences()
assert shadow.state["biomeTimeLocked"] is True
shadow.preferences["biomeTimerFrozen"] = False
shadow._overlay_preferences()
assert shadow.state["biomeTimeLocked"] is False

diff = Hades2DesiredStateReconciler(None)
def biome_actions(desired, observed):
    return [
        action for action in diff._diff(desired, observed, force_full=False)
        if action.command == "lock_biome_time"
    ]
assert not biome_actions({"biomeTimerFrozen": False}, {})
assert [(a.params, a.mismatch) for a in biome_actions({"biomeTimerFrozen": True}, {"biomeTimeLocked": False})] == [
    ({"locked": True}, "biomeTimer")
]
assert [a.params for a in biome_actions({"biomeTimerFrozen": False}, {"biomeTimeLocked": True})] == [
    {"locked": False}
]
assert diff._owner_available(
    biome_actions({"biomeTimerFrozen": True}, {"biomeTimeLocked": False})[0],
    {"capabilities": {"setFeature": True}},
)

source = (ROOT / "Backend/games/hades2/runtime/hades.lua").read_text(encoding="utf-8")
revision_match = __import__("re").search(r"version = 1, revision = (\d+),", source)
assert revision_match and int(revision_match.group(1)) >= 139
assert "setBiomeTime = " in source and "biomeTimeLocked = M.biomeTimerFrozen" in source
assert 'if command == "set_counter" then' in source
assert 'if command == "lock_biome_time" then' in source
assert 'lock_biome_time = true' in source
assert source.count("result = M.updateWithBiomeTimerLock(original, elapsed)") == 2
begin = source.index("  function M.updateWithBiomeTimerLock(original, elapsed)")
end = source.index("  local function synchronize()", begin)
helper = source[begin:end]

# Run the *production helper* against a tiny native UpdateTimers model. This
# tests IGT independence, carried region grants, failure cleanup and unfreeze.
lua = require_lua52("Vow of Time ownership test")
script = """
local M = { biomeTimerFrozen = true }
local CurrentRun = { ActiveBiomeTimer = true, BiomeTime = 120, GameplayTime = 5 }
local function finite(n)
  return type(n) == "number" and n == n and n ~= math.huge and n ~= -math.huge
end
""" + helper + """
local function native(elapsed)
  CurrentRun.GameplayTime = CurrentRun.GameplayTime + elapsed
  if CurrentRun.ActiveBiomeTimer then CurrentRun.BiomeTime = CurrentRun.BiomeTime - elapsed end
end
M.updateWithBiomeTimerLock(native, 10)
assert(CurrentRun.BiomeTime == 120 and CurrentRun.GameplayTime == 15)
assert(CurrentRun.ActiveBiomeTimer == true)
CurrentRun.BiomeTime = math.max(CurrentRun.BiomeTime, 0) + 300
M.updateWithBiomeTimerLock(native, 20)
assert(CurrentRun.BiomeTime == 420 and CurrentRun.GameplayTime == 35)
M.biomeTimerFrozen = false
M.updateWithBiomeTimerLock(native, 20)
assert(CurrentRun.BiomeTime == 400 and CurrentRun.GameplayTime == 55)
M.biomeTimerFrozen = true
local ok = pcall(function()
  M.updateWithBiomeTimerLock(function(_) error("native failure") end, 1)
end)
assert(not ok and CurrentRun.ActiveBiomeTimer == true)
CurrentRun.BiomeTime = -2
M.updateWithBiomeTimerLock(native, 1)
assert(CurrentRun.BiomeTime == -3)
CurrentRun = { ActiveBiomeTimer = true, BiomeTime = 300, GameplayTime = 0 }
M.updateWithBiomeTimerLock(native, 5)
assert(CurrentRun.BiomeTime == 300 and CurrentRun.GameplayTime == 5)
print("biome_timer_lua_ok")
"""
with tempfile.TemporaryDirectory(prefix="mgt-biome-timer-") as temp:
    path = Path(temp) / "biome_timer.lua"
    path.write_text(script, encoding="utf-8")
    proc = subprocess.run([lua, str(path)], capture_output=True, text=True, timeout=15)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "biome_timer_lua_ok" in proc.stdout

view = (ROOT / "Sources/Hades2/Hades2View.swift").read_text(encoding="utf-8")
model = (ROOT / "Sources/Hades2/Hades2Model.swift").read_text(encoding="utf-8")
assert 'text("hades2.metric.biomeTime")' in view
assert "locked: model.biomeTimeLocked" in view
assert "enabled: model.canSetBiomeTime" in view
assert 'case .biomeTime = edit' in model
assert 'static func parseBiomeTime(_ text: String)' in model
print("hades2_biome_timer_contract_ok")
