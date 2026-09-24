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
            'desiredFeatures':{'godMode':False},
            'activeFeatures':{'godMode':False},
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
prefs['godMode'] = True
prefs['nextRoomReward'] = 'WeaponUpgrade'
store.save(prefs)
file_before = pref_path.read_bytes()

transport = FakeTransport()
adapter = Hades2Adapter(transport=transport)
assert adapter.preference_dirty is True
preferences_before = json.loads(json.dumps(adapter.preferences))

# A read-only status is allowed to refresh observable state, but it must not
# replay dirty desired state or persist/capture runtime state.
adapter.execute('status', {}, read_only=True)
assert transport.calls == 1
assert adapter.preference_dirty is True
assert adapter.preferences == preferences_before
assert pref_path.read_bytes() == file_before

# Even when desired state is otherwise clean, diagnostics must not consume the
# persisted one-shot next-room request merely because runtime status reports it
# absent.
adapter.preference_dirty = False
adapter.execute('status', {}, read_only=True)
assert transport.calls == 2
assert adapter.preferences['nextRoomReward'] == 'WeaponUpgrade'
assert pref_path.read_bytes() == file_before

# With no durable desired-state at all, a diagnostics/status read must not adopt
# the live Lua configuration and create a new desired-state file.
preparation.DATA = base/'uninitialized'
preparation.DATA.mkdir(parents=True)
transport2 = FakeTransport()
adapter2 = Hades2Adapter(transport=transport2)
assert adapter2.preference_initialized is False
adapter2.execute('status', {}, read_only=True)
assert adapter2.preference_initialized is False
assert not (preparation.DATA/'desired-state.json').exists()

# The read-only execution mode is deliberately narrow so a future caller cannot
# accidentally use it to bypass persistence semantics for a mutation command.
try:
    adapter2.execute('set_feature', {'feature':'godMode','value':True}, read_only=True)
except ValueError as error:
    assert 'read_only' in str(error)
else:
    raise AssertionError('read_only mutation command unexpectedly accepted')
assert transport2.calls == 1

# Diagnostics itself must request the read-only path. A small probe isolates
# this contract from the real platform checks performed by build_diagnostics.
class AliveTransport:
    def alive(self): return True

class DiagnosticsProbe:
    module_protocol_version = 5
    transport = AliveTransport()
    state = {}
    def __init__(self): self.calls = []
    def execute(self, command, params, **kwargs):
        self.calls.append((command, params, kwargs))
        return {}
    def list_profiles(self): return []

probe = DiagnosticsProbe()
build_diagnostics(probe)
assert probe.calls == [('status', {}, {'read_only': True})]

print('diagnostics_read_only_v0190_ok')
