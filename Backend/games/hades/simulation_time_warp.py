"""Hades I global simulation-time controller over sgg::App::TimeScale.

Owns direct stopped-process inspection and mutation of the supported Intel build's
engine-wide frame clock (`sgg::App::TimeScale`, `sgg::Debug::AUTO_RESET_TIME_SCALE`,
and `App` fixed-step state), leaving Lua `World::SimulationSpeed` (`hitstop`) untouched.
"""
import math
import struct
import sys
import time

from core.adapter import AdapterError, HostPresentationError
from .operation_budgets import PROCESS_CONTROL_TIMEOUT_SECONDS

APP_INSTANCE_SYMBOL = '_ZN3sgg3App8INSTANCEE'
AUTO_RESET_SYMBOL = '_ZN3sgg5Debug21AUTO_RESET_TIME_SCALEE'
NO_FIXED_STEP_SYMBOL = '_ZN3sgg13ConfigOptions11NoFixedStepE'

APP_USE_FIXED_STEP_OFFSET = 0x1A
APP_ACCUMULATOR_OFFSET = 0x90
APP_TIME_SCALE_OFFSET = 0x94

_ZERO_FLOAT32 = struct.pack('<f', 0.0)
_ONE_FLOAT32 = struct.pack('<f', 1.0)


def _normalize_float(value):
    return 0.0 if value == 0.0 else float(value)


