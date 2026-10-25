"""Hades command semantics; debugger lifetime is isolated in its own sidecar."""
from pathlib import Path
import subprocess

from core.adapter import AdapterError, GameAdapter


EXECUTABLE_SUFFIX = 'Hades/Game.macOS.app/Contents/MacOS/Game.macOS'


def locate_process():
    rows = subprocess.check_output(['/bin/ps', '-axo', 'pid=,comm='], text=True)
    matches = []
    for row in rows.splitlines():
        parts = row.strip().split(None, 1)
        if len(parts) == 2 and parts[1].endswith('/' + EXECUTABLE_SUFFIX):
            matches.append((int(parts[0]), str(Path(parts[1]).resolve())))
    if len(matches) > 1:
        raise AdapterError('ambiguous_target', 'hades.error.ambiguousTarget')
    return matches[0] if matches else None


class HadesAdapter(GameAdapter):
    def __init__(self, context, *, runtime=None, locate_process=locate_process):
        super().__init__(context)
        if runtime is None:
            from .client import HadesRuntimeClient
            runtime = HadesRuntimeClient()
        self.runtime = runtime
        self.locate_process = locate_process
        self.connected = False

    def dispatch(self, command, params, request_id):
        if command == 'launch':
            subprocess.run(['/usr/bin/open', 'steam://run/1145360'], check=True)
            return self.dispatch('status', {}, request_id)
        if command == 'connect':
            target = self.locate_process()
            if target is None:
                raise AdapterError('game_not_running', 'hades.error.notRunning')
            return self._observe(self.runtime.connect(*target))
        if command == 'status':
            return self._observe(self.runtime.status()) if self.connected else self._offline()
        if command == 'disconnect':
            return self._observe(self.runtime.disconnect())
        if command == 'set_invincibility':
            value = params.get('value')
            if type(value) is not bool:
                raise AdapterError('invalid_value', 'hades.error.invalidValue')
            if not self.connected:
                raise AdapterError('not_connected', 'hades.error.notConnected')
            return self._observe(self.runtime.set_invincibility(value))
        if command == 'disable_all':
            if not self.connected:
                return self._offline()
            state = self.runtime.status()
            if state.get('heroReady') and state.get('invincible'):
                state = self.runtime.set_invincibility(False)
            return self._observe(state)
        raise AdapterError('unknown_command', 'hades.error.unknownCommand')

    def _observe(self, state):
        self.connected = state['connected']
        return state

    @staticmethod
    def _offline():
        return {'connected': False, 'heroReady': False, 'invincible': False,
                'health': 0, 'maxHealth': 0, 'money': 0, 'pid': None}

    def close(self):
        self.runtime.close()
