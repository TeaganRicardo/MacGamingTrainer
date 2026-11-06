"""Hades I durable desired state against the real adapter, worker and resident Lua.

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


# A Disable All issued while detached must still clear the resident lock on the
# next connect: the game kept enforcing it, so reconnect is the cleanup point.
with tempfile.TemporaryDirectory(prefix='hades-desired-') as directory:
    adapter, runtime, game, store = adapter_for(directory)
    state = adapter.dispatch('connect', {}, 'connect-1')
    adapter.dispatch('lock_resource', {'resource': 'Money', 'locked': True, 'target': state['target']}, 'lock')
    adapter.dispatch('disconnect', {}, 'detach')
    adapter.dispatch('disable_all', {}, 'offline-disable')
    assert store.load()['moneyLock'] is None
    state = adapter.dispatch('connect', {}, 'connect-2')
    assert runtime.replies[-1]['moneyLocked'] is False, 'resident kept a lock after offline Disable All'
    assert_projection_matches_resident(state, runtime.replies[-1], 'offline disable + reconnect')
    game.native('SpendMoney(60)')
    assert game.value('CurrentRun.Money') == '40', 'released lock still pinned native gold'

# Loading a lock-free Profile while detached releases a resident health lock.
with tempfile.TemporaryDirectory(prefix='hades-desired-') as directory:
    adapter, runtime, game, store = adapter_for(directory)
    adapter.dispatch('save_profile', {'name': 'Clean'}, 'save-clean')
    state = adapter.dispatch('connect', {}, 'connect-1')
    adapter.dispatch('lock_vital', {'vital': 'health', 'locked': True, 'target': state['target']}, 'lock-health')
    adapter.dispatch('disconnect', {}, 'detach')
    adapter.dispatch('load_profile', {'name': 'Clean'}, 'load-clean')
    state = adapter.dispatch('connect', {}, 'connect-2')
    assert runtime.replies[-1]['healthLocked'] is False, 'resident kept a health lock the Profile removed'
    assert_projection_matches_resident(state, runtime.replies[-1], 'offline profile + reconnect')

# A same-process Lua reset replays every durable desired value, not only the
# boolean features: fixed locks and the boon rarity target come back too.
with tempfile.TemporaryDirectory(prefix='hades-desired-') as directory:
    adapter, runtime, game, store = adapter_for(directory)
    adapter.dispatch('set_feature', {'feature': 'boonRarityEnabled', 'value': True}, 'rarity-on')
    adapter.dispatch('set_boon_rarity', {'target': 'Epic'}, 'rarity-epic')
    state = adapter.dispatch('connect', {}, 'connect')
    state = adapter.dispatch('lock_resource', {'resource': 'Money', 'locked': True, 'target': state['target']}, 'lock')
    assert state['moneyLock'] == 100
    game.lua_reset()
    state = adapter.dispatch('status', {}, 'status-after-reset')
    resident = runtime.replies[-1]
    assert resident['boonRarityTarget'] == 'Epic', 'Lua reset dropped the rarity target'
    assert resident['moneyLocked'] is True and resident['moneyLock'] == 100, 'Lua reset dropped the gold lock'
    assert_projection_matches_resident(state, resident, 'after Lua reset')
    game.native('SpendMoney(60)')
    state = adapter.dispatch('status', {}, 'status-after-spend')
    assert state['money'] == 100, 'replayed gold lock did not hold the native value'
    # An exact edit while locked updates the lock target instead of failing as a
    # protocol error and restoring the stale value.
    edited = adapter.dispatch('set_value', {'field': 'money', 'value': 44, 'target': state['target']}, 'edit')
    assert edited['money'] == 44 and edited['moneyLock'] == 44
    assert store.load()['moneyLock'] == 44

# A durable lock reaches a newly started game, whose resident has none.
with tempfile.TemporaryDirectory(prefix='hades-desired-') as directory:
    adapter, runtime, game, store = adapter_for(directory)
    state = adapter.dispatch('connect', {}, 'connect-first-game')
    adapter.dispatch('lock_resource', {'resource': 'Money', 'locked': True, 'target': state['target']}, 'lock')
    adapter.dispatch('disconnect', {}, 'detach')
    restarted, runtime, game, _ = adapter_for(directory)
    state = restarted.dispatch('connect', {}, 'connect-restarted-game')
    assert runtime.replies[-1]['moneyLocked'] is True and runtime.replies[-1]['moneyLock'] == 100
    assert_projection_matches_resident(state, runtime.replies[-1], 'restarted game')

# A fresh backend presents the saved desired document, and a detached edit
# merges into it instead of replacing it with defaults plus one change.
with tempfile.TemporaryDirectory(prefix='hades-desired-') as directory:
    first, _, _, store = adapter_for(directory)
    first.dispatch('set_feature', {'feature': 'invincibility', 'value': True}, 'inv')
    first.dispatch('set_feature', {'feature': 'gameSpeed', 'value': 2.0}, 'speed')
    first.dispatch('set_boon_rarity', {'target': 'Epic'}, 'epic')
    saved = store.load()
    fresh, _, _, store = adapter_for(directory)
    state = fresh.dispatch('status', {}, 'fresh-status')
    assert state['features']['invincibility'] is True
    assert state['features']['gameSpeed']['desired'] == 2.0
    assert state['boonRarityTarget'] == 'Epic'
    fresh.dispatch('set_feature', {'feature': 'fullHealth', 'value': True}, 'detached-edit')
    assert store.load() == {**saved, 'fullHealth': True}, 'detached edit discarded saved desired state'

# An unreadable document is never overwritten by a merging edit; a deliberate
# whole-document replacement remains available.
with tempfile.TemporaryDirectory(prefix='hades-desired-') as directory:
    damaged = Path(directory) / 'preferences.json'
    damaged.write_text('{"schemaVersion": 1, "features": ')
    adapter, _, _, store = adapter_for(directory)
    try:
        adapter.dispatch('set_feature', {'feature': 'fullHealth', 'value': True}, 'merge-into-unknown')
    except AdapterError as error:
        assert error.code == 'preferences_failed'
    else:
        raise AssertionError('a merging edit overwrote an unreadable desired-state document')
    assert damaged.read_text() == '{"schemaVersion": 1, "features": '
    adapter.dispatch('disable_all', {}, 'deliberate-reset')
    assert store.load() == DEFAULT_PREFERENCES
    adapter.dispatch('set_feature', {'feature': 'fullHealth', 'value': True}, 'after-reset')
    assert store.load()['fullHealth'] is True

# A manual detach keeps desired features visible in its own reply.
with tempfile.TemporaryDirectory(prefix='hades-desired-') as directory:
    adapter, _, _, _ = adapter_for(directory)
    adapter.dispatch('set_feature', {'feature': 'invincibility', 'value': True}, 'inv')
    adapter.dispatch('connect', {}, 'connect')
    detached = adapter.dispatch('disconnect', {}, 'detach')
    assert detached['connected'] is False
    assert detached['features']['invincibility'] is True, 'detach reply dropped desired features'

print('hades_desired_state_replay_ok')
