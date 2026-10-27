"""Exercise native registration results through the leased transport and worker."""
import io
import json
import runpy
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from lua_native_prerequisites import require_lua52_native

ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_MODULE = json.loads((ROOT / 'Backend/games/hades2/module.json').read_text(encoding='utf-8'))
SUPPORTED_GAME = SUPPORTED_MODULE['supportedBuild']
_, compiler, lua_flags = require_lua52_native('Native query expression', language='c++')
sys.path.insert(0, str(ROOT / 'Backend'))
from core.adapter import AdapterError
from games.hades2.native_effect_query import NativeQueryLibrary
from games.hades2.lldb_worker import Hades2LLDBWorker, serve_requests
from games.hades2.transport_client import _LLDBWorkerClient

fixture = runpy.run_path(str(ROOT / 'tests/test_hades2_transport_outcome_unknown_taint.py'))
fixture['namespace']['TransportError'] = AdapterError
Transport = fixture['Transport']


class RejectedProcess(fixture['SuccessfulProcess']):
    def __init__(self, text):
        super().__init__()
        self.text = text

    def ReadCStringFromMemory(self, address, capacity, error):
        return self.text


for status, reason in (
    (-1, 'Native query registration requires Darwin MainThread'),
    (-2, 'Native query registration cannot reserve Lua stack space'),
    (-3, 'Native query target Mach-O header or load commands are unreadable or invalid (header_read)'),
    (-4, f"Native query target UUID does not match {SUPPORTED_MODULE['displayName']} "
         f"1.{SUPPORTED_GAME['bundleVersion']} {SUPPORTED_GAME['architecture']}"),
    (-100, 'Native query target binding mismatch: lua_gettop'),
    (-200, 'Native query target binding is unreadable: lua_gettop'),
):
    transport = Transport.__new__(Transport)
    transport.native_runtime_installer = NativeQueryLibrary(200, 0x100000000)
    transport.tainted = False
    transport.process = RejectedProcess(reason)
    transport.target = fixture['FakeTarget']()
    transport.last_duration = 0
    transport.boundary = lambda status=status: (
        fixture['FakeThread'](status), 0x2000, fixture['FakeBreakpoint']()
    )
    transport.address = lambda name: 0x3000
    transport.alive = lambda: False
    try:
        transport.execute("return '{}'", expression_timeout_seconds=2)
    except AdapterError as error:
        assert error.code == 'incompatible', (
            f'Native registration status {status} was reported as {error.code}; '
            'the resident operation never executed'
        )
        assert error.presentation == 'hades2.error.nativeQueryUnavailable'
        assert reason in error.diagnostic and f'status={status}' in error.diagnostic
    else:
        raise AssertionError('Native registration rejection was accepted')
    assert transport.target.deleted == [1], 'Rejected install leaked its leased breakpoint'
    assert not transport.tainted, 'Known pre-resident rejection was labeled outcome-unknown'

    # Pass the same rejection through the actual worker JSONL envelope and
    # client decoder used by the application backend.
    transport.pid = 4242
    output = io.StringIO()
    requests = [
        {'id': 'hello', 'method': 'hello', 'params': {}},
        {'id': 'install', 'method': 'transport.execute', 'params': {'source': "return '{}'"}},
    ]
    serve_requests(
        io.StringIO(''.join(json.dumps(row) + '\n' for row in requests)),
        output, Hades2LLDBWorker(transport=transport),
    )

    class ReplayedSidecar:
        started = True
        terminal = False

        def __init__(self):
            self.responses = [json.loads(line) for line in output.getvalue().splitlines()]
            self.calls = []

        def request(self, method, params, **options):
            self.calls.append(method)
            return self.responses.pop(0)

    sidecar = ReplayedSidecar()
    client = _LLDBWorkerClient(sidecar=sidecar)
    try:
        client.call('transport.execute', {'source': "return '{}'"})
    except AdapterError as error:
        assert error.code == 'incompatible'
        assert error.presentation == 'hades2.error.nativeQueryUnavailable'
        assert reason in error.diagnostic and f'status={status}' in error.diagnostic
    else:
        raise AssertionError('Worker lost the native registration rejection')
    assert sidecar.calls == ['hello', 'transport.execute'], 'Native rejection was replayed'
    assert not client.terminal, 'Known native rejection terminalized sidecar trust'

# Installation shares the existing result buffer. A successful resident reply
# is read once, without an additional diagnostic allocation or read.
payload = "residentRuns = (residentRuns or 0) + 1; return '{}'"
class ResultProcess(fixture['SuccessfulProcess']):
    def __init__(self):
        super().__init__()
        self.reads = 0

    def ReadCStringFromMemory(self, address, capacity, error):
        assert address == 0x1000 + len(payload.encode()) + 1
        assert capacity == fixture['namespace']['LUA_TRANSPORT_RESULT_LIMIT_BYTES']
        self.reads += 1
        return '{}'
