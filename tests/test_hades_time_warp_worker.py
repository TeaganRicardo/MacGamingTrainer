"""Hades time-warp RPC uses the existing LLDB transport and resets before detach."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
from core.adapter import AdapterError
from games.hades.time_warp_worker import HADES_TIME_WARP_IMAGE_NAMES, HadesTimeWarpWorker


class FakeTransport:
    pid = 42
    tainted = False

    def __init__(self):
        self.attached = True
        self.detaches = 0

    def alive(self):
        return self.attached

    def detach(self):
        self.detaches += 1
        self.attached = False

    def close(self):
        self.detach()


class FakeTimeWarp:
    def __init__(self):
        self.speed = 1.0
        self.events = []
        self.failure = None

    def current_speed(self):
        self.events.append(('current', None))
        if self.failure:
            raise self.failure
        return self.speed

    def set_speed(self, value):
        self.events.append(('set', value))
        if self.failure:
            raise self.failure
        self.speed = value
        return value

    def reset(self):
        self.events.append(('reset', None))
        if self.failure:
            raise self.failure
        self.speed = 1.0
        return self.speed


transport = FakeTransport()
time_warp = FakeTimeWarp()
worker = HadesTimeWarpWorker(transport=transport, time_warp_factory=lambda _: time_warp)
assert HADES_TIME_WARP_IMAGE_NAMES == ('Game.macOS',)
assert worker.dispatch('time_warp.current_speed', {})['gameSpeed'] == 1.0
assert worker.dispatch('time_warp.set_speed', {'value': 2.5})['gameSpeed'] == 2.5
assert worker.dispatch('time_warp.current_speed', {})['gameSpeed'] == 2.5
assert time_warp.events == [('current', None), ('set', 2.5), ('current', None)]

transport2 = FakeTransport()
time_warp2 = FakeTimeWarp()
time_warp2.speed = 4.0
worker2 = HadesTimeWarpWorker(transport=transport2, time_warp_factory=lambda _: time_warp2)
state = worker2.dispatch('disconnect', {})
assert not state['connected'] and time_warp2.speed == 1.0 and transport2.detaches == 1
assert time_warp2.events == [('reset', None)], 'speed reset must precede LLDB detach'

transport3 = FakeTransport()
time_warp3 = FakeTimeWarp()
time_warp3.speed = 3.0
time_warp3.failure = AdapterError('outcome_unknown', 'host.timeWarp.error.outcomeUnknown')
worker3 = HadesTimeWarpWorker(transport=transport3, time_warp_factory=lambda _: time_warp3)
try:
    worker3.dispatch('disconnect', {})
except AdapterError as error:
    assert error.code == 'outcome_unknown'
else:
    raise AssertionError('uncertain speed reset was hidden')
assert transport3.attached and transport3.detaches == 0, 'uncertain reset detached the only recovery transport'

print('hades_time_warp_worker_reset_and_outcome_contract_ok')
