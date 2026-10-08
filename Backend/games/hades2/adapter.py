"""JSONL worker; one request at a time, no network or arbitrary-code endpoint."""
import copy
import logging
import math
import subprocess
import time
from pathlib import Path

from core.adapter import AdapterError, GameAdapter, GameAdapterContext
from core.process_time_warp import ProcessTimeWarpController, ProcessTimeWarpError

from . import preparation
from .command_contract import Hades2CommandContract
from .desired_reconciliation import Hades2DesiredStateReconciler
from .vital_state import normalize_vital_locks, observed_vital_lock, observed_vital_values
from .config import DATA, GAME_SPEC, MODULE_MANIFEST, STEAM_SPEC
from .persistence import PersistenceError
from .preferences import Hades2PreferenceStore, next_room_reward_consumed
from .profile_service import Hades2ProfileService
from .resident_session import Hades2ResidentSession, ResidentGenerationInvalidated, ResidentSessionError
from .save_workspace import Hades2SaveWorkspace
from .schema import (
    MULTIPLIERS,
    STAT_RULES,
    TOGGLES,
    default_boon_rarity,
    desired_feature_defaults,
    disconnected_capabilities,
    is_valid_next_room_reward,
    normalize_gathering_probabilities,
    validate_gathering_desired,
    normalize_chaos_gate_probability,
    validate_chaos_gate_probability,
)

# Keep these imports public for established adapter-module consumers. In
# particular, tests and downstream callers import STAT_RULES from here.
__all__ = [
    'MULTIPLIERS',
    'STAT_RULES',
    'TOGGLES',
    'AdapterError',
    'GameAdapter',
    'GameAdapterContext',
    'Hades2Adapter',
    'TransportError',
]

TransportError = AdapterError
_TRANSIENT_ACTION_RESULT_FIELDS = (
    'requestId','duplicate','applied','actionOutcome','actionError','lootObjectId',
)

def clear_active(state,preserve_desired=False):
    """Clear verified runtime state; optionally retain the user's desired feature profile."""
    if not preserve_desired:
        defaults=desired_feature_defaults()
        state.update({key:defaults[key] for key in TOGGLES})
        state['desiredFeatures']={key:defaults[key] for key in TOGGLES}
        state['gameSpeed']=defaults['gameSpeed']
        state['gatheringProbabilities']={}
        state['chaosGateProbability']=None
    state['gatheringTargets']={}
    state.update(moneyLocked=False,rerollsLocked=False,healthLocked=False,manaLocked=False,armorLocked=False,scene='unknown')
    stats=state.get('stats')
    if isinstance(stats,dict):
        for item in stats.values():
            if isinstance(item,dict):item['locked']=False;item['target']=None
    state['activeFeatures']={key:False for key in TOGGLES};state['activeFeatures']['gameSpeed']=False
    state['dormantFeatures']={}
    state['capabilities']=disconnected_capabilities()
    for resource in state.get('resources',[]):resource['locked']=False
    for element in state.get('elements',[]):
        if isinstance(element,dict):element['locked']=False

def mark_disconnected(state):
    """Lose transport verification without pretending the Lua session was cleared."""
    state.update(connected=False, scene='unknown')
    state['gatheringTargets']={}
    state['activeFeatures']={key:False for key in TOGGLES}; state['activeFeatures']['gameSpeed']=False
    state['dormantFeatures']={}
    state['featureErrors']={}
    state['featureErrorPresentations']={}
    state['capabilities']=disconnected_capabilities()



