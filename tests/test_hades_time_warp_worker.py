"""Hades I Time Warp uses the game-native simulation clock and resets before detach."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
from core.adapter import AdapterError
from games.hades.time_warp_worker import HadesTimeWarpWorker, error_payload
from games.hades.simulation_time_warp import HadesSimulationTimeWarp


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


class LuaTransport:
    pid = 42

    def __init__(self):
        self.sources = []
        self.installed = False
        self.multiplier = 1.0
        self.native_fraction = 1.0
        self.fail = None

    def execute(self, source, *, mutating=False):
        self.sources.append((source, mutating))
        if self.fail:
            raise self.fail
        if 'return timeWarp.set(' in source:
            match = re.search(r'return timeWarp\.set\(([-+0-9.eE]+)\)', source)
            assert match, source
            self.multiplier = float(match.group(1))
            self.installed = True
        return {
            'wrapperInstalled': self.installed,
            'multiplier': self.multiplier,
            'nativeFraction': self.native_fraction,
            'effectiveFraction': self.multiplier * self.native_fraction,
        }


transport = FakeTransport()
time_warp = FakeTimeWarp()
worker = HadesTimeWarpWorker(transport=transport, time_warp_factory=lambda _: time_warp)
assert worker.dispatch('time_warp.current_speed', {})['gameSpeed'] == 1.0
assert worker.dispatch('time_warp.set_speed', {'value': 2.5})['gameSpeed'] == 2.5
assert worker.dispatch('time_warp.current_speed', {})['gameSpeed'] == 2.5
assert time_warp.events == [('current', None), ('set', 2.5), ('current', None)]

lua_transport = LuaTransport()
simulation_warp = HadesSimulationTimeWarp(lua_transport)
assert simulation_warp.current_speed() == 1.0
assert lua_transport.sources[-1][1] is False
assert simulation_warp.reset() == 1.0
assert len(lua_transport.sources) == 2 and lua_transport.sources[-1][1] is False
assert simulation_warp.set_speed(2.5) == 2.5
source, mutating = lua_transport.sources[-1]
assert mutating is True and 'AdjustSimulationSpeed' in source
assert 'nativeFraction * state.multiplier' in source
assert 'state.nativeArguments' in source and 'state.multiplier' in source
assert simulation_warp.current_speed() == 2.5
lua_transport.native_fraction = 0.5
assert simulation_warp.current_speed() == 2.5
assert lua_transport.native_fraction * simulation_warp.current_speed() == 1.25
assert simulation_warp.set_speed(0.0) == 0.0
assert simulation_warp.set_speed(1.0) == 1.0
for invalid in (True, -0.1, 10.1, float('nan'), float('inf'), '2'):
    try:
        simulation_warp.set_speed(invalid)
    except AdapterError as error:
        assert error.code == 'invalid_value'
    else:
        raise AssertionError(f'invalid game-native speed accepted: {invalid!r}')

transport2 = FakeTransport()
time_warp2 = FakeTimeWarp()
time_warp2.speed = 4.0
worker2 = HadesTimeWarpWorker(transport=transport2, time_warp_factory=lambda _: time_warp2)
state = worker2.dispatch('disconnect', {})
assert not state['connected'] and time_warp2.speed == 1.0 and transport2.detaches == 1
assert time_warp2.events == [('reset', None)]

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
assert transport3.attached and transport3.detaches == 0

# EOF and unexpected end of the JSONL loop must restore the game clock before
# detaching. The close path is distinct from the explicit disconnect command.
transport4 = FakeTransport()
time_warp4 = FakeTimeWarp()
time_warp4.speed = 3.0
worker4 = HadesTimeWarpWorker(transport=transport4, time_warp_factory=lambda _: time_warp4)
worker4.close()
assert transport4.detaches == 1 and time_warp4.speed == 1.0
assert time_warp4.events == [('reset', None)]

# If native reset failed, neither EOF cleanup nor a forced detach may hide
# the unknown outcome or abandon the still attached game process.
transport5 = FakeTransport()
time_warp5 = FakeTimeWarp()
time_warp5.speed = 0.5
time_warp5.failure = AdapterError('outcome_unknown', 'hades.error.outcomeUnknown')
worker5 = HadesTimeWarpWorker(transport=transport5, time_warp_factory=lambda _: time_warp5)
try:
    worker5.close()
except AdapterError as error:
    assert error.code == 'outcome_unknown'
else:
    raise AssertionError('unknown native EOF reset was hidden')
assert transport5.attached and transport5.detaches == 0

for code, suffix in (('outcome_unknown', 'outcomeUnknown'), ('restart_required', 'restartRequired')):
    failure = AdapterError(code, 'host.timeWarp.error.' + suffix, arguments=['native detail'], diagnostic='native detail')
    payload = error_payload(failure)
    assert payload['code'] == code and payload['presentation'] == 'hades.error.' + suffix
    assert payload['arguments'] == [] and payload['diagnostic'] == 'native detail'
known_failure = AdapterError('time_warp_verify_failed', 'host.timeWarp.error.verifyFailed')
assert error_payload(known_failure)['presentation'] == known_failure.presentation

print('hades_game_native_simulation_time_warp_worker_contract_ok')
