"""A durable Disable All stays pending until the resident is observed to match it.

Teardown persists default desired state before crossing the Lua boundary. If
the resident call then never runs (a boon menu that does not close in time
returns `waiting`), the game still holds every feature and lock, so the next
status must reconcile instead of presenting the reset as already applied.
"""
import logging
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
sys.path.insert(0, str(ROOT / 'tests'))
logging.disable(logging.CRITICAL)

from core.adapter import AdapterError  # noqa: E402
from games.hades2 import preparation  # noqa: E402
from games.hades2.adapter import Hades2Adapter  # noqa: E402
from hades2_resident_session_fakes import FakeResidentSession, FakeTimeWarpController  # noqa: E402

CAPABILITIES = {name: True for name in (
    'setFeature', 'setHealth', 'setMana', 'setArmor', 'setResource', 'setRerolls',
    'setSpellCharge', 'setStats', 'setElements',
)}
STILL_ENABLED = {
    'status': 'ready', 'scene': 'run', 'capabilities': CAPABILITIES, 'statAvailable': {},
    'desiredFeatures': {'infiniteAmmo': True}, 'activeFeatures': {'infiniteAmmo': True},
    'dormantFeatures': {}, 'featureErrors': {}, 'stats': {}, 'resources': [], 'elements': [],
    'health': 40, 'maxHealth': 100, 'healthLocked': True, 'money': 500, 'moneyLocked': True,
    'residentDesiredLocks': {
        'statLocks': {}, 'vitalLocks': {'health': {'current': 40, 'max': 100}},
        'resourceLocks': {'Money': 500}, 'elementLocks': {}, 'rerollsLock': None,
    },
}


def teardown_waits(session, record):
    if record['kind'] == 'mutate' and record['command'] == 'disable_all':
        return AdapterError('waiting', '游戏内祝福菜单未能及时关闭，修改尚未执行。')
    return None


with tempfile.TemporaryDirectory(prefix='hades2-teardown-') as directory:
    preparation.DATA = Path(directory)
    resident = FakeResidentSession(payload=STILL_ENABLED, handler=teardown_waits)
    adapter = Hades2Adapter(resident_session=resident, time_warp_controller=FakeTimeWarpController())
    adapter.preferences = adapter._default_preferences()
    adapter.preferences.update(
        infiniteAmmo=True, vitalLocks={'health': {'current': 40, 'max': 100}}, resourceLocks={'Money': 500},
    )
    adapter.preference_initialized = True
    adapter.preference_dirty = False

    try:
        adapter.execute('disable_all', {})
    except AdapterError as error:
        assert error.code == 'waiting', error.code
    else:
        raise AssertionError('the fixture teardown was expected to wait')
    assert (Path(directory) / 'desired-state.json').exists(), 'durable reset was not persisted first'
    assert adapter.preference_dirty, 'an unobserved teardown was recorded as reconciled'

    before = len(resident.calls)
    adapter.execute('status', {})
    reconciles = [call for call in resident.calls[before:] if call['kind'] == 'reconcile']
    assert reconciles, 'status after a failed teardown did not reconcile the resident'
    calls = [(command, params) for command, params in reconciles[0]['batch']]
    assert ('set_feature', {'feature': 'infiniteAmmo', 'value': False}) in calls, calls
    assert ('lock_vital', {'vital': 'health', 'locked': False}) in calls, calls
    assert any(command == 'lock_resource' and params.get('resource') == 'Money' and params.get('locked') is False
               for command, params in calls), calls

print('hades2_failed_teardown_reconcile_ok')
