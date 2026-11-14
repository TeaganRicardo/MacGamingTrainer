import json
from pathlib import Path
import re
import subprocess
import sys
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
from games.hades.lldb_worker import HadesLLDBWorker, close_worker, lua_literal
from core.adapter import AdapterError
from lua_runtime_support import require_lua52

lua = require_lua52('Hades worker captured target dispatch')
module = ROOT / 'Backend/games/hades'
resident = json.loads((module / 'module.json').read_text())['residentRuntime']
revision = re.search(resident['moduleRevisionPattern'], (module / resident['source']).read_text()).group(1)
fixture = r'''
local mutations = 0
local runtime = {version=1,revision=__REVISION__,bootstrapId='fixture', generationId='fixture'}
runtime.health, runtime.maxHealth, runtime.money, runtime.rerolls = 50, 100, 25, 3
function runtime.status()
  return {
    heroId='fixture:run:hero',heroReady=true,health=runtime.health,maxHealth=runtime.maxHealth,
    money=runtime.money,rerolls=runtime.rerolls,
    healthLocked=runtime.healthLock~=nil,healthLock=runtime.healthLock,
    moneyLocked=runtime.moneyLock~=nil,moneyLock=runtime.moneyLock,
    rerollsLocked=runtime.rerollsLock~=nil,rerollsLock=runtime.rerollsLock,
  }
end
function runtime.configure(values) return runtime.status() end
function runtime.configure_locks(health,money,rerolls)
  runtime.healthLock=health
  runtime.moneyLock,runtime.rerollsLock=money,rerolls
  if health~=nil then runtime.health,runtime.maxHealth=health.current,health.max end
  if money~=nil then runtime.money=money end
  if rerolls~=nil then runtime.rerolls=rerolls end
  mutations=mutations+1
  return runtime.status()
end
function runtime.lock_vital(name,locked)
  assert(name=='health' and type(locked)=='boolean')
  runtime.healthLock=locked and {current=runtime.health,max=runtime.maxHealth} or nil
  mutations=mutations+1
  return runtime.status()
end
function runtime.lock_resource(name,locked)
  assert(name=='Money' and type(locked)=='boolean')
  runtime.moneyLock=locked and runtime.money or nil
  mutations=mutations+1
  return runtime.status()
end
function runtime.lock_rerolls(locked)
  assert(type(locked)=='boolean')
  runtime.rerollsLock=locked and runtime.rerolls or nil
  mutations=mutations+1
  return runtime.status()
end
function runtime.set_value(field,value)
  assert(field=='money' and value==500)
  runtime.money=value
  if runtime.moneyLock~=nil then runtime.moneyLock=value end
  mutations=mutations+1
  return runtime.status()
end
local function nullable(value) return value==nil and 'null' or tostring(value) end
function runtime.json(value)
  local healthLock=value.healthLock
  local healthLockJSON=healthLock==nil and 'null' or ('{"current":'..tostring(healthLock.current)..',"max":'..tostring(healthLock.max)..'}')
  return '{"heroId":"'..value.heroId..'","heroReady":true,"health":'..tostring(value.health or 0)
    ..',"maxHealth":'..tostring(value.maxHealth or 0)
    ..',"healthLocked":'..tostring(value.healthLocked==true)..',"healthLock":'..healthLockJSON
    ..',"money":'..tostring(value.money or 0)
    ..',"rerolls":'..tostring(value.rerolls or 0)
    ..',"moneyLocked":'..tostring(value.moneyLocked==true)..',"moneyLock":'..nullable(value.moneyLock)
    ..',"rerollsLocked":'..tostring(value.rerollsLocked==true)..',"rerollsLock":'..nullable(value.rerollsLock)..'}'
end
_G.MacGamingTrainerHades=runtime
'''.replace('__REVISION__', revision)


class Transport:
    pid = 42

    def alive(self):
        return True

    def execute(self, source, *, mutating):
        assert mutating, 'bootstrap can install/reapply native hooks even during observation'
        harness = fixture + '\nlocal ok,result=pcall(function()\n' + source + '\nend)\n'
        harness += 'if not ok then assert(mutations==0); io.stderr:write(result); os.exit(1) end; print(result)'
        result = subprocess.run([lua, '-'], input=harness, capture_output=True, text=True)
        if result.returncode:
            assert 'hades.error.staleTarget' in result.stderr, result.stderr
            raise AdapterError('stale_target', 'hades.error.staleTarget')
        return json.loads(result.stdout)


