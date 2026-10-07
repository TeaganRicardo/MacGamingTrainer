import json
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'Backend'))

from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter
from games.hades2.diagnostics import build_diagnostics
from games.hades2.preferences import Hades2PreferenceStore
from hades2_resident_session_fakes import FakeTimeWarpController


# Source-boundary evidence for the real resident contract: status enters the
# same dispatch path as mutations; normal status synchronizes, but an uncertain
# terminal action returns observation without restoring desired runtime hooks.
lua = (root/'Backend/games/hades2/runtime/hades.lua').read_text(encoding='utf-8')
dispatch = lua[lua.index('  function M.dispatch(command, params)'):]
sync_guard = '    elseif preferenceReplayDepth == 0 then synchronize() end'
assert dispatch.index(sync_guard) < dispatch.index(
    '    if command == "status" then return state(params.includeCatalogs) end',
    dispatch.index(sync_guard),
)


class FakeTransport:
    def __init__(self):
        self.pid = 7331
        self.last_duration = 0.02
        self.calls = 0
    def alive(self): return True
    def execute(self, source):
        self.calls += 1
        return json.dumps({
            'status':'ready',
            'scene':'run',
            'capabilities':{},
            'desiredFeatures':{'invincibility':False},
            'activeFeatures':{'invincibility':False},
            'nextRoomReward':None,
        })
    def detach(self): pass
    def close(self): pass


base = Path(tempfile.mkdtemp(prefix='mgt-diagnostics-readonly-v0190-'))
preparation.DATA = base/'initialized'
preparation.DATA.mkdir(parents=True)
pref_path = preparation.DATA/'desired-state.json'
store = Hades2PreferenceStore(pref_path)
prefs = store.defaults()
prefs['invincibility'] = True
prefs['nextRoomReward'] = 'WeaponUpgrade'
store.save(prefs)
file_before = pref_path.read_bytes()

transport = FakeTransport()
adapter = Hades2Adapter(transport=transport, time_warp_controller=FakeTimeWarpController())
assert adapter.preference_dirty is True
preferences_before = json.loads(json.dumps(adapter.preferences))

# Runtime observation refreshes observable state, but it must not replay
# dirty desired state or persist/capture runtime state.
adapter.observe_runtime()
assert transport.calls == 1
assert adapter.state['desiredFeatures']['invincibility'] is False
assert adapter.preference_dirty is True
assert adapter.preferences == preferences_before
assert pref_path.read_bytes() == file_before

# Even when desired state is otherwise clean, diagnostics must not consume the
# persisted one-shot next-room request merely because runtime status reports it
# absent.
adapter.preference_dirty = False
adapter.observe_runtime()
assert transport.calls == 2
assert adapter.preferences['nextRoomReward'] == 'WeaponUpgrade'
assert pref_path.read_bytes() == file_before

# With no durable desired-state at all, a diagnostics/status read must not adopt
# the live Lua configuration and create a new desired-state file.
preparation.DATA = base/'uninitialized'
preparation.DATA.mkdir(parents=True)
transport2 = FakeTransport()
adapter2 = Hades2Adapter(transport=transport2, time_warp_controller=FakeTimeWarpController())
assert adapter2.preference_initialized is False
adapter2.observe_runtime()
assert adapter2.preference_initialized is False
assert not (preparation.DATA/'desired-state.json').exists()

# Runtime observation is a dedicated status-only API rather than a flag that
# mutation callers can opt into.
try:
    adapter2.execute('set_feature', {'feature':'invincibility','value':True}, read_only=True)
except TypeError:
    pass
else:
    raise AssertionError('execute still exposes the ambiguous read_only flag')
assert transport2.calls == 1

print('diagnostics_runtime_observation_v0190_ok')
