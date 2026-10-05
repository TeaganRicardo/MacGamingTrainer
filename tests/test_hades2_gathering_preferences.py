"""Gathering desired intent survives persistence; generation never replays."""
import copy
import json
import math
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter, TransportError, clear_active, mark_disconnected
from games.hades2.command_validation import validate_command_params
from games.hades2.persistence import PersistenceError, UnsupportedSchemaVersionError
from games.hades2.preferences import Hades2PreferenceStore, DESIRED_STATE_SCHEMA_VERSION, normalize_persisted_desired
from games.hades2.profile_service import Hades2ProfileService, PROFILE_SCHEMA_VERSION

FAMILIES = ('flora', 'mining', 'digging', 'shades', 'fishing')
assert DESIRED_STATE_SCHEMA_VERSION == 7
assert PROFILE_SCHEMA_VERSION == 6
assert Hades2PreferenceStore.defaults()['gatheringProbabilities'] == {}
valid = dict(zip(FAMILIES, (0, 100, 32.5, 1, 99)))
assert Hades2PreferenceStore.normalize({'gatheringProbabilities': valid})['gatheringProbabilities'] == valid
for invalid in (None, [], 'all'):
    assert Hades2PreferenceStore.normalize({'gatheringProbabilities': invalid})['gatheringProbabilities'] == {}
for invalid in (True, -1, 101, 10**1000, math.nan, math.inf, '50', None, [], {}):
    assert Hades2PreferenceStore.normalize({'gatheringProbabilities': {'flora': invalid, 'mining': 100}})['gatheringProbabilities'] == {'mining': 100}
assert Hades2PreferenceStore.normalize({'gatheringProbabilities': {'unknown': 100}})['gatheringProbabilities'] == {}
for version in range(6):
    migrated = normalize_persisted_desired({'gatheringProbabilities': valid}, version)
    assert migrated['gatheringProbabilities'] == {}, 'older schemas must migrate to Native'
assert normalize_persisted_desired({'gatheringProbabilities': valid}, 6)['gatheringProbabilities'] == valid

for family in FAMILIES:
    for probability in (None, 0, 100, 37.5):
        assert validate_command_params('set_gathering_desired', {'family': family, 'probability': probability}) == {'family': family, 'probability': probability}
    assert validate_command_params('generate_gathering', {'family': family, 'scopeToken': 'observed-room'}) == {'family': family, 'scopeToken': 'observed-room'}
for command, params in (
    ('set_gathering_desired', {'family': 'other', 'probability': 10}),
    ('set_gathering_desired', {'family': [], 'probability': 10}),
    ('set_gathering_desired', {'family': 'flora'}),
    *[('set_gathering_desired', {'family': 'flora', 'probability': x}) for x in (True, -1, 101, 10**1000, math.nan, math.inf, '50', [], {})],
    *[('generate_gathering', {'family': 'flora', 'scopeToken': x}) for x in (None, '', True, 1, [], {}, 'x'*129)],
    ('generate_gathering', {'family': 'other', 'scopeToken': 'room'}),
):
    try:
        validate_command_params(command, params)
    except ValueError:
        pass
    else:
        raise AssertionError(f'invalid gathering request accepted: {command} {params!r}')

class Transport:
    pid = 123
    def __init__(self):
        self.live = False
    def alive(self): return self.live

