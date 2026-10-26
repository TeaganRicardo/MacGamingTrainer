"""Hades command semantics; debugger lifetime is isolated in its own sidecar."""
from pathlib import Path
import subprocess

from core.adapter import AdapterError, GameAdapter
from .catalog import catalog, get_entry, resource_catalog, trait_names
from .preferences import HadesPreferenceStore
from .schema import (DEFAULT_FEATURES, DEFAULT_PREFERENCES, FISH_BIOMES, FISH_QUALITIES,
                     ONE_SHOT_COMMANDS, RESOURCE_IDS, preference_value, invalid_value, number)


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
        self.features = dict(DEFAULT_PREFERENCES)
        self._game_speed_actual = None
        self._game_speed_error = None

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
            self._game_speed_actual = None
            self._game_speed_error = None
            runtime_features = {name: value for name, value in self.features.items() if name in DEFAULT_FEATURES}
            state = self.runtime.connect(*target, features=runtime_features)
            self.connected = state['connected']
            self._reconcile_game_speed()
            if not self.connected:
                state = {**self._offline(), 'features': self.features}
            return self._observe(state)
        if command == 'status':
            if not self.connected:
                return self._observe({**self._offline(), 'features': self.features})
            state = self.runtime.status()
            if not state.get('connected'):
                self._game_speed_actual = None
                self._game_speed_error = None
            return self._observe(state)
        if command == 'disconnect':
            try:
                state = self.runtime.disconnect()
            except AdapterError as error:
                self._record_game_speed_error(error)
                raise
            self._game_speed_actual = getattr(self.runtime, 'game_speed_actual', 1.0)
            self._game_speed_error = None
            return self._observe(state)
        if command == 'set_invincibility':
            command, params = 'set_feature', {'feature': 'invincibility', 'value': params.get('value')}
        if command == 'set_feature':
            name = params.get('feature')
            value = preference_value(name, params.get('value'))
            if not self.connected:
                raise AdapterError('not_connected', 'hades.error.notConnected')
            candidate = {**self.features, name: value}
            self.preferences.save(candidate)
            self.features = candidate
            if name == 'gameSpeed':
                try:
                    self._game_speed_actual = self.runtime.set_game_speed(value)
                    self._game_speed_error = None
                except AdapterError as error:
                    self._record_game_speed_error(error)
                    raise
                state = self.runtime.status() if self.connected else {**self._offline(), 'features': self.features}
                return self._observe(state)
            return self._observe(self.runtime.command(command, {'feature': name, 'value': value}))
        if command == 'disable_all':
            persistence_error = None
            try:
                self.preferences.save(DEFAULT_PREFERENCES)
            except AdapterError as error:
                persistence_error = error
            self.features = dict(DEFAULT_PREFERENCES)
            runtime_error = None
            speed_error = None
            state = {**self._offline(), 'features': self.features}
            if self.connected:
                try:
                    state = self.runtime.command('disable_all', {})
                except AdapterError as error:
                    runtime_error = error
                    if not getattr(self.runtime, 'connected', True):
                        self.connected = False
                if self.connected:
                    try:
                        self._game_speed_actual = self.runtime.set_game_speed(1.0)
                        self._game_speed_error = None
                    except AdapterError as error:
                        speed_error = error
                        self._record_game_speed_error(error)
                else:
                    self._game_speed_actual = None
            else:
                self._game_speed_actual = None
            if persistence_error:
                raise persistence_error
            if runtime_error:
                raise runtime_error
            if speed_error:
                raise speed_error
            return self._observe(state)
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
        if command == 'add_resource':
            resource = params.get('resource')
            if not isinstance(resource, str) or resource not in RESOURCE_IDS:
                raise invalid_value()
            return {'resource': resource, 'amount': number(params.get('amount'), 1, 1_000_000, integer=True)}
        if command == 'record_fish':
            biome = params.get('biome')
            quality = params.get('quality')
            if not isinstance(biome, str) or biome not in FISH_BIOMES:
                raise invalid_value()
            if not isinstance(quality, str) or quality not in FISH_QUALITIES:
                raise invalid_value()
            return {'biome': biome, 'quality': quality}
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
        if not isinstance(identifier, str) or not identifier:
            raise invalid_value()
        result = {'instanceId': identifier}
        if command == 'update_trait':
            rarity = params.get('rarity')
            if rarity not in ('Common', 'Rare', 'Epic', 'Heroic', 'Legendary'):
                raise invalid_value()
            result.update({'rarity': rarity, 'level': number(params.get('level'), 1, 100, integer=True)})
        return result

    def _reconcile_game_speed(self):
        if not self.connected:
            return
        try:
            actual = self.runtime.current_game_speed()
            self._game_speed_actual = actual
            desired = self.features['gameSpeed']
            if abs(actual - desired) > 0.000001:
                self._game_speed_actual = self.runtime.set_game_speed(desired)
            self._game_speed_error = None
        except AdapterError as error:
            self._record_game_speed_error(error)
            if error.code in ('outcome_unknown', 'restart_required') or not getattr(self.runtime, 'connected', True):
                self.connected = False

    def _record_game_speed_error(self, error):
        self._game_speed_error = {
            'presentation': error.presentation,
            'arguments': list(getattr(error, 'arguments', ()) or ()),
        }
        if error.code == 'time_warp_verify_failed' and error.arguments:
            try:
                observed = float(error.arguments[-1])
                if 0 <= observed <= 10:
                    self._game_speed_actual = observed
            except (TypeError, ValueError):
                pass
        if error.code in ('outcome_unknown', 'restart_required') or not getattr(self.runtime, 'connected', True):
            self._game_speed_actual = None
            if not getattr(self.runtime, 'connected', True):
                self.connected = False

    def _game_speed_projection(self):
        error = self._game_speed_error or {}
        actual = self._game_speed_actual
        return {
            'desired': self.features.get('gameSpeed', 1.0),
            'actual': actual,
            'active': None if actual is None else abs(actual - 1.0) > 0.000001,
            'errorPresentation': error.get('presentation'),
            'errorArguments': [str(value) for value in error.get('arguments', ())],
        }

    def _observe(self, state):
        self.connected = state['connected']
        features = state.get('features')
        features = dict(features) if isinstance(features, dict) else {}
        features['gameSpeed'] = self._game_speed_projection()
        state['features'] = features
        return state

    @staticmethod
    def _offline():
        return {'connected': False, 'heroReady': False, 'invincible': False,
                'health': 0, 'maxHealth': 0, 'money': 0, 'pid': None}

    def close(self):
        self.runtime.close()
