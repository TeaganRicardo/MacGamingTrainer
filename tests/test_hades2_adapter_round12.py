from pathlib import Path
import sys, tempfile, io, json, logging

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'Backend'))

from games.hades2 import preparation as prep
from core.adapter import AdapterError
from games.hades2.adapter import Hades2Adapter, TOGGLES, STAT_RULES

base = Path(tempfile.mkdtemp(prefix='mgt-hades2-adapter-r12-'))
prep.DATA = base
prep.GAME = base/'Hades II.app'
prep.SAVES = base/'Saves'
prep.official_display_names = lambda ids, language='zh-CN': {}

class FakeTransport:
    def __init__(self):
        self.pid = None
        self.last_duration = 0
        self.live = False
    def alive(self): return self.live
    def detach(self): self.pid = None; self.live = False
    def close(self): self.live = False
    def attach(self, pid): self.pid = pid; self.live = True

transport = FakeTransport()
a = Hades2Adapter(transport=transport)

class LoggingTransport(FakeTransport):
    def __init__(self):
        super().__init__()
        self.pid = 4242
        self.live = True
    def execute(self, source):
        self.last_duration = 0.001
        return json.dumps({
            'status': 'ready',
            'scene': 'run',
            'capabilities': {},
            'desiredFeatures': {},
            'activeFeatures': {},
            'dormantFeatures': {},
            'featureErrors': {},
        })

log_stream = io.StringIO()
log_handler = logging.StreamHandler(log_stream)
root_logger = logging.getLogger()
old_level = root_logger.level
root_logger.addHandler(log_handler)
root_logger.setLevel(logging.INFO)
try:
    logging_adapter = Hades2Adapter(transport=LoggingTransport())
    logging_adapter.preference_initialized = True
    logging_adapter.execute('spawn_reward', {
        'reward': 'EmptyMaxHealthDrop',
        'requestId': 'log-reward-1',
    })
finally:
    root_logger.removeHandler(log_handler)
    root_logger.setLevel(old_level)
log_output = log_stream.getvalue()
assert 'Lua spawn_reward' in log_output
assert 'reward=EmptyMaxHealthDrop' in log_output

def reset_payload(god_mode=False):
    desired={key:(key=='godMode' and god_mode) for key in TOGGLES}
    active=dict(desired)
    return {
        'status':'ready','scene':'run','capabilities':{'setFeature':True},
        'desiredFeatures':desired,'activeFeatures':active,'dormantFeatures':{},'featureErrors':{},
        'damageMultiplier':2.0,'moneyMultiplier':2.0,'resourceMultiplier':2.0,'gameSpeed':1.0,
        'boonRarity':{'target':'Epic','multiplier':100.0,'forceLegendary':False,'forceDuo':False},
        'nextRoomReward':None,'stats':{},'resources':[],'elements':[],'boons':[],'rewards':[],
    }

class ResetTransport(FakeTransport):
    def __init__(self, fail_once=True):
        super().__init__()
        self.pid=4242;self.live=True;self.fail_once=fail_once;self.sources=[];self.god_mode=False
    def execute(self, source):
        self.sources.append(source);self.last_duration=0.001
        if self.fail_once:
            self.fail_once=False
            raise AdapterError('lua_error', '[string "MacGamingTrainer"]:1: attempt to index global \'__MacGamingTrainerV1\' (a nil value)')
        if '"set_feature"' in source and 'godMode' in source:
            self.god_mode=True
        return json.dumps(reset_payload(self.god_mode))

# A profile reload destroys/recreates Hades' Lua VM without changing the PID or
# debugger attachment. A read-only status refresh must recognize the vanished
# resident module, bootstrap the new Lua generation exactly once, and replay the
# durable desired profile without requiring a debugger reconnect.
reset_transport=ResetTransport()
reset_adapter=Hades2Adapter(transport=reset_transport)
reset_adapter._runtime_bootstrapped=True
reset_adapter._catalog_initialized=True
reset_adapter.preferences=reset_adapter._default_preferences()
reset_adapter.preferences['godMode']=True
reset_adapter.preference_initialized=True
reset_adapter.preference_dirty=False
recovered=reset_adapter.execute('status', {})
assert len(reset_transport.sources) >= 3
assert 'local previousModule' not in reset_transport.sources[0]
assert 'local previousModule' in reset_transport.sources[1]
assert any('"set_feature"' in source and 'godMode' in source for source in reset_transport.sources[2:])
assert recovered['activeFeatures']['godMode'] is True
assert reset_adapter._runtime_bootstrapped is True
assert reset_adapter._catalog_initialized is True
assert reset_adapter.preference_dirty is False

