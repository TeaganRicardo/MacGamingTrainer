"""Hades command semantics; debugger lifetime is isolated in its own sidecar."""
from functools import partial
from pathlib import Path

from core.adapter import AdapterError, GameAdapter
from core.errors import PresentableError
from core.structured_save_edit import SaveEditorWorkspaceRegistry
from core.target_probe import (
    AmbiguousTargetError,
    BoundedCommandTimeoutError,
    bounded_run,
    locate_target,
    process_executable_path as process_executable_path,
)
from . import config
from .catalog import catalog, get_entry, resource_catalog, trait_names
from .preferences import HadesPreferenceStore
from .recovery import HadesRecoveryJournal
from .world import WORLD_COMMANDS, mutation_params as world_mutation_params, reward_catalog, world_terms
from .cheats import from_runtime_feature_map, to_runtime_feature, to_runtime_features
from .profiles import HadesProfileStore
from .diagnostics import build_diagnostics
from .operation_budgets import LAUNCH_TIMEOUT_SECONDS, PROCESS_QUERY_TIMEOUT_SECONDS
from .save_document import HadesSaveValueError
from .schema import (DEFAULT_FEATURES, LOCK_FIELDS, ONE_SHOT_COMMANDS,
                     RESOURCE_IDS, default_preferences, feature_value, preference_value, invalid_value, number)


def _rarity_params(features):
    return {
        'target': features['boonRarityTarget'],
        'forceLegendary': features['boonForceLegendary'],
        'forceDuo': features['boonForceDuo'],
    }


def _locate_hades_target(context):
    try:
        located = locate_target(context, timeout=PROCESS_QUERY_TIMEOUT_SECONDS)
    except AmbiguousTargetError as error:
        raise AdapterError('ambiguous_target', 'hades.error.ambiguousTarget') from error
    except BoundedCommandTimeoutError:
        raise
    if located is None:
        return None
    return (located.pid, str(located.executable_path))


