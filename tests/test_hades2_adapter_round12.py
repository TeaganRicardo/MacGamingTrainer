from pathlib import Path
import sys, tempfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'Backend'))

from games.hades2 import preparation as prep
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
assert a.game_id == 'hades2' and a.display_name == 'Hades II' and a.module_protocol_version == 5
assert 'gardenQoL' in TOGGLES and 'enemyHealth' in STAT_RULES
assert a.metadata()['transport'] == 'supergiant-lldb-lua' and a.metadata()['protocolVersion'] == 5

# Offline desired profile semantics survived the module move.
state = a.set_desired('gardenQoL', True)
assert state['gardenQoL'] is True and a.preferences['gardenQoL'] is True
state = a.set_next_room_reward_desired('WeaponUpgrade')
assert state['nextRoomReward'] == 'WeaponUpgrade'

saved = a.save_profile('模块化测试', {'godMode': 1, 'disableAll': 0})
assert saved['saved'] and saved['profiles'][0]['name'] == '模块化测试'
a.preferences['gardenQoL'] = False; a._save_preferences()
loaded = a.load_profile('模块化测试')
assert loaded['loadedProfile'] == '模块化测试' and a.preferences['gardenQoL'] is True
assert loaded['shortcuts']['godMode'] == 1
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
