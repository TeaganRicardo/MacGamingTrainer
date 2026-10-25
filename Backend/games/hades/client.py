"""Bundled-Python client for the Hades-owned Xcode-Python debugger worker."""
import os
from pathlib import Path

from core.adapter import AdapterError
from core.sidecar import JsonLineSidecarClient, SidecarStartError, SidecarTerminalError
from .recovery import HadesRecoveryJournal, process_identity
from .schema import MUTATING_COMMANDS


class HadesRuntimeClient:
    def __init__(self, sidecar=None, *, recovery=None, identity=process_identity):
        self.sidecar = sidecar or self._new_sidecar()
        self.connected = False
        self.pid = None
        self.uncertain_pid = None
        self.recovery = recovery or HadesRecoveryJournal()
        self.identity = identity
        self.process_identity = None

    @staticmethod
    def _new_sidecar():
        backend = Path(__file__).resolve().parents[2]
        environment = dict(os.environ)
        environment['PYTHONPATH'] = str(backend)
        environment['PYTHONDONTWRITEBYTECODE'] = '1'
        return JsonLineSidecarClient(
            ['/usr/bin/xcrun', 'python3', '-u', '-m', 'games.hades.lldb_worker'],
            cwd=backend, env=environment, reply_timeout_seconds=120,
        )

    def _call(self, method, params=None):
        self.sidecar.reply_timeout_seconds = 120 if method == 'connect' else 12
        crosses_runtime = method != 'disconnect'
        if crosses_runtime and self.uncertain_pid is not None and self.uncertain_pid == self.pid:
            raise AdapterError('restart_required', 'hades.error.restartRequired')
        if crosses_runtime:
            self.recovery.begin(self.pid, self.process_identity, method)
        try:
            response = self.sidecar.request(
                method, params or {}, allow_start=method == 'connect',
                outcome_unknown_on_loss=crosses_runtime,
            )
        except SidecarStartError as error:
            if crosses_runtime:
                self.recovery.complete()
            raise AdapterError('debugger_start', 'hades.error.debuggerStart', diagnostic=str(error)) from error
        except SidecarTerminalError as error:
            self.connected = False
            if error.outcome_unknown:
                self.uncertain_pid = self.pid
            elif crosses_runtime:
                self.recovery.complete()
            key = 'outcomeUnknown' if error.outcome_unknown else 'debuggerLost'
            raise AdapterError('outcome_unknown' if error.outcome_unknown else 'debugger_lost',
                               'hades.error.' + key, diagnostic=str(error)) from error
        error = response.get('error')
        if error:
            if error['code'] in ('outcome_unknown', 'restart_required'):
                self.uncertain_pid = self.pid
                self.connected = False
            elif crosses_runtime:
                self.recovery.complete()
            raise AdapterError(error['code'], error['presentation'],
                               diagnostic=error.get('diagnostic'), arguments=error.get('arguments', []))
        result = response.get('result')
        if not isinstance(result, dict) or type(result.get('connected')) is not bool:
            self.sidecar.close()
            self.connected = False
            if crosses_runtime:
                self.uncertain_pid = self.pid
            raise AdapterError('debugger_protocol', 'hades.error.debuggerProtocol')
        if crosses_runtime:
            self.recovery.complete()
        self.connected = result['connected']
        return result

    def connect(self, pid, executable, features=None):
        identity = self.identity(pid)
        self.recovery.guard(pid, identity)
        if self.sidecar.terminal:
            self.sidecar.close()
            self.sidecar = self._new_sidecar()
        self.pid = pid
        self.uncertain_pid = None
        self.process_identity = identity
        params = {'pid': pid, 'executable': executable}
        if features is not None:
            params['features'] = features
        return self._call('connect', params)

    def status(self):
        if not self.connected:
            from .adapter import HadesAdapter
            return HadesAdapter._offline()
        return self._call('status')

    def set_invincibility(self, value):
        return self._call('set_invincibility', {'value': value})

    def command(self, method, params):
        if method not in MUTATING_COMMANDS:
            raise ValueError('Unsupported Hades runtime command: ' + method)
        return self._call(method, params)

    def disconnect(self):
        if self.sidecar.started:
            result = self._call('disconnect')
            self.sidecar.close()
            return result
        self.connected = False
        from .adapter import HadesAdapter
        return HadesAdapter._offline()

    def close(self):
        try:
            self.disconnect()
        finally:
            self.sidecar.close()
