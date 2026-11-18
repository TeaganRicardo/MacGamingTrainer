"""Hades I Time Warp uses engine-global sgg::App::TimeScale and resets before detach."""
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
from core.adapter import AdapterError
from games.hades.time_warp_worker import HadesTimeWarpWorker, error_payload
from games.hades.simulation_time_warp import (
    APP_ACCUMULATOR_OFFSET,
    APP_INSTANCE_SYMBOL,
    APP_TIME_SCALE_OFFSET,
    APP_USE_FIXED_STEP_OFFSET,
    AUTO_RESET_SYMBOL,
    HadesSimulationTimeWarp,
    NO_FIXED_STEP_SYMBOL,
)


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


class MemoryTransport:
    pid = 42
    APP_PTR = 0x200000

    def __init__(self):
        self.attached = True
        self.tainted = False
        self.cleanup_pending = False
        self.vm_interrupted = False
        self.detaches = 0
        self.addresses = {
            APP_INSTANCE_SYMBOL: 0x100000,
            AUTO_RESET_SYMBOL: 0x100010,
            NO_FIXED_STEP_SYMBOL: 0x100020,
        }
        self.memory = {
            0x100010: bytearray(b'\x00'),
            0x100020: bytearray(b'\x00'),
            self.APP_PTR + APP_USE_FIXED_STEP_OFFSET: bytearray(b'\x01'),
            self.APP_PTR + APP_ACCUMULATOR_OFFSET: bytearray(struct.pack('<f', 0.0)),
            self.APP_PTR + APP_TIME_SCALE_OFFSET: bytearray(struct.pack('<f', 1.0)),
        }
        self.writes = []

    def alive(self):
        return self.attached

    def stop(self, deadline):
        pass

    def resume(self, deadline):
        pass

    def read_pointer(self, address):
        return self.APP_PTR

    def read_memory(self, address, size):
        return bytes(self.memory[address])

    def write_memory(self, address, data):
        self.writes.append((address, bytes(data)))
        self.memory[address] = bytearray(data)

    def detach(self):
        self.detaches += 1
        self.attached = False

    def close(self):
        self.detach()


transport = FakeTransport()
time_warp = FakeTimeWarp()
worker = HadesTimeWarpWorker(transport=transport, time_warp_factory=lambda _: time_warp)
assert worker.dispatch('time_warp.current_speed', {})['gameSpeed'] == 1.0
assert worker.dispatch('time_warp.set_speed', {'value': 2.5})['gameSpeed'] == 2.5
assert worker.dispatch('time_warp.current_speed', {})['gameSpeed'] == 2.5
assert time_warp.events == [('current', None), ('set', 2.5), ('current', None)]

memory_transport = MemoryTransport()
app_warp = HadesSimulationTimeWarp(memory_transport)
real_worker = HadesTimeWarpWorker(transport=memory_transport, time_warp_factory=lambda _: app_warp)
assert app_warp.current_speed() == 1.0
assert memory_transport.writes == []
assert app_warp.reset() == 1.0
assert memory_transport.writes == []
assert real_worker.dispatch('time_warp.set_speed', {'value': 2.5})['gameSpeed'] == 2.5
assert memory_transport.memory[0x100010] == b'\x01'
assert memory_transport.memory[memory_transport.APP_PTR + APP_USE_FIXED_STEP_OFFSET] == b'\x01'
assert app_warp.current_speed() == 2.5
assert real_worker.dispatch('time_warp.set_speed', {'value': 0.0})['gameSpeed'] == 0.0
assert memory_transport.memory[memory_transport.APP_PTR + APP_USE_FIXED_STEP_OFFSET] == b'\x00'
assert real_worker.dispatch('time_warp.set_speed', {'value': 8.0})['gameSpeed'] == 8.0
assert memory_transport.memory[memory_transport.APP_PTR + APP_USE_FIXED_STEP_OFFSET] == b'\x00'
state_disconnected = real_worker.dispatch('disconnect', {})
assert not state_disconnected['connected'] and memory_transport.detaches == 1
assert struct.unpack('<f', memory_transport.memory[memory_transport.APP_PTR + APP_TIME_SCALE_OFFSET])[0] == 1.0
assert memory_transport.memory[0x100010] == b'\x00'
assert memory_transport.memory[memory_transport.APP_PTR + APP_USE_FIXED_STEP_OFFSET] == b'\x01'
for invalid in (True, -0.1, 10.1, float('nan'), float('inf'), '2'):
    try:
        app_warp.set_speed(invalid)
    except AdapterError as error:
        assert error.code == 'invalid_value'
    else:
        raise AssertionError(f'invalid App::TimeScale speed accepted: {invalid!r}')

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

