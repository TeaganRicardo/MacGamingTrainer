"""Hades-only methods over the generic Core sidecar framing contract."""
import json
from pathlib import Path
import sys
import traceback
import uuid

from core.adapter import AdapterError
from core.sidecar import serve_jsonl_requests
from .schema import (DEFAULT_FEATURES, LOCK_FIELDS, MUTATING_COMMANDS, ONE_SHOT_COMMANDS, WORLD_COMMANDS, boon_rarity_target,
                     feature_document, feature_value)
from .world import (mutation_params as world_mutation_params, runtime_definitions,
                    runtime_definitions_identity)


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
        # The resident's last acknowledged lock and rarity intent. A same-process
        # Lua reset recreates the runtime table, so the bootstrap replays the
        # complete acknowledged desired state, not only the boolean features.
        self.locks = (None, None, None)
        self.boon_rarity_target = 'Heroic'

    def _invoke(self, method='status', arguments=(), *, target=None):
        definitions = runtime_definitions()
        definitions_identity = lua_literal(runtime_definitions_identity(definitions))
        source = 'local runtime = (function()\n' + self.source + '\nend)()\n'
        source += ('if runtime.worldDefinitions then assert(runtime.worldDefinitionsIdentity=='
                   + definitions_identity + ',"hades.error.restartRequired") else '
                   + 'runtime.worldDefinitions=' + lua_literal(definitions)
                   + ';runtime.worldDefinitionsIdentity=' + definitions_identity + ' end\n')
        replay = 'runtime.configure(' + lua_literal(self.features) + ')'
        if any(lock is not None for lock in self.locks):
            replay += ';runtime.configure_locks(' + ','.join(map(lua_literal, self.locks)) + ')'
        if self.boon_rarity_target != 'Heroic':
            replay += ';runtime.set_boon_rarity(' + lua_literal(self.boon_rarity_target) + ')'
        source += ('if not runtime.bootstrapId then runtime.bootstrapId=' + lua_literal(uuid.uuid4().hex)
                   + ';runtime.generationId=runtime.bootstrapId;' + replay + ' end\n')
        if target is not None:
            source += ('assert(runtime.status().heroId==' + lua_literal(target['heroId'])
                       + ',"hades.error.staleTarget")\n')
        source += 'return runtime.json(runtime.' + method + '(' + ','.join(map(lua_literal, arguments)) + '))'
        result = self.transport.execute(source, mutating=True)
        self._remember(result)
        result.update({'connected': True, 'pid': self.transport.pid})
        result['target'] = {'heroId': result.get('heroId', '')}
        return result

    def _remember(self, result):
        """Record lock/rarity intent from a reply that reports the resident status."""
        if all(type(result.get(flag)) is bool for flag, _ in LOCK_FIELDS):
            self.locks = tuple(result.get(value) if result[flag] else None for flag, value in LOCK_FIELDS)
        if result.get('boonRarityTarget') in ('Common', 'Rare', 'Epic', 'Heroic'):
            self.boon_rarity_target = result['boonRarityTarget']

    def dispatch(self, method, params):
        if method == 'connect':
            pid = params.get('pid')
            executable = params.get('executable')
            if type(pid) is not int or pid <= 0 or not isinstance(executable, str) or not executable:
                raise ValueError('connect requires a target pid and executable path')
            if 'features' in params:
                self.features = feature_document(params['features'])
            # A new connection reconciles locks and rarity from durable desired
            # state; never replay intent acknowledged by an earlier connection.
            self.locks = (None, None, None)
            self.boon_rarity_target = 'Heroic'
            self.transport.attach(pid, executable)
            return self._invoke('configure', (self.features,))
        if method == 'disconnect':
            self.transport.detach()
        elif method == 'status':
            if self.transport.alive():
                return self._invoke()
        elif method in MUTATING_COMMANDS:
            if not self.transport.alive():
                raise AdapterError('not_connected', 'hades.error.notConnected')
            target = None
            if method in ONE_SHOT_COMMANDS or method in ('lock_vital', 'lock_resource', 'lock_rerolls'):
                target = params.get('target')
                if not isinstance(target, dict) or not isinstance(target.get('heroId'), str) or not target['heroId']:
                    raise AdapterError('stale_target', 'hades.error.staleTarget')
            if method == 'set_feature':
                name = params.get('feature')
                value = feature_value(name, params.get('value'))
                result = self._invoke(method, (name, value))
                self.features[name] = value
                return result
            if method == 'set_boon_rarity':
                target = boon_rarity_target(params.get('target'))
                return self._invoke(method, (target,))
            if method == 'configure':
                values = feature_document(params.get('features'))
                result = self._invoke(method, (values,))
                self.features = values
                return result
            if method == 'configure_locks':
                return self._invoke(method, (
                    params.get('health'), params.get('money'), params.get('rerolls')
                ))
            if method == 'lock_vital':
                return self._invoke(method, (params.get('vital'), params.get('locked')), target=target)
            if method == 'lock_resource':
                return self._invoke(method, (params.get('resource'), params.get('locked')), target=target)
            if method == 'lock_rerolls':
                return self._invoke(method, (params.get('locked'),), target=target)
            if method in WORLD_COMMANDS:
                values = world_mutation_params(method, params)
                return self._invoke(method, (values,), target=target)
            arguments = {
                'disable_all': (),
                'set_value': (params.get('field'), params.get('value')),
                'set_resource': (params.get('resource'), params.get('value')),
                'add_trait': (params.get('trait'), params.get('rarity'), params.get('level')),
                'update_trait': (params.get('instanceId'), params.get('rarity'), params.get('level')),
                'remove_trait': (params.get('instanceId'),),
                'set_trait_uses': (params.get('instanceId'), params.get('uses')),
                'expire_trait': (params.get('instanceId'),),
                'refresh_trait': (params.get('instanceId'),),
                'add_chaos_pair': (params.get('blessing'), params.get('curse'), params.get('rarity'), params.get('encounters')),
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
