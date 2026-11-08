"""Hades command semantics; debugger lifetime is isolated in its own sidecar."""
import ctypes
from functools import partial
import os
from pathlib import Path
import subprocess
import sys

from core.adapter import AdapterError, GameAdapter
from .catalog import catalog, get_entry, resource_catalog, trait_names
from .config import steam_launch_url
from .preferences import HadesPreferenceStore
from .world import WORLD_COMMANDS, mutation_params as world_mutation_params, reward_catalog, world_terms
from .profiles import HadesProfileStore
from .diagnostics import build_diagnostics
from .schema import (DEFAULT_FEATURES, DEFAULT_PREFERENCES, LOCK_FIELDS, ONE_SHOT_COMMANDS,
                     RESOURCE_IDS, feature_value, preference_value, invalid_value, number)


def process_executable_path(pid):
    """Return the kernel-reported executable path for a PID on macOS."""
    if sys.platform != 'darwin':
        return None
    try:
        libproc = ctypes.CDLL('/usr/lib/libproc.dylib')
        proc_pidpath = libproc.proc_pidpath
        proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        proc_pidpath.restype = ctypes.c_int
        buffer = ctypes.create_string_buffer(4096)
        length = proc_pidpath(pid, buffer, len(buffer))
    except (OSError, AttributeError):
        return None
    if length <= 0:
        return None
    return str(Path(os.fsdecode(buffer.value)).resolve())


def _locate_process(executable_suffix):
    rows = subprocess.check_output(['/bin/ps', '-axo', 'pid=,comm='], text=True)
    expected_name = Path(executable_suffix).name
    matches = []
    for row in rows.splitlines():
        parts = row.strip().split(None, 1)
        if len(parts) != 2:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        command = parts[1]
        # BSD ps may expose a process command name rather than its executable
        # path. Use it only to narrow candidates; proc_pidpath verifies identity.
        if Path(command).name != expected_name and not command.endswith('/' + executable_suffix):
            continue
        executable = process_executable_path(pid)
        if executable is None and command.endswith('/' + executable_suffix):
            executable = str(Path(command).resolve())
        if executable is None:
            continue
        executable = str(Path(executable).resolve())
        if executable.endswith('/' + executable_suffix):
            matches.append((pid, executable))
    if len(matches) > 1:
        raise AdapterError('ambiguous_target', 'hades.error.ambiguousTarget')
    return matches[0] if matches else None


