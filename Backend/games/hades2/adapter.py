"""JSONL worker; one request at a time, no network or arbitrary-code endpoint."""
from pathlib import Path
import json, subprocess, time, logging, math
from core.adapter import AdapterError, GameAdapter, GameAdapterContext
from core.process_time_warp import LLDBProcessTimeWarpDriver, ProcessTimeWarpController
from . import preparation
from .config import GAME_SPEC, STEAM_SPEC, MODULE_MANIFEST, DATA
from .schema import TOGGLES, MULTIPLIERS, STAT_RULES, disconnected_capabilities
from .catalog import localize_catalog
from .boundary_ledger import execute_with_ledger
from .preferences import Hades2PreferenceStore
from .profile_service import Hades2ProfileService
from .command_router import Hades2CommandRouter
TransportError = AdapterError

def clear_active(state,preserve_desired=False):
    """Clear verified runtime state; optionally retain the user's desired feature profile."""
    if not preserve_desired:
        state.update({key:False for key in TOGGLES})
        state['desiredFeatures']={key:False for key in TOGGLES}
        state['gameSpeed']=1
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
    state['activeFeatures']={key:False for key in TOGGLES}; state['activeFeatures']['gameSpeed']=False
    state['dormantFeatures']={}
    state['featureErrors']={}
    state['capabilities']=disconnected_capabilities()


def lua_value(value):
    if value is None:return 'nil'
    if isinstance(value,bool):return 'true' if value else 'false'
    if isinstance(value,(int,float)):
        if not math.isfinite(value):raise ValueError('必须输入有限数值。')
        return str(value)
    if isinstance(value,str):
        return '"'+''.join(('\\%03d'%ord(c)) if ord(c)<32 or c in ('"','\\') else c for c in value)+'"'
    if isinstance(value,dict):return '{'+','.join('['+lua_value(k)+']='+lua_value(v) for k,v in value.items())+'}'
    raise ValueError('参数类型不支持。')

_PREPERSISTED_RUNTIME_COMMANDS = frozenset((
    'set_feature', 'set_boon_rarity', 'set_next_room_reward',
))


