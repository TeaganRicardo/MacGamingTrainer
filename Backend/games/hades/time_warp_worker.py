"""Hades I sidecar extension for the game-native simulation-time owner."""
import sys

from core.adapter import AdapterError
from core.sidecar import serve_jsonl_requests

from .lldb_worker import HadesLLDBWorker, error_payload as runtime_error_payload
from .simulation_time_warp import HadesSimulationTimeWarp


class HadesTimeWarpWorker(HadesLLDBWorker):
    """Adds the game's native simulation-time owner to the Hades Lua bridge."""

    def __init__(self, transport=None, time_warp_factory=None):
        super().__init__(transport)
        self.time_warp = (time_warp_factory or HadesSimulationTimeWarp)(self.transport)

    def dispatch(self, method, params):
        if method == 'time_warp.current_speed':
            if not self.transport.alive():
                raise AdapterError('runtime_disconnected', 'hades.error.runtimeDisconnected')
            return {'gameSpeed': self.time_warp.current_speed()}
        if method == 'time_warp.set_speed':
            if not self.transport.alive():
                raise AdapterError('runtime_disconnected', 'hades.error.runtimeDisconnected')
            value = params.get('value')
            if type(value) not in (int, float):
                raise AdapterError('invalid_value', 'hades.error.invalidValue')
            reset = type(value) in (int, float) and value == 1
            applied = self.time_warp.reset() if reset else self.time_warp.set_speed(value)
            return {'gameSpeed': applied}
        if method == 'disconnect' and self.transport.alive():
            # Restore the Trainer multiplier before detaching. If the Lua
            # mutation is uncertain, retain this transport as the recovery path.
            self.time_warp.reset()
        return super().dispatch(method, params)


def error_payload(error):
    payload = runtime_error_payload(error)
    if payload.get('code') in ('outcome_unknown', 'restart_required'):
        payload['presentation'] = 'hades.error.' + (
            'outcomeUnknown' if payload['code'] == 'outcome_unknown' else 'restartRequired'
        )
        payload['arguments'] = []
        if payload.get('diagnostic') is None and error.arguments:
            payload['diagnostic'] = str(error.arguments[0])
    return payload


def main():
    worker = HadesTimeWarpWorker()
    try:
        serve_jsonl_requests(worker)
    except KeyboardInterrupt:
        pass
    except Exception as error:
        print(f"Hades Time Warp worker failed: {error}", file=sys.stderr)
        raise
    finally:
        worker.close()


if __name__ == '__main__':
    main()
