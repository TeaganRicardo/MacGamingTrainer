"""Hades-only methods over the generic Core sidecar framing contract."""
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback
import uuid

from core.adapter import AdapterError
from core.sidecar import serve_jsonl_requests
from core.resident_source import resident_source
from .cheats import HADES_CHEAT_CATALOG, to_runtime_feature, to_runtime_features
from .mailbox import KNOWN_LUA_REFUSAL_KEYS
from .operation_budgets import PROCESS_CONTROL_TIMEOUT_SECONDS
from .schema import (DEFAULT_FEATURES, DEFERRED_TRAIT_COMMANDS, DEFERRED_WORLD_COMMANDS, LOCK_FIELDS,
                     MUTATING_COMMANDS, ONE_SHOT_COMMANDS, WORLD_COMMANDS, boon_rarity_target,
                     feature_value, invalid_value)
from .world import (mutation_params as world_mutation_params, runtime_definitions,
                    runtime_definitions_identity)

_RUNTIME_FEATURE_DEFAULTS = to_runtime_features(DEFAULT_FEATURES, DEFAULT_FEATURES)


def _runtime_feature_entry(name, value):
    if not isinstance(name, str):
        raise invalid_value()
    canonical = HADES_CHEAT_CATALOG.resolve_id(name)
    if canonical is None:
        raise invalid_value()
    return to_runtime_feature(canonical), feature_value(canonical, value)