# Non-idempotent mutations are never replayed after an outcome error. Mark the
# cached generation stale so the next status can heal it, but surface this
# command's failure unchanged.
mutation_transport=ResetTransport()
mutation_adapter=Hades2Adapter(transport=mutation_transport)
mutation_adapter._runtime_bootstrapped=True
mutation_adapter._catalog_initialized=True
try:
    mutation_adapter.execute('spawn_reward', {'reward':'EmptyMaxHealthDrop','requestId':'generation-reset-mutation'})
except AdapterError as error:
    assert error.code == 'lua_error'
else:
    raise AssertionError('lost Lua generation unexpectedly replayed spawn_reward')
assert len(mutation_transport.sources) == 1
assert mutation_adapter._runtime_bootstrapped is False
assert mutation_adapter._catalog_initialized is False
assert mutation_adapter.preference_dirty is True
assert a.game_id == 'hades2' and a.display_name == 'Hades II' and a.module_protocol_version == 5
assert 'gardenQoL' in TOGGLES and 'enemyHealth' in STAT_RULES
assert a.metadata()['transport'] == 'supergiant-lldb-lua' and a.metadata()['protocolVersion'] == 5

# Offline desired profile semantics survived the module move.
state = a.set_desired('gardenQoL', True)
assert state['gardenQoL'] is True and a.preferences['gardenQoL'] is True
state = a.set_next_room_reward_desired('WeaponUpgrade')
assert state['nextRoomReward'] == 'WeaponUpgrade'

saved = a.save_profile('模块化测试', {
    'godMode': {'keyCode':18,'modifiers':6144,'keyLabel':'1'},
    'disableAll': {'keyCode':29,'modifiers':6144,'keyLabel':'0'},
})
assert saved['saved'] and saved['profiles'][0]['name'] == '模块化测试'
a.preferences['gardenQoL'] = False; a._save_preferences()
loaded = a.load_profile('模块化测试')
assert loaded['loadedProfile'] == '模块化测试' and a.preferences['gardenQoL'] is True
assert loaded['shortcuts']['godMode'] == {'keyCode':18,'modifiers':6144,'keyLabel':'1'}
assert a.delete_profile('模块化测试')['deleted']

# Game-specific validation now lives behind the Hades adapter, not core server.
calls = []
def fake_execute(command, params, replay=False):
    calls.append((command, dict(params), replay))
    return {'connected': True, 'status': 'ready'}
a.execute = fake_execute
assert a.dispatch('set_stat', {'stat':'enemyHealth','locked':True,'value':175}, 'r1')['status'] == 'ready'
assert calls[-1][0] == 'set_stat'
for bad in (
    ('set_boon_choice_desired', {'count':2}),
    ('add_resource', {'resource':'Money','amount':1}),
    ('spawn_boon', {'loot':'ZeusUpgrade'}),
    # Internal adapter->Lua replay commands are deliberately not public Host-v5 requests.
    ('set_feature', {'feature':'godMode','value':True}),
    ('set_boon_rarity', {'target':'Epic','multiplier':100,'forceLegendary':False,'forceDuo':False}),
    ('set_next_room_reward', {'reward':'WeaponUpgrade'}),
    ('set_stat', {'stat':'enemyHealth','locked':True,'value':9}),
    ('set_desired', {'feature':'gameSpeed','value':9}),
    ('set_element', {'element':'Void','amount':1}),
):
    try:
        a.dispatch(bad[0], bad[1], 'bad')
    except ValueError:
        pass
    else:
        raise AssertionError('invalid Hades command accepted: '+repr(bad))

# Request IDs are injected only for game operations that rely on Lua idempotency.
a.dispatch('set_resource', {'resource':'Money','amount':10}, 'resource-id')
assert calls[-1][1]['requestId'] == 'resource-id'

# Full desired replay remains adapter-local and covers persistent Hades state.
a.state={'connected':True,'status':'ready','desiredFeatures':{},'stats':{},'resources':[],'elements':[],
         'capabilities':{'setFeature':True},'healthLocked':False,'manaLocked':False,'armorLocked':False,
         'rerollsLocked':False,'nextRoomReward':None}
a.preferences=a._default_preferences();a.preferences.update(gardenQoL=True,nextRoomReward='WeaponUpgrade')
a.preferences['statLocks']={'enemyHealth':175,'dashSpeed':140,'manaRegen':12}
a.preferences['resourceLocks']={'Money':999};a.preferences['rerollsLock']=7;a.preferences['elementLocks']={'Fire':8}
# _replay_preferences captures runtime preferences before saving, so mark the
# wanted snapshot dirty and ensure the state starts unlocked/empty.
a.preference_dirty = True
transport.live = True
calls.clear()
a._replay_preferences(force_full=True)
assert any(c=='set_stat' and p.get('stat')=='enemyHealth' for c,p,_ in calls)
assert any(c=='set_next_room_reward' and p.get('reward')=='WeaponUpgrade' for c,p,_ in calls)
assert any(c=='lock_resource' and p.get('resource')=='Money' for c,p,_ in calls)

print('hades2_adapter_round12_ok')
