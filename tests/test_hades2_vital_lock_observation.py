import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from games.hades2 import preparation, resident_session
from games.hades2.adapter import Hades2Adapter
from games.hades2.preferences import Hades2PreferenceStore
from games.hades2.resident_session import Hades2ResidentSession
from hades2_lua_observation_fixture import LuaObservationTransport
from hades2_resident_session_fakes import FakeTimeWarpController

with tempfile.TemporaryDirectory(prefix='mgt-vital-lock-observation-') as temporary, \
     patch.object(resident_session, 'localize_catalog', side_effect=lambda payload: payload):
    preparation.DATA = Path(temporary)
    transport = LuaObservationTransport()
    try:
        adapter = Hades2Adapter(resident_session=Hades2ResidentSession(transport, bootstrap=''),
                                time_warp_controller=FakeTimeWarpController())
        adapter.execute('status', {})
        adapter.execute('lock_vital', {'vital': 'health', 'locked': True})
        state = adapter.execute('set_vital', {'vital': 'health', 'field': 'current', 'value': 200})
        assert state['health'] == 100, 'requested 200 overwrote native clamped health 100'
        assert adapter.preferences['vitalLocks']['health'] == {'current': 100, 'max': 100}
        state = adapter.execute('set_vital', {'vital': 'health', 'field': 'max', 'value': 40})
        assert state['health'] == 40 and state['maxHealth'] == 40
        assert adapter.preferences['vitalLocks']['health'] == {'current': 40, 'max': 40}
        transport.evaluate('UpdateTimers(0)')
        assert adapter.observe_runtime()['health'] == 40

        transport.evaluate('CurrentRun.Hero.Mana = 30; CurrentRun.Hero.ReservedMana = 20')
        adapter.execute('lock_vital', {'vital': 'mana', 'locked': True})
        state = adapter.execute('set_vital', {'vital': 'mana', 'field': 'current', 'value': 100})
        assert state['mana'] == 30 and state['availableMana'] == 30
        assert adapter.preferences['vitalLocks']['mana'] == {'current': 30, 'max': 50}
        state = adapter.execute('set_vital', {'vital': 'mana', 'field': 'max', 'value': 25})
        assert state['mana'] == 5 and state['availableMana'] == 5
        assert adapter.preferences['vitalLocks']['mana'] == {'current': 5, 'max': 25}

        # Changing the native reservation can reduce an attainable lock. Replay
        # confirms and persists the normalized result from the actual batch.
        transport.evaluate('CurrentRun.Hero.ReservedMana = 24; UpdateTimers(0)')
        adapter.preference_dirty = True
        state = adapter.execute('status', {})
        assert state['mana'] == 1 and not adapter.preference_dirty
        assert adapter.preferences['vitalLocks']['mana'] == {'current': 1, 'max': 25}

        adapter.disconnect()
        adapter.scan = lambda: adapter.state.update(pid=4242)
        adapter.connect()
        assert not adapter.preference_dirty
        persisted, initialized = adapter.preference_store.load()
        assert initialized and persisted['vitalLocks'] == adapter.preferences['vitalLocks']
        adapter.execute('lock_vital', {'vital': 'health', 'locked': False})
        assert 'health' not in adapter.preferences['vitalLocks']
        adapter.preferences['vitalLocks']['health'] = {'current': 30, 'max': 60}
        adapter.preference_dirty = True
        adapter.preference_store.save(adapter.preferences)
        state = adapter.execute('set_vital', {'vital': 'health', 'field': 'current', 'value': 200})
        assert state['health'] == 40
        assert adapter.runtime.observe_status().payload['healthLocked'] is False
        assert adapter.preferences['vitalLocks']['health'] == {'current': 40, 'max': 60}
        adapter.execute('status', {})
        assert not adapter.preference_dirty
        assert adapter.preferences['vitalLocks']['health'] == {'current': 40, 'max': 60}
    finally:
        transport.close()

normalized = Hades2PreferenceStore.normalize({'vitalLocks': {
    'health': {'current': 200, 'max': 100}, 'mana': {'current': 80, 'max': 50},
}})
assert normalized['vitalLocks'] == {
    'health': {'current': 100, 'max': 100}, 'mana': {'current': 50, 'max': 50},
}
print('hades2_vital_lock_observation_ok')
