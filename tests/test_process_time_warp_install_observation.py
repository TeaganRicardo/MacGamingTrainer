"""Controller recovery observes native installation instead of installing on reset."""
from contextlib import contextmanager
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
from core.process_time_warp import ProcessTimeWarpController, ProcessTimeWarpError


class Driver:
    def __init__(self, state=0, *, present=True):
        self.pid = 42
        self.state = state
        self.present = present
        self.alive = True
        self.version = ProcessTimeWarpController.ABI_VERSION
        self.speed = 1.0 if state == 0 else 2.0
        self.installs = []
        self.sets = []
        self.loads = 0
        self.install_result = 0

    def is_alive(self): return self.alive
    def helper_present(self): return self.present
    def abi(self): return self.version
    def install_state(self, image_names):
        assert image_names == b'Fixture'
        return self.state
    def hook_mask(self): return 1 if self.state in (1, 2) else 0
    def get_speed(self): return self.speed

    @contextmanager
    def session(self):
        yield

    def load_helper(self, path):
        self.loads += 1
        self.present = True

    def install(self, images, speed):
        self.installs.append((images, speed))
        if self.install_result == 0:
            self.state = 1
            self.speed = speed
        return self.install_result

    def set_speed(self, speed):
        self.sets.append(speed)
        self.speed = speed
        return 0


def controller(driver):
    return ProcessTimeWarpController(driver, ROOT / 'helper.dylib', ['Fixture'])


class InstallationObservation(unittest.TestCase):
    def test_loaded_uninstalled_reset_does_not_install(self):
        driver = Driver()
        driver.install_result = -3
        self.assertEqual(controller(driver).reset(), 1.0)
        self.assertEqual(driver.installs, [])
        self.assertEqual(driver.sets, [])

    def test_fresh_worker_adopts_existing_installation(self):
        driver = Driver(1)
        self.assertEqual(controller(driver).set_speed(3.0), 3.0)
        self.assertEqual(driver.installs, [])
        self.assertEqual(driver.sets, [3.0])
        self.assertEqual(controller(driver).reset(), 1.0)
        self.assertEqual(driver.installs, [])

    def test_partial_and_unknown_states_refuse_mutation_and_observation(self):
        for state in (2, 3):
            for operation in ('current_speed', 'reset', 'set_speed'):
                with self.subTest(state=state, operation=operation):
                    driver = Driver(state)
                    owner = controller(driver)
                    with self.assertRaises(ProcessTimeWarpError) as raised:
                        getattr(owner, operation)(*([] if operation != 'set_speed' else [3.0]))
                    self.assertEqual(raised.exception.code, 'restart_required')
                    self.assertEqual(driver.installs, [])
                    self.assertEqual(driver.sets, [])

    def test_legacy_helper_is_refused_before_mutation(self):
        driver = Driver(1)
        driver.version -= 1
        with self.assertRaises(ProcessTimeWarpError) as raised:
            controller(driver).reset()
        self.assertEqual(raised.exception.code, 'time_warp_abi_mismatch')
        self.assertEqual(driver.installs, [])
        self.assertEqual(driver.sets, [])

    def test_resident_image_filter_mismatch_is_refused(self):
        driver = Driver(-4)
        with self.assertRaises(ProcessTimeWarpError) as raised:
            controller(driver).reset()
        self.assertEqual(raised.exception.code, 'time_warp_install_failed')
        self.assertEqual(driver.installs, [])
        self.assertEqual(driver.sets, [])

    def test_new_lifetime_and_unloaded_dead_reset(self):
        driver = Driver(1)
        owner = controller(driver)
        owner.set_speed(3.0)
        driver.pid = 43
        driver.state = 0
        driver.speed = 1.0
        driver.install_result = -3
        self.assertEqual(owner.reset(), 1.0)
        self.assertEqual(driver.installs, [])
        unloaded = Driver(present=False)
        self.assertEqual(controller(unloaded).reset(), 1.0)
        self.assertEqual(unloaded.loads, 0)
        unloaded.alive = False
        self.assertEqual(controller(unloaded).reset(), 1.0)


if __name__ == '__main__':
    unittest.main()
