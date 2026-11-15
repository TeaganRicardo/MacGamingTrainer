"""Hades I global App::TimeScale controller and binary symbol contracts."""
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
from core.adapter import AdapterError
from games.hades.simulation_time_warp import (
    APP_ACCUMULATOR_OFFSET,
    APP_INSTANCE_SYMBOL,
    APP_TIME_SCALE_OFFSET,
    APP_USE_FIXED_STEP_OFFSET,
    AUTO_RESET_SYMBOL,
    HadesSimulationTimeWarp,
    NO_FIXED_STEP_SYMBOL,
)


symbols = json.loads((ROOT / 'Backend/games/hades/symbols.json').read_text(encoding='utf-8'))['symbols']
for required in (
    APP_INSTANCE_SYMBOL,
    AUTO_RESET_SYMBOL,
    NO_FIXED_STEP_SYMBOL,
    '_ZN3sgg3App13UpdateAndDrawEf',
    '_ZN3sgg3App6UpdateEf',
):
    assert required in symbols, f'missing symbol in symbols.json: {required}'
    assert type(symbols[required]['rva']) is int and symbols[required]['rva'] > 0
for text_symbol in ('_ZN3sgg3App13UpdateAndDrawEf', '_ZN3sgg3App6UpdateEf'):
    prefix = symbols[text_symbol].get('prefix', '')
    assert len(prefix) == 32 and bytes.fromhex(prefix), text_symbol


class Transport:
    APP_PTR = 0x200000

    def __init__(self, *, app_ptr=APP_PTR, no_fixed_step=0):
        self.addresses = {
            APP_INSTANCE_SYMBOL: 0x100000,
            AUTO_RESET_SYMBOL: 0x100010,
            NO_FIXED_STEP_SYMBOL: 0x100020,
        }
        self.memory = {
            0x100010: bytearray(b'\x00'),
            0x100020: bytearray(bytes([no_fixed_step])),
            self.APP_PTR + APP_USE_FIXED_STEP_OFFSET: bytearray(bytes([0 if no_fixed_step else 1])),
            self.APP_PTR + APP_ACCUMULATOR_OFFSET: bytearray(struct.pack('<f', 0.0)),
            self.APP_PTR + APP_TIME_SCALE_OFFSET: bytearray(struct.pack('<f', 1.0)),
        }
        self.app_ptr = app_ptr
        self.writes = []
        self.events = []
        self.live = True
        self.tainted = False
        self.cleanup_pending = False
        self.stop_error = None
        self.resume_error = None
        self.write_error_on_call = None
        self.readback_tamper = {}

    def _quarantined_error(self):
        return AdapterError('detach_failed', 'hades.error.detachFailed', diagnostic='quarantined')

    def alive(self):
        return self.live

    def stop(self, deadline):
        self.events.append('stop')
        if self.stop_error is not None:
            raise self.stop_error

    def resume(self, deadline):
        self.events.append('resume')
        if self.resume_error is not None:
            raise self.resume_error

    def read_pointer(self, address):
        assert address == self.addresses[APP_INSTANCE_SYMBOL]
        return self.app_ptr

    def read_memory(self, address, size):
        if address in self.readback_tamper:
            return self.readback_tamper[address]
        assert address in self.memory and len(self.memory[address]) == size, (hex(address), size)
        return bytes(self.memory[address])

    def write_memory(self, address, data):
        self.writes.append((address, bytes(data)))
        if self.write_error_on_call is not None and len(self.writes) >= self.write_error_on_call:
            raise AdapterError('memory_error', 'hades.error.debuggerCall', diagnostic='synthetic write error')
        self.memory[address] = bytearray(data)


t = Transport()
owner = HadesSimulationTimeWarp(t)

# Clean 1.0 state: current_speed and reset perform zero memory writes.
assert owner.current_speed() == 1.0
assert t.writes == [] and t.events == ['stop', 'resume']
assert owner.reset() == 1.0
assert t.writes == [] and t.events == ['stop', 'resume', 'stop', 'resume']

# 0x freeze: sets TimeScale = 0.0, AUTO_RESET = 1, clears Accumulator, switches UseFixedStep = 0
# so App::Update(0.0f) stays live for input and _boundary().
t.memory[t.APP_PTR + APP_ACCUMULATOR_OFFSET] = bytearray(struct.pack('<f', 0.015))
assert owner.set_speed(0) == 0.0
assert struct.unpack('<f', t.memory[t.APP_PTR + APP_TIME_SCALE_OFFSET])[0] == 0.0
assert t.memory[0x100010] == b'\x01'
assert t.memory[t.APP_PTR + APP_USE_FIXED_STEP_OFFSET] == b'\x00'
assert struct.unpack('<f', t.memory[t.APP_PTR + APP_ACCUMULATOR_OFFSET])[0] == 0.0
assert owner.current_speed() == 0.0

