"""Chaos Gate durable intent is independent of native door transactions."""
import copy
import json
import math
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
sys.path.insert(0, str(ROOT / 'tests'))
from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter, TransportError, clear_active, mark_disconnected
from games.hades2.command_validation import validate_command_params
from games.hades2.persistence import PersistenceError, UnsupportedSchemaVersionError
from games.hades2.preferences import Hades2PreferenceStore, DESIRED_STATE_SCHEMA_VERSION, normalize_persisted_desired
from games.hades2.profile_service import Hades2ProfileService, PROFILE_SCHEMA_VERSION
from hades2_resident_session_fakes import FakeResidentSession, FakeTimeWarpController

assert Hades2PreferenceStore.defaults()['chaosGateProbability'] is None
assert DESIRED_STATE_SCHEMA_VERSION == 7 and PROFILE_SCHEMA_VERSION == 6
for value in (None, 0, 100, 32.5):
    assert validate_command_params('set_chaos_gate_desired', {'probability': value}) == {'probability': value}
    assert Hades2PreferenceStore.normalize({'chaosGateProbability': value})['chaosGateProbability'] == value
for value in (True, -1, 101, 10**1000, math.nan, math.inf, '50', [], {}):
    assert Hades2PreferenceStore.normalize({'chaosGateProbability': value})['chaosGateProbability'] is None
    try: validate_command_params('set_chaos_gate_desired', {'probability': value})
    except ValueError: pass
    else: raise AssertionError('invalid probability accepted')
try: validate_command_params('set_chaos_gate_desired', {})
except ValueError: pass
else: raise AssertionError('missing probability silently restored Native')
for version in range(7):
    migrated = normalize_persisted_desired({'chaosGateProbability': 100, 'gatheringProbabilities': {'flora': 25}}, version)
    assert migrated['chaosGateProbability'] is None
    assert migrated['gatheringProbabilities'] == ({'flora': 25} if version >= 6 else {})
assert normalize_persisted_desired({'chaosGateProbability': 0}, 7)['chaosGateProbability'] == 0

class Transport:
    pid = 123
    live = False
    def alive(self): return self.live

