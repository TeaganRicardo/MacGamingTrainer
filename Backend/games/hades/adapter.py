"""Hades command semantics; debugger lifetime is isolated in its own sidecar."""
import ctypes
import os
from pathlib import Path
import subprocess

from core.adapter import AdapterError, GameAdapter
from .catalog import catalog, get_entry, resource_catalog, trait_names
from .preferences import HadesPreferenceStore
from .world import WORLD_COMMANDS, mutation_params as world_mutation_params, reward_catalog, world_terms
from .profiles import HadesProfileStore
from .diagnostics import build_diagnostics
from .schema import (DEFAULT_FEATURES, DEFAULT_PREFERENCES, ONE_SHOT_COMMANDS,
                     RESOURCE_IDS, preference_value, invalid_value, number)


EXECUTABLE_SUFFIX = 'Hades/Game.macOS.app/Contents/MacOS/Game.macOS'


def _process_executable_path(pid):
    """Return the kernel-reported executable path for a macOS process."""
    try:
        libproc = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
        proc_pidpath = libproc.proc_pidpath
        proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        proc_pidpath.restype = ctypes.c_int
        buffer = ctypes.create_string_buffer(1024)
        length = proc_pidpath(pid, buffer, len(buffer))
        if length <= 0:
            return None
        return os.fsdecode(buffer.value)
    except (OSError, AttributeError):
        return None