class HadesAdapter(GameAdapter):
    def __init__(self, context, *, runtime=None, locate_process=None, preferences=None):
        super().__init__(context)
        if runtime is None:
            from .client import HadesRuntimeClient
            runtime = HadesRuntimeClient()
        self.runtime = runtime
        self.locate_process = locate_process or partial(_locate_process, context.executable_path_suffix)
        self.connected = False
        self.preferences = preferences or HadesPreferenceStore()
        self.profiles = HadesProfileStore(self.preferences.path.parent / 'profiles')
        self.features = dict(DEFAULT_PREFERENCES)
        self._preferences_error = None
        try:
            self.features = self.preferences.load()
        except AdapterError as error:
            # Keep the backend available. Edits that merge into the unread
            # document are refused (see _require_known_desired_state) so the
            # durable file is never replaced by defaults plus one change.
            self._preferences_error = error
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
            self._preferences_error = None
            self.features = features
            state = {**self._offline(), 'features': self.features}
            if self.connected:
                runtime_features = {name: value for name, value in features.items() if name in DEFAULT_FEATURES}
                try:
                    state = self.runtime.command('configure', {'features': runtime_features})
                    state = self._reconcile_locks(state)
                    if features['boonRarityTarget'] != 'Heroic':
                        state = self.runtime.command(
                            'set_boon_rarity', {'target': features['boonRarityTarget']}
                        )
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
            subprocess.run(['/usr/bin/open', steam_launch_url(self.context.module_dir)], check=True)
            return self.dispatch('status', {}, request_id)
        if command == 'connect':
            target = self.locate_process()
            if target is None:
                raise AdapterError('game_not_running', 'hades.error.notRunning')
            self.features = self.preferences.load()
            self._preferences_error = None
            self._game_speed_actual = None
            self._game_speed_error = None
            runtime_features = {name: value for name, value in self.features.items() if name in DEFAULT_FEATURES}
            state = self.runtime.connect(*target, features=runtime_features)
            self.connected = state['connected']
            if self.connected:
                state = self._reconcile_locks(state)
            if self.connected and self.features['boonRarityTarget'] != 'Heroic':
                state = self.runtime.command(
                    'set_boon_rarity', {'target': self.features['boonRarityTarget']}
                )
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
            if not state.get('connected'):
                state = {**state, 'features': self.features}
            return self._observe(state)
        if command == 'set_boon_rarity':
            self._require_known_desired_state()
            target = preference_value('boonRarityTarget', params.get('target'))
            candidate = {**self.features, 'boonRarityTarget': target}
            self.preferences.save(candidate)
            self.features = candidate
            if not self.connected:
                return self._observe({**self._offline(), 'features': self.features})
            return self._observe(self.runtime.command('set_boon_rarity', {'target': target}))
        if command == 'set_feature':
            self._require_known_desired_state()
            name = params.get('feature')
            value = preference_value(name, params.get('value')) if name == 'gameSpeed' else feature_value(name, params.get('value'))
            candidate = {**self.features, name: value}
            if name == 'moneyNoDecrease' and value:
                candidate['moneyLock'] = None
            if name == 'rerollsNoDecrease' and value:
                candidate['rerollsLock'] = None
            self.preferences.save(candidate)
            self.features = candidate
            if name == 'gameSpeed':
                if not self.connected:
                    self._game_speed_actual = None
                    self._game_speed_error = None
                    return self._observe({**self._offline(), 'features': self.features})
                try:
                    self._game_speed_actual = self.runtime.set_game_speed(value)
                    self._game_speed_error = None
                except AdapterError as error:
                    self._record_game_speed_error(error)
                    raise
                return self._observe(self.runtime.status())
            if not self.connected:
                return self._observe({**self._offline(), 'features': self.features})
            return self._observe(self.runtime.command(command, {'feature': name, 'value': value}))
        if command in ('lock_vital', 'lock_resource', 'lock_rerolls'):
            if not self.connected:
                raise AdapterError('not_connected', 'hades.error.notConnected')
            target = params.get('target')
            if not isinstance(target, dict) or not isinstance(target.get('heroId'), str) or not target['heroId']:
                raise AdapterError('stale_target', 'hades.error.staleTarget')
            locked = params.get('locked')
            if type(locked) is not bool:
                raise invalid_value()
            self._require_known_desired_state()
            if command == 'lock_vital':
                if params.get('vital') != 'health':
                    raise invalid_value()
                runtime_params = {'vital': 'health', 'locked': locked, 'target': target}
                key, state_key, flag_key = 'healthLock', 'healthLock', 'healthLocked'
            elif command == 'lock_resource':
                if params.get('resource') != 'Money':
                    raise invalid_value()
                runtime_params = {'resource': 'Money', 'locked': locked, 'target': target}
                key, state_key, flag_key = 'moneyLock', 'moneyLock', 'moneyLocked'
            else:
                runtime_params = {'locked': locked, 'target': target}
                key, state_key, flag_key = 'rerollsLock', 'rerollsLock', 'rerollsLocked'
            previous = dict(self.features)
            state = self.runtime.command(command, runtime_params)
            candidate = dict(self.features)
            try:
                if state.get(flag_key) is True:
                    candidate[key] = (
                        preference_value('healthLock', state.get(state_key))
                        if key == 'healthLock'
                        else number(state.get(state_key), 0, 1_000_000_000, integer=True)
                    )
                elif state.get(flag_key) is False:
                    candidate[key] = None
                else:
                    raise AdapterError('debugger_protocol', 'hades.error.debuggerProtocol')
            except AdapterError as error:
                self._rollback_runtime_locks(previous)
                if error.code == 'invalid_value':
                    raise AdapterError('debugger_protocol', 'hades.error.debuggerProtocol') from error
                raise
            try:
                self.preferences.save(candidate)
            except AdapterError:
                self._rollback_runtime_locks(previous)
                raise
            self.features = candidate
            return self._observe(state)
        if command == 'disable_all':
            persistence_error = None
            try:
                self.preferences.save(DEFAULT_PREFERENCES)
                self._preferences_error = None
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
            previous = dict(self.features)
            state = self.runtime.command(command, values)
            if command == 'set_value':
                key = {
                    'health': 'healthLock',
                    'maxHealth': 'healthLock',
                    'money': 'moneyLock',
                    'rerolls': 'rerollsLock',
                }.get(values.get('field'))
                if key is not None and previous.get(key) is not None:
                    state_key = key
                    flag_key = {
                        'healthLock': 'healthLocked',
                        'moneyLock': 'moneyLocked',
                        'rerollsLock': 'rerollsLocked',
                    }[key]
                    if state.get(flag_key) is not True:
                        self._rollback_runtime_locks(previous)
                        raise AdapterError('debugger_protocol', 'hades.error.debuggerProtocol')
                    candidate = dict(self.features)
                    try:
                        candidate[key] = (
                            preference_value('healthLock', state.get(state_key))
                            if key == 'healthLock'
                            else number(state.get(state_key), 0, 1_000_000_000, integer=True)
                        )
                    except AdapterError as error:
                        self._rollback_runtime_locks(previous)
                        raise AdapterError(
                            'debugger_protocol', 'hades.error.debuggerProtocol'
                        ) from error
                    try:
                        self.preferences.save(candidate)
                    except AdapterError:
                        self._rollback_runtime_locks(previous)
                        raise
                    self.features = candidate
            return self._observe(state)
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

    def _require_known_desired_state(self):
        if self._preferences_error is not None:
            # Re-read: raises the typed failure while the document stays unreadable.
            self.features = self.preferences.load()
            self._preferences_error = None

    @staticmethod
    def _observed_locks(state):
        return tuple(state.get(value) if state.get(flag) is True else None
                     for flag, value in LOCK_FIELDS)

    def _reconcile_locks(self, state):
        """Converge the resident's lock intent, which survives detach, on desired state."""
        desired = (self.features['healthLock'], self.features['moneyLock'], self.features['rerollsLock'])
        if self._observed_locks(state) == desired:
            return state
        return self.runtime.command('configure_locks', {
            'health': desired[0], 'money': desired[1], 'rerolls': desired[2],
        })

    def _rollback_runtime_locks(self, preferences):
        try:
            self.runtime.command('configure_locks', {
                'health': preferences.get('healthLock'),
                'money': preferences.get('moneyLock'),
                'rerolls': preferences.get('rerollsLock'),
            })
        except AdapterError:
            # The original persistence/protocol failure remains authoritative.
            # Recovery on reconnect will replay the durable document.
            pass

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
        observed = state.get('features')
        features = ({name: value for name, value in observed.items() if name in DEFAULT_FEATURES}
                    if isinstance(observed, dict) else {})
        features['gameSpeed'] = self._game_speed_projection()
        state['features'] = features
        # A live resident reply reports what it actually enforces; only a
        # detached projection shows durable desired state.
        live = state.get('connected') is True
        for flag, value in LOCK_FIELDS:
            if live and type(state.get(flag)) is bool:
                state[value] = state.get(value) if state[flag] else None
            else:
                state[value] = self.features.get(value)
                state[flag] = state[value] is not None
        if not (live and state.get('boonRarityTarget') in ('Common', 'Rare', 'Epic', 'Heroic')):
            state['boonRarityTarget'] = self.features.get('boonRarityTarget', 'Heroic')
        return state

    @staticmethod
    def _offline():
        return {'connected': False, 'heroReady': False, 'invincible': False,
                'health': 0, 'maxHealth': 0, 'money': 0, 'pid': None}

    def close(self):
        self.save_workspaces.clear()
        self.runtime.close()