with tempfile.TemporaryDirectory(prefix='mgt-chaos-gate-preferences-') as temporary:
    base = Path(temporary)
    preparation.DATA = base
    transport = Transport()
    adapter = Hades2Adapter(transport=transport)
    adapter.dispatch('set_gathering_desired', {'family': 'flora', 'probability': 25}, 'gathering')
    for value in (0, 100, 32.5, None, 80):
        result = adapter.dispatch('set_chaos_gate_desired', {'probability': value}, 'desired')
        assert result['chaosGateProbability'] == value
    persisted = json.loads((base/'desired-state.json').read_text())
    assert persisted['schemaVersion'] == 7 and persisted['chaosGateProbability'] == 80
    assert persisted['gatheringProbabilities'] == {'flora': 25}
    assert not {'ForceSecretDoor', 'ForceNextRoom', 'door', 'scopeToken'} & set(persisted)
    restarted = Hades2Adapter(transport=Transport())
    assert restarted.preferences['chaosGateProbability'] == 80 and restarted.preference_dirty
    adapter.save_profile('Chaos Gate')
    envelope = json.loads(adapter.profile_service.path('Chaos Gate').read_text())
    assert envelope['schemaVersion'] == 6 and envelope['desiredSchemaVersion'] == 7
    assert envelope['desired']['chaosGateProbability'] == 80
    adapter.reset_desired()
    assert adapter.preferences['chaosGateProbability'] is None and adapter.state['chaosGateProbability'] is None
    adapter.load_profile('Chaos Gate')
    assert adapter.preferences['chaosGateProbability'] == 80
    assert adapter.preferences['gatheringProbabilities'] == {'flora': 25}

    calls = []
    original_save = adapter.preference_store.save
    def save(preferences):
        calls.append(('save', preferences['chaosGateProbability']))
        original_save(preferences)
    adapter.preference_store.save = save
    def execute(command, params, **kwargs):
        calls.append((command, copy.deepcopy(params), copy.deepcopy(kwargs)))
        if command == 'set_chaos_gate_probability':
            assert json.loads((base/'desired-state.json').read_text())['chaosGateProbability'] == params['probability']
            adapter.state['chaosGateProbability'] = params['probability']
        for name, values in kwargs.get('batch', []):
            if name == 'set_chaos_gate_probability': adapter.state['chaosGateProbability'] = values['probability']
        return dict(adapter.state)
    adapter.execute = execute
    transport.live = True
    adapter.state.update(status='ready', connected=True)
    adapter.preference_dirty = True
    adapter.dispatch('set_chaos_gate_desired', {'probability': 0}, 'zero')
    assert [call[0] for call in calls] == ['save', 'set_chaos_gate_probability']
    assert calls[-1][1] == {'probability': 0} and adapter.preference_dirty
    calls.clear()
    before = copy.deepcopy(adapter.preferences)
    def fail_save(preferences): raise PersistenceError('fixture disk error')
    adapter.preference_store.save = fail_save
    try: adapter.dispatch('set_chaos_gate_desired', {'probability': 100}, 'failed-save')
    except PersistenceError: pass
    else: raise AssertionError('runtime applied before failed durable write')
    assert adapter.preferences == before and not calls
    adapter.preference_store.save = original_save
    def failed_apply(command, params, **kwargs): raise TransportError('lua_error', 'fixture unavailable')
    adapter.execute = failed_apply
    try: adapter.dispatch('set_chaos_gate_desired', {'probability': 100}, 'pending')
    except TransportError: pass
    assert adapter.preferences['chaosGateProbability'] == 100 and adapter.preference_dirty
    adapter.execute = execute
    adapter.state['chaosGateProbability'] = None
    adapter._replay_preferences()
    batch = calls[-1][2]['batch']
    assert ('set_chaos_gate_probability', {'probability': 100}) in batch
    assert all(name not in ('generate_gathering', 'spawn_reward', 'use_door') for name, _ in batch)
    assert adapter.preference_dirty is False
    adapter.dispatch('set_chaos_gate_desired', {'probability': None}, 'native')
    assert calls[-1][1] == {'probability': None}
    assert adapter.preferences['gatheringProbabilities'] == {'flora': 25}
    observed = {'chaosGateProbability': 50}
    mark_disconnected(observed)
    clear_active(observed, preserve_desired=True)
    assert observed['chaosGateProbability'] == 50
    clear_active(observed)
    assert observed['chaosGateProbability'] is None
    adapter.dispatch('set_chaos_gate_desired', {'probability': 60}, 'capture')
    adapter._capture_runtime_preferences({'status': 'ready'})
    assert adapter.preferences['chaosGateProbability'] == 60
    adapter._capture_runtime_preferences({'chaosGateProbability': None})
    assert adapter.preferences['chaosGateProbability'] is None

    future_path = base/'future-desired.json'
    future_path.write_text(json.dumps(dict(persisted, schemaVersion=8)))
    before_bytes = future_path.read_bytes()
    store = Hades2PreferenceStore(future_path)
    defaults, loaded = store.load()
    assert not loaded and defaults['chaosGateProbability'] is None
    try: store.save(defaults)
    except UnsupportedSchemaVersionError: pass
    else: raise AssertionError('future desired schema overwritten')
    assert future_path.read_bytes() == before_bytes
    service = Hades2ProfileService(base/'future-profiles')
    service.save('Future', {'chaosGateProbability': 100})
    path = service.path('Future')
    document = json.loads(path.read_text()); document['desiredSchemaVersion'] = 8
    path.write_text(json.dumps(document)); before_bytes = path.read_bytes()
    for action in (lambda: service.load('Future'), lambda: service.save('Future', {})):
        try: action()
        except UnsupportedSchemaVersionError: pass
        else: raise AssertionError('future embedded desired schema accepted')
    assert path.read_bytes() == before_bytes and not list(path.parent.glob('*.corrupt*'))

    # Exercise the real Adapter -> resident-session boundary as well: a
    # prepersisted native setter must not save a second time after its reply.
    session_calls = []
    def session_handler(session, record):
        session_calls.append(copy.deepcopy(record))
        assert record['kind'] == 'mutate'
        assert record['command'] == 'set_chaos_gate_probability'
        assert record['params'] == {'probability': 0}
        assert json.loads((base/'desired-state.json').read_text())['chaosGateProbability'] == 0
        return {'status': 'ready', 'scene': 'run', 'chaosGateProbability': 0}

    reply_session = FakeResidentSession(
        {'status': 'ready', 'scene': 'run', 'chaosGateProbability': None},
        handler=session_handler,
        pid=123,
    )
    real = Hades2Adapter(
        resident_session=reply_session,
        time_warp_controller=FakeTimeWarpController(),
    )
    real.state.update(status='ready', connected=True)
    real.preference_initialized = True
    writes = []
    real_save = real.preference_store.save
    def count_save(values):
        writes.append(copy.deepcopy(values))
        real_save(values)
    real.preference_store.save = count_save
    result = real.dispatch('set_chaos_gate_desired', {'probability': 0}, 'real-boundary')
    assert result['chaosGateProbability'] == 0 and len(writes) == 1
    assert len(session_calls) == 1


print('hades2_chaos_gate_preferences_ok')
