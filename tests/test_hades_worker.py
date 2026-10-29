import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
from games.hades.lldb_worker import HadesLLDBWorker, lua_literal
from core.adapter import AdapterError
from lua_runtime_support import require_lua52

lua = require_lua52('Hades worker captured target dispatch')
fixture = r'''
local mutations = 0
local runtime = {version=1,revision=5,bootstrapId='fixture', generationId='fixture'}
function runtime.status() return {heroId='fixture:run:hero',heroReady=true,health=50} end
function runtime.configure(values) return runtime.status() end
function runtime.set_value(field,value)
  assert(field=='money' and value==500)
  mutations=mutations+1
  return {heroId='fixture:run:hero',heroReady=true,money=value}
end
function runtime.json(value)
  return '{"heroId":"'..value.heroId..'","heroReady":true,"money":'..tostring(value.money or 0)..'}'
end
_G.MacGamingTrainerHades=runtime
'''


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
for target in ({'heroId': 'old:run:hero'}, None):
    try:
        worker.dispatch('set_value', {'field': 'money', 'value': 500, 'target': target})
    except AdapterError as error:
        assert error.code == 'stale_target'
    else:
        raise AssertionError('an obsolete or absent hero identity reached the mutation')

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
