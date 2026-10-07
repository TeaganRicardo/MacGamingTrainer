import io
import json
import logging
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'Backend'))
sys.path.insert(0, str(root/'tests'))

import games.hades2.adapter as adapter_module
from core.adapter import AdapterError
from games.hades2 import preparation as prep
from games.hades2.adapter import STAT_RULES, TOGGLES, Hades2Adapter
from games.hades2.error_presentation import Hades2PresentationError
from games.hades2.desired_reconciliation import DesiredReconciliationOutcome
from games.hades2.resident_session import ResidentGenerationInvalidated, ResidentMetrics, ResidentReply
from hades2_resident_session_fakes import FakeResidentSession, FakeTimeWarpController

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
    desired={key:(key=='invincibility' and god_mode) for key in TOGGLES}
    active=dict(desired)
    return {
        'status':'ready','scene':'run','capabilities':{'setFeature':True},
        'desiredFeatures':desired,'activeFeatures':active,'dormantFeatures':{},'featureErrors':{},
        'damageMultiplier':2.0,'moneyMultiplier':2.0,'resourceMultiplier':2.0,'gameSpeed':1.0,
        'boonRarity':{'target':'Epic','multiplier':100.0,'forceLegendary':False,'forceDuo':False},
        'nextRoomReward':None,'stats':{},'resources':[],'elements':[],'boons':[],'rewards':[],
    }

class ResetSession(FakeResidentSession):
    def __init__(self, generation_reset=False):
        super().__init__(reset_payload(False))
        self.generation_reset = generation_reset
        self.god_mode = False

    def status(self, params=None):
        self.process_time_warp_allowed = True
        self.calls.append({
            'kind': 'status',
            'command': 'status',
            'params': dict(params or {}),
            'batch': None,
        })
        reply = ResidentReply(
            payload=reset_payload(self.god_mode),
            metrics=ResidentMetrics(boundary_duration=0.001),
            generation_reset=self.generation_reset,
        )
        self.generation_reset = False
        return reply

    def reconcile(self, calls):
        calls = list(calls)
        self.calls.append({
            'kind': 'reconcile',
            'command': 'replay_preferences',
            'params': {},
            'batch': calls,
        })
        for command, params in calls:
            if command == 'set_feature' and params.get('feature') == 'invincibility':
                self.god_mode = bool(params.get('value'))
        return ResidentReply(
            payload=reset_payload(self.god_mode),
            metrics=ResidentMetrics(boundary_duration=0.001),
        )


# A profile reload destroys/recreates Hades' Lua VM without changing the PID.
# ResidentSession owns re-bootstrap/recovery; Adapter only projects the
# generation-reset evidence and replays the durable desired profile once.
reset_session=ResetSession(generation_reset=True)
reset_adapter=Hades2Adapter(
    resident_session=reset_session,
    time_warp_controller=FakeTimeWarpController(),
)
reset_adapter.preferences=reset_adapter._default_preferences()
reset_adapter.preferences['invincibility']=True
reset_adapter.preference_initialized=True
reset_adapter.preference_dirty=False
recovered=reset_adapter.execute('status', {})
assert [call['kind'] for call in reset_session.calls] == ['status', 'reconcile']
assert any(
    command == 'set_feature'
    and params.get('feature') == 'invincibility'
    and params.get('value') is True
    for command, params in reset_session.calls[1]['batch']
)
assert recovered['activeFeatures']['invincibility'] is True
assert reset_adapter.preference_dirty is False

# A run-log reset is lifecycle evidence only: it invalidates the resident
# generation and projects waiting state without crossing a resident boundary.
proactive_session=ResetSession()
proactive_adapter=Hades2Adapter(
    resident_session=proactive_session,
    time_warp_controller=FakeTimeWarpController(),
)
proactive_adapter.state.update(connected=True,pid=4242,status='ready',scene='run')
proactive_adapter.preferences=proactive_adapter._default_preferences()
proactive_adapter.preferences['invincibility']=True
proactive_adapter.preference_initialized=True
proactive_adapter.preference_dirty=False
before_invalidations=proactive_session.invalidations
invalidated=proactive_adapter.dispatch('runtime_reset', {}, 'runtime-reset-signal')
assert proactive_session.calls == []
assert proactive_session.invalidations == before_invalidations + 1
assert invalidated['connected'] is True
assert invalidated['status'] == 'waiting'
assert proactive_adapter.preference_dirty is True
proactive_recovered=proactive_adapter.execute('status', {})
assert [call['kind'] for call in proactive_session.calls] == ['status', 'reconcile']
assert proactive_recovered['activeFeatures']['invincibility'] is True
assert proactive_adapter.preference_dirty is False

# Non-idempotent mutations are never replayed across a missing resident
# generation. Session reports invalidation; Adapter projects waiting state and
# surfaces the original command failure unchanged.
missing_error=AdapterError(
    'lua_error',
    '[string "MacGamingTrainer"]:1: attempt to index global \'__MacGamingTrainerV1\' (a nil value)',
)
def mutation_reset_handler(session, record):
    if record['kind'] == 'mutate':
        return ResidentGenerationInvalidated(missing_error)
    return reset_payload(False)