known_failure = AdapterError('time_warp_verify_failed', 'host.timeWarp.error.verifyFailed')
assert error_payload(known_failure)['presentation'] == known_failure.presentation
interrupted = AdapterError('outcome_unknown', 'hades.error.luaInterrupted', diagnostic='native interruption')
assert error_payload(interrupted)['presentation'] == 'hades.error.luaInterrupted'
exit_failed = AdapterError('outcome_unknown', 'hades.error.luaTerminationFailed', diagnostic='native kill failed')
assert error_payload(exit_failed)['presentation'] == 'hades.error.luaTerminationFailed'

# An interrupted VM must not enter another native reset on disconnect or EOF.
for operation in ('disconnect', 'close'):
    interrupted_transport = FakeTransport()
    interrupted_transport.vm_interrupted = True
    interrupted_time_warp = FakeTimeWarp()
    interrupted_worker = HadesTimeWarpWorker(transport=interrupted_transport,
                                           time_warp_factory=lambda _: interrupted_time_warp)
    if operation == 'disconnect':
        interrupted_worker.dispatch('disconnect', {})
    else:
        interrupted_worker.close()
    assert interrupted_time_warp.events == [] and interrupted_transport.detaches == 1

# An already-tainted transport keeps explicit disconnect blocked with restart_required,
# yet EOF close still releases the debugger instead of crashing before transport.close().
tainted_transport = MemoryTransport()
tainted_worker = HadesTimeWarpWorker(
    transport=tainted_transport,
    time_warp_factory=HadesSimulationTimeWarp,
)
assert tainted_worker.dispatch('time_warp.set_speed', {'value': 0.0})['gameSpeed'] == 0.0
tainted_transport.tainted = True
try:
    tainted_worker.dispatch('disconnect', {})
except AdapterError as error:
    assert error.code == 'restart_required'
else:
    raise AssertionError('tainted disconnect was accepted')
assert tainted_transport.attached and tainted_transport.detaches == 0
tainted_worker.close()
assert not tainted_transport.attached and tainted_transport.detaches == 1
assert struct.unpack('<f', tainted_transport.memory[
    tainted_transport.APP_PTR + APP_TIME_SCALE_OFFSET
])[0] == 1.0, 'tainted EOF detached while 0x clock lease survived'
assert tainted_transport.memory[0x100010] == b'\x00'
assert tainted_transport.memory[tainted_transport.APP_PTR + APP_USE_FIXED_STEP_OFFSET] == b'\x01'

# A failed last-chance cleanup must preserve the debugger attachment; after
# the transport is writable again, EOF cleanup may be retried without replay.
failed_cleanup_transport = MemoryTransport()
failed_cleanup_worker = HadesTimeWarpWorker(
    transport=failed_cleanup_transport,
    time_warp_factory=HadesSimulationTimeWarp,
)
assert failed_cleanup_worker.dispatch('time_warp.set_speed', {'value': 0.0})['gameSpeed'] == 0.0
failed_cleanup_transport.tainted = True
original_write = failed_cleanup_transport.write_memory
def fail_cleanup_write(address, data):
    raise AdapterError('memory_error', 'hades.error.debuggerCall', diagnostic='write denied')
failed_cleanup_transport.write_memory = fail_cleanup_write
try:
    failed_cleanup_worker.close()
except AdapterError as error:
    assert error.code == 'outcome_unknown'
else:
    raise AssertionError('failed tainted EOF cleanup detached')
assert failed_cleanup_transport.attached and failed_cleanup_transport.detaches == 0
failed_cleanup_transport.write_memory = original_write
failed_cleanup_worker.close()
assert not failed_cleanup_transport.attached and failed_cleanup_transport.detaches == 1
assert struct.unpack('<f', failed_cleanup_transport.memory[
    failed_cleanup_transport.APP_PTR + APP_TIME_SCALE_OFFSET
])[0] == 1.0

print('hades_game_native_simulation_time_warp_worker_contract_ok')
