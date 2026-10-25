"""Hades-only methods over the generic Core sidecar framing contract."""
import json
from pathlib import Path
import sys
import traceback

from core.adapter import AdapterError
from core.sidecar import serve_jsonl_requests


class HadesLLDBWorker:
    def __init__(self, transport=None):
        if transport is None:
            from .transport import HadesLuaTransport
            transport = HadesLuaTransport()
        self.transport = transport
        self.source = Path(__file__).with_name('runtime.lua').read_text()

    def _status(self, *, enabled=None):
        source = 'local runtime = (function()\n' + self.source + '\nend)()\n'
        if enabled is None:
            source += 'return runtime.json(runtime.status())'
        else:
            source += 'return runtime.json(runtime.set_invincibility(' + str(enabled).lower() + '))'
        result = self.transport.execute(source, mutating=enabled is not None)
        result.update({'connected': True, 'pid': self.transport.pid})
        return result

    def dispatch(self, method, params):
        if method == 'connect':
            pid = params.get('pid')
            executable = params.get('executable')
            if type(pid) is not int or pid <= 0 or not isinstance(executable, str) or not executable:
                raise ValueError('connect requires a target pid and executable path')
            self.transport.attach(pid, executable)
            return self._status()
        if method == 'disconnect':
            self.transport.detach()
        elif method == 'status':
            if self.transport.alive():
                return self._status()
        elif method == 'set_invincibility':
            value = params.get('value')
            if type(value) is not bool:
                raise ValueError('set_invincibility requires a boolean value')
            if not self.transport.alive():
                raise AdapterError('not_connected', 'hades.error.notConnected')
            return self._status(enabled=value)
        else:
            raise ValueError('unsupported Hades worker method: ' + method)
        from .adapter import HadesAdapter
        return HadesAdapter._offline()


def error_payload(error):
    if isinstance(error, AdapterError):
        return {'code': error.code, 'presentation': error.presentation,
                'diagnostic': error.diagnostic, 'arguments': error.arguments}
    return {'code': 'debugger_internal', 'presentation': 'hades.error.debuggerCall',
            'diagnostic': ''.join(traceback.format_exception(type(error), error, error.__traceback__)),
            'arguments': []}


def main():
    worker = HadesLLDBWorker()
    try:
        serve_jsonl_requests(sys.stdin, sys.stdout, worker.dispatch, error_payload=error_payload)
    finally:
        worker.transport.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