_PREPERSISTED_RUNTIME_COMMANDS = frozenset((
    'set_feature', 'set_boon_rarity', 'set_next_room_reward', 'set_gathering_probabilities', 'set_chaos_gate_probability',
))
class Hades2Adapter(GameAdapter):
    data_dir = DATA
    def __init__(self, transport=None, context=None, resident_session=None, time_warp_controller=None):
        if context is None:
            context = GameAdapterContext(
                game_id=MODULE_MANIFEST.id,
                display_name=MODULE_MANIFEST.display_name,
                module_protocol_version=MODULE_MANIFEST.module_protocol_version,
                module_dir=Path(__file__).resolve().parent,
                public_metadata=MODULE_MANIFEST.public_metadata(),
                process_name=MODULE_MANIFEST.process_name,
                save_management=MODULE_MANIFEST.save_management,
            )
        super().__init__(context)
        if resident_session is None:
            if transport is None:
                from .transport_client import Hades2LuaTransport
                transport = Hades2LuaTransport()
            self.runtime=Hades2ResidentSession(transport)
        else:
            if transport is not None:
                raise ValueError('resident_session and transport are mutually exclusive.')
            self.runtime=resident_session
        if time_warp_controller is None:
            if transport is None:
                raise ValueError('time_warp_controller is required with an injected resident_session.')
            helper_path=Path(__file__).resolve().parents[2]/'core/native/libMGTTimeWarp.dylib'
            create_remote_time_warp=getattr(transport,'create_time_warp_controller',None)
            if callable(create_remote_time_warp):
                time_warp_controller=create_remote_time_warp(
                    helper_path,[GAME_SPEC.executable_name]
                )
            else:
                from .lldb_time_warp import LLDBProcessTimeWarpDriver
                time_warp_controller=ProcessTimeWarpController(
                    LLDBProcessTimeWarpDriver(transport),helper_path,[GAME_SPEC.executable_name]
                )
        self.time_warp=time_warp_controller
        self.desired_reconciler=Hades2DesiredStateReconciler(self.runtime)
        self._time_warp_speed=None;self._time_warp_pid=None;self._time_warp_error=None
        self._last_status_boundary_duration=0.0;self._last_status_json_duration=0.0;self._last_status_localize_duration=0.0
        desired_defaults=desired_feature_defaults()
        self.state={'connected':False,'pid':None,'version':'1.'+preparation.VERSION,'status':'disconnected','scene':'unknown',
                    **desired_defaults,
                    'resources':[],'rewards':[],'stats':{},'statSupport':{},'elements':[], 'boonRarity':default_boon_rarity(), 'nextRoomReward':None, 'gatheringProbabilities':{}, 'gatheringTargets':{},
                    'desiredFeatures':{key:desired_defaults[key] for key in TOGGLES},
                    'activeFeatures':{key:False for key in TOGGLES},
                    'dormantFeatures':{},
                    'featureErrorPresentations':{},
                    'capabilities':disconnected_capabilities()}
        self.preference_store=Hades2PreferenceStore(preparation.DATA/'desired-state.json')
        self.preferences,self.preference_initialized=self.preference_store.load()
        self.preference_write_blocked=self.preference_store.write_blocked_error is not None
        self.profile_service=Hades2ProfileService(preparation.DATA/'profiles')
        self.command_contract=Hades2CommandContract(self)
        self.save_workspace=None
        # A persisted desired profile is intentionally treated as pending on a
        # fresh backend process. If the resident Lua module already matches it,
        # replay is a no-op; if Hades itself restarted, the same profile is
        # automatically restored on the first ready connection.
        self._preference_runtime_dirty=(
            self.preference_initialized and not self.preference_write_blocked
        )
        self._preference_persistence_dirty=False
        self._overlay_preferences()

    @staticmethod
    def _default_preferences():
        return Hades2PreferenceStore.defaults()

    def _normalize_preferences(self,raw):
        return Hades2PreferenceStore.normalize(raw)

    @property
    def preference_dirty(self):
        return self._preference_runtime_dirty or self._preference_persistence_dirty

    @preference_dirty.setter
    def preference_dirty(self,value):
        # Existing callers/tests use this as the runtime-reconciliation flag.
        # Durable-write pending is owned separately and cannot be cleared here.
        self._preference_runtime_dirty=bool(value)

    def _persist_preferences_candidate(self,preferences):
        # Candidate writes happen before adopting new in-memory desired state.
        # A successful full-document write also resolves any older persistence
        # pending state carried by the current desired snapshot.
        self.preference_store.save(preferences)
        self._preference_persistence_dirty=False

    def _save_preferences(self):
        try:
            self.preference_store.save(self.preferences)
        except PersistenceError:
            self._preference_persistence_dirty=True
            raise
        self._preference_persistence_dirty=False

    def list_profiles(self):
        return self.profile_service.list()

    def save_profile(self,name,shortcuts=None):
        # Profiles snapshot canonical durable desired state. Runtime/public
        # projection may lag while reconciliation is pending and must never
        # overwrite that intent merely because the user saves a Profile.
        return self.profile_service.save(name,self.preferences,shortcuts)

    def delete_profile(self,name):
        return self.profile_service.delete(name)

    def load_profile(self,name):
        profile=self.profile_service.load(name)
        preferences=self._normalize_preferences(profile['desired'])
        if preferences.get('nextRoomReward') is not None:
            preferences['nextRoomRewardToken']='profile-'+str(time.time_ns())
        observed_state=None
        if self.runtime.alive() and self.state.get('connected'):
            observed_state=copy.deepcopy(self.observe_runtime())
        self._persist_preferences_candidate(preferences)
        self.preferences=preferences
        self.preference_initialized=True;self.preference_dirty=True
        self._overlay_preferences()
        if self.runtime.alive() and isinstance(observed_state,dict):
            self._replay_preferences(observed_state,force_full=True)
        result=dict(self.state);result.update(loadedProfile=profile['name'],shortcuts=profile['shortcuts'],profiles=self.list_profiles())
        return result

    def _overlay_preferences(self):
        defaults=desired_feature_defaults()
        desired={key:bool(self.preferences.get(key,defaults[key])) for key in TOGGLES}
        self.state['desiredFeatures']=desired
        for key,value in desired.items():self.state[key]=value
        for key in MULTIPLIERS:self.state[key]=self.preferences.get(key,defaults[key])
        self.state['boonRarity']=dict(self.preferences.get('boonRarity',{}))
        self.state['nextRoomReward']=self.preferences.get('nextRoomReward')
        self.state['gatheringProbabilities']=dict(self.preferences.get('gatheringProbabilities',{}))
        self.state['chaosGateProbability']=self.preferences.get('chaosGateProbability')
        stat_locks=self.preferences.get('statLocks',{}) if isinstance(self.preferences.get('statLocks'),dict) else {}
        stats=self.state.get('stats') if isinstance(self.state.get('stats'),dict) else {}
        for stat,target in stat_locks.items():
            row=stats.get(stat) if isinstance(stats.get(stat),dict) else {}
            row=dict(row,locked=True,target=target,value=target);stats[stat]=row
        for stat,row in stats.items():
            if stat not in stat_locks and isinstance(row,dict):row['locked']=False;row['target']=None
        self.state['stats']=stats
        vital=self.preferences.get('vitalLocks',{}) if isinstance(self.preferences.get('vitalLocks'),dict) else {}
        for key in ('health','mana','armor'):
            self.state[key+'Locked']=key in vital
        resources=self.preferences.get('resourceLocks',{}) if isinstance(self.preferences.get('resourceLocks'),dict) else {}
        self.state['moneyLocked']='Money' in resources
        if 'Money' in resources:self.state['money']=resources['Money']
        for item in self.state.get('resources',[]):
            if isinstance(item,dict) and isinstance(item.get('id'),str):
                item['locked']=item['id'] in resources
                if item['locked']:item['count']=resources[item['id']]
        reroll=self.preferences.get('rerollsLock')
        self.state['rerollsLocked']=reroll is not None
        if reroll is not None:self.state['rerolls']=reroll
        elements=self.preferences.get('elementLocks',{}) if isinstance(self.preferences.get('elementLocks'),dict) else {}
        for item in self.state.get('elements',[]):
            if isinstance(item,dict) and isinstance(item.get('id'),str):
                item['locked']=item['id'] in elements
                if item['locked']:item['count']=elements[item['id']]
        self._project_time_warp()

    def _project_time_warp(self):
        active=self.state.get('activeFeatures')
        active=dict(active) if isinstance(active,dict) else {}
        active['gameSpeed']=self._time_warp_speed is not None and abs(self._time_warp_speed-1.0)>1e-6
        self.state['activeFeatures']=active
        support=self.state.get('featureSupport')
        support=dict(support) if isinstance(support,dict) else {}
        support['gameSpeed']=True
        self.state['featureSupport']=support
        # Runtime-native feature errors remain in the legacy string map. A
        # Core-owned Time Warp failure carries a presentation token instead so
        # the frontend can resolve the Host key in the live language without
        # embedding localized copy in module state.
        errors=self.state.get('featureErrors')
        errors=dict(errors) if isinstance(errors,dict) else {}
        errors.pop('gameSpeed',None)
        self.state['featureErrors']=errors
        presentations=self.state.get('featureErrorPresentations')
        presentations=dict(presentations) if isinstance(presentations,dict) else {}
        if self._time_warp_error:presentations['gameSpeed']=dict(self._time_warp_error)
        else:presentations.pop('gameSpeed',None)
        self.state['featureErrorPresentations']=presentations
        diagnostics=self.state.get('runtimeDiagnostics')
        if isinstance(diagnostics,dict):
            diagnostics=dict(diagnostics)
            diagnostics['gameSpeedMethod']='processTimeWarp'
            diagnostics['gameSpeedAppliedValue']=self._time_warp_speed
            self.state['runtimeDiagnostics']=diagnostics

    def _apply_game_speed(self,value):
        try:
            actual=self.time_warp.reset() if abs(float(value)-1.0)<1e-9 else self.time_warp.set_speed(float(value))
        except AdapterError as error:
            self._time_warp_error={
                'presentation':error.presentation,
                'arguments':list(getattr(error,'arguments',()) or ()),
            }
            self._project_time_warp();raise
        self._time_warp_speed=float(actual);self._time_warp_pid=self.runtime.pid
        self._time_warp_error=None;self._project_time_warp()
        return self._time_warp_speed

    def _invalidate_game_speed_observation(self):
        self._time_warp_speed=None;self._time_warp_pid=None;self._time_warp_error=None
        self.preference_dirty=True
        self._project_time_warp()

    def _mark_disconnected(self):
        self._invalidate_game_speed_observation()
        mark_disconnected(self.state)

    def _project_detached_runtime(self):
        self.state.update(connected=False,status='disconnected')
        self._mark_disconnected()
        self._overlay_preferences()

    def _attach_runtime(self,pid):
        try:
            self.runtime.attach(pid)
        except Exception:
            if self.runtime.pid is None:self._project_detached_runtime()
            raise

    def _detach_runtime(self):
        detached=False
        try:
            self.runtime.detach()
            detached=True
        finally:
            # Release can complete before OS resume reports a failure. All
            # attachment cleanup callers share this authoritative projection;
            # failures before release retain the attachment for recovery.
            if detached or self.runtime.pid is None:self._project_detached_runtime()

    def _observe_game_speed(self):
        if not self.runtime.allows_process_time_warp():return
        pid=self.runtime.pid
        if self._time_warp_pid==pid and self._time_warp_speed is not None:return
        try:
            actual=self.time_warp.current_speed()
            if pid is None or self.runtime.pid!=pid:
                raise ProcessTimeWarpError('disconnected','host.timeWarp.error.disconnected',
                                           diagnostic='Time Warp observation lost its verified target PID.')
        except AdapterError as error:
            self.preference_dirty=True
            self._time_warp_error={
                'presentation':error.presentation,
                'arguments':list(getattr(error,'arguments',()) or ()),
            }
            self._project_time_warp();raise
        self._time_warp_speed=float(actual);self._time_warp_pid=pid
        self._time_warp_error=None
        target=float(self.preferences.get('gameSpeed',1.0))
        if abs(self._time_warp_speed-target)>1e-6:self.preference_dirty=True
        self._project_time_warp()

    def _reset_preferences(self):
        preferences=self._default_preferences()
        # Durable desired intent is the primary owner. Persist the reset before
        # changing in-memory state or crossing the Lua boundary so an exit-time
        # cleanup that later returns waiting cannot resurrect enabled features
        # on the next trainer launch.
        self._persist_preferences_candidate(preferences)
        self.preferences=preferences
        self.preference_initialized=True;self.preference_dirty=False
        self._overlay_preferences()

    def reset_desired(self):
        self._reset_preferences()
        # This command is deliberately transport-free.  If the debugger died
        # behind the host's back, report the connection loss rather than trying
        # to reattach during application termination.
        if self.state.get('connected') and not self.runtime.alive():
            self._mark_disconnected()
        self._overlay_preferences()
        return dict(self.state)

    def _adopt_runtime_preferences(self,decoded):
        if not isinstance(decoded,dict):return
        desired=decoded.get('desiredFeatures') if isinstance(decoded.get('desiredFeatures'),dict) else {}
        for key in TOGGLES:
            if key in desired:self.preferences[key]=bool(desired[key])
        for key in MULTIPLIERS:
            if key=='gameSpeed':continue
            value=decoded.get(key)
            if type(value) in (int,float) and not isinstance(value,bool) and math.isfinite(value):self.preferences[key]=float(value)
        rarity=decoded.get('boonRarity')
        if isinstance(rarity,dict):self.preferences['boonRarity']=self._normalize_preferences({'boonRarity':rarity})['boonRarity']
        gathering=decoded.get('gatheringProbabilities')
        if isinstance(gathering,dict):self.preferences['gatheringProbabilities']=normalize_gathering_probabilities(gathering)
        if 'chaosGateProbability' in decoded:
            self.preferences['chaosGateProbability']=normalize_chaos_gate_probability(decoded['chaosGateProbability'])
        locks={}
        for key,item in (decoded.get('stats') or {}).items() if isinstance(decoded.get('stats'),dict) else []:
            if isinstance(item,dict) and item.get('locked') and type(item.get('target')) in (int,float):locks[key]=item['target']
        self.preferences['statLocks']=locks
        vital={}
        for key in ('health','mana','armor'):
            row=observed_vital_lock(key,decoded)
            if row is not None:vital[key]=row
        self.preferences['vitalLocks']=vital
        self.preferences['resourceLocks']={str(item['id']):item.get('count',0) for item in decoded.get('resources',[]) if isinstance(item,dict) and item.get('locked') and isinstance(item.get('id'),str)}
        if decoded.get('moneyLocked'):self.preferences['resourceLocks']['Money']=decoded.get('money',0)
        self.preferences['rerollsLock']=decoded.get('rerolls') if decoded.get('rerollsLocked') else None
        self.preferences['elementLocks']={str(item['id']):item.get('count',0) for item in decoded.get('elements',[]) if isinstance(item,dict) and item.get('locked') and isinstance(item.get('id'),str)}
        reward=decoded.get('nextRoomReward')
        if reward is None or isinstance(reward,str):
            self.preferences['nextRoomReward']=reward
            diagnostics=decoded.get('runtimeDiagnostics')
            token=diagnostics.get('nextRoomRewardToken') if isinstance(diagnostics,dict) else None
            self.preferences['nextRoomRewardToken']=token if reward is not None and isinstance(token,str) and token else None

    def _adopt_lua_preferences(self,decoded):
        self._adopt_runtime_preferences(decoded)
        self.preference_initialized=True;self.preference_dirty=False
        self._save_preferences()

    def _capture_command_preferences(self,command,params,decoded):
        """Capture only durable state owned by one successful runtime command."""
        if not isinstance(decoded,dict):return False
        params=params if isinstance(params,dict) else {}

        if command=='set_stat':
            stat=params.get('stat')
            locked=params.get('locked')
            if not isinstance(stat,str) or type(locked) is not bool:return False
            locks=dict(self.preferences.get('statLocks',{}))
            if locked:
                target=params.get('value')
                if type(target) not in (int,float) or isinstance(target,bool):return False
                locks[stat]=target
            else:
                locks.pop(stat,None)
            self.preferences['statLocks']=locks
            return True

        if command in ('set_vital','lock_vital'):
            vital=params.get('vital')
            if vital not in ('health','mana','armor'):return False
            locks=dict(self.preferences.get('vitalLocks',{}))
            if command=='set_vital' and vital not in locks:return False
            if command=='lock_vital' and type(params.get('locked')) is not bool:return False
            if command=='lock_vital' and not params['locked']:
                locks.pop(vital,None)
            else:
                row=observed_vital_lock(vital,decoded)
                if row is None and command=='set_vital' and decoded.get(vital+'Locked') is False:
                    # A pending lock still owns durable intent. Only the edited
                    # value is acknowledged while its native lock is inactive;
                    # unrelated pending targets must not be replaced by defaults.
                    actual=observed_vital_values(vital,decoded)
                    field=params.get('field')
                    if actual is not None and field in actual:
                        pending=dict(locks[vital]);pending[field]=actual[field]
                        row=normalize_vital_locks({vital:pending}).get(vital)
                if row is None:return False
                locks[vital]=row
            self.preferences['vitalLocks']=locks
            return True

        if command=='set_resource':
            resource=params.get('resource');amount=params.get('amount')
            locks=dict(self.preferences.get('resourceLocks',{}))
            if resource not in locks or type(amount) is not int:return False
            locks[resource]=amount
            self.preferences['resourceLocks']=locks
            return True

        if command=='lock_resource':
            resource=params.get('resource');locked=params.get('locked')
            if not isinstance(resource,str) or not resource or type(locked) is not bool:return False
            locks=dict(self.preferences.get('resourceLocks',{}))
            if not locked:
                locks.pop(resource,None)
            elif resource=='Money':
                amount=decoded.get('money')
                if type(amount) is not int:return False
                locks[resource]=amount
            else:
                row=next((
                    item for item in decoded.get('resources',[])
                    if isinstance(item,dict) and item.get('id')==resource
                ),None)
                if not isinstance(row,dict) or type(row.get('count')) is not int:return False
                locks[resource]=row['count']
            self.preferences['resourceLocks']=locks
            return True

        if command=='set_rerolls':
            amount=params.get('amount')
            if self.preferences.get('rerollsLock') is None or type(amount) is not int:return False
            self.preferences['rerollsLock']=amount
            return True

        if command=='lock_rerolls':
            locked=params.get('locked')
            if type(locked) is not bool:return False
            if not locked:
                self.preferences['rerollsLock']=None
            else:
                amount=decoded.get('rerolls')
                if type(amount) is not int:return False
                self.preferences['rerollsLock']=amount
            return True

        if command=='set_element':
            element=params.get('element');amount=params.get('amount')
            locks=dict(self.preferences.get('elementLocks',{}))
            if element not in locks or type(amount) is not int:return False
            locks[element]=amount
            self.preferences['elementLocks']=locks
            return True

        if command=='lock_element':
            element=params.get('element');locked=params.get('locked')
            if not isinstance(element,str) or not element or type(locked) is not bool:return False
            locks=dict(self.preferences.get('elementLocks',{}))
            if not locked:
                locks.pop(element,None)
            else:
                row=next((
                    item for item in decoded.get('elements',[])
                    if isinstance(item,dict) and item.get('id')==element
                ),None)
                if not isinstance(row,dict) or type(row.get('count')) is not int:return False
                locks[element]=row['count']
            self.preferences['elementLocks']=locks
            return True

        return False

    def set_desired(self,feature,value):
        preferences=dict(self.preferences);preferences[feature]=value
        self._persist_preferences_candidate(preferences)
        self.preferences=preferences
        self.preference_initialized=True
        was_dirty=self.preference_dirty
        self._overlay_preferences()
        if feature=='gameSpeed':
            self.preference_dirty=True
            if self.runtime.alive() and self.runtime.allows_process_time_warp():
                try:
                    self._apply_game_speed(value)
                    self.preference_dirty=was_dirty
                    self.state.pop('preferenceApplyError',None)
                except TransportError as error:
                    logging.warning('Desired gameSpeed stored pending reconnect: %s',error)
                    self.state['preferenceApplyError']=str(error)
                    self._overlay_preferences()
            return dict(self.state)
        self.preference_dirty=True
        # Lua-owned desired state remains editable while detached and replays
        # when a compatible scene becomes available.
        if self.runtime.alive() and self.state.get('capabilities',{}).get('setFeature'):
            try:
                result=self.execute('set_feature',{'feature':feature,'value':value})
                self.preference_dirty=was_dirty
                return result
            except TransportError as error:
                logging.warning('Desired feature %s stored pending reconnect: %s',feature,error)
                self.state['preferenceApplyError']=str(error)
                self._overlay_preferences()
        return dict(self.state)

    def set_boon_rarity_desired(self,config):
        normalized=self._normalize_preferences({'boonRarity':config})['boonRarity']
        preferences=dict(self.preferences);preferences['boonRarity']=normalized
        self._persist_preferences_candidate(preferences);self.preferences=preferences
        self.preference_initialized=True
        was_dirty=self.preference_dirty
        self.preference_dirty=True;self._overlay_preferences()
        if self.runtime.alive() and self.state.get('status')=='ready':
            result=self.execute('set_boon_rarity',dict(normalized));self.preference_dirty=was_dirty;return result
        return dict(self.state)


    def set_gathering_desired(self,family,probability):
        validate_gathering_desired(family,probability)
        probabilities=dict(self.preferences.get('gatheringProbabilities',{}))
        if probability is None:probabilities.pop(family,None)
        else:probabilities[family]=float(probability)
        preferences=dict(self.preferences,gatheringProbabilities=probabilities)
        self._persist_preferences_candidate(preferences)
        self.preferences=preferences;self.preference_initialized=True
        was_dirty=self.preference_dirty
        self.preference_dirty=True;self._overlay_preferences()
        if self.runtime.alive() and self.state.get('status')=='ready':
            result=self.execute('set_gathering_probabilities',{'probabilities':probabilities})
            self.preference_dirty=was_dirty
            return result
        return dict(self.state)

    def set_chaos_gate_desired(self,probability):
        validate_chaos_gate_probability(probability)
        probability=normalize_chaos_gate_probability(probability)
        preferences=dict(self.preferences,chaosGateProbability=probability)
        self._persist_preferences_candidate(preferences)
        self.preferences=preferences;self.preference_initialized=True
        was_dirty=self.preference_dirty
        self.preference_dirty=True;self._overlay_preferences()
        if self.runtime.alive() and self.state.get('status')=='ready':
            result=self.execute('set_chaos_gate_probability',{'probability':probability})
            self.preference_dirty=was_dirty
            return result
        return dict(self.state)

    def set_next_room_reward_desired(self,reward):
        if not is_valid_next_room_reward(reward):raise ValueError('下一房奖励无效。')
        preferences=dict(self.preferences);preferences['nextRoomReward']=reward
        preferences['nextRoomRewardToken']=None if reward is None else 'next-room-'+str(time.time_ns())
        self._persist_preferences_candidate(preferences);self.preferences=preferences
        self.preference_initialized=True
        was_dirty=self.preference_dirty
        self.preference_dirty=True;self._overlay_preferences()
        if self.runtime.alive() and self.state.get('status')=='ready':
            result=self.execute('set_next_room_reward',{'reward':reward,'token':self.preferences.get('nextRoomRewardToken')});self.preference_dirty=was_dirty;return result
        return dict(self.state)

    def _replay_preferences(self,observed_state,force_full=False):
        if not self.runtime.alive():return dict(self.state)
        if self._preference_persistence_dirty:
            # Current in-memory desired is authoritative. Retry its failed
            # durable write before crossing another runtime mutation boundary.
            self._save_preferences()

        speed_target=float(self.preferences.get('gameSpeed',desired_feature_defaults()['gameSpeed']))
        self._observe_game_speed()
        speed_confirmed=self._time_warp_speed is not None and abs(self._time_warp_speed-speed_target)<=1e-6
        if self.runtime.allows_process_time_warp():
            if force_full or not speed_confirmed:
                self._apply_game_speed(speed_target)
            speed_confirmed=abs(self._time_warp_speed-speed_target)<=1e-6

        if not isinstance(observed_state,dict):raise TypeError('reconciliation requires a runtime observation.')
        observed=observed_state
        if observed.get('status')!='ready':
            self._overlay_preferences()
            return dict(self.state)

        try:
            outcome=self.desired_reconciler.reconcile(
                self.preferences,
                observed,
                force_full=force_full,
            )
            if outcome.reply is not None:
                self._merge_resident_reply(outcome.reply)
                if outcome.reply.outcome_unknown:
                    raise TransportError(
                        'outcome_unknown',
                        '游戏调用结果不明，未自动重试；请检查游戏并重启。',
                    )
        except ResidentGenerationInvalidated as invalidated:
            self._mark_runtime_generation_invalidated()
            raise invalidated.original
        except TransportError as error:
            self._project_runtime_error(error,project_desired=True)
            raise

        mismatches=list(outcome.mismatches)
        if outcome.normalized_vital_locks:
            locks=dict(self.preferences.get('vitalLocks',{}))
            locks.update(outcome.normalized_vital_locks)
            self.preferences=dict(self.preferences,vitalLocks=locks)
            self._save_preferences()
        if not speed_confirmed:mismatches.append('feature:gameSpeed')
        if not mismatches:
            self.preference_dirty=False
            self.state.pop('preferenceApplyError',None)
        else:
            self.preference_dirty=True
            logging.warning(
                'ReplayPreferences pending mismatches=%s',
                ','.join(dict.fromkeys(mismatches)),
            )
        self._overlay_preferences()
        return dict(self.state)

    def scan(self):
        try:
            identity=preparation.compatibility(strict=False)
            version=str(identity['version'])
            self.state.update(version=version if version.startswith('1.') else '1.'+version,
                              warnings=identity.get('warnings',[]),steamBuild=identity['steam_build'])
        except Exception:
            self.state['status']='incompatible'
            raise
        result=subprocess.run(['/usr/bin/pgrep','-x',GAME_SPEC.process_name],capture_output=True,text=True,timeout=5)
        if result.returncode not in (0,1):
            detail=(result.stderr or result.stdout).strip() or '未知错误'
            raise RuntimeError(f'查询 {GAME_SPEC.display_name} 进程失败（{result.returncode}）：{detail}')
        pids=[] if result.returncode==1 else [int(x) for x in result.stdout.split()]
        if len(pids)>1:raise RuntimeError(f'检测到多个 {GAME_SPEC.display_name} 进程，请保留一个。')
        pid=pids[0] if pids else None
        if self.runtime.pid and (pid!=self.runtime.pid or not self.runtime.alive()):
            attached_pid=self.runtime.pid
            same_process=pid is not None and pid==attached_pid
            if not same_process:clear_active(self.state,preserve_desired=True)
            self._detach_runtime()
        elif self.state.get('pid') is not None and pid!=self.state.get('pid'):
            # A different game process cannot contain the prior session-local Lua module.
            clear_active(self.state,preserve_desired=True);self.preference_dirty=True;self._overlay_preferences();self.state.update(connected=False)
        previous_pid=self.state.get('pid')
        self.state['pid']=pid
        if pid!=previous_pid:
            self.runtime.invalidate_generation()
            self._invalidate_game_speed_observation()
        if not pid:self.state['status']='not_running'
        elif not self.state['connected']:self.state['status']='disconnected'
        if not self.state['connected']:
            self.state['scene']='unknown'
            self.state['capabilities']=disconnected_capabilities()
        return dict(self.state)
    def connect(self,probe_runtime=True):
        self._last_status_boundary_duration=0.0;self._last_status_json_duration=0.0;self._last_status_localize_duration=0.0
        started=time.monotonic();profile={};attach_profile={};outcome='ok'
        try:
            phase=time.monotonic();self.scan();profile['scan']=time.monotonic()-phase
            if not self.state['pid']:raise TransportError('not_running',f'请先启动 {GAME_SPEC.display_name} 并进入存档。')
            # A reconnect invalidates the prior native helper observation.
            # Resident-session attach separately owns Lua generation/bootstrap.
            self._invalidate_game_speed_observation()
            phase=time.monotonic()
            try:
                self._attach_runtime(self.state['pid'])
            finally:
                profile['attachTotal']=time.monotonic()-phase
                attach_profile=self.runtime.last_attach_profile
            self.state['connected']=True
            if not probe_runtime:
                outcome='deferred'
                clear_active(self.state,preserve_desired=True)
                self.state.update(connected=True,pid=self.runtime.pid,status='waiting',scene='loading')
                self._overlay_preferences()
                return dict(self.state)
            phase=time.monotonic()
            try:
                result=self.execute('status',{'includeCatalogs':True})
            except TransportError as e:
                message=str(e)
                bootstrap_waiting=e.code=='lua_error' and any(marker in message for marker in (
                    'Unsupported game runtime: missing table SessionState',
                    'Unsupported game runtime: missing table GameState',
                    'Unsupported game runtime: missing UpdateTimers',
                ))
                if e.code=='waiting' or bootstrap_waiting:
                    outcome='waiting'
                    self.state['status']='waiting'
                    if bootstrap_waiting:self.state['scene']='loading'
                    result=dict(self.state)
                else:
                    outcome=e.code
                    self._detach_runtime();raise
            profile['firstStatusTotal']=time.monotonic()-phase
            return result
        except Exception as exc:
            outcome=getattr(exc,'code',type(exc).__name__)
            raise
        finally:
            profile['total']=time.monotonic()-started
            logging.info(
                'ConnectProfile outcome=%s total=%.3fs scan=%.3fs attachTotal=%.3fs '
                'createTarget=%.3fs attachProcess=%.3fs identity=%.3fs symbols=%.3fs resume=%.3fs '
                'firstStatusTotal=%.3fs firstLuaBoundary=%.3fs jsonDecode=%.3fs catalogLocalization=%.3fs',
                outcome,profile['total'],profile.get('scan',0.0),profile.get('attachTotal',0.0),
                attach_profile.get('createTarget',0.0),attach_profile.get('attachProcess',0.0),attach_profile.get('identity',0.0),
                attach_profile.get('symbols',0.0),attach_profile.get('resume',0.0),profile.get('firstStatusTotal',0.0),
                self._last_status_boundary_duration,self._last_status_json_duration,self._last_status_localize_duration,
            )

    def _mark_runtime_generation_invalidated(self):
        self._invalidate_game_speed_observation()
        self.preference_dirty=True
        clear_active(self.state,preserve_desired=True)
        self.state.update(connected=True,pid=self.runtime.pid,status='waiting',scene='loading')
        self._overlay_preferences()

    def _invalidate_runtime_generation(self):
        self.runtime.invalidate_generation()
        self._mark_runtime_generation_invalidated()

    def runtime_reset(self):
        if not self.runtime.alive() or not self.state.get('connected'):
            return dict(self.state)
        self._invalidate_runtime_generation()
        logging.info('Lua runtime generation invalidated from run-log lifecycle signal')
        return dict(self.state)

    def observe_runtime(self):
        """Refresh runtime observation without Host adoption/replay/persistence.

        Resident status may still run synchronize() maintenance. The returned
        state intentionally excludes durable desired-state projection.
        """
        return self._execute_runtime(
            'status',{},host_observation_only=True,
        )

    def execute(self,command,params):
        return self._execute_runtime(
            command,params,
            host_observation_only=False,
        )

    def _merge_resident_reply(self,reply):
        # Resident replies are full observations with explicit nulls for absent
        # runtime values. Only expensive catalogs may be omitted. Profile/Save
        # command patches bypass this seam and retain Swift's absence semantics.
        decoded=dict(reply.payload) if isinstance(reply.payload,dict) else {}
        prior_warnings=self.state.get('warnings') if isinstance(self.state.get('warnings'),list) else []
        catalog_warnings=decoded.get('warnings') if isinstance(decoded.get('warnings'),list) else []
        if prior_warnings or catalog_warnings:
            decoded['warnings']=list(dict.fromkeys([*prior_warnings,*catalog_warnings]))
        capabilities=decoded.get('capabilities')
        if not isinstance(capabilities,dict):capabilities={}
        capabilities=dict(disconnected_capabilities(),**capabilities)
        capabilities['hotBackup']=True;capabilities['hotRestore']=False
        decoded['capabilities']=capabilities
        for key in _TRANSIENT_ACTION_RESULT_FIELDS:
            self.state.pop(key,None)
        self.state.update(decoded,connected=True,pid=self.runtime.pid)
        self.state.pop('error',None)
        return decoded

    def _project_runtime_error(self,error,project_desired):
        if error.code=='waiting':self.state['status']='waiting'
        elif error.code=='disconnected':
            self.state.update(status='disconnected');self._mark_disconnected()
        elif error.code in ('restart_required','outcome_unknown','restore_failed'):
            self.state['status']='restart_required'
        if project_desired:self._overlay_preferences()

    def _execute_runtime(
        self,command,params,
        host_observation_only=False,
    ):
        # Host projection/persistence remains Adapter-owned. The resident session
        # owns the debugger/Lua transaction, generation, bootstrap, handoff and trust.
        if host_observation_only and command!='status':
            raise ValueError('runtime observation 仅允许 status。')
        project_desired=not host_observation_only
        teardown=not host_observation_only and command in ('disable_all','cleanup')
        teardown_persistence_error=None
        if teardown:
            try:self._reset_preferences()
            except PersistenceError as error:
                teardown_persistence_error=error
                logging.warning('Durable teardown reset failed; continuing runtime cleanup: %s',error)
        if command in ('disable_all','cleanup') and not self.runtime.alive():
            # Explicit teardown must never be faked. Reattach to the same live
            # process so app exit / “全部关闭” can really clear resident hooks.
            self.scan()
            if not self.state.get('pid'):
                clear_active(self.state);self.state.update(connected=False,status='not_running')
                if teardown_persistence_error is not None:raise teardown_persistence_error
                return dict(self.state)
            self._attach_runtime(self.state['pid']);self.state['connected']=True
        if not self.runtime.alive():
            error=TransportError('disconnected','请先连接游戏。')
            self._project_runtime_error(error,project_desired)
            raise error
        teardown_speed_error=None
        if teardown:
            try:self._apply_game_speed(1.0)
            except TransportError as error:
                teardown_speed_error=error
                logging.warning('Time Warp teardown failed; continuing Lua cleanup: %s',error)
        try:
            runtime_params=dict(params or {})
            if command=='status':
                self._last_status_boundary_duration=0.0
                self._last_status_json_duration=0.0
                self._last_status_localize_duration=0.0
            try:
                if command=='status':
                    if host_observation_only:
                        reply=self.runtime.observe_status(runtime_params)
                    else:
                        reply=self.runtime.status(runtime_params)
                else:
                    reply=self.runtime.mutate(command,runtime_params)
            except ResidentGenerationInvalidated as invalidated:
                self._mark_runtime_generation_invalidated()
                raise invalidated.original
            if reply.generation_reset:
                # The session has already re-bootstraped the new generation.
                # Adapter only projects that lifecycle evidence into desired/observed state.
                self._mark_runtime_generation_invalidated()
            raw_decoded=reply.payload if isinstance(reply.payload,dict) else {}
            if command=='status':
                self._last_status_boundary_duration=reply.metrics.boundary_duration
                self._last_status_json_duration=reply.metrics.json_duration
                self._last_status_localize_duration=reply.metrics.localize_duration
            asynchronous_unknown=reply.outcome_unknown
            if not asynchronous_unknown and not host_observation_only and not self.preference_initialized and not self.preference_write_blocked:
                self._adopt_lua_preferences(raw_decoded)
            decoded=self._merge_resident_reply(reply)
            # Runtime observation skips durable Hades desired-state projection,
            # but Core-owned Process Time Warp remains observable Host state.
            if host_observation_only:self._project_time_warp()
            if not host_observation_only and command=='status' and next_room_reward_consumed(self.preferences,raw_decoded,self.preference_dirty):
                self.preferences['nextRoomReward']=None
                self.preferences['nextRoomRewardToken']=None
                self.state['nextRoomReward']=None
                self._save_preferences()
            # Session trust is already tainted before this evidence reaches Adapter.
            if asynchronous_unknown:
                raise TransportError('outcome_unknown','游戏调用结果不明，未自动重试；请检查游戏并重启。')
            self._observe_game_speed()
            if not host_observation_only and command=='status' and self.preference_dirty:
                return self._replay_preferences(copy.deepcopy(self.state))
            if not host_observation_only and command not in ('status',) and command not in _PREPERSISTED_RUNTIME_COMMANDS:
                if teardown_persistence_error is None and self._capture_command_preferences(command,runtime_params,raw_decoded):
                    self._save_preferences()
            if project_desired:self._overlay_preferences()
            if teardown_speed_error is not None:raise teardown_speed_error
            if teardown_persistence_error is not None:raise teardown_persistence_error
            reward_context = f" reward={runtime_params.get('reward')}" if command == 'spawn_reward' else ''
            logging.info('Lua %s%s %.3fs scene=%s desired=%s active=%s featureErrors=%s diagnostics=%s',
                         command,reward_context,reply.metrics.boundary_duration,self.state.get('scene'),
                         self.state.get('desiredFeatures'),self.state.get('activeFeatures'),
                         self.state.get('featureErrors'),self.state.get('runtimeDiagnostics'))
            return dict(self.state)
        except TransportError as e:
            if command=='status' and isinstance(e,ResidentSessionError):
                self._last_status_boundary_duration=e.metrics.boundary_duration
                self._last_status_json_duration=e.metrics.json_duration
                self._last_status_localize_duration=e.metrics.localize_duration
            self._project_runtime_error(e,project_desired)
            raise
    def disconnect(self):
        # Manual disconnect is a debugger detach only. The trainer Lua module
        # stays resident in the same game process, so desired features/locks
        # continue running and can be inspected again after reconnect.
        if self.runtime.alive():self._detach_runtime()
        else:self._project_detached_runtime()
        return dict(self.state)

    def bind_save_service(self, save_service):
        super().bind_save_service(save_service)
        self.save_workspace = None

    def _require_save_workspace(self):
        if self.save_workspace is None:
            raise ValueError("Save Editor workspace is not open.")
        return self.save_workspace

    def open_save_editor(self):
        if self.save_service is None:
            raise ValueError("Save Editor save management is unavailable.")
        self.save_workspace = Hades2SaveWorkspace.open(self.save_service)
        return self.save_workspace.summary()

    def query_save_editor(self, params):
        return self._require_save_workspace().query(**params)

    def stage_save_editor(self, params):
        return self._require_save_workspace().stage(
            params["entryId"],
            params["operation"],
            params.get("value"),
        )

    def review_save_editor(self):
        return self._require_save_workspace().review()

    def cancel_save_editor(self):
        return self._require_save_workspace().cancel()

    def apply_save_editor(self):
        return self._require_save_workspace().apply()

    def metadata(self):
        metadata = super().metadata()
        metadata.update({
            'steamAppId': STEAM_SPEC.app_id,
            'transport': 'supergiant-lldb-lua',
        })
        return metadata

    def dispatch(self, command, params, request_id):
        return self.command_contract.dispatch(command, params, request_id)

    def close(self):
        try:
            self.disconnect()
        except Exception:
            logging.exception('Graceful %s cleanup failed; attempting debugger detach.', GAME_SPEC.display_name)
        finally:
            self.runtime.close()