class HadesAdapter(GameAdapter):
    def __init__(self, context, *, runtime=None, locate_process=None, preferences=None, recovery=None):
        super().__init__(context)
        if runtime is None:
            from .client import HadesRuntimeClient
            recovery = recovery or HadesRecoveryJournal(context.data_dir / 'runtime-request.json')
            runtime = HadesRuntimeClient(recovery=recovery)
        self.runtime = runtime
        if recovery is not None:
            self.recovery = recovery
        else:
            try:
                self.recovery = object.__getattribute__(runtime, 'recovery')
            except AttributeError:
                self.recovery = None
        self.locate_process = locate_process or partial(_locate_hades_target, context)
        self.connected = False
        self._connected_game_version = ''
        self.preferences = preferences or HadesPreferenceStore(context.data_dir / 'preferences.json')
        self.profiles = HadesProfileStore(self.preferences.path.parent / 'profiles')
        self.features = default_preferences()
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
        self.save_workspaces = SaveEditorWorkspaceRegistry(
            lambda: self.save_service,
            inventory=self._hades_save_inventory,
            open_workspace=self._hades_save_open,
            unavailable_error=lambda: AdapterError(
                'save_editor_unavailable',
                'hades.saveEditor.error.unavailable',
                diagnostic='Save management is unavailable.',
            ),
            not_open_error=lambda _identifier: HadesSaveValueError(
                'hades.saveEditor.error.notOpen',
                'This editor workspace is closed. Reopen the selected document.',
            ),
            stale_baseline_error=lambda: HadesSaveValueError(
                'hades.saveEditor.error.staleBaseline',
                'This control belongs to an earlier document baseline. Refresh the editor before editing.',
            ),
        )

    def _reconcile_rarity_and_occurrence(self, state):
        rarity = _rarity_params(self.features)
        observed_rarity = {
            'target': state.get('boonRarityTarget', 'Heroic'),
            'forceLegendary': state.get('boonForceLegendary', False),
            'forceDuo': state.get('boonForceDuo', False),
        }
        if observed_rarity != rarity:
            state = self.runtime.command('set_boon_rarity', rarity)
        for key, command in (('fishingChance', 'set_fishing_chance'), ('chaosGateChance', 'set_chaos_gate_chance')):
            chance = self.features[key]
            if chance is not None or state.get(key) is not None:
                state = self.runtime.command(command, {'chance': chance})
        return state

    @staticmethod
    def _hades_save_inventory(save_service, snapshot_id=None):
        from .save_workspace import HadesSaveWorkspace
        return HadesSaveWorkspace.inventory(save_service, snapshot_id)

    @staticmethod
    def _hades_save_open(save_service, *, snapshot_id=None, source=None, target=None):
        from .save_workspace import HadesSaveWorkspace
        return HadesSaveWorkspace.open(save_service, snapshot_id=snapshot_id, source=source, target=target)

    def dispatch(self, command, params, request_id):
        if command.startswith('save_editor_'):
            return self._save_editor(command[len('save_editor_'):], params)
        if command == 'list_profiles':
            return {'profiles': self.profiles.list()}
        if command == 'save_profile':
            return {'profiles': self.profiles.save(params.get('name'), self.preferences.load(), params.get('shortcuts'))}
        if command == 'delete_profile':
            return {'profiles': self.profiles.delete(params.get('name'))}
        if command == 'load_profile':
            profile = self.profiles.load_record(params.get('name'))
            features = profile['features']
            self.preferences.save(features)
            self._preferences_error = None
            self.features = features
            state = {**self._offline(), 'features': self.features}
            if self.connected:
                runtime_features = to_runtime_features(features, DEFAULT_FEATURES)
                try:
                    state = self.runtime.command('configure', {'features': runtime_features})
                    state = self._reconcile_locks(state)
                    state = self._reconcile_rarity_and_occurrence(state)
                except AdapterError as error:
                    if error.code in ('outcome_unknown', 'restart_required') or not self.runtime.connected:
                        self.connected = False
                    raise
                self._observe(state)
                speed_error = self._reconcile_game_speed()
                if speed_error:
                    raise speed_error
            observed = self._observe(state)
            observed['shortcuts'] = profile['shortcuts']
            return observed
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
            url = self.context.steam_launch_url
            if url is None:
                raise RuntimeError('Hades module manifest is missing a valid steamAppId.')
            bounded_run(['/usr/bin/open', url], LAUNCH_TIMEOUT_SECONDS, check=True)
            return self.dispatch('status', {}, request_id)
        if command == 'connect':
            target = self.locate_process()
            if target is None:
                raise AdapterError('game_not_running', 'hades.error.notRunning')
            self.features = self.preferences.load()
            self._preferences_error = None
            self._game_speed_actual = None
            self._game_speed_error = None
            runtime_features = to_runtime_features(self.features, DEFAULT_FEATURES)
            state = self.runtime.connect(*target, features=runtime_features)
            self.connected = state['connected']
            if self.connected:
                game_app, executable, _ = config.resolve_game_install(Path(target[1]))
                self._connected_game_version = config.read_build_version(game_app) if executable.is_file() else ''
                state = self._reconcile_locks(state)
                state = self._reconcile_rarity_and_occurrence(state)
            speed_error = self._reconcile_game_speed()
            if not self.connected:
                if speed_error is not None:
                    raise speed_error
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
            force_legendary = preference_value('boonForceLegendary', params.get('forceLegendary'))
            force_duo = preference_value('boonForceDuo', params.get('forceDuo'))
            candidate = {
                **self.features,
                'boonRarityTarget': target,
                'boonForceLegendary': force_legendary,
                'boonForceDuo': force_duo,
            }
            self.preferences.save(candidate)
            self.features = candidate
            if not self.connected:
                return self._observe({**self._offline(), 'features': self.features})
            return self._observe(self.runtime.command('set_boon_rarity', _rarity_params(self.features)))
        if command in ('set_fishing_chance', 'set_chaos_gate_chance'):
            self._require_known_desired_state()
            if 'chance' not in params:
                raise invalid_value()
            key = 'fishingChance' if command == 'set_fishing_chance' else 'chaosGateChance'
            value = preference_value(key, params['chance'])
            candidate = {**self.features, key: value}
            self.preferences.save(candidate)
            self.features = candidate
            if not self.connected:
                return self._observe({**self._offline(), 'features': self.features})
            return self._observe(self.runtime.command(command, {'chance': value}))
        if command == 'set_feature':
            self._require_known_desired_state()
            name = params.get('feature')
            value = preference_value(name, params.get('value')) if name == 'gameSpeed' else feature_value(name, params.get('value'))
            candidate = {**self.features, name: value}
            if name == 'infiniteMoney' and value:
                candidate['moneyLock'] = None
            if name == 'infiniteRerolls' and value:
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
            return self._observe(
                self.runtime.command(command, {'feature': to_runtime_feature(name), 'value': value})
            )
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
                resource = params.get('resource')
                if resource == 'Money':
                    runtime_params = {'resource': 'Money', 'locked': locked, 'target': target}
                    key, state_key, flag_key = 'moneyLock', 'moneyLock', 'moneyLocked'
                elif isinstance(resource, str) and resource in RESOURCE_IDS:
                    runtime_params = {'resource': resource, 'locked': locked, 'target': target}
                    key, state_key, flag_key = 'resourceLocks', 'resourceLocks', None
                else:
                    raise invalid_value()
            else:
                runtime_params = {'locked': locked, 'target': target}
                key, state_key, flag_key = 'rerollsLock', 'rerollsLock', 'rerollsLocked'
            previous = {**self.features, 'resourceLocks': dict(self.features.get('resourceLocks') or {})}
            state = self.runtime.command(command, runtime_params)
            candidate = {**self.features, 'resourceLocks': dict(self.features.get('resourceLocks') or {})}
            try:
                if flag_key is None:
                    observed_locks = state.get(state_key)
                    if not isinstance(observed_locks, dict):
                        raise AdapterError('debugger_protocol', 'hades.error.debuggerProtocol')
                    validated_locks = preference_value('resourceLocks', observed_locks)
                    if locked != (resource in validated_locks):
                        raise AdapterError('debugger_protocol', 'hades.error.debuggerProtocol')
                    candidate[key] = validated_locks
                elif state.get(flag_key) is True:
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
                self.preferences.save(default_preferences())
                self._preferences_error = None
            except AdapterError as error:
                persistence_error = error
            self.features = default_preferences()
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
            mutation_input = dict(params)
            if command in (
                'apply_world_exit', 'cancel_world_exit',
                'apply_world_occurrence', 'cancel_world_occurrence',
            ):
                mutation_input['requestId'] = request_id
            values = self._mutation_params(command, mutation_input)
            values['target'] = target
            previous = {**self.features, 'resourceLocks': dict(self.features.get('resourceLocks') or {})}
            state = self.runtime.command(command, values)
            if command == 'set_resource':
                res_name = values.get('resource')
                if res_name in previous.get('resourceLocks', {}):
                    observed_locks = state.get('resourceLocks')
                    if not isinstance(observed_locks, dict):
                        self._rollback_runtime_locks(previous)
                        raise AdapterError('debugger_protocol', 'hades.error.debuggerProtocol')
                    try:
                        validated_locks = preference_value('resourceLocks', observed_locks)
                    except AdapterError as error:
                        self._rollback_runtime_locks(previous)
                        raise AdapterError('debugger_protocol', 'hades.error.debuggerProtocol') from error
                    if validated_locks.get(res_name) != values.get('value'):
                        self._rollback_runtime_locks(previous)
                        raise AdapterError('debugger_protocol', 'hades.error.debuggerProtocol')
                    candidate = {**self.features, 'resourceLocks': validated_locks}
                    try:
                        self.preferences.save(candidate)
                    except AdapterError:
                        self._rollback_runtime_locks(previous)
                        raise
                    self.features = candidate
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
        try:
            return self.save_workspaces.handle(command, params, language=params.get('language', 'en'))
        except PresentableError:
            raise
        except (ValueError, KeyError, TypeError, OSError) as error:
            raise AdapterError('save_editor_invalid', 'hades.saveEditor.error.operationFailed',
                               diagnostic=str(error)) from error

    @staticmethod
    def _mutation_params(command, params):
        if command in WORLD_COMMANDS:
            return world_mutation_params(command, params)
        if command == 'open_sell_traits':
            return {}
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
        base = tuple(state.get(value) if state.get(flag) is True else None
                     for flag, value in LOCK_FIELDS)
        raw_res = state.get('resourceLocks')
        res = dict(raw_res) if isinstance(raw_res, dict) else {}
        return (*base, res)

    def _reconcile_locks(self, state):
        """Converge the resident's lock intent, which survives detach, on desired state."""
        desired_res = dict(self.features.get('resourceLocks') or {})
        desired = (self.features['healthLock'], self.features['moneyLock'], self.features['rerollsLock'], desired_res)
        observed = self._observed_locks(state)
        if observed == desired:
            return state
        params = {'health': desired[0], 'money': desired[1], 'rerolls': desired[2]}
        if desired_res or observed[3]:
            params['resourceLocks'] = desired_res
        return self.runtime.command('configure_locks', params)

    def _rollback_runtime_locks(self, preferences):
        try:
            self.runtime.command('configure_locks', {
                'health': preferences.get('healthLock'),
                'money': preferences.get('moneyLock'),
                'rerolls': preferences.get('rerollsLock'),
                'resourceLocks': dict(preferences.get('resourceLocks') or {}),
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
        if error.code == 'time_warp_verify_failed':
            # A corrupted TimeScale or inconsistent auto-reset/step flag leaves
            # the effective applied speed unverified. Retain a numeric observed
            # speed only when the controller explicitly reports one.
            self._game_speed_actual = None
            if error.arguments:
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
        features = (
            from_runtime_feature_map(observed, DEFAULT_FEATURES)
            if isinstance(observed, dict)
            else {}
        )
        features['gameSpeed'] = self._game_speed_projection()
        state['features'] = features
        # A live resident reply reports what it actually enforces; only a
        # detached projection shows durable desired state.
        live = state.get('connected') is True
        active = state.get('activeFeatures')
        if isinstance(active, dict):
            state['activeFeatures'] = (
                from_runtime_feature_map(active, DEFAULT_FEATURES) if live else {}
            )
        # Dormancy is the resident's observation of a desired intent waiting
        # for its native environment. A detached projection observes none.
        dormant = state.get('dormantFeatures')
        state['dormantFeatures'] = (
            from_runtime_feature_map(dormant, DEFAULT_FEATURES)
            if live and isinstance(dormant, dict)
            else {}
        )
        for flag, value in LOCK_FIELDS:
            if live and type(state.get(flag)) is bool:
                state[value] = state.get(value) if state[flag] else None
            else:
                state[value] = self.features.get(value)
                state[flag] = state[value] is not None
        if live and isinstance(state.get('resourceLocks'), dict):
            state['resourceLocks'] = dict(state['resourceLocks'])
        else:
            state['resourceLocks'] = dict(self.features.get('resourceLocks') or {})
        if not (live and state.get('boonRarityTarget') in ('Common', 'Rare', 'Epic', 'Heroic')):
            state['boonRarityTarget'] = self.features.get('boonRarityTarget', 'Heroic')
        for flag in ('boonForceLegendary', 'boonForceDuo'):
            if not (live and type(state.get(flag)) is bool):
                state[flag] = self.features.get(flag, False)
        state['canOpenSellTraits'] = bool(state.get('canOpenSellTraits')) if live else False
        for key in ('fishingChance', 'chaosGateChance'):
            if live:
                raw = state.get(key)
                state[key] = float(raw) if type(raw) in (int, float) else None
            else:
                state[key] = self.features.get(key)
        pending_recovery = self._describe_recovery()
        state['recovery'] = pending_recovery
        if live:
            state['version'] = self._connected_game_version
            raw_status = state.get('status')
            if not isinstance(raw_status, str) or not raw_status:
                state['status'] = 'ready' if state.get('heroReady') else 'waiting'
            raw_scene = state.get('scene')
            if not isinstance(raw_scene, str) or not raw_scene:
                state['scene'] = 'unknown'
        else:
            located = None
            locate_error = None
            try:
                located = self.locate_process()
            except (AdapterError, BoundedCommandTimeoutError) as error:
                locate_error = error
            located_exe = Path(located[1]) if located is not None and len(located) > 1 and located[1] else None
            if located_exe is not None and located_exe.is_file():
                install = config.inspect_install(located_exe)
                installed, compatible = install['installed'], install['compatible']
                state['version'] = install['version']
            else:
                game_app, executable, _ = config.resolve_game_install()
                installed = game_app.is_dir() and executable.is_file()
                compatible = True
                state['version'] = config.read_build_version(game_app) if installed else ''
            observed_pid = located[0] if located is not None else state.get('pid')
            state['pid'] = observed_pid
            state['scene'] = 'unknown'
            state['roomName'] = None
            state['runtimeRevision'] = None
            recovery_matches = (
                pending_recovery is not None
                and (
                    pending_recovery.get('outcome') == 'unavailable'
                    or observed_pid is None
                    or pending_recovery.get('pid') == observed_pid
                )
            )
            if recovery_matches:
                state['status'] = 'restart_required'
            elif located is not None:
                if not compatible:
                    state['status'] = 'incompatible'
                else:
                    state['status'] = 'disconnected'
            elif locate_error is not None and getattr(locate_error, 'code', None) == 'ambiguous_target':
                state['status'] = 'disconnected'
            else:
                state['status'] = 'not_running' if installed else 'not_installed'
        return state

    def _describe_recovery(self):
        if self.recovery is None or not callable(getattr(self.recovery, 'describe', None)):
            return None
        try:
            return self.recovery.describe()
        except AdapterError as error:
            return {'outcome': 'unavailable', 'presentation': error.presentation}

    def state_for_error(self):
        return self._observe({**self._offline(), 'features': self.features})

    @staticmethod
    def _offline():
        return {'connected': False, 'heroReady': False, 'invincible': False,
                'health': 0, 'maxHealth': 0, 'money': 0, 'pid': None}

    def close(self):
        self.save_workspaces.clear()
        self.runtime.close()
