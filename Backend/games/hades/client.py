"""Bundled-Python client for the Hades-owned Xcode-Python debugger worker."""
import os
from pathlib import Path

from core.adapter import AdapterError
from core.sidecar import JsonLineSidecarClient, SidecarStartError, SidecarTerminalError
from .operation_budgets import (
    SIDECAR_CONNECT_TIMEOUT_SECONDS,
    SIDECAR_DEFAULT_TIMEOUT_SECONDS,
    SIDECAR_DEFERRED_TRAIT_TIMEOUT_SECONDS,
)
from .recovery import process_identity
from .schema import DEFERRED_TRAIT_COMMANDS, DEFERRED_WORLD_COMMANDS, MUTATING_COMMANDS

_KNOWN_PRE_MUTATION_ERROR_CODES = frozenset((
    'not_connected',
    'debugger_lost',
    'attach_denied',
    'debugger_configuration',
    'incompatible',
    'invalid_value',
    'stale_target',
    'stale_room',
    'stale_door',
    'runtime_not_ready',
    'stop_timeout',
    'stop_failed',
    'unexpected_stop',
    'memory_error',
    'detach_failed',
    'lua_error',
))


class HadesRuntimeClient:
    @staticmethod
    def _reply_timeout(method):
        if method == 'connect':
            return SIDECAR_CONNECT_TIMEOUT_SECONDS
        if method in DEFERRED_TRAIT_COMMANDS or method in DEFERRED_WORLD_COMMANDS:
            return SIDECAR_DEFERRED_TRAIT_TIMEOUT_SECONDS
        return SIDECAR_DEFAULT_TIMEOUT_SECONDS
    def __init__(self, sidecar=None, *, recovery, identity=process_identity):
        self.sidecar = sidecar or self._new_sidecar()
        self.connected = False
        self.pid = None
        self.uncertain_pid = None
        self.recovery = recovery
        self.identity = identity
        self.process_identity = None
        self.game_speed_actual = None

    @staticmethod
    def _new_sidecar():
        backend = Path(__file__).resolve().parents[2]
        environment = dict(os.environ)
        environment['PYTHONPATH'] = str(backend)
        environment['PYTHONDONTWRITEBYTECODE'] = '1'
        return JsonLineSidecarClient(
            ['/usr/bin/xcrun', 'python3', '-u', '-m', 'games.hades.time_warp_worker'],
            cwd=backend, env=environment, reply_timeout_seconds=SIDECAR_CONNECT_TIMEOUT_SECONDS,
            child_owns_cleanup=True,
        )

    def _require_current_lifetime(self, lifetime):
        if lifetime != (self.pid, self.process_identity, self.sidecar):
            raise AdapterError('debugger_lost', 'hades.error.debuggerLost')

    def _call(self, method, params=None):
        lifetime = (self.pid, self.process_identity, self.sidecar)
        sidecar = self.sidecar
        sidecar.reply_timeout_seconds = self._reply_timeout(method)
        # Status installs hooks, disconnect resets native time, and even a
        # speed query can stop/resume the process. Protect every boundary.
        if self.uncertain_pid is not None and self.uncertain_pid == self.pid:
            raise AdapterError('restart_required', 'hades.error.restartRequired')
        pending = self.recovery.begin(self.pid, self.process_identity, method)
        try:
            response = sidecar.request(
                method, params or {}, allow_start=method == 'connect',
                outcome_unknown_on_loss=True,
            )
        except SidecarStartError as error:
            self._require_current_lifetime(lifetime)
            self.recovery.complete(pending)
            raise AdapterError('debugger_start', 'hades.error.debuggerStart', diagnostic=str(error)) from error
        except SidecarTerminalError as error:
            self._require_current_lifetime(lifetime)
            self.connected = False
            if error.outcome_unknown:
                self.uncertain_pid = self.pid
            else:
                self.recovery.complete(pending)
            key = 'outcomeUnknown' if error.outcome_unknown else 'debuggerLost'
            raise AdapterError('outcome_unknown' if error.outcome_unknown else 'debugger_lost',
                               'hades.error.' + key, diagnostic=str(error)) from error
        self._require_current_lifetime(lifetime)
        worker_state = response.get('state')
        if worker_state is not None and not isinstance(worker_state, dict):
            self.sidecar.close()
            self.connected = False
            self.uncertain_pid = self.pid
            raise AdapterError('debugger_protocol', 'hades.error.debuggerProtocol')
        error = response.get('error')
        if error is not None:
            if (not isinstance(error, dict)
                    or not isinstance(error.get('code'), str)
                    or not isinstance(error.get('presentation'), str)):
                self.sidecar.close()
                self.connected = False
                self.uncertain_pid = self.pid
                raise AdapterError('debugger_protocol', 'hades.error.debuggerProtocol')
            state_dict = worker_state or {}
            code = error['code']
            known_safe = (
                code in _KNOWN_PRE_MUTATION_ERROR_CODES
                and state_dict.get('tainted') is not True
                and state_dict.get('ackPending') is not True
            )
            if not known_safe:
                self.uncertain_pid = self.pid
                self.connected = False
                if code == 'debugger_internal':
                    self.sidecar.close()
                    raise AdapterError(
                        'outcome_unknown',
                        'hades.error.outcomeUnknown',
                        diagnostic=error.get('diagnostic'),
                    )
            else:
                if code in ('not_connected', 'debugger_lost', 'detach_failed'):
                    self.connected = False
                self.recovery.complete(pending)
            raise AdapterError(
                code,
                error['presentation'],
                diagnostic=error.get('diagnostic'),
                arguments=error.get('arguments', []),
            )
        result = response.get('result')
        if not isinstance(result, dict) or type(result.get('connected')) is not bool:
            self.sidecar.close()
            self.connected = False
            self.uncertain_pid = self.pid
            raise AdapterError('debugger_protocol', 'hades.error.debuggerProtocol')
        ack_pending = isinstance(worker_state, dict) and worker_state.get('ackPending') is True
        if ack_pending:
            ack_seq = worker_state.get('ackSequence')
            ack_id = worker_state.get('ackId')
            ack_method = worker_state.get('ackMethod')
            if (type(ack_seq) is not int or ack_seq <= 0
                    or not isinstance(ack_id, str) or not ack_id
                    or ack_method != method):
                self.sidecar.close()
                self.connected = False
                self.uncertain_pid = self.pid
                raise AdapterError('debugger_protocol', 'hades.error.debuggerProtocol')
        if method in ('time_warp.current_speed', 'time_warp.set_speed'):
            speed = result.get('gameSpeed')
            if type(speed) not in (int, float) or not 0 <= speed <= 10:
                self.sidecar.close()
                self.connected = False
                self.uncertain_pid = self.pid
                raise AdapterError('debugger_protocol', 'hades.error.debuggerProtocol')
        if ack_pending:
            receipt = {
                'method': method,
                'ackId': worker_state['ackId'],
                'ackSequence': worker_state['ackSequence'],
                'connected': result['connected'],
            }
            target = result.get('target')
            if isinstance(target, dict) and isinstance(target.get('heroId'), str):
                receipt['heroId'] = target['heroId']
            if isinstance(params, dict) and isinstance(params.get('requestId'), str):
                receipt['requestId'] = params['requestId']
            try:
                self.recovery.require_current(pending, self.pid, self.process_identity)
                self.recovery.confirm(pending, receipt)
            except AdapterError as error:
                self.sidecar.close()
                self.connected = False
                self.uncertain_pid = self.pid
                if error.code == 'debugger_lost':
                    raise
                raise AdapterError(
                    'outcome_unknown',
                    'hades.error.outcomeUnknown',
                    diagnostic=error.diagnostic or str(error),
                ) from error
            except Exception as error:
                self.sidecar.close()
                self.connected = False
                self.uncertain_pid = self.pid
                raise AdapterError(
                    'outcome_unknown',
                    'hades.error.outcomeUnknown',
                    diagnostic=str(error),
                ) from error
            ack_params = {
                'sequence': worker_state['ackSequence'],
                'ackId': worker_state['ackId'],
                'method': method,
            }
            try:
                ack_response = sidecar.request(
                    'acknowledge_result',
                    ack_params,
                    allow_start=False,
                    outcome_unknown_on_loss=False,
                )
            except Exception as error:
                self.sidecar.close()
                self.connected = False
                self.uncertain_pid = self.pid
                raise AdapterError(
                    'restart_required',
                    'hades.error.commandResultConnectionLost',
                    diagnostic=getattr(error, 'detail', None) or str(error),
                ) from error
            if not isinstance(ack_response, dict) or ack_response.get('error') is not None:
                self.sidecar.close()
                self.connected = False
                self.uncertain_pid = self.pid
                err = ack_response.get('error') if isinstance(ack_response, dict) else None
                detail = err.get('diagnostic') if isinstance(err, dict) else repr(ack_response)
                raise AdapterError(
                    'restart_required',
                    'hades.error.commandResultConnectionLost',
                    diagnostic=detail,
                )
            ack_result = ack_response.get('result')
            if not isinstance(ack_result, dict) or ack_result.get('acknowledged') is not True:
                self.sidecar.close()
                self.connected = False
                self.uncertain_pid = self.pid
                raise AdapterError(
                    'restart_required',
                    'hades.error.commandResultConnectionLost',
                    diagnostic=f'Malformed mailbox acknowledgement reply: {ack_result!r}',
                )
            self.recovery.require_current(pending, self.pid, self.process_identity)
            self.recovery.complete(pending)
        else:
            self.recovery.complete(pending)
        self.connected = result['connected']
        return result

    def connect(self, pid, executable, features=None):
        identity = self.identity(pid)
        self.recovery.guard(pid, identity)
        if self.sidecar.terminal:
            self.sidecar.close()
            self.sidecar = self._new_sidecar()
        if self.pid != pid:
            self.game_speed_actual = None
        self.pid = pid
        self.uncertain_pid = None
        self.process_identity = identity
        params = {'pid': pid, 'executable': executable}
        if features is not None:
            params['features'] = {name: value for name, value in features.items() if name != 'gameSpeed'}
        return self._call('connect', params)

    def status(self):
        if not self.connected:
            from .adapter import HadesAdapter
            return HadesAdapter._offline()
        return self._call('status')

    def current_game_speed(self):
        result = self._call('time_warp.current_speed')
        value = result.get('gameSpeed')
        if type(value) not in (int, float) or not 0 <= value <= 10:
            raise AdapterError('debugger_protocol', 'hades.error.debuggerProtocol')
        self.game_speed_actual = float(value)
        return self.game_speed_actual

    def set_game_speed(self, value):
        result = self._call('time_warp.set_speed', {'value': value})
        actual = result.get('gameSpeed')
        if type(actual) not in (int, float) or not 0 <= actual <= 10:
            self.connected = False
            self.uncertain_pid = self.pid
            self.game_speed_actual = None
            raise AdapterError('debugger_protocol', 'hades.error.debuggerProtocol')
        self.game_speed_actual = float(actual)
        return self.game_speed_actual

    def command(self, method, params):
        if method not in MUTATING_COMMANDS:
            raise ValueError('Unsupported Hades runtime command: ' + method)
        return self._call(method, params)

    def disconnect(self):
        if self.sidecar.started:
            result = self._call('disconnect')
            self.game_speed_actual = 1.0
            self.sidecar.close()
            return result
        self.connected = False
        self.game_speed_actual = None
        from .adapter import HadesAdapter
        return HadesAdapter._offline()

    def close(self):
        try:
            self.disconnect()
        finally:
            self.sidecar.close()
