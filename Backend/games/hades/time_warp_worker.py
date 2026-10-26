"""Hades I sidecar extension for the Core-owned process Time Warp helper."""
from pathlib import Path
import sys

from core.adapter import AdapterError
from .lldb_time_warp import LLDBProcessTimeWarpDriver
from core.process_time_warp import ProcessTimeWarpController
from core.sidecar import serve_jsonl_requests

from .lldb_worker import HadesLLDBWorker, error_payload

HADES_TIME_WARP_IMAGE_NAMES = ('Game.macOS',)


class HadesTimeWarpWorker(HadesLLDBWorker):
    def __init__(self, transport=None, time_warp_factory=None):
        super().__init__(transport)
        self.time_warp = (time_warp_factory or self._default_time_warp_factory)(self.transport)

    @staticmethod
    def _default_time_warp_factory(transport):
        helper = Path(__file__).resolve().parents[2] / 'core/native/libMGTTimeWarp.dylib'
        return ProcessTimeWarpController(
            LLDBProcessTimeWarpDriver(transport), helper, HADES_TIME_WARP_IMAGE_NAMES
        )

    def dispatch(self, method, params):
        if not isinstance(params, dict):
            raise ValueError('Hades worker params must be an object')
        if method in ('time_warp.current_speed', 'time_warp.set_speed'):
            if not self.transport.alive():
                raise AdapterError('not_connected', 'hades.error.notConnected')
            if method == 'time_warp.current_speed':
                speed = self.time_warp.current_speed()
            else:
                value = params.get('value')
                reset = type(value) in (int, float) and value == 1
                speed = self.time_warp.reset() if reset else self.time_warp.set_speed(value)
            return {'connected': True, 'pid': self.transport.pid, 'gameSpeed': speed}
        if method == 'disconnect' and self.transport.alive():
            # Reset before releasing the only debugger transport. An uncertain
            # native outcome must retain the attachment for explicit recovery.
            self.time_warp.reset()
        return super().dispatch(method, params)


def main():
    worker = HadesTimeWarpWorker()
    try:
        serve_jsonl_requests(sys.stdin, sys.stdout, worker.dispatch, error_payload=error_payload)
    finally:
        worker.transport.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
