"""Hades-only methods over the generic Core sidecar framing contract."""
import json
from pathlib import Path
import sys
import traceback
import uuid

from core.adapter import AdapterError
from core.sidecar import serve_jsonl_requests
from .schema import DEFAULT_FEATURES, ONE_SHOT_COMMANDS, feature_document, feature_value


def lua_literal(value):
    if value is None:
        return 'nil'
    if type(value) is bool:
        return str(value).lower()
    if type(value) in (int, float):
        return json.dumps(value, allow_nan=False)
    if isinstance(value, str):
        return '"' + ''.join(chr(byte) if 32 <= byte < 127 and byte not in (34, 92)
                              else '\\' + str(byte).zfill(3) for byte in value.encode('utf-8')) + '"'
    if isinstance(value, dict):
        return '{' + ','.join('[' + lua_literal(key) + ']=' + lua_literal(item)
                              for key, item in value.items()) + '}'
    raise ValueError('Unsupported Hades Lua argument.')


class HadesLLDBWorker:
    def __init__(self, transport=None):
        if transport is None:
            from .transport import HadesLuaTransport
            transport = HadesLuaTransport()
        self.transport = transport
        self.source = Path(__file__).with_name('runtime.lua').read_text()
        self.features = dict(DEFAULT_FEATURES)

    def _invoke(self, method='status', arguments=(), *, target=None):
        source = 'local runtime = (function()\n' + self.source + '\nend)()\n'
        source += ('if not runtime.bootstrapId then runtime.bootstrapId=' + lua_literal(uuid.uuid4().hex)
                   + ';runtime.generationId=runtime.bootstrapId;runtime.configure('
                   + lua_literal(self.features) + ') end\n')
        if target is not None:
            source += ('assert(runtime.status().heroId==' + lua_literal(target['heroId'])
                       + ',"hades.error.staleTarget")\n')
        source += 'return runtime.json(runtime.' + method + '(' + ','.join(map(lua_literal, arguments)) + '))'
        result = self.transport.execute(source, mutating=True)
        result.update({'connected': True, 'pid': self.transport.pid})
        result['target'] = {'heroId': result.get('heroId', '')}
        return result

    def dispatch(self, method, params):
        if method == 'connect':
            pid = params.get('pid')
            executable = params.get('executable')
            if type(pid) is not int or pid <= 0 or not isinstance(executable, str) or not executable:
                raise ValueError('connect requires a target pid and executable path')
            if 'features' in params:
                self.features = feature_document(params['features'])
            self.transport.attach(pid, executable)
            return self._invoke('configure', (self.features,))
        if method == 'disconnect':
            self.transport.detach()
        elif method == 'status':
            if self.transport.alive():
                return self._invoke()
        elif method in ('set_feature', 'set_invincibility', 'configure', 'disable_all') or method in ONE_SHOT_COMMANDS:
            if not self.transport.alive():
                raise AdapterError('not_connected', 'hades.error.notConnected')
            if method == 'set_invincibility':
                method, params = 'set_feature', {'feature': 'invincibility', 'value': params.get('value')}
            target = None
            if method in ONE_SHOT_COMMANDS:
                target = params.get('target')
                if not isinstance(target, dict) or not isinstance(target.get('heroId'), str) or not target['heroId']:
                    raise AdapterError('stale_target', 'hades.error.staleTarget')
            if method == 'set_feature':
                name = params.get('feature')
                value = feature_value(name, params.get('value'))
                result = self._invoke(method, (name, value))
                self.features[name] = value
                return result
            if method == 'configure':
                values = feature_document(params.get('features'))
                result = self._invoke(method, (values,))
                self.features = values
                return result
            arguments = {
                'disable_all': (), 'heal': (),
                'set_value': (params.get('field'), params.get('value')),
                'set_resource': (params.get('resource'), params.get('value')),
                'add_trait': (params.get('trait'), params.get('rarity'), params.get('level')),
                'update_trait': (params.get('instanceId'), params.get('rarity'), params.get('level')),
                'remove_trait': (params.get('instanceId'),),
            }[method]
            result = self._invoke(method, arguments, target=target)
            if method == 'disable_all':
                self.features = dict(DEFAULT_FEATURES)
            return result
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
