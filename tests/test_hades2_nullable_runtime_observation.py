import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from games.hades2 import preparation, resident_session
from games.hades2.adapter import Hades2Adapter
from games.hades2.resident_session import Hades2ResidentSession
from hades2_lua_observation_fixture import LuaObservationTransport
from hades2_resident_session_fakes import FakeTimeWarpController

with tempfile.TemporaryDirectory(prefix='mgt-nullable-observation-') as temporary, \
     patch.object(resident_session, 'localize_catalog', side_effect=lambda payload: payload):
    preparation.DATA = Path(temporary)
    transport = LuaObservationTransport()
    try:
        adapter = Hades2Adapter(resident_session=Hades2ResidentSession(transport, bootstrap=''),
                                time_warp_controller=FakeTimeWarpController())
        transport.evaluate("CurrentRun.Hero.Traits = { { Slot = 'Spell', PreEquipWeapons = { 'HexWeapon' } } }")
        first = adapter.observe_runtime()
        assert first['spellChargeCost'] == 20
        catalogs = (first['boons'], first['rewards'])
        transport.evaluate('CurrentRun.Hero.Traits = {}')
        raw = adapter.runtime.observe_status({'includeCatalogs': False}).payload
        assert 'spellChargeCost' in raw and raw['spellChargeCost'] is None, 'absent Hex omitted its nullable cost'
        assert 'boons' not in raw and 'rewards' not in raw
        assert 'nextRoomReward' in raw and raw['nextRoomReward'] is None
        assert 'lastAction' in raw and raw['lastAction'] is None
        assert 'currentRunTraitsReason' in raw
        adapter._merge_resident_reply(adapter.runtime.observe_status({'includeCatalogs': False}))
        assert adapter.state['spellChargeCost'] is None
        assert (adapter.state['boons'], adapter.state['rewards']) == catalogs
        adapter.dispatch('list_profiles', {}, 'profiles')
        assert adapter.state['spellChargeCost'] is None and adapter.state['scene'] == 'run'
    finally:
        transport.close()

print('hades2_nullable_runtime_observation_ok')