mutation_session=FakeResidentSession(reset_payload(False), handler=mutation_reset_handler)
mutation_adapter=Hades2Adapter(
    resident_session=mutation_session,
    time_warp_controller=FakeTimeWarpController(),
)
try:
    mutation_adapter.execute('spawn_reward', {'reward':'EmptyMaxHealthDrop','requestId':'generation-reset-mutation'})
except AdapterError as error:
    assert error.code == 'lua_error'
else:
    raise AssertionError('lost Lua generation unexpectedly replayed spawn_reward')
assert len(mutation_session.calls) == 1
assert mutation_adapter.preference_dirty is True
assert mutation_adapter.state['status'] == 'waiting'
assert a.game_id == 'hades2' and a.display_name == 'Hades II' and a.module_protocol_version == 13
assert a.state['version'] == '1.143476'
assert 'gardenQoL' in TOGGLES and 'enemyHealth' in STAT_RULES
assert a.metadata()['transport'] == 'supergiant-lldb-lua' and a.metadata()['protocolVersion'] == 13

# A process-query failure is not evidence that Hades stopped. Preserve the
# existing debugger/session state and surface the query error instead of
# detaching or projecting not_running.
scan_transport = FakeTransport()
scan_transport.pid = 4242
scan_transport.live = True
scan_adapter = Hades2Adapter(transport=scan_transport)
scan_adapter.state.update(pid=4242, connected=True, status='ready', scene='run')
old_compatibility = adapter_module.preparation.compatibility
old_run = adapter_module.subprocess.run
class FailedProcessQuery:
    returncode = 2
    stdout = ''
    stderr = 'pgrep permission denied'
try:
    adapter_module.preparation.compatibility = lambda strict=False: {
        'version':'139672', 'steam_build':'24556151', 'warnings':[],
    }
    adapter_module.subprocess.run = lambda *args, **kwargs: FailedProcessQuery()
    try:
        scan_adapter.scan()
    except RuntimeError as error:
        assert '查询 Hades II 进程失败' in str(error)
    else:
        raise AssertionError('pgrep failure was misreported as game-not-running')
    assert scan_transport.pid == 4242 and scan_transport.live is True
    assert scan_adapter.state['pid'] == 4242
    assert scan_adapter.state['connected'] is True
finally:
    adapter_module.preparation.compatibility = old_compatibility
    adapter_module.subprocess.run = old_run


# Offline desired profile semantics survived the module move.
state = a.set_desired('gardenQoL', True)
assert state['gardenQoL'] is True and a.preferences['gardenQoL'] is True
state = a.set_next_room_reward_desired('WeaponUpgrade')
assert state['nextRoomReward'] == 'WeaponUpgrade'

saved = a.save_profile('模块化测试', {
    'invincibility': {'keyCode':18,'modifiers':6144,'keyLabel':'1'},
    'disableAll': {'keyCode':29,'modifiers':6144,'keyLabel':'0'},
})
assert saved['saved'] and saved['profiles'][0]['name'] == '模块化测试'
a.preferences['gardenQoL'] = False; a._save_preferences()
loaded = a.load_profile('模块化测试')
assert loaded['loadedProfile'] == '模块化测试' and a.preferences['gardenQoL'] is True
assert loaded['shortcuts']['invincibility'] == {'keyCode':18,'modifiers':6144,'keyLabel':'1'}
assert a.delete_profile('模块化测试')['deleted']

# Game-specific validation now lives behind the Hades adapter, not core server.
calls = []
def fake_execute(command, params):
    calls.append((command, dict(params)))
    return {'connected': True, 'status': 'ready'}
a.execute = fake_execute
assert a.dispatch('set_stat', {'stat':'enemyHealth','locked':True,'value':175}, 'r1')['status'] == 'ready'
assert calls[-1][0] == 'set_stat'
for bad in (
    ('set_boon_choice_desired', {'count':2}),
    ('add_resource', {'resource':'Money','amount':1}),
    ('spawn_boon', {'loot':'ZeusUpgrade'}),
    # Internal adapter->Lua replay commands are deliberately not public Host-v5 requests.
    ('set_feature', {'feature':'invincibility','value':True}),
    ('set_boon_rarity', {'target':'Epic','multiplier':100,'forceLegendary':False,'forceDuo':False}),
    ('set_next_room_reward', {'reward':'WeaponUpgrade'}),
    ('set_stat', {'stat':'enemyHealth','locked':True,'value':9}),
    ('set_desired', {'feature':'gameSpeed','value':20.1}),
    ('set_element', {'element':'Void','amount':1}),
):
    try:
        a.dispatch(bad[0], bad[1], 'bad')
    except Hades2PresentationError as error:
        # Invalid input is rejected with a language-neutral presentation key.
        assert error.presentation.startswith('hades2.error.'), error.presentation
    else:
        raise AssertionError('invalid Hades command accepted: '+repr(bad))

# Request IDs are injected only for game operations that rely on Lua idempotency.
a.dispatch('set_resource', {'resource':'Money','amount':10}, 'resource-id')
assert calls[-1][1]['requestId'] == 'resource-id'

# Desired replay planning is owned by Hades2DesiredStateReconciler and is
# exercised through that interface. Adapter's general execution interface no
# longer accepts synthetic replay/batch controls.
try:
    a.execute('status', {}, replay=True)
except TypeError:
    pass
else:
    raise AssertionError('Adapter.execute still exposes replay implementation controls')

print('hades2_adapter_round12_ok')
