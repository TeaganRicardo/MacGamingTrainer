"""Game-native Hades I clock receipt and lifecycle contracts (transport stub)."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
from core.adapter import AdapterError
from games.hades.simulation_time_warp import HadesSimulationTimeWarp


class Transport:
    def __init__(self):
        self.calls = []
        self.installed = False
        self.multiplier = 1.0
        self.native = 1.0
        self.mutate_result = None

    def execute(self, source, *, mutating):
        self.calls.append((source, mutating))
        if 'return timeWarp.set(' in source:
            match = re.search(r'return timeWarp\.set\(([-+\d.eE]+)\)', source)
            assert match
            self.multiplier = float(match.group(1))
            self.installed = True
        result = {
            'wrapperInstalled': self.installed,
            'multiplier': self.multiplier,
            'nativeFraction': self.native,
            'effectiveFraction': self.multiplier * self.native,
        }
        if self.mutate_result is not None:
            result.update(self.mutate_result)
        return result


t = Transport()
owner = HadesSimulationTimeWarp(t)
assert owner.current_speed() == 1.0 and t.calls[-1][1] is False
assert owner.reset() == 1.0 and len(t.calls) == 2 and t.calls[-1][1] is False
assert owner.set_speed(0) == 0.0
assert t.calls[-1][1] is True
assert 'AdjustSimulationSpeed' in t.calls[-1][0]
assert owner.set_speed(0.5) == 0.5
assert owner.set_speed(2) == 2.0
assert owner.set_speed(10) == 10.0
assert owner.set_speed(1) == 1.0
assert owner.reset() == 1.0 and t.calls[-1][1] is False
for invalid in (True, -0.001, 10.001, float('nan'), float('inf'), '1', None):
    try:
        owner.set_speed(invalid)
    except AdapterError as error:
        assert error.code == 'invalid_value'
    else:
        raise AssertionError('invalid speed accepted: %r' % (invalid,))
for bad in ({'wrapperInstalled': False}, {'effectiveFraction': 77}, {'nativeFraction': 'broken'}):
    t.mutate_result = bad
    try:
        owner.set_speed(3)
    except AdapterError as error:
        assert error.code in ('time_warp_verify_failed', 'debugger_protocol')
    else:
        raise AssertionError('bad receipt accepted: %r' % (bad,))
    t.mutate_result = None
assert owner.set_speed(1) == 1.0
print('hades_simulation_time_warp_controller_contract_ok')
