"""Temporary Lua 5.2 game state shared by Hades I behavior journeys.

The game's Lua state survives a debugger detach and is replaced only by a
same-process Lua reset, so these journeys keep one persistent Lua history and
model a reset by clearing it. Contract: ENGINEERING_INVARIANTS.md sections 2-4
(desired state survives detach/backend restart and replays after a reset;
observable state is never inferred from desired state alone).
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
sys.path.insert(0, str(ROOT / 'tests'))
from core.adapter import AdapterError, GameAdapterContext  # noqa: E402
from games.hades.adapter import HadesAdapter  # noqa: E402
from games.hades.lldb_worker import HadesLLDBWorker  # noqa: E402
from games.hades.preferences import HadesPreferenceStore  # noqa: E402
from games.hades.schema import DEFAULT_PREFERENCES  # noqa: E402
from lua_runtime_support import require_lua52  # noqa: E402

LUA = require_lua52('Hades desired-state replay')

NATIVE = r'''
SaveIgnores = {}
GameState = { Resources = { MetaPoints = 5 } }
function UpdateHealthUI() end
function UpdateMoneyUI(value) end
function UpdateRerollUI(value) end
function ValidateMaxHealth() end
function AddOutgoingDamageModifier(unit, modifier) table.insert(unit.OutgoingDamageModifiers, modifier) end
function AddIncomingDamageModifier(unit, modifier) table.insert(unit.IncomingDamageModifiers, modifier) end
function SetPlayerInvulnerable(flag) CurrentRun.Hero.InvulnerableFlags[flag]=true; CurrentRun.InvulnerableFlags[flag]=true end
function SetPlayerVulnerable(flag) CurrentRun.Hero.InvulnerableFlags[flag]=nil; CurrentRun.InvulnerableFlags[flag]=nil end
-- Native spending refreshes the HUD, which is where the resident enforces a gold lock.
function SpendMoney(amount) CurrentRun.Money = CurrentRun.Money - amount; UpdateMoneyUI(CurrentRun.Money) end
CurrentRun = { Hero = { ObjectId = 40000, Health = 50, MaxHealth = 50, Traits = {}, InvulnerableFlags = {},
  OutgoingDamageModifiers = {}, IncomingDamageModifiers = {} }, Money = 100, NumRerolls = 3, InvulnerableFlags = {} }
'''


class PersistentGameLua:
    """One game process: Lua state persists across attachments until a Lua reset."""
    pid = 42

    def __init__(self):
        self.history = []
        self.attached = False

    def alive(self):
        return self.attached

    def attach(self, pid, executable):
        self.attached = True

    def detach(self):
        self.attached = False

    def lua_reset(self):
        self.history.clear()

    def native(self, lua):
        self.history.append(lua)

    def _script(self, extra):
        script = NATIVE
        for previous in self.history:
            script += '\n(function()\n' + previous + '\nend)();\n'
        return script + extra

    def value(self, expression):
        result = subprocess.run([LUA, '-'], input=self._script('\nprint(' + expression + ')'),
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    def execute(self, source, *, mutating=False):
        script = self._script('\nlocal ok,result=pcall(function()\n' + source + '\nend)\n'
                              'if not ok then io.stderr:write(tostring(result)); os.exit(1) end; print(result)')
        result = subprocess.run([LUA, '-'], input=script, capture_output=True, text=True)
        if result.returncode:
            if 'hades.error.restartRequired' in result.stderr:
                raise AdapterError('restart_required', 'hades.error.restartRequired', diagnostic=result.stderr)
            raise AdapterError('outcome_unknown', 'hades.error.outcomeUnknown', diagnostic=result.stderr)
        self.history.append(source)
        return json.loads(result.stdout)


class WorkerRuntime:
    """In-process stand-in for the sidecar client over the real worker."""

    def __init__(self, worker):
        self.worker = worker
        self.connected = False
        self.game_speed_actual = 1.0
        self.replies = []

    def _record(self, state):
        self.replies.append(json.loads(json.dumps(state)))
        self.connected = state['connected']
        return state

    def connect(self, pid, executable, features=None):
        params = {'pid': pid, 'executable': executable}
        if features is not None:
            params['features'] = features
        return self._record(self.worker.dispatch('connect', params))

    def status(self):
        if not self.connected:
            return HadesAdapter._offline()
        return self._record(self.worker.dispatch('status', {}))

    def command(self, method, params):
        return self._record(self.worker.dispatch(method, params))

    def current_game_speed(self):
        return self.game_speed_actual

    def set_game_speed(self, value):
        self.game_speed_actual = float(value)
        return self.game_speed_actual

    def disconnect(self):
        result = self.worker.dispatch('disconnect', {})
        self.connected = False
        return result

    def close(self):
        pass


CONTEXT = GameAdapterContext('hades', 'Hades', 2, ROOT / 'Backend/games/hades', {})


def adapter_for(directory, game=None):
    game = game or PersistentGameLua()
    runtime = WorkerRuntime(HadesLLDBWorker(game))
    store = HadesPreferenceStore(Path(directory) / 'preferences.json')
    adapter = HadesAdapter(CONTEXT, runtime=runtime, preferences=store,
                           locate_process=lambda: (42, '/tmp/Hades/Game.macOS.app/Contents/MacOS/Game.macOS'))
    return adapter, runtime, game, store


def assert_projection_matches_resident(state, resident, label):
    for flag, value in (('healthLocked', 'healthLock'), ('moneyLocked', 'moneyLock'),
                        ('rerollsLocked', 'rerollsLock')):
        assert state[flag] == resident[flag], (label, flag, state[flag], resident[flag])
        assert state[value] == (resident[value] if resident[flag] else None), (label, value)
    assert state['boonRarityTarget'] == resident['boonRarityTarget'], label