transport = Transport.__new__(Transport)
transport.native_runtime_installer = NativeQueryLibrary(200, 0x100000000)
transport.process = ResultProcess(); transport.target = fixture['FakeTarget']()
transport.boundary = lambda: (fixture['FakeThread'](0), 0x2000, fixture['FakeBreakpoint']())
transport.address = lambda name: 0x3000
transport.alive = lambda: False; transport.tainted = False
for _ in range(2):
    assert transport.execute(payload) == '{}'
    assert transport.process.allocated_size == len(payload.encode()) + 1 + fixture['namespace']['LUA_TRANSPORT_RESULT_LIMIT_BYTES']
assert transport.process.reads == 2

# Compile the actual generated expression against real Lua 5.2. Only its fixture
# addresses are substituted; the expression's control flow/copy/stack code is
# exactly what execute emitted. The install stub implements the ABI3 contract.
expressions = []
class CapturingFrame:
    def EvaluateExpression(self, expression, options):
        expressions.append(expression)
        return fixture['FakeResult'](-3)
transport = Transport.__new__(Transport)
transport.native_runtime_installer = NativeQueryLibrary(0x400000, 0x500000)
transport.process = RejectedProcess('fixture rejection'); transport.target = fixture['FakeTarget']()
transport.boundary = lambda: (SimpleNamespace(GetFrameAtIndex=lambda index: CapturingFrame()), 0x2000, fixture['FakeBreakpoint']())
transport.alive = lambda: False; transport.tainted = False
names = ['lua_gettop', 'luaL_loadbufferx', 'lua_pcallk', 'lua_tolstring', 'lua_settop']
addresses = {name: 0x300000 + index * 0x100 for index, name in enumerate(names)}
transport.address = addresses.__getitem__
try:
    transport.execute(payload)
except AdapterError as error:
    assert error.code == 'incompatible'
out_offset = len(payload.encode()) + 1
replacements = {0x1000: '(uintptr_t)scratch', 0x1000 + out_offset: '(uintptr_t)(scratch+PAYLOADSIZE+1)',
    0x2000: '(uintptr_t)state', 0x400000: '(uintptr_t)installStub'}
replacements.update({address: '(uintptr_t)' + name for name, address in addresses.items()})
expression = re.sub(r'\b\d+\b', lambda match: replacements.get(int(match.group()), match.group()), expressions[0])
program = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <initializer_list>
extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
}
static int mode;
static char *outputBuffer;
static int installStub(void *p, unsigned long base, char *output, unsigned long capacity) {
    assert(base==0x500000 && output==outputBuffer && capacity==CAP);
    output[0]=0;
    if(mode<0) snprintf(output,capacity,"Native query rejected (%d)",mode);
    else if(mode>0) {
        assert(luaL_loadstring((lua_State*)p,"error('protected-install-error')")==0);
        return lua_pcall((lua_State*)p,0,0,0);
    }
    return mode;
}
int main() {
    lua_State *state=luaL_newstate();assert(state);luaL_openlibs(state);
    lua_pushinteger(state,42);
    char scratch[CAP+PAYLOADSIZE+1]={};
    memcpy(scratch,PAYLOAD,PAYLOADSIZE);
    outputBuffer=scratch+PAYLOADSIZE+1;
    for(int status: {-1,-2,-3,-4,-100,-200,2,0}) {
        mode=status;
        int rc=EXPRESSION;
        assert(rc==status && lua_gettop(state)==1 && lua_tointeger(state,1)==42);
        const char *text=scratch+PAYLOADSIZE+1;
        if(status<0) {
            char expected[64];snprintf(expected,sizeof(expected),"Native query rejected (%d)",status);
            assert(strcmp(text,expected)==0);
        }
        if(status==2)assert(strstr(text,"protected-install-error"));
        if(!status)assert(strcmp(text,"{}")==0);
        lua_getglobal(state,"residentRuns");
        assert(lua_tointeger(state,-1)==(status==0 ? 1 : 0));lua_pop(state,1);
    }
    lua_close(state);
    puts("native_query_generated_expression_ok: ABI3 args, bounded failure, protected Lua error, resident result, stack restore");
}
'''
program = program.replace('EXPRESSION', expression).replace('CAP', str(fixture['namespace']['LUA_TRANSPORT_RESULT_LIMIT_BYTES']))
program = program.replace('PAYLOADSIZE', str(len(payload.encode()))).replace('PAYLOAD', json.dumps(payload))
with tempfile.TemporaryDirectory(prefix='mgt-native-query-expression-') as temporary:
    root = Path(temporary); cpp = root/'expression.cpp'; cpp.write_text(program)
    executable = root/'expression'
    subprocess.run([compiler, '-std=c++17', str(cpp), *lua_flags, '-lm', '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True, timeout=15)

print('hades2_native_query_registration_ok: precise rejection, worker envelope, no replay, leased cleanup')
