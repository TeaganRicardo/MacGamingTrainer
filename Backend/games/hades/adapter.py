"""Hades command semantics; debugger lifetime is isolated in its own sidecar."""
from pathlib import Path
import subprocess

from core.adapter import AdapterError, GameAdapter
from .catalog import catalog, get_entry, resource_catalog, trait_names
from .preferences import HadesPreferenceStore
from .schema import DEFAULT_FEATURES, ONE_SHOT_COMMANDS, RESOURCE_IDS, feature_value, invalid_value, number


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
    def __init__(self, context, *, runtime=None, locate_process=locate_process, preferences=None):
        super().__init__(context)
        if runtime is None:
            from .client import HadesRuntimeClient
            runtime = HadesRuntimeClient()
        self.runtime = runtime
        self.locate_process = locate_process
        self.connected = False
        self.preferences = preferences or HadesPreferenceStore()
        self.features = dict(DEFAULT_FEATURES)

    def dispatch(self, command, params, request_id):
        if command == 'catalog':
            try:
                language = params.get('language', 'zh-CN')
                return {'catalog': catalog(language, params.get('query', ''), params.get('kind', 'all')),
                        'resourceCatalog': resource_catalog(language), 'traitNames': trait_names()}
            except ValueError as error:
                raise invalid_value() from error
        if command == 'launch':
            subprocess.run(['/usr/bin/open', 'steam://run/1145360'], check=True)
            return self.dispatch('status', {}, request_id)
        if command == 'connect':
            target = self.locate_process()
            if target is None:
                raise AdapterError('game_not_running', 'hades.error.notRunning')
            self.features = self.preferences.load()
            return self._observe(self.runtime.connect(*target, features=self.features))
        if command == 'status':
            return self._observe(self.runtime.status()) if self.connected else {**self._offline(), 'features': self.features}
        if command == 'disconnect':
            return self._observe(self.runtime.disconnect())
        if command == 'set_invincibility':
            command, params = 'set_feature', {'feature': 'invincibility', 'value': params.get('value')}
        if command == 'set_feature':
            name = params.get('feature')
            value = feature_value(name, params.get('value'))
            if not self.connected:
                raise AdapterError('not_connected', 'hades.error.notConnected')
            candidate = {**self.features, name: value}
            self.preferences.save(candidate)
            self.features = candidate
            return self._observe(self.runtime.command(command, {'feature': name, 'value': value}))
        if command == 'disable_all':
            persistence_error = None
            try:
                self.preferences.save(DEFAULT_FEATURES)
            except AdapterError as error:
                persistence_error = error
            self.features = dict(DEFAULT_FEATURES)
            state = (self._observe(self.runtime.command('disable_all', {})) if self.connected
                     else {**self._offline(), 'features': self.features})
            if persistence_error:
                raise persistence_error
            return state
        if command in ONE_SHOT_COMMANDS:
            if not self.connected:
                raise AdapterError('not_connected', 'hades.error.notConnected')
            target = params.get('target')
            if not isinstance(target, dict) or not isinstance(target.get('heroId'), str) or not target['heroId']:
                raise AdapterError('stale_target', 'hades.error.staleTarget')
            values = self._mutation_params(command, params)
            values['target'] = target
            return self._observe(self.runtime.command(command, values))
        raise AdapterError('unknown_command', 'hades.error.unknownCommand')

    @staticmethod
    def _mutation_params(command, params):
        if command == 'heal':
            return {}
        if command == 'set_value':
            field = params.get('field')
            if field not in ('health', 'maxHealth', 'money', 'rerolls'):
                raise invalid_value()
            return {'field': field, 'value': number(params.get('value'),
                    1 if field in ('health', 'maxHealth') else 0, integer=True)}
        if command == 'set_resource':
            resource = params.get('resource')
            if not isinstance(resource, str) or resource not in RESOURCE_IDS:
                raise invalid_value()
            return {'resource': resource, 'value': number(params.get('value'), integer=True)}
        if command == 'add_trait':
            identifier = params.get('trait')
            entry = get_entry(identifier) if isinstance(identifier, str) else None
            if entry is None:
                raise invalid_value()
            rarity = params.get('rarity')
            if rarity not in entry['rarities']:
                raise invalid_value()
            level = number(params.get('level'), 1, 100, integer=True)
            if not entry.get('supportsLevel', True) and level != 1:
                raise invalid_value()
            return {'trait': identifier, 'rarity': rarity, 'level': level}
        identifier = params.get('instanceId')
        if not isinstance(identifier, str) or not identifier or len(identifier) > 128:
            raise invalid_value()
        result = {'instanceId': identifier}
        if command == 'update_trait':
            rarity = params.get('rarity')
            if rarity not in ('Common', 'Rare', 'Epic', 'Heroic', 'Legendary'):
                raise invalid_value()
            result.update({'rarity': rarity, 'level': number(params.get('level'), 1, 100, integer=True)})
        return result

    def _observe(self, state):
        self.connected = state['connected']
        return state

    @staticmethod
    def _offline():
        return {'connected': False, 'heroReady': False, 'invincible': False,
                'health': 0, 'maxHealth': 0, 'money': 0, 'pid': None}

    def close(self):
        self.runtime.close()