def locate_process():
    rows = subprocess.check_output(['/bin/ps', '-axo', 'pid=,comm='], text=True)
    matches = []
    executable_name = Path(EXECUTABLE_SUFFIX).name
    for row in rows.splitlines():
        parts = row.strip().split(None, 1)
        if len(parts) != 2:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue

        command = parts[1]
        if command.endswith('/' + EXECUTABLE_SUFFIX):
            executable = command
        elif Path(command).name == executable_name:
            # Some launch paths expose only argv[0] through ps(1). Verify the
            # actual executable with proc_pidpath before accepting the process.
            executable = _process_executable_path(pid)
            if not executable or not executable.endswith('/' + EXECUTABLE_SUFFIX):
                continue
        else:
            continue
        matches.append((pid, str(Path(executable).resolve())))

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
        self.profiles = HadesProfileStore(self.preferences.path.parent / 'profiles')
        self.features = dict(DEFAULT_PREFERENCES)
        self._game_speed_actual = None
        self._game_speed_error = None
        self.save_workspaces = {}

    def dispatch(self, command, params, request_id):
        if command.startswith('save_editor_'):
            return self._save_editor(command[len('save_editor_'):], params)
        if command == 'list_profiles':
            return {'profiles': self.profiles.list()}
        if command == 'save_profile':
            self.profiles.save(params.get('name'), self.preferences.load())
            return {'profiles': self.profiles.list()}
        if command == 'delete_profile':
            self.profiles.delete(params.get('name'))
            return {'profiles': self.profiles.list()}
        if command == 'load_profile':
            features = self.profiles.load(params.get('name'))
            self.preferences.save(features)
            self.features = features
            state = {**self._offline(), 'features': self.features}
            if self.connected:
                runtime_features = {name: value for name, value in features.items() if name in DEFAULT_FEATURES}
                try:
                    state = self.runtime.command('configure', {'features': runtime_features})
                except AdapterError as error:
                    if error.code in ('outcome_unknown', 'restart_required') or not self.runtime.connected:
                        self.connected = False
                    raise
                self._observe(state)
                speed_error = self._reconcile_game_speed()
                if speed_error:
                    raise speed_error
            return self._observe(state)
        if command == 'diagnostics':
            state = self.dispatch('status', {}, request_id)
            return {**state, 'diagnostics': build_diagnostics(self, state)}
        if command == 'catalog':
            try:
                language = params.get('language', 'zh-CN')
                return {'catalog': catalog(language, params.get('query', ''), params.get('kind', 'all')),
                        'resourceCatalog': resource_catalog(language), 'traitNames': trait_names(),
                        'worldRewards': reward_catalog(), 'worldTerms': world_terms()}
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

    def _save_editor(self, command, params):
        from .save_workspace import HadesSaveWorkspace
        if self.save_service is None:
            raise AdapterError('save_editor_unavailable', 'hades.saveEditor.error',
                               arguments=['Save management is unavailable.'])
        try:
            if command == 'inventory':
                return HadesSaveWorkspace.inventory(self.save_service, params.get('snapshotId'))
            if command == 'open':
                workspace = HadesSaveWorkspace.open(self.save_service,
                    snapshot_id=params.get('snapshotId'), source=params.get('source'), target=params.get('target'))
                self.save_workspaces[workspace.identifier] = workspace
                return workspace.summary(params.get('language', 'en'))
            identifier = params.get('workspaceId')
            if not isinstance(identifier, str) or identifier not in self.save_workspaces:
                raise ValueError('This editor workspace is closed. Reopen the selected document.')
            workspace = self.save_workspaces[identifier]
            if command == 'close':
                del self.save_workspaces[identifier]
                return {'closed': True}
            if command == 'target': return workspace.set_target(params['target'], baseline_generation=params.get('baselineGeneration'))
            if command == 'query':
                return workspace.query(**{key: value for key, value in params.items() if key != 'workspaceId'})
            language = params.get('language', 'en')
            if command == 'detail': return workspace.detail(params['entryId'], language)
            if command == 'stage': return workspace.stage(params['entryId'], params['operation'], params.get('value'), language,
                                                         baseline_generation=params.get('baselineGeneration'))
            if command == 'unstage': return workspace.unstage(params['entryId'], language,
                                                             baseline_generation=params.get('baselineGeneration'))
            if command == 'review': return workspace.review(language)
            if command == 'cancel': return workspace.cancel(language, baseline_generation=params.get('baselineGeneration'))
            if command == 'apply': return workspace.apply(baseline_generation=params.get('baselineGeneration'))
            raise ValueError('Unknown Save Editor operation.')
        except (ValueError, KeyError, TypeError, OSError) as error:
            recovery = getattr(error, 'recovery_path', None)
            wrapped = AdapterError('rollback_failed' if recovery is not None else 'save_editor_invalid', 'hades.saveEditor.error',
                                   diagnostic=str(error), arguments=[str(error)])
            if recovery is not None: wrapped.recovery_path = str(recovery)
            raise wrapped from error

    @staticmethod
    def _mutation_params(command, params):
        if command in WORLD_COMMANDS:
            return world_mutation_params(command, params)
        if command == 'set_value':
            field = params.get('field')
            if field not in ('health', 'maxHealth', 'money', 'rerolls', 'godGauge'):
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
            if entry is None or entry.get('acquirable') is False:
                raise invalid_value()
            rarity = params.get('rarity')
            if rarity not in entry['rarities']:
                raise invalid_value()
            level = number(params.get('level'), 1, 100, integer=True)
            if not entry.get('supportsLevel', True) and level != 1:
                raise invalid_value()
            return {'trait': identifier, 'rarity': rarity, 'level': level}
        if command == 'add_chaos_pair':
            blessing, curse = params.get('blessing'), params.get('curse')
            entry = get_entry(blessing) if isinstance(blessing, str) else None
            curse_entry = get_entry(curse) if isinstance(curse, str) else None
            if (entry is None or entry['kind'] != 'chaos' or curse_entry is None
                    or curse_entry['kind'] != 'curse' or params.get('rarity') not in entry['rarities']):
                raise invalid_value()
            return {'blessing': blessing, 'curse': curse, 'rarity': params['rarity'],
                    'encounters': number(params.get('encounters'), 1, 100, integer=True)}
        identifier = params.get('instanceId')
        if not isinstance(identifier, str) or not identifier:
            raise invalid_value()
        result = {'instanceId': identifier}
        if command == 'set_trait_uses':
            result['uses'] = number(params.get('uses'), 0, 1000, integer=True)
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
            return error

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
        self.save_workspaces.clear()
        self.runtime.close()
