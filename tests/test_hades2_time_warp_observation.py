import copy
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.process_time_warp import ProcessTimeWarpController
from core.adapter import AdapterError
from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter
from games.hades2.preferences import Hades2PreferenceStore
from games.hades2.schema import MULTIPLIERS, TOGGLES
from hades2_resident_session_fakes import FakeResidentSession


class ResidentHelperDriver:
    def __init__(self):
        self.pid = 4242
        self.speed = 2.0
        self.present = True
        self.queries = 0
        self.writes = []

    def is_alive(self):
        return True

    @contextmanager
    def session(self):
        yield

    def helper_present(self):
        self.queries += 1
        return self.present

    def abi(self):
        return 1

    def get_speed(self):
        return self.speed

    def hook_mask(self):
        return 1

    def install(self, images, speed):
        return self.set_speed(speed)

    def set_speed(self, speed):
        self.writes.append(speed)
        self.speed = speed
        return 0

    def load_helper(self, path):
        self.present = True


with tempfile.TemporaryDirectory(prefix="mgt-speed-observation-") as temporary:
    preparation.DATA = Path(temporary)
    store = Hades2PreferenceStore(preparation.DATA / "desired-state.json")
    store.save(store.defaults())
    driver = ResidentHelperDriver()
    controller = ProcessTimeWarpController(driver, Path(temporary) / "helper", ["Hades II"])
    session = FakeResidentSession()
    session.payload.update(
        desiredFeatures={key: False for key in TOGGLES},
        boonRarity=store.defaults()['boonRarity'],
        **{key: store.defaults()[key] for key in MULTIPLIERS if key != 'gameSpeed'},
    )
    adapter = Hades2Adapter(resident_session=session, time_warp_controller=controller)
    adapter.state.update(connected=True, pid=4242)

    # Observe first without changing durable intent or the live helper.
    observed = adapter.observe_runtime()
    assert observed["activeFeatures"]["gameSpeed"] is True, "resident 2x helper was reported inactive"
    assert driver.queries > 0, "adapter never observed the native helper"
    assert driver.speed == 2.0 and driver.writes == []
    assert adapter.preference_dirty
    adapter.dispatch("status", {}, "first-status")
    assert driver.speed == 1.0, "default desired 1x did not reset a resident helper"
    assert not adapter.preference_dirty
    queries = driver.queries
    adapter.dispatch("status", {}, "steady-status")
    assert driver.queries == queries, "steady status introduced native polling"

    # Manual detach preserves the native effect; an offline change back to 1x
    # is reconciled after a verified same-PID reconnect.
    adapter.dispatch("set_desired", {"feature": "gameSpeed", "value": 2.0}, "speed")
    adapter.disconnect()
    assert driver.speed == 2.0
    adapter.dispatch("set_desired", {"feature": "gameSpeed", "value": 1.0}, "offline")
    adapter.scan = lambda: adapter.state.update(pid=driver.pid)
    adapter.connect()
    assert driver.speed == 1.0 and not adapter.preference_dirty

    # A same-PID reattach must refresh even a formerly confirmed default.
    driver.speed = 3.0
    adapter.connect()
    assert driver.speed == 1.0

    # A replacement game process has its own helper observation; the old
    # applied value cannot be inherited just because desired remained 1x.
    driver.pid = 5000
    driver.speed = 4.0
    adapter.connect()
    assert driver.speed == 1.0 and adapter.runtime.pid == 5000

    # Backend restart against the same live process repeats the actual query.
    driver.speed = 2.0
    restarted = Hades2Adapter(resident_session=FakeResidentSession(session.payload, pid=5000),
                             time_warp_controller=controller)
    restarted.state.update(connected=True, pid=5000)
    restarted.dispatch("status", {}, "backend-restart")
    assert driver.speed == 1.0 and not restarted.preference_dirty

    # A sidecar/process loss during the first query cannot turn the controller's
    # disconnected default into a verified observation for this PID.
    class LostController:
        def current_speed(self):
            session.pid = None
            session.live = False
            return 1.0
    lost = Hades2Adapter(resident_session=session, time_warp_controller=LostController())
    lost.state.update(connected=True, pid=5000)
    try:
        lost.observe_runtime()
    except AdapterError as error:
        assert error.code == 'disconnected'
    else:
        raise AssertionError('lost PID default was adopted as actual speed')
    assert lost._time_warp_speed is None and lost.preference_dirty

    # Every connection-loss route invalidates the last observed helper value,
    # including read-only observations and preflight failures before dispatch.
    for loss in ('observe', 'status', 'preflight', 'scan'):
        disconnected_driver = ResidentHelperDriver()
        disconnected_controller = ProcessTimeWarpController(
            disconnected_driver, Path(temporary) / 'helper', ['Hades II'])
        disconnected_session = FakeResidentSession(session.payload)
        disconnected_session.payload['runtimeDiagnostics'] = {}
        disconnected = Hades2Adapter(resident_session=disconnected_session,
                                     time_warp_controller=disconnected_controller)
        disconnected.state.update(connected=True, pid=4242)
        assert disconnected.observe_runtime()['activeFeatures']['gameSpeed']
        desired = copy.deepcopy(disconnected.preferences)

        def lose_connection(resident, record):
            resident.live = False
            resident.pid = None
            return AdapterError('disconnected', 'test connection loss')

        if loss == 'scan':
            disconnected_session.live = False
            with patch.object(preparation, 'compatibility', return_value={
                    'version': '1.143476', 'warnings': [], 'steam_build': '25481925'}), \
                    patch('games.hades2.adapter.subprocess.run', return_value=SimpleNamespace(
                        returncode=0, stdout='4242\n', stderr='')):
                disconnected.scan()
        else:
            if loss == 'preflight':
                disconnected_session.live = False
            else:
                disconnected_session.handler = lose_connection
            try:
                if loss == 'observe':
                    disconnected.observe_runtime()
                else:
                    disconnected.dispatch('status', {}, 'lost-' + loss)
            except AdapterError as error:
                assert error.code == 'disconnected'
            else:
                raise AssertionError('lost connection did not fail: ' + loss)
        assert not disconnected.state['connected'], loss
        assert not disconnected.state['activeFeatures']['gameSpeed'], loss
        assert disconnected.state['runtimeDiagnostics']['gameSpeedAppliedValue'] is None, loss
        assert disconnected.preferences == desired, loss
        assert disconnected_driver.speed == 2.0 and disconnected_driver.writes == [], loss

print("hades2_time_warp_observation_ok")
