from contextlib import contextmanager
from pathlib import Path
import math
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.process_time_warp import LLDBProcessTimeWarpDriver, ProcessTimeWarpController, ProcessTimeWarpError


class FakeDriver:
    def __init__(self):
        self.pid = 100
        self.alive = True
        self.present = False
        self.hooks = 1
        self.speed = 1.0
        self.loads = 0
        self.installs = []
        self.sets = []
        self.sessions = 0

    def is_alive(self):
        return self.alive

    @contextmanager
    def session(self):
        self.sessions += 1
        yield

    def helper_present(self):
        return self.present

    def load_helper(self, path):
        assert Path(path).name == "libMGTTimeWarp.dylib"
        self.loads += 1
        self.present = True

    def abi(self):
        return 1

    def install(self, image_names, speed):
        self.installs.append((image_names, speed))
        self.speed = speed
        return 0

    def set_speed(self, speed):
        self.sets.append(speed)
        self.speed = speed
        return 0

    def get_speed(self):
        return self.speed

    def hook_mask(self):
        return self.hooks


helper = ROOT / "Backend/core/native/libMGTTimeWarp.dylib"
driver = FakeDriver()
controller = ProcessTimeWarpController(driver, helper, ["Hades II"])

for invalid in (True, float("nan"), 0.09, 20.01):
    try:
        controller.set_speed(invalid)
    except (TypeError, ValueError):
        pass
    else:
        raise AssertionError(f"invalid speed accepted: {invalid!r}")
assert driver.sessions == 0

assert controller.set_speed(2.0) == 2.0
assert driver.loads == 1
assert driver.installs == [(b"Hades II", 2.0)]
assert driver.sets == []
assert driver.sessions == 1

assert controller.set_speed(0.5) == 0.5
assert driver.loads == 1
assert driver.installs == [(b"Hades II", 2.0)]
assert driver.sets == [0.5]

driver.pid = 101
driver.present = False
assert controller.set_speed(3.0) == 3.0
assert driver.loads == 2
assert driver.installs[-1] == (b"Hades II", 3.0)

# A fresh backend/controller against the same PID must adopt a resident helper,
# not load a second image.
reuse = ProcessTimeWarpController(driver, helper, ["Hades II"])
loads_before = driver.loads
assert reuse.set_speed(1.5) == 1.5
assert driver.loads == loads_before
assert driver.installs[-1] == (b"Hades II", 1.5)

# Unsupported target: selected images contain none of the clock imports.
unsupported_driver = FakeDriver()
unsupported_driver.hooks = 0
unsupported = ProcessTimeWarpController(unsupported_driver, helper, ["Hades II"])
try:
    unsupported.set_speed(2.0)
except ProcessTimeWarpError as error:
    assert error.code == "time_warp_unsupported", error.code
else:
    raise AssertionError("zero hook mask was accepted")

# Reset is intentionally lazy: do not inject a helper just to establish 1x.
clean_driver = FakeDriver()
clean = ProcessTimeWarpController(clean_driver, helper, ["Hades II"])
assert clean.reset() == 1.0
assert clean_driver.loads == 0
assert clean_driver.sessions == 0

driver.present = True
assert reuse.reset() == 1.0
assert driver.speed == 1.0

driver.alive = False
try:
    reuse.set_speed(2.0)
except ProcessTimeWarpError as error:
    assert error.code == "disconnected"
else:
    raise AssertionError("dead target accepted")

class FakeLLDB:
    eStateStopped = 5

class FakeStoppedProcess:
    def GetState(self):
        return FakeLLDB.eStateStopped

class TaintedTransport:
    pid = 200
    tainted = True
    process = FakeStoppedProcess()
    def alive(self):
        return True
    def stop(self, deadline):
        raise AssertionError("tainted transport must be rejected before stop")
    def resume(self, deadline):
        raise AssertionError("tainted transport must never resume")

class TargetlessTransport:
    pid = 201
    target = None
    def alive(self):
        return True

targetless_driver = LLDBProcessTimeWarpDriver(TargetlessTransport(), lldb_module=object())
assert targetless_driver.helper_present() is False

tainted_driver = LLDBProcessTimeWarpDriver(TaintedTransport(), lldb_module=FakeLLDB)
try:
    with tainted_driver.session():
        raise AssertionError("tainted session entered")
except ProcessTimeWarpError as error:
    assert error.code == "restart_required", error.code
else:
    raise AssertionError("tainted transport accepted")

print("process_time_warp_controller_ok")