# 0x -> 2.0x: clears Accumulator and restores UseFixedStep = 1 for deterministic fixed stepping.
t.writes.clear()
t.memory[t.APP_PTR + APP_ACCUMULATOR_OFFSET] = bytearray(struct.pack('<f', 0.012))
assert owner.set_speed(2) == 2.0
assert struct.unpack('<f', t.memory[t.APP_PTR + APP_TIME_SCALE_OFFSET])[0] == 2.0
assert t.memory[0x100010] == b'\x01'
assert t.memory[t.APP_PTR + APP_USE_FIXED_STEP_OFFSET] == b'\x01'
assert struct.unpack('<f', t.memory[t.APP_PTR + APP_ACCUMULATOR_OFFSET])[0] == 0.0

# Non-dyadic float (0.3x) round-trips within 1e-6 float32 tolerance without mismatching readback.
actual_03 = owner.set_speed(0.3)
assert abs(actual_03 - 0.3) < 1e-6
assert owner.set_speed(5.0) == 5.0
assert t.memory[t.APP_PTR + APP_USE_FIXED_STEP_OFFSET] == b'\x01'

# >5x (e.g. 7.5x, 10x): switches UseFixedStep = 0 to bypass the 0.083333336s (5-step) cap.
t.memory[t.APP_PTR + APP_ACCUMULATOR_OFFSET] = bytearray(struct.pack('<f', 0.01))
assert owner.set_speed(10) == 10.0
assert struct.unpack('<f', t.memory[t.APP_PTR + APP_TIME_SCALE_OFFSET])[0] == 10.0
assert t.memory[t.APP_PTR + APP_USE_FIXED_STEP_OFFSET] == b'\x00'
assert struct.unpack('<f', t.memory[t.APP_PTR + APP_ACCUMULATOR_OFFSET])[0] == 0.0

# Reset / 1x restores TimeScale = 1.0, AUTO_RESET = 0, UseFixedStep = 1, Accumulator = 0.0.
assert owner.reset() == 1.0
assert struct.unpack('<f', t.memory[t.APP_PTR + APP_TIME_SCALE_OFFSET])[0] == 1.0
assert t.memory[0x100010] == b'\x00'
assert t.memory[t.APP_PTR + APP_USE_FIXED_STEP_OFFSET] == b'\x01'
assert struct.unpack('<f', t.memory[t.APP_PTR + APP_ACCUMULATOR_OFFSET])[0] == 0.0

# Even if TimeScale is already 1.0, reset() cleans up leftover AUTO_RESET or UseFixedStep = 0.
t.memory[0x100010] = b'\x01'
t.memory[t.APP_PTR + APP_USE_FIXED_STEP_OFFSET] = b'\x00'
t.writes.clear()
assert owner.reset() == 1.0
assert t.writes and t.memory[0x100010] == b'\x00' and t.memory[t.APP_PTR + APP_USE_FIXED_STEP_OFFSET] == b'\x01'

# Native -NoFixedStep launch option (ConfigOptions::NoFixedStep = 1) must be preserved on reset.
t_nofixed = Transport(no_fixed_step=1)
owner_nofixed = HadesSimulationTimeWarp(t_nofixed)
assert owner_nofixed.set_speed(2.0) == 2.0
assert t_nofixed.memory[t_nofixed.APP_PTR + APP_USE_FIXED_STEP_OFFSET] == b'\x00'
assert owner_nofixed.reset() == 1.0
assert t_nofixed.memory[t_nofixed.APP_PTR + APP_USE_FIXED_STEP_OFFSET] == b'\x00'

# A matching TimeScale byte is insufficient if the game's auto-reset or fixed-
# step mode has drifted. 2x with AUTO_RESET=0 is restored to 1x next frame;
# 0x with FixedStep=1 can starve input and the debugger boundary.
for speed, wrong_field, wrong_value in (
    (2.0, 'auto', b'\x00'),
    (0.0, 'fixed', b'\x01'),
    (10.0, 'fixed', b'\x01'),
    (1.0, 'auto', b'\x01'),
):
    drift_transport = Transport()
    drift_owner = HadesSimulationTimeWarp(drift_transport)
    assert drift_owner.set_speed(speed) == speed
    address = (
        drift_transport.addresses[AUTO_RESET_SYMBOL]
        if wrong_field == 'auto'
        else drift_transport.APP_PTR + APP_USE_FIXED_STEP_OFFSET
    )
    drift_transport.memory[address] = bytearray(wrong_value)
    write_count = len(drift_transport.writes)
    try:
        drift_owner.current_speed()
    except AdapterError as error:
        assert error.code == 'time_warp_verify_failed' and not drift_transport.tainted
        assert 'autoReset=' in error.arguments[0] and 'fixedStep=' in error.arguments[1]
    else:
        raise AssertionError(f'inconsistent engine clock flags passed readback at {speed}x')
    assert len(drift_transport.writes) == write_count, 'readback modified target state'
    assert drift_transport.events[-1] == 'resume', 'readback left target paused'
    assert drift_owner.reset() == 1.0, 'explicit reset must recover valid drift'

