"""Hades I simulation-time controller over the owned game Lua execution boundary.

The Lua module owns game-specific speed semantics. A command is confirmed
only after reading the Lua owner's receipt.
"""
import json
import math
from pathlib import Path

from core.adapter import AdapterError


class HadesSimulationTimeWarp:
    MINIMUM = 0.0
    MAXIMUM = 10.0

    def __init__(self, transport, source_path=None):
        self.transport = transport
        path = Path(source_path) if source_path is not None else Path(__file__).with_name('simulation_time_warp.lua')
        self.source = path.read_text(encoding='utf-8')

    @classmethod
    def _validate_speed(cls, value):
        if type(value) not in (int, float):
            raise AdapterError('invalid_value', 'hades.error.invalidValue')
        speed = float(value)
        if not math.isfinite(speed) or not cls.MINIMUM <= speed <= cls.MAXIMUM:
            raise AdapterError('invalid_value', 'hades.error.invalidValue')
        return speed

    def _invalid_receipt(self, operation, detail, *, verify=False):
        if operation == 'set':
            # The Lua native speed owner may have applied the requested speed.
            # A contradictory receipt cannot be treated as a retryable failure.
            self.transport.tainted = True
            raise AdapterError('outcome_unknown', 'hades.error.outcomeUnknown', diagnostic=detail)
        code = 'time_warp_verify_failed' if verify else 'debugger_protocol'
        key = 'host.timeWarp.error.verifyFailed' if verify else 'hades.error.debuggerProtocol'
        raise AdapterError(code, key, diagnostic=detail)

    def _execute(self, operation, value=None):
        source = 'local timeWarp = (function()\n' + self.source + '\nend)()\n'
        if operation == 'set':
            source += 'return timeWarp.set(' + json.dumps(value, allow_nan=False) + ')'
        else:
            source += 'return timeWarp.current()'
        receipt = self.transport.execute(source, mutating=operation == 'set')
        if not isinstance(receipt, dict):
            self._invalid_receipt(operation, 'native simulation-time receipt is not a JSON object')
        speed = receipt.get('multiplier')
        native = receipt.get('nativeFraction')
        effective = receipt.get('effectiveFraction')
        installed = receipt.get('wrapperInstalled')
        if (type(speed) not in (int, float) or not math.isfinite(float(speed))
                or not self.MINIMUM <= speed <= self.MAXIMUM
                or type(native) not in (int, float) or not math.isfinite(float(native))
                or type(effective) not in (int, float) or not math.isfinite(float(effective))
                or type(installed) is not bool):
            self._invalid_receipt(operation, 'invalid native simulation-time receipt fields')
        if abs(float(effective) - float(native) * float(speed)) > 1e-6:
            self._invalid_receipt(operation, 'effective simulation fraction disagrees with native multiplied fraction', verify=True)
        if operation == 'set' and (not installed or abs(float(speed) - value) > 1e-6):
            self._invalid_receipt(operation, 'Lua speed owner did not confirm the applied multiplier', verify=True)
        return receipt

    def current_speed(self):
        return float(self._execute('current')['multiplier'])

    def set_speed(self, value):
        speed = self._validate_speed(value)
        return float(self._execute('set', speed)['multiplier'])

    def reset(self):
        observation = self._execute('current')
        if not observation['wrapperInstalled'] or observation['multiplier'] == 1.0:
            return 1.0
        return self.set_speed(1.0)