worker = HadesLLDBWorker(Transport())
status = worker.dispatch('status', {})
assert status['connected'] and status['target'] == {'heroId': 'fixture:run:hero'}
edited = worker.dispatch('set_value', {'field': 'money', 'value': 500, 'target': status['target']})
assert edited['money'] == 500
configured = worker.dispatch('configure_locks', {
    'health': {'current': 45, 'max': 90}, 'money': 40, 'rerolls': 6
})
assert configured['healthLocked'] and configured['healthLock'] == {'current': 45, 'max': 90}
assert configured['moneyLocked'] and configured['moneyLock'] == 40
assert configured['rerollsLocked'] and configured['rerollsLock'] == 6
health_locked = worker.dispatch(
    'lock_vital', {'vital': 'health', 'locked': True, 'target': status['target']}
)
assert health_locked['healthLocked'] and health_locked['healthLock'] == {'current': 50, 'max': 100}
money_locked = worker.dispatch(
    'lock_resource', {'resource': 'Money', 'locked': True, 'target': status['target']}
)
assert money_locked['moneyLocked'] and money_locked['moneyLock'] == 25
rerolls_locked = worker.dispatch(
    'lock_rerolls', {'locked': True, 'target': status['target']}
)
assert rerolls_locked['rerollsLocked'] and rerolls_locked['rerollsLock'] == 3
for target in ({'heroId': 'old:run:hero'}, None):
    try:
        worker.dispatch('lock_vital', {'vital': 'health', 'locked': True, 'target': target})
    except AdapterError as error:
        assert error.code == 'stale_target'
    else:
        raise AssertionError('an obsolete or absent hero identity reached the health lock mutation')
    try:
        worker.dispatch('lock_resource', {'resource': 'Money', 'locked': True, 'target': target})
    except AdapterError as error:
        assert error.code == 'stale_target'
    else:
        raise AssertionError('an obsolete or absent hero identity reached the fixed lock mutation')

native_fixture = '''
SaveIgnores = {}
GameState = { Resources = {} }
CurrentRun = { Hero = { ObjectId = 40000, Health = 50, MaxHealth = 50, Traits = {} }, Money = 25 }
function UpdateMoneyUI() end
'''


class LuaStateTransport:
    pid = 42

    def __init__(self):
        self.history = []

    def alive(self):
        return True

    def execute(self, source, *, mutating):
        assert mutating
        harness = native_fixture
        for previous in self.history:
            harness += '\n(function()\n' + previous + '\nend)();\n'
        harness += '\nlocal ok,result=pcall(function()\n' + source + '\nend)\n'
        harness += 'if not ok then assert(CurrentRun.Money==25); io.stderr:write(result); os.exit(1) end; print(result)'
        result = subprocess.run([lua, '-'], input=harness, capture_output=True, text=True)
        if result.returncode:
            assert 'hades.error.staleTarget' in result.stderr, result.stderr
            raise AdapterError('stale_target', 'hades.error.staleTarget')
        self.history.append(source)
        return json.loads(result.stdout)


reset_transport = LuaStateTransport()
reset_worker = HadesLLDBWorker(reset_transport)
before_reset = reset_worker.dispatch('status', {})
assert reset_worker.dispatch('status', {})['target'] == before_reset['target']
reset_transport.history.clear()
after_reset = reset_worker.dispatch('status', {})
try:
    reset_worker.dispatch('set_value', {'field': 'money', 'value': 500, 'target': before_reset['target']})
except AdapterError as error:
    assert error.code == 'stale_target'
else:
    raise AssertionError('a draft from before the Lua reset mutated the replacement hero')
assert after_reset['target'] != before_reset['target']
assert reset_worker.dispatch('status', {})['target'] == after_reset['target']
edited = reset_worker.dispatch('set_value', {'field': 'money', 'value': 500, 'target': after_reset['target']})
assert edited['money'] == 500

value = '中"\\\n\09'
encoded = lua_literal(value)
probe = 'local v=' + encoded + '; assert(#v==8); assert(string.byte(v,1)==228); assert(string.byte(v,7)==0); print("escaped")'
result = subprocess.run([lua, '-e', probe], capture_output=True, text=True)
assert result.returncode == 0, result.stderr
print('hades_worker_native_target_capture_and_lua_encoding_ok')


class InterruptedReceiptTransport:
    tainted = False

    def execute(self, source, *, mutating):
        if source == 'submit':
            return {'id': 'receipt', 'state': 'pending'}
        raise AdapterError('outcome_unknown', 'hades.error.luaInterrupted', diagnostic='interrupted receipt read')


receipt_transport = InterruptedReceiptTransport()
try:
    HadesLLDBWorker(receipt_transport)._trait_command('submit', 'receipt')
except AdapterError as error:
    assert error.code == 'outcome_unknown' and error.presentation == 'hades.error.luaInterrupted'
    assert error.diagnostic == 'interrupted receipt read'
else:
    raise AssertionError('an interrupted receipt read lost its recovery instruction')
assert receipt_transport.tainted
print('hades_worker_interrupted_receipt_recovery_ok')

cleanup_events = []
cleanup_transport = types.SimpleNamespace(vm_interrupted=True)
def finish_cleanup():
    cleanup_events.append('kill')
    if cleanup_events.count('kill') < 3:
        raise AdapterError('outcome_unknown', 'hades.error.luaTerminationFailed')
    cleanup_transport.vm_interrupted = False
with patch('games.hades.lldb_worker.time.sleep', side_effect=lambda seconds: cleanup_events.append('wait')):
    close_worker(types.SimpleNamespace(transport=cleanup_transport, close=finish_cleanup))
assert cleanup_events == ['kill', 'wait', 'kill', 'wait', 'kill']
cleanup_transport.vm_interrupted = False
with patch('games.hades.lldb_worker.time.sleep', side_effect=AssertionError('ordinary cleanup error was retried')):
    try:
        close_worker(types.SimpleNamespace(transport=cleanup_transport,
                     close=lambda: (_ for _ in ()).throw(AdapterError('detach_failed', 'hades.error.detachFailed'))))
    except AdapterError as error:
        assert error.code == 'detach_failed'
    else:
        raise AssertionError('ordinary cleanup failure was hidden')
print('hades_worker_eof_retains_interrupted_target_until_exit_ok')