# Validation failures must never stop or write to target memory.
t.writes.clear()
t.events.clear()
for invalid in (True, False, -0.001, 10.001, float('nan'), float('inf'), '1', None):
    try:
        owner.set_speed(invalid)
    except AdapterError as error:
        assert error.code == 'invalid_value'
    else:
        raise AssertionError(f'invalid speed accepted: {invalid!r}')
assert not t.writes and not t.events and not t.tainted

# Pre-initialization null App::INSTANCE fails current/set with runtime_not_ready (untainted),
# while reset() on clean null App returns 1.0 without wedging early detach.
t_early = Transport(app_ptr=0)
early_owner = HadesSimulationTimeWarp(t_early)
for fn in (early_owner.current_speed, lambda: early_owner.set_speed(2.0)):
    try:
        fn()
    except AdapterError as error:
        assert error.code == 'runtime_not_ready' and not t_early.tainted
    else:
        raise AssertionError('null App::INSTANCE was accepted')
assert early_owner.reset() == 1.0 and not t_early.tainted

# Initial stop failure must not call resume or taint the process.
t_stop = Transport()
t_stop.stop_error = AdapterError('stop_timeout', 'hades.error.stopTimeout')
stop_owner = HadesSimulationTimeWarp(t_stop)
try:
    stop_owner.set_speed(2.0)
except AdapterError as error:
    assert error.code == 'stop_timeout' and not t_stop.tainted and t_stop.events == ['stop']
else:
    raise AssertionError('stop timeout was hidden')

# Out-of-range or non-finite reads raise verifyFailed with (target, actual) arguments without taint,
# while write/readback or resume failures mark the transport tainted with outcome_unknown.
t.memory[t.APP_PTR + APP_TIME_SCALE_OFFSET] = bytearray(struct.pack('<f', 12.0))
try:
    owner.current_speed()
except AdapterError as error:
    assert error.code == 'time_warp_verify_failed' and error.arguments == ['0..10', '12'] and not t.tainted
else:
    raise AssertionError('out-of-range speed accepted in current_speed')
assert owner.reset() == 1.0  # reset recovers cleanly from finite >10 value

for bad_value, expected_actual in ((-1.0, '-1'), (float('nan'), 'nan')):
    t.memory[t.APP_PTR + APP_TIME_SCALE_OFFSET] = bytearray(struct.pack('<f', bad_value))
    try:
        owner.current_speed()
    except AdapterError as error:
        assert error.code == 'time_warp_verify_failed' and error.arguments == ['0..10', expected_actual]
        assert not t.tainted
    else:
        raise AssertionError('non-finite/negative speed accepted in current_speed')
    try:
        owner.set_speed(2.0)
    except AdapterError as error:
        assert error.code == 'time_warp_verify_failed' and error.arguments == ['2', expected_actual]
        assert not t.tainted
    else:
        raise AssertionError('non-finite/negative prior speed mutated by set_speed')
t.memory[t.APP_PTR + APP_TIME_SCALE_OFFSET] = bytearray(struct.pack('<f', 1.0))

# Subnormal speeds that pack to IEEE-754 float32 0.0 must still route to variable-step mode.
assert owner.set_speed(1e-46) == 0.0
assert t.memory[t.APP_PTR + APP_USE_FIXED_STEP_OFFSET] == b'\x00'
assert owner.reset() == 1.0

t.readback_tamper[t.APP_PTR + APP_TIME_SCALE_OFFSET] = struct.pack('<f', 9.0)
try:
    owner.set_speed(3.0)
except AdapterError as error:
    assert error.code == 'outcome_unknown' and error.presentation == 'hades.error.outcomeUnknown'
    assert t.tainted
else:
    raise AssertionError('mismatched readback accepted')
t.readback_tamper.clear()
t.tainted = False

t.resume_error = AdapterError('resume_timeout', 'hades.error.resumeFailed', diagnostic='resume stalled')
try:
    owner.current_speed()
except AdapterError as error:
    assert error.code == 'outcome_unknown' and t.tainted and 'resume stalled' in (error.diagnostic or '')
else:
    raise AssertionError('resume timeout was hidden')

print('hades_simulation_time_warp_controller_contract_ok')