def _runtime_feature_document(values):
    if not isinstance(values, dict) or len(values) != len(DEFAULT_FEATURES):
        raise invalid_value()
    translated = {}
    seen_canonicals = set()
    for key, value in values.items():
        if not isinstance(key, str):
            raise invalid_value()
        canonical = HADES_CHEAT_CATALOG.resolve_id(key)
        if canonical is None or canonical not in DEFAULT_FEATURES or canonical in seen_canonicals:
            raise invalid_value()
        seen_canonicals.add(canonical)
        translated[to_runtime_feature(canonical)] = feature_value(canonical, value)
    if seen_canonicals != set(DEFAULT_FEATURES):
        raise invalid_value()
    return translated


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
        raw_source = Path(__file__).with_name('runtime.lua').read_text()
        self.revision = hashlib.sha256(raw_source.encode('utf-8')).hexdigest()
        self.source = resident_source(raw_source)
        self.features = dict(_RUNTIME_FEATURE_DEFAULTS)
        # The resident's last acknowledged lock and rarity intent. A same-process
        # Lua reset recreates the runtime table, so the bootstrap replays the
        # complete acknowledged desired state, not only the boolean features.
        self.locks = (None, None, None)
        self.boon_rarity_target = 'Heroic'
        self._bootstrapped = None
        self._pending_ack_method = None
        self._pending_ack_id = None

    def state(self):
        mailbox = getattr(self.transport, '_mailbox', None)
        pending_seq = getattr(mailbox, '_pending_sequence', None) if mailbox is not None else None
        if pending_seq is None:
            pending_seq = getattr(self.transport, 'pending_acknowledgement_sequence', None)
            if callable(pending_seq):
                pending_seq = None
        ack_pending = pending_seq is not None
        return {
            'ackPending': ack_pending,
            'ackSequence': pending_seq if ack_pending else None,
            'ackMethod': self._pending_ack_method if ack_pending else None,
            'ackId': self._pending_ack_id if ack_pending else None,
            'tainted': bool(getattr(self.transport, 'tainted', False)),
        }

    def _has_pending_acknowledgement(self):
        if bool(getattr(self.transport, 'has_pending_acknowledgement', False)):
            return True
        mailbox = getattr(self.transport, '_mailbox', None)
        return mailbox is not None and getattr(mailbox, '_pending_sequence', None) is not None

    def _acknowledge_transport(self):
        acknowledge = getattr(self.transport, 'acknowledge_result', None)
        if callable(acknowledge):
            acknowledge()
        self._pending_ack_method = None
        self._pending_ack_id = None

    def _taint_transport(self):
        try:
            self.transport.tainted = True
        except AttributeError:
            pass

    @staticmethod
    def _validate_status_payload(payload):
        if not isinstance(payload, dict):
            raise ValueError('Hades status payload must be a JSON object')
        if 'needsBootstrap' in payload:
            raise ValueError('Unexpected needsBootstrap marker in Hades status payload')
        if not isinstance(payload.get('heroId'), str):
            raise ValueError('Hades status payload is missing string heroId')
        if 'heroReady' in payload and type(payload['heroReady']) is not bool:
            raise ValueError('Hades status payload heroReady must be a boolean')
        for flag, _ in LOCK_FIELDS:
            if flag in payload and type(payload[flag]) is not bool:
                raise ValueError(f'Hades status payload {flag} must be a boolean')
        if 'boonRarityTarget' in payload and payload['boonRarityTarget'] not in ('Common', 'Rare', 'Epic', 'Heroic'):
            raise ValueError('Hades status payload has invalid boonRarityTarget')
        return payload

    @classmethod
    def _unwrap_direct_receipt(cls, raw, *, command_id, method, allow_bootstrap):
        if not isinstance(raw, dict):
            raise ValueError(f'Hades command receipt must be a JSON object, got {type(raw).__name__}')
        receipt_meta = raw.get('__mgtReceipt')
        if receipt_meta != {'id': command_id, 'method': method}:
            raise ValueError('Hades command receipt identity mismatch')
        if allow_bootstrap and set(raw) == {'__mgtReceipt', 'needsBootstrap'} and raw['needsBootstrap'] is True:
            return None
        if set(raw) != {'__mgtReceipt', 'result'}:
            raise ValueError('Hades command receipt envelope has unexpected keys')
        return cls._validate_status_payload(raw['result'])

    def _build_call(self, owner, method, arguments):
        use_mailbox = getattr(self.transport, 'mailbox_mode', 'lldb') == 'mailbox'
        if method in DEFERRED_TRAIT_COMMANDS or (method in DEFERRED_WORLD_COMMANDS and not use_mailbox):
            is_trait = method in DEFERRED_TRAIT_COMMANDS
            submit_cmd = 'submit_trait_command' if is_trait else 'submit_world_command'
            result_cmd = 'trait_command_result' if is_trait else 'world_command_result'
            cancel_cmd = 'cancel_trait_command' if is_trait else 'cancel_world_command'
            command_id = uuid.uuid4().hex
            values = {index + 1: value for index, value in enumerate(arguments)}
            values['n'] = len(arguments)
            call_src = ('return ' + owner + '.json(' + owner + '.' + submit_cmd + '(' + lua_literal(command_id)
                        + ',' + lua_literal(method) + ',' + lua_literal(values) + '))')
            return command_id, result_cmd, cancel_cmd, call_src
        if not isinstance(method, str) or not method.isidentifier() or not method.isascii():
            raise ValueError('Unsupported Hades Lua method: ' + str(method))
        command_id = uuid.uuid4().hex
        envelope_prefix = (
            '{"__mgtReceipt":{"id":' + json.dumps(command_id) + ',"method":' + json.dumps(method) + '},"result":'
        )
        call_src = (
            'local __mgt_result=' + owner + '.' + method + '(' + ','.join(map(lua_literal, arguments)) + ')\n'
            'return ' + lua_literal(envelope_prefix) + '..' + owner + '.json(__mgt_result).."}"'
        )
        return command_id, None, None, call_src

    def _invoke_fast(self, method, arguments, *, definitions_identity, target=None):
        literal_rev = lua_literal(self.revision)
        literal_def = lua_literal(definitions_identity)
        command_id, result_cmd, cancel_cmd, call_src = self._build_call('runtime', method, arguments)
        sentinel = (
            '{"__mgtReceipt":{"id":' + json.dumps(command_id) + ',"method":' + json.dumps(method)
            + '},"needsBootstrap":true}'
        )
        sentinel_literal = lua_literal(sentinel)
        source = (
            'local runtime=rawget(_G,"MacGamingTrainerHades")\n'
            'if type(runtime)~="table" then return ' + sentinel_literal + ' end\n'
            'if runtime.revision~=' + literal_rev + ' then error("hades.error.restartRequired") end\n'
            'if runtime.worldDefinitions then assert(runtime.worldDefinitionsIdentity==' + literal_def
            + ',"hades.error.restartRequired") end\n'
            'if not runtime.bootstrapId or not runtime.worldDefinitions then return ' + sentinel_literal + ' end\n'
        )
        if target is not None:
            source += 'assert(runtime.status().heroId==' + lua_literal(target['heroId']) + ',"hades.error.staleTarget")\n'
        source += call_src
        if result_cmd is not None:
            return command_id, self._deferred_command(
                source, command_id,
                result_cmd=result_cmd, cancel_cmd=cancel_cmd,
                method=method, allow_bootstrap=True,
            )
        raw = self.transport.execute(source, mutating=True)
        try:
            payload = self._unwrap_direct_receipt(
                raw, command_id=command_id, method=method, allow_bootstrap=True,
            )
            if payload is None:
                self._acknowledge_transport()
                return command_id, {'needsBootstrap': True}
            return command_id, payload
        except Exception as error:
            self._taint_transport()
            if isinstance(error, AdapterError) and error.code == 'outcome_unknown':
                raise
            raise AdapterError(
                'outcome_unknown',
                'hades.error.outcomeUnknown',
                diagnostic=getattr(error, 'diagnostic', None) or str(error),
            ) from error

    def _invoke(self, method='status', arguments=(), *, target=None, rpc_method=None, _generation_retried=False):
        definitions = runtime_definitions()
        definitions_identity = runtime_definitions_identity(definitions)
        transport_key = (id(self.transport), getattr(self.transport, 'pid', None))
        try:
            if self._bootstrapped == transport_key and transport_key[1] is not None:
                call_id, result = self._invoke_fast(
                    method, arguments, definitions_identity=definitions_identity, target=target,
                )
                if not result.get('needsBootstrap'):
                    try:
                        self._remember(result)
                        result.update({'connected': True, 'pid': self.transport.pid})
                        result['target'] = {'heroId': result.get('heroId', '')}
                        if self._has_pending_acknowledgement():
                            self._pending_ack_method = rpc_method or method
                            self._pending_ack_id = call_id
                        return result
                    except Exception as error:
                        self._taint_transport()
                        if isinstance(error, AdapterError) and error.code == 'outcome_unknown':
                            raise
                        raise AdapterError(
                            'outcome_unknown',
                            'hades.error.outcomeUnknown',
                            diagnostic=getattr(error, 'diagnostic', None) or str(error),
                        ) from error
                self._bootstrapped = None

            literal_identity = lua_literal(definitions_identity)
            source = 'local runtime = (function()\n' + self.source + '\nend)()\n'
            source += ('if runtime.worldDefinitions then assert(runtime.worldDefinitionsIdentity=='
                       + literal_identity + ',"hades.error.restartRequired") else '
                       + 'runtime.worldDefinitions=' + lua_literal(definitions)
                       + ';runtime.worldDefinitionsIdentity=' + literal_identity + ' end\n')
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
            command_id, result_cmd, cancel_cmd, call_src = self._build_call('runtime', method, arguments)
            source += call_src
            if result_cmd is not None:
                result = self._deferred_command(
                    source, command_id,
                    result_cmd=result_cmd, cancel_cmd=cancel_cmd,
                    method=method, allow_bootstrap=False,
                )
            else:
                raw = self.transport.execute(source, mutating=True)
                try:
                    result = self._unwrap_direct_receipt(
                        raw, command_id=command_id, method=method, allow_bootstrap=False,
                    )
                except Exception as error:
                    self._taint_transport()
                    if isinstance(error, AdapterError) and error.code == 'outcome_unknown':
                        raise
                    raise AdapterError(
                        'outcome_unknown',
                        'hades.error.outcomeUnknown',
                        diagnostic=getattr(error, 'diagnostic', None) or str(error),
                    ) from error
            try:
                self._bootstrapped = transport_key
                self._remember(result)
                result.update({'connected': True, 'pid': self.transport.pid})
                result['target'] = {'heroId': result.get('heroId', '')}
                if self._has_pending_acknowledgement():
                    self._pending_ack_method = rpc_method or method
                    self._pending_ack_id = command_id
                return result
            except Exception as error:
                self._taint_transport()
                if isinstance(error, AdapterError) and error.code == 'outcome_unknown':
                    raise
                raise AdapterError(
                    'outcome_unknown',
                    'hades.error.outcomeUnknown',
                    diagnostic=getattr(error, 'diagnostic', None) or str(error),
                ) from error
        except AdapterError as error:
            if error.code == 'resident_generation_missing':
                self._bootstrapped = None
                if method == 'status' and target is None and not _generation_retried:
                    return self._invoke(
                        method, arguments, target=target, rpc_method=rpc_method, _generation_retried=True,
                    )
                presentation = 'hades.error.staleTarget' if target is not None else 'hades.error.runtimeNotReady'
                raise AdapterError('runtime_not_ready', presentation, diagnostic=error.diagnostic) from error
            raise

    def _trait_command(self, source, command_id):
        return self._deferred_command(
            source, command_id,
            result_cmd='trait_command_result', cancel_cmd='cancel_trait_command',
        )

    def _deferred_command(self, source, command_id, *, result_cmd, cancel_cmd, method=None, allow_bootstrap=False):
        deadline = time.monotonic() + PROCESS_CONTROL_TIMEOUT_SECONDS
        receipt = self.transport.execute(source, mutating=True)
        if allow_bootstrap and method is not None and isinstance(receipt, dict) and receipt == {
            '__mgtReceipt': {'id': command_id, 'method': method},
            'needsBootstrap': True,
        }:
            try:
                self._acknowledge_transport()
            except Exception as error:
                self._taint_transport()
                if isinstance(error, AdapterError) and error.code == 'outcome_unknown':
                    raise
                raise AdapterError(
                    'outcome_unknown',
                    'hades.error.outcomeUnknown',
                    diagnostic=getattr(error, 'diagnostic', None) or str(error),
                ) from error
            return {'needsBootstrap': True}
        if isinstance(receipt, dict) and receipt.get('needsBootstrap') is True and '__mgtReceipt' not in receipt and allow_bootstrap and method is None:
            self._acknowledge_transport()
            return {'needsBootstrap': True}

        def valid_receipt(candidate):
            return (
                isinstance(candidate, dict)
                and candidate.get('id') == command_id
                and candidate.get('state') in ('pending', 'running', 'complete', 'cancelled', 'error')
            )

        if not valid_receipt(receipt):
            self._taint_transport()
            raise AdapterError(
                'outcome_unknown',
                'hades.error.outcomeUnknown',
                diagnostic='Native command initial receipt structure or identity is invalid.',
            )

        owner = 'MacGamingTrainerHades'
        identifier = lua_literal(command_id)

        def read(read_method, *, mutating=False):
            snippet = 'return ' + owner + '.json(' + owner + '.' + read_method + '(' + identifier + '))'
            try:
                return self.transport.execute(snippet, mutating=mutating)
            except AdapterError as error:
                self._taint_transport()
                if error.code == 'outcome_unknown':
                    raise
                raise AdapterError('outcome_unknown', 'hades.error.outcomeUnknown',
                                   diagnostic=error.diagnostic or str(error)) from error
            except Exception as error:
                self._taint_transport()
                raise AdapterError('outcome_unknown', 'hades.error.outcomeUnknown', diagnostic=str(error)) from error

        while receipt.get('id') == command_id and receipt.get('state') in ('pending', 'running'):
            try:
                self._acknowledge_transport()
            except Exception as error:
                self._taint_transport()
                if isinstance(error, AdapterError) and error.code == 'outcome_unknown':
                    raise
                raise AdapterError('outcome_unknown', 'hades.error.outcomeUnknown', diagnostic=str(error)) from error
            if time.monotonic() >= deadline:
                receipt = read(cancel_cmd, mutating=True)
                if not valid_receipt(receipt):
                    self._taint_transport()
                    raise AdapterError(
                        'outcome_unknown',
                        'hades.error.outcomeUnknown',
                        diagnostic='Native command cancel receipt structure or identity is invalid.',
                    )
                break
            time.sleep(0.02)
            receipt = read(result_cmd)
            if not valid_receipt(receipt):
                self._taint_transport()
                raise AdapterError(
                    'outcome_unknown',
                    'hades.error.outcomeUnknown',
                    diagnostic='Native command poll receipt structure or identity is invalid.',
                )
        state = receipt.get('state')
        if state == 'complete':
            payload = receipt.get('result')
            try:
                return self._validate_status_payload(payload)
            except Exception as error:
                self._taint_transport()
                raise AdapterError('outcome_unknown', 'hades.error.outcomeUnknown', diagnostic=str(error)) from error
        if state == 'cancelled':
            if receipt.get('mutationStarted') is True:
                self._taint_transport()
                raise AdapterError(
                    'outcome_unknown',
                    'hades.error.outcomeUnknown',
                    diagnostic='Native command reported cancelled after mutation started.',
                )
            self._acknowledge_transport()
            raise AdapterError('runtime_not_ready', 'hades.error.runtimeNotReady',
                               diagnostic='Native command did not start; close the pause menu and try again.')
        if state == 'error' and receipt.get('mutationStarted') is False:
            detail = receipt.get('error')
            if isinstance(detail, str):
                for key in KNOWN_LUA_REFUSAL_KEYS:
                    if 'hades.error.' + key in detail:
                        self._acknowledge_transport()
                        raise AdapterError('runtime_not_ready', 'hades.error.' + key, diagnostic=detail)
        self._taint_transport()
        error_detail = receipt.get('error')
        raise AdapterError(
            'outcome_unknown',
            'hades.error.outcomeUnknown',
            diagnostic=error_detail if isinstance(error_detail, str) and error_detail else 'Native command completion was not confirmed.',
        )

    def _remember(self, result):
        """Record lock/rarity intent from a reply that reports the resident status."""
        if all(type(result.get(flag)) is bool for flag, _ in LOCK_FIELDS):
            self.locks = tuple(result.get(value) if result[flag] else None for flag, value in LOCK_FIELDS)
        if result.get('boonRarityTarget') in ('Common', 'Rare', 'Epic', 'Heroic'):
            self.boon_rarity_target = result['boonRarityTarget']

    def close(self):
        self._bootstrapped = None
        self._pending_ack_method = None
        self._pending_ack_id = None
        self.transport.close()

    def dispatch(self, method, params):
        if not isinstance(params, dict):
            raise ValueError('Hades worker params must be an object')
        if method == 'acknowledge_result':
            if self._has_pending_acknowledgement():
                mailbox = getattr(self.transport, '_mailbox', None)
                pending_seq = getattr(mailbox, '_pending_sequence', None) if mailbox is not None else None
                if pending_seq is None:
                    pending_seq = getattr(self.transport, 'pending_acknowledgement_sequence', None)
                if (params.get('sequence') != pending_seq
                        or params.get('ackId') != self._pending_ack_id
                        or params.get('method') != self._pending_ack_method):
                    self._taint_transport()
                    raise AdapterError(
                        'restart_required',
                        'hades.error.commandResultConnectionLost',
                        diagnostic='Mailbox acknowledgement identity mismatch',
                    )
            self._acknowledge_transport()
            return {'acknowledged': True}
        if method == 'disconnect':
            self._pending_ack_method = None
            self._pending_ack_id = None
            self._bootstrapped = None
            self.transport.detach()
        elif method == 'connect':
            if self._has_pending_acknowledgement():
                raise AdapterError(
                    'restart_required',
                    'hades.error.restartRequired',
                    diagnostic='Previous mailbox receipt has not been acknowledged',
                )
            self._bootstrapped = None
            pid = params.get('pid')
            executable = params.get('executable')
            if type(pid) is not int or pid <= 0 or not isinstance(executable, str) or not executable:
                raise ValueError('connect requires a target pid and executable path')
            if 'features' in params:
                self.features = _runtime_feature_document(params['features'])
            # A new connection reconciles locks and rarity from durable desired
            # state; never replay intent acknowledged by an earlier connection.
            self.locks = (None, None, None)
            self.boon_rarity_target = 'Heroic'
            self.transport.attach(pid, executable)
            try:
                return self._invoke('configure', (self.features,), rpc_method='connect')
            except Exception as error:
                if (not getattr(self.transport, 'tainted', False)
                        and not getattr(self.transport, 'vm_interrupted', False)
                        and not getattr(self.transport, 'cleanup_pending', False)):
                    rollback = getattr(self.transport, '_rollback_failed_attach', None)
                    if callable(rollback):
                        rollback(error)
                    elif hasattr(self.transport, 'detach'):
                        self.transport.detach()
                raise
        elif method == 'status':
            if self._has_pending_acknowledgement():
                raise AdapterError(
                    'restart_required',
                    'hades.error.restartRequired',
                    diagnostic='Previous mailbox receipt has not been acknowledged',
                )
            if getattr(self.transport, 'cleanup_pending', False):
                raise self.transport._quarantined_error()
            if self.transport.alive():
                return self._invoke()
        elif method in MUTATING_COMMANDS:
            if self._has_pending_acknowledgement():
                raise AdapterError(
                    'restart_required',
                    'hades.error.restartRequired',
                    diagnostic='Previous mailbox receipt has not been acknowledged',
                )
            if getattr(self.transport, 'cleanup_pending', False):
                raise self.transport._quarantined_error()
            if not self.transport.alive():
                raise AdapterError('not_connected', 'hades.error.notConnected')
            target = None
            if method in ONE_SHOT_COMMANDS or method in ('lock_vital', 'lock_resource', 'lock_rerolls'):
                target = params.get('target')
                if not isinstance(target, dict) or not isinstance(target.get('heroId'), str) or not target['heroId']:
                    raise AdapterError('stale_target', 'hades.error.staleTarget')
            if method == 'set_feature':
                runtime_name, value = _runtime_feature_entry(params.get('feature'), params.get('value'))
                result = self._invoke(method, (runtime_name, value))
                self.features[runtime_name] = value
                return result
            if method == 'set_boon_rarity':
                target = boon_rarity_target(params.get('target'))
                return self._invoke(method, (target,))
            if method == 'configure':
                values = _runtime_feature_document(params.get('features'))
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
                self.features = dict(_RUNTIME_FEATURE_DEFAULTS)
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


def close_worker(worker):
    while True:
        try:
            worker.close()
            return
        except AdapterError:
            if not worker.transport.vm_interrupted:
                raise
            # The parent relinquishes this worker on EOF. It must retain the
            # debugger until the unsafe target exits, even after Trainer quits.
            time.sleep(1)


def main():
    worker = HadesLLDBWorker()
    try:
        serve_jsonl_requests(sys.stdin, sys.stdout, worker.dispatch, error_payload=error_payload, state=worker.state)
    finally:
        close_worker(worker)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
