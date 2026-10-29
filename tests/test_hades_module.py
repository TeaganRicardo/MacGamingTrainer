"""Hades module identity, request ownership and safe feature scope."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from core.adapter import AdapterError, GameAdapterContext
from games.hades import adapter as hades_adapter
from games.hades.adapter import HadesAdapter
from games.hades.preferences import HadesPreferenceStore
from games.hades.recovery import HadesRecoveryJournal


class Runtime:
    def __init__(self):
        self.calls = []
        self.connected = False
        self.invincible = False
        self.speed = 1.0

    def connect(self, pid, executable, features=None):
        self.calls.append(('connect', pid, executable))
        self.connected = True
        return self.status()

    def status(self):
        return {'connected': self.connected, 'heroReady': self.connected,
                'invincible': self.invincible, 'health': 50, 'maxHealth': 100,
                'money': 25, 'pid': 42 if self.connected else None}

    def current_game_speed(self):
        return self.speed

    def set_game_speed(self, value):
        self.speed = value
        return value

    def set_invincibility(self, value):
        self.calls.append(('set_invincibility', value))
        self.invincible = value
        return self.status()

    def command(self, method, params):
        if method == 'set_feature':
            assert params['feature'] == 'invincibility'
            return self.set_invincibility(params['value'])
        assert method == 'disable_all'
        return self.set_invincibility(False)

    def disconnect(self):
        self.calls.append(('disconnect',))
        self.speed = 1.0
        self.connected = False
        return self.status()

    def close(self):
        self.calls.append(('close',))
        self.connected = False


context = GameAdapterContext('hades', 'Hades', 1, ROOT / 'Backend/games/hades', {})
test_data = tempfile.TemporaryDirectory(prefix='hades-module-')
preferences = HadesPreferenceStore(Path(test_data.name) / 'preferences.json')
runtime = Runtime()
adapter = HadesAdapter(context, runtime=runtime, locate_process=lambda: (42, '/tmp/Hades/Game.macOS'), preferences=preferences)
assert adapter.dispatch('status', {}, 's0')['connected'] is False
assert runtime.calls == [], 'offline status must not launch a debugger'
assert adapter.dispatch('connect', {}, 'c1')['connected'] is True
assert runtime.calls[0] == ('connect', 42, '/tmp/Hades/Game.macOS')
with patch('games.hades.adapter.subprocess.run'):
    assert adapter.dispatch('launch', {}, 'launch')['connected'] is True
assert adapter.dispatch('set_invincibility', {'value': True}, 'm1')['invincible'] is True
assert adapter.dispatch('disconnect', {}, 'd1')['connected'] is False
assert runtime.invincible, 'manual disconnect preserves the current game effect'
assert adapter.dispatch('connect', {}, 'c2')['invincible'] is True
assert adapter.dispatch('disable_all', {}, 'x1')['invincible'] is False
try:
    adapter.dispatch('set_invincibility', {'value': 'false'}, 'invalid')
except (ValueError, AdapterError):
    pass
else:
    raise AssertionError('non-boolean intent must be rejected before runtime mutation')
assert runtime.calls[-1] == ('set_invincibility', False)
adapter.close()
assert runtime.calls[-1] == ('close',)

from core.sidecar import SidecarTerminalError
from games.hades.client import HadesRuntimeClient


class Sidecar:
    started = True
    terminal = False

    def __init__(self):
        self.calls = []

    def request(self, method, params, **options):
        self.calls.append((method, params, options))
        if method == 'set_invincibility':
            self.terminal = True
            self.started = False
            raise SidecarTerminalError('acknowledgement lost', outcome_unknown=True)
        return {'result': {'connected': method != 'disconnect', 'heroReady': True, 'pid': 42}}

    def close(self):
        self.started = False


sidecar = Sidecar()
client = HadesRuntimeClient(sidecar, recovery=HadesRecoveryJournal(Path(test_data.name) / 'runtime.json'), identity=lambda pid: str(pid))
client.connect(42, '/tmp/Hades/Game.macOS')
try:
    client.set_invincibility(True)
except AdapterError as error:
    assert error.code == 'outcome_unknown'
else:
    raise AssertionError('a lost mutation acknowledgement must remain unknown')
sent = len(sidecar.calls)
try:
    client.connect(42, '/tmp/Hades/Game.macOS')
except AdapterError as error:
    assert error.code == 'restart_required'
else:
    raise AssertionError('unknown native call must block reconnect to the same process')
assert len(sidecar.calls) == sent, 'unknown mutation must not be replayed'
replacement = Sidecar()
client._new_sidecar = lambda: replacement
assert client.connect(43, '/tmp/Hades/Game.macOS')['connected']
assert replacement.calls[0][0] == 'connect', 'a new process gets a new connection, never a replay'


no_game = HadesAdapter(context, runtime=Runtime(), locate_process=lambda: None, preferences=preferences)
try:
    no_game.dispatch('connect', {}, 'missing')
except AdapterError as error:
    assert error.code == 'game_not_running'
    assert error.presentation.startswith('hades.')
else:
    raise AssertionError('missing game must have a typed failure')

# Process-list command names are candidate hints only; the kernel path owns identity.
expected_executable = str(Path(
    '/Users/test/Library/Application Support/Steam/steamapps/common/Hades/'
    'Game.macOS.app/Contents/MacOS/Game.macOS'
).resolve())
unrelated_executable = str(Path('/tmp/Other/Game.macOS').resolve())
with patch('games.hades.adapter.subprocess.check_output',
           return_value='42 Game.macOS\n43 Game.macOS\n'):
    with patch('games.hades.adapter.process_executable_path',
               side_effect=lambda pid: expected_executable if pid == 42 else unrelated_executable):
        assert hades_adapter.locate_process() == (42, expected_executable), (
            'basename-only comm must resolve through the actual executable path'
        )

with patch('games.hades.adapter.subprocess.check_output',
           return_value=f'42 {expected_executable}\n'):
    with patch('games.hades.adapter.process_executable_path', return_value=None):
        assert hades_adapter.locate_process() == (42, expected_executable), (
            'a full matching ps path remains a valid fallback if proc_pidpath is unavailable'
        )

with patch('games.hades.adapter.subprocess.check_output',
           return_value='42 Game.macOS\n43 Game.macOS\n'):
    with patch('games.hades.adapter.process_executable_path', return_value=expected_executable):
        try:
            hades_adapter.locate_process()
        except AdapterError as error:
            assert error.code == 'ambiguous_target'
        else:
            raise AssertionError('multiple matching Hades processes must fail closed')

if sys.platform == 'darwin':
    current_executable = hades_adapter.process_executable_path(os.getpid())
    assert current_executable and Path(current_executable).is_absolute(), (
        'proc_pidpath must resolve the current test process on macOS'
    )

source = (ROOT / 'Backend/games/hades/runtime.lua').read_text()
from lua_runtime_support import require_lua52
lua = require_lua52('Hades module feature ownership')
harness = r'''
local calls = {}
CurrentRun = {Money=25,InvulnerableFlags={NativeMenu=true},Hero={ObjectId=10,Health=50,MaxHealth=100,InvulnerableFlags={NativeMenu=true}}}
SetPlayerInvulnerable = function(flag)
  calls[#calls+1] = {'enable',flag}
  CurrentRun.Hero.InvulnerableFlags[flag]=true
  CurrentRun.InvulnerableFlags[flag]=true
end
SetPlayerVulnerable = function(flag)
  calls[#calls+1] = {'disable',flag}
  CurrentRun.Hero.InvulnerableFlags[flag]=nil
  CurrentRun.InvulnerableFlags[flag]=nil
end
local runtime = assert(load(SOURCE))()
local before = runtime.status()
assert(before.heroReady and not before.invincible)
local enabled = runtime.set_invincibility(true)
assert(enabled.invincible and CurrentRun.InvulnerableFlags.NativeMenu)
assert(CurrentRun.Hero.InvulnerableFlags.NativeMenu)
local disabled = runtime.set_invincibility(false)
assert(not disabled.invincible and CurrentRun.InvulnerableFlags.NativeMenu)
assert(CurrentRun.Hero.InvulnerableFlags.NativeMenu)
assert(calls[1][2] == calls[2][2] and calls[1][2] ~= 'Generic')
CurrentRun = nil
assert(not runtime.status().heroReady)
local ok = pcall(function() runtime.set_invincibility(true) end)
assert(not ok and #calls == 2)
print('hades_runtime_ownership_ok')
'''
proc = subprocess.run([lua, '-e', 'local SOURCE=' + json.dumps(source) + '\n' + harness], capture_output=True, text=True)
assert proc.returncode == 0, proc.stderr
print(proc.stdout.strip())
print('hades_module_ok')
test_data.cleanup()