class HadesSimulationTimeWarp:
    MINIMUM = 0.0
    MAXIMUM = 10.0
    FIXED_STEP_MAXIMUM = 5.0
    BOUNDED_TIMEOUT_SECONDS = PROCESS_CONTROL_TIMEOUT_SECONDS

    def __init__(self, transport):
        self.transport = transport

    @classmethod
    def _validate_speed(cls, value):
        if type(value) not in (int, float):
            raise AdapterError('invalid_value', 'hades.error.invalidValue')
        speed = float(value)
        if not math.isfinite(speed) or not cls.MINIMUM <= speed <= cls.MAXIMUM:
            raise AdapterError('invalid_value', 'hades.error.invalidValue')
        return _normalize_float(speed)

    def _require_usable_transport(self, *, allow_tainted_cleanup=False):
        if getattr(self.transport, 'cleanup_pending', False):
            raise self.transport._quarantined_error()
        if getattr(self.transport, 'tainted', False) and not allow_tainted_cleanup:
            raise AdapterError('restart_required', 'hades.error.restartRequired')
        if not self.transport.alive():
            raise AdapterError('not_connected', 'hades.error.notConnected')
        addresses = getattr(self.transport, 'addresses', None) or {}
        missing = [
            symbol for symbol in (APP_INSTANCE_SYMBOL, AUTO_RESET_SYMBOL, NO_FIXED_STEP_SYMBOL)
            if symbol not in addresses
        ]
        if missing:
            raise AdapterError(
                'incompatible',
                'hades.error.unsupportedBuild',
                diagnostic='Missing native Time Warp symbols: ' + ', '.join(missing),
            )
        return (
            addresses[APP_INSTANCE_SYMBOL],
            addresses[AUTO_RESET_SYMBOL],
            addresses[NO_FIXED_STEP_SYMBOL],
        )

    def _with_stopped_process(self, operation, *, allow_tainted_cleanup=False):
        app_instance_addr, auto_reset_addr, no_fixed_step_addr = self._require_usable_transport(
            allow_tainted_cleanup=allow_tainted_cleanup
        )
        stopped = False
        try:
            self.transport.stop(time.monotonic() + self.BOUNDED_TIMEOUT_SECONDS)
            stopped = True
            return operation(app_instance_addr, auto_reset_addr, no_fixed_step_addr)
        finally:
            primary_error = sys.exc_info()[1]
            if stopped and self.transport.alive():
                try:
                    self.transport.resume(time.monotonic() + self.BOUNDED_TIMEOUT_SECONDS)
                except Exception as resume_error:
                    self.transport.tainted = True
                    detail = getattr(resume_error, 'diagnostic', None) or str(resume_error)
                    if primary_error is not None:
                        original = getattr(primary_error, 'diagnostic', None) or str(primary_error)
                        detail = f'{original}; resume: {detail}' if original else f'resume: {detail}'
                    raise AdapterError(
                        'outcome_unknown', 'hades.error.outcomeUnknown', diagnostic=detail
                    ) from resume_error

    def _read_snapshot(self, app_instance_addr, auto_reset_addr, no_fixed_step_addr, *, allow_null_on_reset=False):
        app_ptr = self.transport.read_pointer(app_instance_addr)
        auto_reset_raw = self.transport.read_memory(auto_reset_addr, 1)
        if auto_reset_raw not in (b'\x00', b'\x01'):
            raise AdapterError(
                'incompatible',
                'hades.error.unsupportedBuild',
                diagnostic='Unexpected sgg::Debug::AUTO_RESET_TIME_SCALE flag byte',
            )
        if app_ptr == 0:
            if allow_null_on_reset and auto_reset_raw == b'\x00':
                return None
            raise AdapterError(
                'runtime_not_ready',
                'hades.error.runtimeNotReady',
                diagnostic='sgg::App::INSTANCE is null',
            )
        no_fixed_step_raw = self.transport.read_memory(no_fixed_step_addr, 1)
        use_fixed_step_raw = self.transport.read_memory(app_ptr + APP_USE_FIXED_STEP_OFFSET, 1)
        time_scale_raw = self.transport.read_memory(app_ptr + APP_TIME_SCALE_OFFSET, 4)
        if no_fixed_step_raw not in (b'\x00', b'\x01') or use_fixed_step_raw not in (b'\x00', b'\x01'):
            raise AdapterError(
                'incompatible',
                'hades.error.unsupportedBuild',
                diagnostic='Unexpected sgg::App fixed-step flag byte',
            )
        time_scale = _normalize_float(struct.unpack('<f', time_scale_raw)[0])
        return (
            app_ptr,
            auto_reset_raw,
            no_fixed_step_raw,
            use_fixed_step_raw,
            time_scale_raw,
            time_scale,
        )

    def _verify_finite_non_negative(self, time_scale, *, target='0..10'):
        if not math.isfinite(time_scale) or time_scale < self.MINIMUM:
            observed = f'{time_scale:g}' if math.isfinite(time_scale) else str(time_scale)
            raise HostPresentationError(
                'time_warp_verify_failed',
                'host.timeWarp.error.verifyFailed',
                arguments=(target, observed),
                diagnostic=f'Observed sgg::App::TimeScale is invalid: {observed}',
            )

    def _verify_finite_range(self, time_scale):
        target = f'{self.MINIMUM:g}..{self.MAXIMUM:g}'
        self._verify_finite_non_negative(time_scale, target=target)
        if time_scale > self.MAXIMUM:
            observed = f'{time_scale:g}'
            raise HostPresentationError(
                'time_warp_verify_failed',
                'host.timeWarp.error.verifyFailed',
                arguments=(target, observed),
                diagnostic=f'Observed sgg::App::TimeScale out of supported range: {observed}',
            )

    def _expected_owner_flags(self, time_scale, no_fixed_step_raw):
        baseline_step = b'\x00' if no_fixed_step_raw == b'\x01' else b'\x01'
        use_fixed_step = (
            b'\x00'
            if time_scale == 0.0 or time_scale > self.FIXED_STEP_MAXIMUM
            else baseline_step
        )
        auto_reset = b'\x00' if time_scale == 1.0 else b'\x01'
        return use_fixed_step, auto_reset

    def current_speed(self):
        def read_op(app_instance_addr, auto_reset_addr, no_fixed_step_addr):
            snapshot = self._read_snapshot(app_instance_addr, auto_reset_addr, no_fixed_step_addr)
            _, auto_reset_raw, no_fixed_step_raw, use_fixed_step_raw, _, time_scale = snapshot
            self._verify_finite_range(time_scale)
            expected_fixed_step, expected_auto_reset = self._expected_owner_flags(
                time_scale, no_fixed_step_raw
            )
            if (auto_reset_raw != expected_auto_reset
                    or use_fixed_step_raw != expected_fixed_step):
                expected = (
                    f'autoReset={expected_auto_reset[0]}, fixedStep={expected_fixed_step[0]}'
                )
                observed = (
                    f'autoReset={auto_reset_raw[0]}, fixedStep={use_fixed_step_raw[0]}'
                )
                raise HostPresentationError(
                    'time_warp_verify_failed',
                    'host.timeWarp.error.verifyFailed',
                    arguments=(expected, observed),
                    diagnostic=(
                        f'sgg::App::TimeScale={time_scale:g} has inconsistent '
                        f'engine clock control flags: expected {expected}, observed {observed}'
                    ),
                )
            return time_scale

        return self._with_stopped_process(read_op)

    def _apply_speed(self, target_speed, *, skip_if_clean=False, allow_tainted_cleanup=False):
        def write_op(app_instance_addr, auto_reset_addr, no_fixed_step_addr):
            snapshot = self._read_snapshot(
                app_instance_addr,
                auto_reset_addr,
                no_fixed_step_addr,
                allow_null_on_reset=skip_if_clean,
            )
            if snapshot is None:
                return 1.0
            (
                app_ptr,
                auto_reset_raw,
                no_fixed_step_raw,
                use_fixed_step_raw,
                time_scale_raw,
                current_scale,
            ) = snapshot
            packed_speed = _ONE_FLOAT32 if target_speed == 1.0 else struct.pack('<f', target_speed)
            effective_speed = _normalize_float(struct.unpack('<f', packed_speed)[0])
            self._verify_finite_non_negative(current_scale, target=f'{effective_speed:g}')

            expected_fixed_step = b'\x00' if no_fixed_step_raw == b'\x01' else b'\x01'
            # At 0x, FixedStep stops calling sgg::App::Update, freezing input and
            # starving the LLDB boundary. Above 5x, the fixed-step accumulator has
            # a five-step limit. The variable-step branch avoids both constraints.
            target_fixed_step, target_auto_reset = self._expected_owner_flags(
                effective_speed, no_fixed_step_raw
            )
            if effective_speed == 1.0:
                packed_speed = _ONE_FLOAT32

            if (
                skip_if_clean
                and time_scale_raw == packed_speed
                and auto_reset_raw == b'\x00'
                and use_fixed_step_raw == expected_fixed_step
            ):
                return 1.0

            switch_step_mode = use_fixed_step_raw != target_fixed_step
            clear_accumulator = switch_step_mode or effective_speed == 0.0 or effective_speed == 1.0

            try:
                if effective_speed == 1.0:
                    if clear_accumulator:
                        self.transport.write_memory(app_ptr + APP_ACCUMULATOR_OFFSET, _ZERO_FLOAT32)
                    if switch_step_mode:
                        self.transport.write_memory(app_ptr + APP_USE_FIXED_STEP_OFFSET, target_fixed_step)
                    self.transport.write_memory(app_ptr + APP_TIME_SCALE_OFFSET, packed_speed)
                    self.transport.write_memory(auto_reset_addr, target_auto_reset)
                else:
                    self.transport.write_memory(auto_reset_addr, target_auto_reset)
                    self.transport.write_memory(app_ptr + APP_TIME_SCALE_OFFSET, packed_speed)
                    if clear_accumulator:
                        self.transport.write_memory(app_ptr + APP_ACCUMULATOR_OFFSET, _ZERO_FLOAT32)
                    if switch_step_mode:
                        self.transport.write_memory(app_ptr + APP_USE_FIXED_STEP_OFFSET, target_fixed_step)

                observed_auto_reset = self.transport.read_memory(auto_reset_addr, 1)
                observed_fixed_step = self.transport.read_memory(app_ptr + APP_USE_FIXED_STEP_OFFSET, 1)
                observed_scale_raw = self.transport.read_memory(app_ptr + APP_TIME_SCALE_OFFSET, 4)
                if (
                    observed_auto_reset != target_auto_reset
                    or observed_fixed_step != target_fixed_step
                    or observed_scale_raw != packed_speed
                ):
                    raise AdapterError(
                        'outcome_unknown',
                        'hades.error.outcomeUnknown',
                        diagnostic='Hades App clock readback did not match written TimeScale state',
                    )
                if clear_accumulator:
                    observed_acc = self.transport.read_memory(app_ptr + APP_ACCUMULATOR_OFFSET, 4)
                    if observed_acc != _ZERO_FLOAT32:
                        raise AdapterError(
                            'outcome_unknown',
                            'hades.error.outcomeUnknown',
                            diagnostic='Hades App accumulator readback did not clear to zero',
                        )
                return _normalize_float(struct.unpack('<f', observed_scale_raw)[0])
            except Exception as error:
                self.transport.tainted = True
                if isinstance(error, AdapterError) and error.code == 'outcome_unknown':
                    raise
                detail = getattr(error, 'diagnostic', None) or str(error)
                raise AdapterError('outcome_unknown', 'hades.error.outcomeUnknown', diagnostic=detail) from error

        return self._with_stopped_process(
            write_op, allow_tainted_cleanup=allow_tainted_cleanup
        )

    def set_speed(self, value):
        speed = self._validate_speed(value)
        return self._apply_speed(speed, skip_if_clean=False)

    def reset(self):
        return self._apply_speed(1.0, skip_if_clean=True)

    def reset_for_close(self):
        """Best-effort idempotent clock release on EOF after a non-VM taint.

        The native 1x reset never replays a Lua mutation. It must complete
        stopped-process readback before the debugger may detach. The worker
        excludes interrupted Lua VMs, whose separate exit path kills the game.
        """
        return self._apply_speed(1.0, skip_if_clean=True, allow_tainted_cleanup=True)