class Hades2Adapter(GameAdapter):
    data_dir = DATA
    def __init__(self, transport=None, context=None):
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
        if transport is None:
            from .transport import Hades2LuaTransport
            transport = Hades2LuaTransport()
        self.transport=transport;self.bootstrap=(Path(__file__).with_name('runtime') / 'hades.lua').read_text()
        helper_path=Path(__file__).resolve().parents[2]/'core/native/libMGTTimeWarp.dylib'
        self.time_warp=ProcessTimeWarpController(LLDBProcessTimeWarpDriver(self.transport),helper_path,[GAME_SPEC.executable_name])
        self._time_warp_speed=1.0;self._time_warp_error=''
        self._runtime_bootstrapped=False;self._catalog_initialized=False
        self._last_status_boundary_duration=0.0;self._last_status_json_duration=0.0;self._last_status_localize_duration=0.0
        self.state={'connected':False,'pid':None,'version':'1.139672','status':'disconnected','scene':'unknown',
                    'godMode':False,'infiniteHealth':False,'infiniteMana':False,'damageEnabled':False,'instantCastCooldown':False,'hexAlwaysReady':False,'infiniteAmmo':False,'autoMiniGames':False,'gardenQoL':False,'boonRarityEnabled':False,'damageMultiplier':2,'gameSpeed':1,'resources':[],'rewards':[],'stats':{},'statSupport':{},'elements':[], 'boonRarity':{'target':'Epic','multiplier':100.0,'forceLegendary':False,'forceDuo':False}, 'nextRoomReward':None,
                    'desiredFeatures':{key:False for key in TOGGLES},
                    'activeFeatures':{key:False for key in TOGGLES},
                    'dormantFeatures':{},
                    'capabilities':disconnected_capabilities()}
        self.preference_store=Hades2PreferenceStore(preparation.DATA/'desired-state.json')
        self.preferences,self.preference_initialized=self.preference_store.load()
        self.preference_write_blocked=self.preference_store.write_blocked_error is not None
        self.profile_service=Hades2ProfileService(preparation.DATA/'profiles')
        self.command_router=Hades2CommandRouter(self)
        # A persisted desired profile is intentionally treated as pending on a
        # fresh backend process. If the resident Lua module already matches it,
        # replay is a no-op; if Hades itself restarted, the same profile is
        # automatically restored on the first ready connection.
        self.preference_dirty=self.preference_initialized and not self.preference_write_blocked
        self._overlay_preferences()

    @staticmethod
    def _default_preferences():
        return Hades2PreferenceStore.defaults()

    def _normalize_preferences(self,raw):
        return Hades2PreferenceStore.normalize(raw)

    def _save_preferences(self):
        self.preference_store.save(self.preferences)

    def list_profiles(self):
        return self.profile_service.list()

    def save_profile(self,name,shortcuts=None):
        if self.state.get('connected'): self._capture_runtime_preferences(self.state)
        return self.profile_service.save(name,self.preferences,shortcuts)

    def delete_profile(self,name):
        return self.profile_service.delete(name)

    def load_profile(self,name):
        profile=self.profile_service.load(name)
        preferences=self._normalize_preferences(profile['desired'])
        self.preference_store.save(preferences)
        self.preferences=preferences
        self.preference_initialized=True;self.preference_dirty=True
        self._overlay_preferences()
        if self.transport.alive():self._replay_preferences(force_full=True)
        result=dict(self.state);result.update(loadedProfile=profile['name'],shortcuts=profile['shortcuts'],profiles=self.list_profiles())
        return result

    def _overlay_preferences(self):
        desired={key:bool(self.preferences.get(key,False)) for key in TOGGLES}
        self.state['desiredFeatures']=desired
        for key,value in desired.items():self.state[key]=value
        for key in MULTIPLIERS:self.state[key]=self.preferences.get(key,1.0 if key=='gameSpeed' else 2.0)
        self.state['boonRarity']=dict(self.preferences.get('boonRarity',{}))
        self.state['nextRoomReward']=self.preferences.get('nextRoomReward')
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
            row=vital.get(key)
            if isinstance(row,dict):
                if type(row.get('current')) in (int,float):self.state[key]=row['current']
                if key!='armor' and type(row.get('max')) in (int,float):self.state['max'+key.capitalize()]=row['max']
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
        active['gameSpeed']=abs(self._time_warp_speed-1.0)>1e-6
        self.state['activeFeatures']=active
        support=self.state.get('featureSupport')
        support=dict(support) if isinstance(support,dict) else {}
        support['gameSpeed']=True
        self.state['featureSupport']=support
        errors=self.state.get('featureErrors')
        errors=dict(errors) if isinstance(errors,dict) else {}
        if self._time_warp_error:errors['gameSpeed']=self._time_warp_error
        else:errors.pop('gameSpeed',None)
        self.state['featureErrors']=errors
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
            self._time_warp_error=str(error);self._project_time_warp();raise
        self._time_warp_speed=float(actual);self._time_warp_error='';self._project_time_warp()
        return self._time_warp_speed

    def _reset_preferences(self):
        preferences=self._default_preferences()
        # Durable desired intent is the primary owner. Persist the reset before
        # changing in-memory state or crossing the Lua boundary so an exit-time
        # cleanup that later returns waiting cannot resurrect enabled features
        # on the next trainer launch.
        self.preference_store.save(preferences)
        self.preferences=preferences
        self.preference_initialized=True;self.preference_dirty=False
        self._overlay_preferences()

    def reset_desired(self):
        self._reset_preferences()
        # This command is deliberately transport-free.  If the debugger died
        # behind the host's back, report the connection loss rather than trying
        # to reattach during application termination.
        if self.state.get('connected') and not self.transport.alive():
            mark_disconnected(self.state)
        self._overlay_preferences()
        return dict(self.state)

    def _capture_runtime_preferences(self,decoded):
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
        locks={}
        for key,item in (decoded.get('stats') or {}).items() if isinstance(decoded.get('stats'),dict) else []:
            if isinstance(item,dict) and item.get('locked') and type(item.get('target')) in (int,float):locks[key]=item['target']
        self.preferences['statLocks']=locks
        vital={}
        for key in ('health','mana','armor'):
            if decoded.get(key+'Locked'):
                row={'current':decoded.get(key)}
                if key in ('health','mana'):row['max']=decoded.get('max'+key.capitalize())
                vital[key]=row
        self.preferences['vitalLocks']=vital
        self.preferences['resourceLocks']={str(item['id']):item.get('count',0) for item in decoded.get('resources',[]) if isinstance(item,dict) and item.get('locked') and isinstance(item.get('id'),str)}
        if decoded.get('moneyLocked'):self.preferences['resourceLocks']['Money']=decoded.get('money',0)
        self.preferences['rerollsLock']=decoded.get('rerolls') if decoded.get('rerollsLocked') else None
        self.preferences['elementLocks']={str(item['id']):item.get('count',0) for item in decoded.get('elements',[]) if isinstance(item,dict) and item.get('locked') and isinstance(item.get('id'),str)}
        reward=decoded.get('nextRoomReward')
        if reward is None or isinstance(reward,str):self.preferences['nextRoomReward']=reward

    def _adopt_lua_preferences(self,decoded):
        self._capture_runtime_preferences(decoded)
        self.preference_initialized=True;self.preference_dirty=False
        self._save_preferences()

    def set_desired(self,feature,value):
        preferences=dict(self.preferences);preferences[feature]=value
        self.preference_store.save(preferences)
        self.preferences=preferences
        self.preference_initialized=True
        was_dirty=self.preference_dirty
        self._overlay_preferences()
        if feature=='gameSpeed':
            self.preference_dirty=True
            if self.transport.alive() and self._runtime_bootstrapped:
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
        if self.transport.alive() and self.state.get('capabilities',{}).get('setFeature'):
            try:
                result=self.execute('set_feature',{'feature':feature,'value':value})
                self.preference_dirty=False
                return result
            except TransportError as error:
                logging.warning('Desired feature %s stored pending reconnect: %s',feature,error)
                self.state['preferenceApplyError']=str(error)
                self._overlay_preferences()
        return dict(self.state)

    def set_boon_rarity_desired(self,config):
        normalized=self._normalize_preferences({'boonRarity':config})['boonRarity']
        preferences=dict(self.preferences);preferences['boonRarity']=normalized
        self.preference_store.save(preferences);self.preferences=preferences
        self.preference_initialized=True;self.preference_dirty=True;self._overlay_preferences()
        if self.transport.alive() and self.state.get('status')=='ready':
            result=self.execute('set_boon_rarity',dict(normalized));self.preference_dirty=False;return result
        return dict(self.state)


    def set_next_room_reward_desired(self,reward):
        if reward is not None and (not isinstance(reward,str) or len(reward)>128):raise ValueError('下一房奖励无效。')
        preferences=dict(self.preferences);preferences['nextRoomReward']=reward
        self.preference_store.save(preferences);self.preferences=preferences
        self.preference_initialized=True;self.preference_dirty=True;self._overlay_preferences()
        if self.transport.alive() and self.state.get('status')=='ready':
            result=self.execute('set_next_room_reward',{'reward':reward});self.preference_dirty=False;return result
        return dict(self.state)

    def _replay_preferences(self,force_full=False):
        if not self.transport.alive():return dict(self.state)
        if self._runtime_bootstrapped:self._apply_game_speed(self.preferences.get('gameSpeed',1.0))
        if self.state.get('status')!='ready':
            self._overlay_preferences()
            return dict(self.state)
        desired=self.state.get('desiredFeatures') if isinstance(self.state.get('desiredFeatures'),dict) else {}
        pending=[]
        for key in TOGGLES:
            if force_full or bool(desired.get(key,self.state.get(key,False)))!=bool(self.preferences.get(key,False)):
                pending.append(('set_feature',{'feature':key,'value':self.preferences[key]}))
        for key in MULTIPLIERS:
            if key=='gameSpeed':continue
            current=self.state.get(key);target=self.preferences[key]
            if force_full or type(current) not in (int,float) or abs(float(current)-float(target))>1e-6:pending.append(('set_feature',{'feature':key,'value':target}))
        rarity=self.preferences.get('boonRarity',{})
        pending.append(('set_boon_rarity',dict(rarity)))
        # First release stale locks that are not in the desired snapshot.
        current_stats=self.state.get('stats') if isinstance(self.state.get('stats'),dict) else {}
        wanted_stats=self.preferences.get('statLocks',{})
        for stat,item in current_stats.items():
            if isinstance(item,dict) and item.get('locked') and stat not in wanted_stats:pending.append(('set_stat',{'stat':stat,'locked':False}))
        for stat,value in wanted_stats.items():pending.append(('set_stat',{'stat':stat,'locked':True,'value':value}))
        current_vitals={key for key in ('health','mana','armor') if self.state.get(key+'Locked')}
        wanted_vitals=self.preferences.get('vitalLocks',{})
        for vital in current_vitals-set(wanted_vitals):pending.append(('lock_vital',{'vital':vital,'locked':False}))
        for vital,row in wanted_vitals.items():
            if not isinstance(row,dict):continue
            for field in ('max','current'):
                value=row.get(field)
                if field=='max' and vital=='armor':continue
                if type(value) in (int,float) and not isinstance(value,bool):pending.append(('set_vital',{'vital':vital,'field':field,'value':value}))
            pending.append(('lock_vital',{'vital':vital,'locked':True}))
        current_resources={item.get('id') for item in self.state.get('resources',[]) if isinstance(item,dict) and item.get('locked')}
        wanted_resources=self.preferences.get('resourceLocks',{})
        for resource in current_resources-set(wanted_resources):pending.append(('lock_resource',{'resource':resource,'locked':False,'requestId':f'replay-{time.time_ns()}'}))
        for resource,amount in wanted_resources.items():
            pending.append(('set_resource',{'resource':resource,'amount':int(amount),'requestId':f'replay-{time.time_ns()}'}));pending.append(('lock_resource',{'resource':resource,'locked':True,'requestId':f'replay-{time.time_ns()}'}))
        if self.state.get('rerollsLocked') and self.preferences.get('rerollsLock') is None:pending.append(('lock_rerolls',{'locked':False,'requestId':f'replay-{time.time_ns()}'}))
        if self.preferences.get('rerollsLock') is not None:
            amount=int(self.preferences['rerollsLock']);pending.append(('set_rerolls',{'amount':amount,'requestId':f'replay-{time.time_ns()}'}));pending.append(('lock_rerolls',{'locked':True,'requestId':f'replay-{time.time_ns()}'}))
        current_elements={item.get('id') for item in self.state.get('elements',[]) if isinstance(item,dict) and item.get('locked')}
        wanted_elements=self.preferences.get('elementLocks',{})
        for element in current_elements-set(wanted_elements):pending.append(('lock_element',{'element':element,'locked':False}))
        for element,amount in wanted_elements.items():pending.append(('set_element',{'element':element,'amount':int(amount)}));pending.append(('lock_element',{'element':element,'locked':True}))
        reward=self.preferences.get('nextRoomReward')
        if force_full or self.state.get('nextRoomReward')!=reward:pending.append(('set_next_room_reward',{'reward':reward}))
        if pending:self.execute('replay_preferences',{},replay=True,batch=pending)
        self.preference_dirty=False;self.state.pop('preferenceApplyError',None)
        self._capture_runtime_preferences(self.state);self._save_preferences();self._overlay_preferences()
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
        if self.transport.pid and (pid!=self.transport.pid or not self.transport.alive()):
            attached_pid=self.transport.pid
            same_process=pid is not None and pid==attached_pid
            self.transport.detach()
            if same_process:mark_disconnected(self.state)
            else:
                clear_active(self.state,preserve_desired=True);self.preference_dirty=True;self._overlay_preferences();self.state.update(connected=False)
        elif self.state.get('pid') is not None and pid!=self.state.get('pid'):
            # A different game process cannot contain the prior session-local Lua module.
            clear_active(self.state,preserve_desired=True);self.preference_dirty=True;self._overlay_preferences();self.state.update(connected=False)
        previous_pid=self.state.get('pid')
        self.state['pid']=pid
        if pid!=previous_pid:
            self._runtime_bootstrapped=False
            self._catalog_initialized=False
            self._time_warp_speed=1.0;self._time_warp_error='';self._project_time_warp()
        if not pid:self.state['status']='not_running'
        elif not self.state['connected']:self.state['status']='disconnected'
        if not self.state['connected']:
            self.state['scene']='unknown'
            self.state['capabilities']=disconnected_capabilities()
        return dict(self.state)
    def connect(self):
        self._last_status_boundary_duration=0.0;self._last_status_json_duration=0.0;self._last_status_localize_duration=0.0
        started=time.monotonic();profile={};attach_profile={};outcome='ok'
        try:
            phase=time.monotonic();self.scan();profile['scan']=time.monotonic()-phase
            if not self.state['pid']:raise TransportError('not_running',f'请先启动 {GAME_SPEC.display_name} 并进入存档。')
            phase=time.monotonic()
            try:
                self.transport.attach(self.state['pid'])
            finally:
                profile['attachTotal']=time.monotonic()-phase
                attach_profile=dict(getattr(self.transport,'last_attach_profile',{}) or {})
            # A debugger reconnect is the synchronization boundary for the resident
            # module. Bootstrap once here even when the same game process survived a
            # manual detach, then use dispatch-only payloads for subsequent calls.
            self._runtime_bootstrapped=False
            self.state['connected']=True
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
                    self.transport.detach();mark_disconnected(self.state);raise
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

    @staticmethod
    def _runtime_generation_missing(error):
        message=str(error)
        return error.code=='lua_error' and '__MacGamingTrainerV1' in message and 'nil value' in message

    def _invalidate_runtime_generation(self):
        self._runtime_bootstrapped=False
        self._catalog_initialized=False
        self.preference_dirty=True
        clear_active(self.state,preserve_desired=True)
        self.state.update(connected=True,pid=self.transport.pid,status='waiting',scene='loading')
        self._overlay_preferences()

    def runtime_reset(self):
        if not self.transport.alive() or not self.state.get('connected'):
            return dict(self.state)
        self._invalidate_runtime_generation()
        logging.info('Lua runtime generation invalidated from run-log lifecycle signal')
        return dict(self.state)

    def execute(self,command,params,replay=False,read_only=False,batch=None):
        # read_only suppresses host-side adoption/replay/persistence only. The
        # current Lua status dispatch still performs its resident synchronize()
        # maintenance, so this is not yet a strict transport/Lua snapshot API.
        if read_only and command!='status':raise ValueError('read_only 仅允许 status。')
        teardown=not read_only and command in ('disable_all','cleanup')
        # Durable intent is reset before any potentially slow debugger attach or
        # Lua boundary.  Even if runtime teardown later fails, a future trainer
        # session must not replay features that the user explicitly closed.
        if teardown:self._reset_preferences()
        if command in ('disable_all','cleanup') and not self.transport.alive():
            # Explicit teardown must never be faked. Reattach to the same live
            # process so app exit / “全部关闭” can really clear resident hooks.
            self.scan()
            if not self.state.get('pid'):
                clear_active(self.state);self.state.update(connected=False,status='not_running')
                return dict(self.state)
            self.transport.attach(self.state['pid']);self.state['connected']=True
        if not self.transport.alive():raise TransportError('disconnected','请先连接游戏。')
        teardown_speed_error=None
        if teardown:
            try:self._apply_game_speed(1.0)
            except TransportError as error:
                teardown_speed_error=error
                logging.warning('Time Warp teardown failed; continuing Lua cleanup: %s',error)
        try:
            runtime_params=dict(params or {})
            if 'includeCatalogs' not in runtime_params:
                runtime_params['includeCatalogs']=not self._catalog_initialized
            decode_metrics={}
            def decode_runtime(raw):
                phase=time.monotonic()
                payload=json.loads(raw)
                decode_metrics['json']=time.monotonic()-phase
                phase=time.monotonic()
                payload=localize_catalog(payload)
                decode_metrics['localize']=time.monotonic()-phase
                return payload
            if command=='status':
                self._last_status_boundary_duration=0.0
                self._last_status_json_duration=0.0
                self._last_status_localize_duration=0.0
            recovered_generation=False
            try:
                while True:
                    if batch is None:
                        dispatch='return __MacGamingTrainerV1.json(__MacGamingTrainerV1.dispatch('+lua_value(command)+','+lua_value(runtime_params)+'))'
                    else:
                        calls=[]
                        for batch_command,batch_params in batch:
                            item_params=dict(batch_params or {});item_params['includeCatalogs']=False
                            calls.append('__MacGamingTrainerV1.dispatch('+lua_value(batch_command)+','+lua_value(item_params)+')')
                        calls.append('return __MacGamingTrainerV1.dispatch("status",{["includeCatalogs"]=false})')
                        dispatch='return __MacGamingTrainerV1.json((function() '+ ';'.join(calls) +' end)())'
                    code=(self.bootstrap+'\n'+dispatch) if not self._runtime_bootstrapped else dispatch
                    try:
                        decoded=execute_with_ledger(
                            self.transport,command,code,decode_runtime,
                            replay=replay,read_only=read_only,
                        )
                        break
                    except TransportError as error:
                        if not self._runtime_generation_missing(error):
                            raise
                        self._invalidate_runtime_generation()
                        if command!='status' or recovered_generation:
                            raise
                        recovered_generation=True
                        runtime_params['includeCatalogs']=True
                        logging.info('Lua runtime generation reset detected; re-bootstrap status in same debugger attachment')
            finally:
                if command=='status':
                    self._last_status_boundary_duration=getattr(self.transport,'last_duration',0.0) or 0.0
            if command=='status':
                self._last_status_json_duration=decode_metrics.get('json',0.0)
                self._last_status_localize_duration=decode_metrics.get('localize',0.0)
            self._runtime_bootstrapped=True
            if 'boons' in decoded and 'rewards' in decoded:self._catalog_initialized=True
            if not read_only and not self.preference_initialized and not self.preference_write_blocked:self._adopt_lua_preferences(decoded)
            prior_warnings=self.state.get('warnings') if isinstance(self.state.get('warnings'),list) else []
            catalog_warnings=decoded.get('warnings') if isinstance(decoded.get('warnings'),list) else []
            if prior_warnings or catalog_warnings:
                decoded['warnings']=list(dict.fromkeys([*prior_warnings,*catalog_warnings]))
            capabilities=decoded.get('capabilities')
            if not isinstance(capabilities,dict):capabilities={}
            capabilities=dict(disconnected_capabilities(),**capabilities)
            # Backup is server-side and can take a verified stable snapshot while the game is running.
            capabilities['hotBackup']=True;capabilities['hotRestore']=False
            decoded['capabilities']=capabilities
            self.state.update(decoded,connected=True,pid=self.transport.pid)
            self.state.pop('error',None)
            # nextRoomReward is a one-shot runtime request. Once Lua consumes it,
            # a later clean status omits the field; clear the persisted desired
            # value too so it is not visually resurrected or replayed on reconnect.
            if not read_only and command=='status' and not self.preference_dirty and self.preferences.get('nextRoomReward') is not None and decoded.get('nextRoomReward') is None:
                self.preferences['nextRoomReward']=None
                self.state['nextRoomReward']=None
                self._save_preferences()
            if not read_only and command=='status' and self.preference_dirty and not replay:
                return self._replay_preferences()
            if not read_only and command not in ('status',) and not replay and command not in _PREPERSISTED_RUNTIME_COMMANDS:
                self._capture_runtime_preferences(self.state);self._save_preferences()
            self._overlay_preferences()
            if teardown_speed_error is not None:raise teardown_speed_error
            reward_context = f" reward={runtime_params.get('reward')}" if command == 'spawn_reward' else ''
            logging.info('Lua %s%s %.3fs scene=%s desired=%s active=%s featureErrors=%s diagnostics=%s',
                         command,reward_context,self.transport.last_duration,self.state.get('scene'),
                         self.state.get('desiredFeatures'),self.state.get('activeFeatures'),
                         self.state.get('featureErrors'),self.state.get('runtimeDiagnostics'))
            return dict(self.state)
        except TransportError as e:
            if e.code=='waiting':self.state['status']='waiting'
            elif e.code=='disconnected':self.state.update(status='disconnected');mark_disconnected(self.state)
            elif e.code in ('restart_required','outcome_unknown','restore_failed'):self.state['status']='restart_required'
            self._overlay_preferences()
            raise
    def disconnect(self):
        # Manual disconnect is a debugger detach only. The trainer Lua module
        # stays resident in the same game process, so desired features/locks
        # continue running and can be inspected again after reconnect.
        if self.transport.alive():self.transport.detach()
        self.state.update(connected=False,status='disconnected')
        mark_disconnected(self.state)
        self._overlay_preferences()
        return dict(self.state)

    def metadata(self):
        metadata = super().metadata()
        metadata.update({
            'steamAppId': STEAM_SPEC.app_id,
            'transport': 'supergiant-lldb-lua',
        })
        return metadata

    def dispatch(self, command, params, request_id):
        return self.command_router.dispatch(command, params, request_id)

    def close(self):
        try:
            self.disconnect()
        except Exception:
            logging.exception('Graceful %s cleanup failed; attempting debugger detach.', GAME_SPEC.display_name)
        finally:
            self.transport.close()
