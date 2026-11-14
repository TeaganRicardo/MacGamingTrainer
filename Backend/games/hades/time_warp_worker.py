"""Hades I sidecar extension for the game-native simulation-time owner."""
import sys

from core.adapter import AdapterError
from core.sidecar import serve_jsonl_requests
from .lldb_worker import HadesLLDBWorker, error_payload as runtime_error_payload
from .simulation_time_warp import HadesSimulationTimeWarp


def error_payload(error):
    payload = runtime_error_payload(error)
    recovery = {'outcome_unknown': 'outcomeUnknown', 'restart_required': 'restartRequired'}
    if payload['code'] in recovery:
        payload['presentation'] = 'hades.error.' + recovery[payload['code']]
        payload['arguments'] = []
    return payload


class HadesTimeWarpWorker(HadesLLDBWorker):
    def __init__(self, transport=None, time_warp_factory=None):
        super().__init__(transport)
        self.time_warp = (time_warp_factory or HadesSimulationTimeWarp)(self.transport)

    def dispatch(self, method, params):
        if not isinstance(params, dict):
            raise ValueError('Hades worker params must be an object')
        if method in ('time_warp.current_speed', 'time_warp.set_speed'):
            if getattr(self.transport, 'cleanup_pending', False):
                raise self.transport._quarantined_error()
            if not self.transport.alive():
                raise AdapterError('not_connected', 'hades.error.notConnected')
            if method == 'time_warp.current_speed':
                speed = self.time_warp.current_speed()
            else:
                value = params.get('value')
                reset = type(value) in (int, float) and value == 1
                speed = self.time_warp.reset() if reset else self.time_warp.set_speed(value)
            return {'connected': True, 'pid': self.transport.pid, 'gameSpeed': speed}
        if (method == 'disconnect' and self.transport.alive()
                and not getattr(self.transport, 'cleanup_pending', False)):
            # Never detach after an uncertain native reset: the attachment is
            # the sole same-process recovery opportunity.
            self.time_warp.reset()
        return super().dispatch(method, params)

    def close(self):
        # The JSONL server also exits on EOF and protocol failure, without
        # receiving an explicit "disconnect" method. Release an active speed
        # lease before the debugger is detached on those ordinary exit paths.
        # On reset failure leave the attachment intact; its outcome may be
        # unknown and a forced detach would strand the live target.
        if self.transport.alive() and not getattr(self.transport, 'cleanup_pending', False):
            self.time_warp.reset()
        self.transport.close()


def main():
    worker = HadesTimeWarpWorker()
    try:
        serve_jsonl_requests(sys.stdin, sys.stdout, worker.dispatch, error_payload=error_payload)
    finally:
        worker.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
