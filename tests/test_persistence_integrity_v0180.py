from pathlib import Path
import json
import logging
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'Backend'))

from core.adapter import GameAdapter, GameAdapterContext
from core.protocol import JsonlRequestRouter
from games.hades2 import persistence, preparation
from games.hades2.adapter import Hades2Adapter
from games.hades2.persistence import PersistenceError
from games.hades2.preferences import Hades2PreferenceStore
from games.hades2.profile_service import Hades2ProfileService


base = Path(tempfile.mkdtemp(prefix='mgt-persistence-v0180-'))

# Successful preference writes use the shared atomic path and leave no staging
# debris behind.
pref_path = base/'desired-state.json'
store = Hades2PreferenceStore(pref_path)
prefs = store.defaults(); prefs['godMode'] = True
store.save(prefs)
assert json.loads(pref_path.read_text(encoding='utf-8'))['godMode'] is True
assert list(base.glob('.desired-state.json.*.tmp')) == []

# A replace failure must preserve the previous durable file, clean the staged
# file and surface a typed error rather than pretending persistence succeeded.
original_replace = persistence.os.replace
try:
    logging.disable(logging.CRITICAL)
    def fail_replace(source, destination):
        raise OSError('simulated replace failure')
    persistence.os.replace = fail_replace
    changed = dict(prefs); changed['godMode'] = False
    try:
        store.save(changed)
    except PersistenceError as error:
        assert error.code == 'persistence_failed'
    else:
        raise AssertionError('desired-state write failure was swallowed')
finally:
    logging.disable(logging.NOTSET)
    persistence.os.replace = original_replace
assert json.loads(pref_path.read_text(encoding='utf-8'))['godMode'] is True
assert list(base.glob('.desired-state.json.*.tmp')) == []

# Profile writes use the same durable primitive.  A failed replacement must not
# destroy the previous profile either.
profiles = Hades2ProfileService(base/'profiles')
profiles.save('stable', prefs, {'godMode': 1})
profile_path = profiles.path('stable')
profile_before = profile_path.read_bytes()
try:
    persistence.os.replace = fail_replace
    try:
        profiles.save('stable', changed, {'godMode': 1})
    except PersistenceError:
        pass
    else:
        raise AssertionError('profile write failure was swallowed')
finally:
    persistence.os.replace = original_replace
assert profile_path.read_bytes() == profile_before
assert list((base/'profiles').glob('.*.tmp')) == []

# Desired-only mutations persist before becoming the in-memory owner.  If disk
# persistence fails, no transport mutation may be attempted and the old desired
# state remains authoritative in memory.
preparation.DATA = base/'adapter-data'

class FakeTransport:
    def __init__(self):
        self.pid = 123
        self.last_duration = 0.0
    def alive(self): return True
    def detach(self): pass
    def close(self): pass

adapter = Hades2Adapter(transport=FakeTransport())
adapter.state['capabilities'] = dict(adapter.state.get('capabilities', {}), setFeature=True)
transport_calls = []
adapter.execute = lambda *args, **kwargs: transport_calls.append((args, kwargs)) or dict(adapter.state)
old_preferences = dict(adapter.preferences)
old_state_value = adapter.state['godMode']
adapter.preference_store.save = lambda preferences: (_ for _ in ()).throw(PersistenceError('simulated'))
try:
    adapter.set_desired('godMode', True)
except PersistenceError:
    pass
else:
    raise AssertionError('set_desired hid a persistence failure')
assert adapter.preferences == old_preferences
assert adapter.state['godMode'] == old_state_value
assert transport_calls == []

# The generic router must preserve typed module error codes so the Swift client
# can distinguish persistence failure from a generic operation failure.
class PersistenceFailAdapter(GameAdapter):
    def __init__(self):
        super().__init__(GameAdapterContext(
            game_id='fake', display_name='Fake', module_protocol_version=1,
            module_dir=base, public_metadata={},
        ))
        self.state = {'connected': False}
    def dispatch(self, command, params, request_id):
        raise PersistenceError('cannot save')
    def close(self): pass

logging.disable(logging.CRITICAL)
try:
    reply = JsonlRequestRouter(PersistenceFailAdapter()).handle({'id':'p1','command':'write','params':{}})
finally:
    logging.disable(logging.NOTSET)
assert reply['ok'] is False
assert reply['error']['code'] == 'persistence_failed'

print('persistence_integrity_v0180_ok')