with tempfile.TemporaryDirectory(prefix='mgt-gathering-preferences-') as temporary:
    base = Path(temporary)
    preparation.DATA = base
    transport = Transport()
    adapter = Hades2Adapter(transport=transport)
    for family, percentage in valid.items():
        result = adapter.dispatch('set_gathering_desired', {'family': family, 'probability': percentage}, 'desired-'+family)
        assert result['gatheringProbabilities'][family] == percentage
    persisted = json.loads((base/'desired-state.json').read_text())
    assert persisted['schemaVersion'] == 7 and persisted['gatheringProbabilities'] == valid
    assert not {'gatheringTargets', 'scopeToken', 'generate_gathering'} & set(persisted)
    restarted = Hades2Adapter(transport=Transport())
    assert restarted.preferences['gatheringProbabilities'] == valid and restarted.preference_dirty
    adapter.dispatch('set_gathering_desired', {'family': 'flora', 'probability': None}, 'native')
    wanted = dict(valid); wanted.pop('flora')
    assert adapter.preferences['gatheringProbabilities'] == wanted
    assert adapter.state['gatheringProbabilities'] == wanted
    adapter.state['gatheringTargets'] = {'mining': {'available': True, 'scopeToken': 'ephemeral'}}
    adapter.save_profile('Gathering')
    envelope = json.loads(adapter.profile_service.path('Gathering').read_text())
    assert envelope['schemaVersion'] == 6 and envelope['desiredSchemaVersion'] == 7
    assert envelope['desired']['gatheringProbabilities'] == wanted
    assert 'gatheringTargets' not in envelope['desired'] and 'scopeToken' not in envelope['desired']
    adapter.reset_desired()
    assert adapter.preferences['gatheringProbabilities'] == {} and adapter.state['gatheringProbabilities'] == {}
    adapter.load_profile('Gathering')
    assert adapter.preferences['gatheringProbabilities'] == wanted

    # Durable commit must happen before a native setter and exactly once.
    calls = []
    transport.live = True
    adapter.state.update(status='ready', connected=True)
    adapter.preference_dirty = True  # another pending desired action remains pending
    original_save = adapter.preference_store.save
    def save(preferences):
        calls.append(('save', copy.deepcopy(preferences['gatheringProbabilities'])))
        return original_save(preferences)
    adapter.preference_store.save = save
    def execute(command, params, **kwargs):
        calls.append((command, copy.deepcopy(params)))
        if command == 'set_gathering_probabilities':
            assert json.loads((base/'desired-state.json').read_text())['gatheringProbabilities'] == params['probabilities']
            adapter.state['gatheringProbabilities'] = dict(params['probabilities'])
        return dict(adapter.state)
    adapter.execute = execute
    adapter.dispatch('set_gathering_desired', {'family': 'flora', 'probability': 0}, 'zero')
    assert [call[0] for call in calls] == ['save', 'set_gathering_probabilities']
    assert calls[-1][1]['probabilities'] == valid | {'flora': 0}
    assert adapter.preference_dirty is True
    before = copy.deepcopy(adapter.preferences)
    calls.clear()
    def fail_save(preferences): raise PersistenceError('fixture disk error')
    adapter.preference_store.save = fail_save
    try:
        adapter.dispatch('set_gathering_desired', {'family': 'flora', 'probability': 100}, 'failed-save')
    except PersistenceError:
        pass
    else:
        raise AssertionError('failed durable write allowed runtime application')
    assert adapter.preferences == before and calls == []
    adapter.preference_store.save = original_save

    # Runtime application failure retains desired state for an explicit later
    # reconciliation; it never turns a generation action into a desired field.
    def failed_apply(command, params, **kwargs): raise TransportError('lua_error', 'fixture unavailable')
    adapter.execute = failed_apply
    try:
        adapter.dispatch('set_gathering_desired', {'family': 'flora', 'probability': 100}, 'pending')
    except TransportError:
        pass
    assert adapter.preferences['gatheringProbabilities']['flora'] == 100
    assert adapter.preference_dirty is True
    calls.clear()
    def replay_execute(command, params, **kwargs):
        calls.append((command, copy.deepcopy(params), copy.deepcopy(kwargs)))
        for name, values in kwargs.get('batch', []):
            if name == 'set_gathering_probabilities': adapter.state['gatheringProbabilities'] = dict(values['probabilities'])
        return dict(adapter.state)
    adapter.execute = replay_execute
    adapter.state['gatheringProbabilities'] = {}
    adapter._replay_preferences()
    batch = calls[0][2]['batch']
    assert ('set_gathering_probabilities', {'probabilities': valid | {'flora': 100}}) in batch
    assert all(name != 'generate_gathering' for name, _ in batch)
    assert adapter.preference_dirty is False
    calls.clear()
    preferences = copy.deepcopy(adapter.preferences)
    adapter.dispatch('generate_gathering', {'family': 'mining', 'scopeToken': 'observed-room'}, 'generation-request')
    assert calls == [('generate_gathering', {'family': 'mining', 'scopeToken': 'observed-room', 'requestId': 'generation-request'}, {})]
    assert adapter.preferences == preferences

    # Scene/transport invalidation clears ephemeral targets without erasing
    # safely accepted durable probability intent.
    observed = {'gatheringProbabilities': valid, 'gatheringTargets': {'flora': {'available': True, 'scopeToken': 'old-room'}}}
    mark_disconnected(observed)
    assert observed['gatheringTargets'] == {} and observed['gatheringProbabilities'] == valid
    observed['gatheringTargets'] = {'flora': {'available': True, 'scopeToken': 'other-old-room'}}
    clear_active(observed, preserve_desired=True)
    assert observed['gatheringTargets'] == {} and observed['gatheringProbabilities'] == valid
    clear_active(observed)
    assert observed['gatheringProbabilities'] == {}

    # An older peer/sparse snapshot cannot silently clear accepted new intent.
    adapter._capture_runtime_preferences({'status': 'ready'})
    assert adapter.preferences['gatheringProbabilities'] == valid | {'flora': 100}
    adapter._capture_runtime_preferences({'gatheringProbabilities': {}})
    assert adapter.preferences['gatheringProbabilities'] == {}

    future = dict(persisted, schemaVersion=8)
    future_path = base/'future-desired.json'
    future_path.write_text(json.dumps(future))
    before_bytes = future_path.read_bytes()
    store = Hades2PreferenceStore(future_path)
    defaults, loaded = store.load()
    assert not loaded and defaults['gatheringProbabilities'] == {}
    try: store.save(defaults)
    except UnsupportedSchemaVersionError: pass
    else: raise AssertionError('future desired schema was overwritten')
    assert future_path.read_bytes() == before_bytes
    service = Hades2ProfileService(base/'future-profiles')
    service.save('Future', {'gatheringProbabilities': valid})
    path = service.path('Future')
    document = json.loads(path.read_text()); document['desiredSchemaVersion'] = 8
    path.write_text(json.dumps(document)); before_bytes = path.read_bytes()
    for action in (lambda: service.load('Future'), lambda: service.save('Future', {})):
        try: action()
        except UnsupportedSchemaVersionError: pass
        else: raise AssertionError('future embedded desired schema was accepted')
    assert path.read_bytes() == before_bytes and not list(path.parent.glob('*.corrupt*'))

print('hades2_gathering_preferences_ok')
