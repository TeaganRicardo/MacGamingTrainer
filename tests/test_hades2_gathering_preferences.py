"""Gathering desired intent survives persistence; generation never replays."""
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
from games.hades2.desired_reconciliation import DesiredReconciliationOutcome
from games.hades2.persistence import PersistenceError, UnsupportedSchemaVersionError
from games.hades2.preferences import Hades2PreferenceStore, DESIRED_STATE_SCHEMA_VERSION, normalize_persisted_desired
from games.hades2.profile_service import Hades2ProfileService, PROFILE_SCHEMA_VERSION
from hades2_resident_session_fakes import FakeResidentSession, FakeTimeWarpController

FAMILIES = ('flora', 'mining', 'digging', 'shades', 'fishing')
assert DESIRED_STATE_SCHEMA_VERSION == 8
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


class OfflineSession(FakeResidentSession):
    def __init__(self):
        super().__init__(pid=123)
        self.live = False

with tempfile.TemporaryDirectory(prefix='mgt-gathering-preferences-') as temporary:
    base = Path(temporary)
    preparation.DATA = base
    transport = OfflineSession()
    adapter = Hades2Adapter(resident_session=transport, time_warp_controller=FakeTimeWarpController())
    # Host request validation is owned by the command-contract dispatch seam.
    for command, params in (
        ('set_gathering_desired', {'family': 'other', 'probability': 10}),
        ('set_gathering_desired', {'family': [], 'probability': 10}),
        ('set_gathering_desired', {'family': 'flora'}),
        *[('set_gathering_desired', {'family': 'flora', 'probability': x})
          for x in (True, -1, 101, 10**1000, math.nan, math.inf, '50', [], {})],
        *[('generate_gathering', {'family': 'flora', 'scopeToken': x})
          for x in (None, '', True, 1, [], {}, 'x'*129)],
        ('generate_gathering', {'family': 'other', 'scopeToken': 'room'}),
    ):
        try:
            adapter.dispatch(command, params, 'invalid')
        except Exception:
            pass
        else:
            raise AssertionError(
                f'invalid gathering request accepted: {command} {params!r}'
            )

    for family, percentage in valid.items():
        result = adapter.dispatch('set_gathering_desired', {'family': family, 'probability': percentage}, 'desired-'+family)
        assert result['gatheringProbabilities'][family] == percentage
    persisted = json.loads((base/'desired-state.json').read_text())
    assert persisted['schemaVersion'] == 8 and persisted['gatheringProbabilities'] == valid
    assert not {'gatheringTargets', 'scopeToken', 'generate_gathering'} & set(persisted)
    restarted = Hades2Adapter(resident_session=OfflineSession(), time_warp_controller=FakeTimeWarpController())
    assert restarted.preferences['gatheringProbabilities'] == valid and restarted.preference_dirty
    adapter.dispatch('set_gathering_desired', {'family': 'flora', 'probability': None}, 'native')
    wanted = dict(valid); wanted.pop('flora')
    assert adapter.preferences['gatheringProbabilities'] == wanted
    assert adapter.state['gatheringProbabilities'] == wanted
    adapter.state['gatheringTargets'] = {'mining': {'available': True, 'scopeToken': 'ephemeral'}}
    adapter.save_profile('Gathering')
    envelope = json.loads(adapter.profile_service.path('Gathering').read_text())
    assert envelope['schemaVersion'] == 6 and envelope['desiredSchemaVersion'] == 8
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
    def execute(command, params):
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
    def failed_apply(command, params): raise TransportError('lua_error', 'fixture unavailable')
    adapter.execute = failed_apply
    try:
        adapter.dispatch('set_gathering_desired', {'family': 'flora', 'probability': 100}, 'pending')
    except TransportError:
        pass
    assert adapter.preferences['gatheringProbabilities']['flora'] == 100
    assert adapter.preference_dirty is True
    class ConfirmingReconciler:
        def __init__(self):
            self.calls = []
        def reconcile(self, desired, observed, *, force_full=False):
            self.calls.append((copy.deepcopy(desired), copy.deepcopy(observed), force_full))
            return DesiredReconciliationOutcome(reply=None, confirmed=True, mismatches=())

    reconciler = ConfirmingReconciler()
    adapter.desired_reconciler = reconciler
    adapter.state['gatheringProbabilities'] = {}
    adapter._replay_preferences(copy.deepcopy(adapter.state))
    assert len(reconciler.calls) == 1
    assert reconciler.calls[0][0]['gatheringProbabilities'] == valid | {'flora': 100}
    assert adapter.preference_dirty is False

    calls.clear()
    adapter.execute = execute
    preferences = copy.deepcopy(adapter.preferences)
    adapter.dispatch('generate_gathering', {'family': 'mining', 'scopeToken': 'observed-room'}, 'generation-request')
    assert calls == [('generate_gathering', {'family': 'mining', 'scopeToken': 'observed-room', 'requestId': 'generation-request'})]
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

    # Saving a Profile snapshots canonical durable desired state; a stale
    # runtime/public projection cannot overwrite pending gathering intent.
    adapter.state['gatheringProbabilities'] = {}
    adapter.save_profile('Pending Gathering')
    assert adapter.preferences['gatheringProbabilities'] == valid | {'flora': 100}
    saved_pending = json.loads(
        adapter.profile_service.path('Pending Gathering').read_text()
    )
    assert saved_pending['desired']['gatheringProbabilities'] == valid | {'flora': 100}

    future = dict(persisted, schemaVersion=9)
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
    document = json.loads(path.read_text()); document['desiredSchemaVersion'] = 9
    path.write_text(json.dumps(document)); before_bytes = path.read_bytes()
    for action in (lambda: service.load('Future'), lambda: service.save('Future', {})):
        try: action()
        except UnsupportedSchemaVersionError: pass
        else: raise AssertionError('future embedded desired schema was accepted')
    assert path.read_bytes() == before_bytes and not list(path.parent.glob('*.corrupt*'))

print('hades2_gathering_preferences_ok')
