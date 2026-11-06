"""A lock the resident still holds is released even while its owner is absent.

In a Hero-less Crossroads the resident retains health/rerolls lock intent in
its own tables and re-applies it to the next Hero. Per-owner lock_* releases
cannot run without that owner, so a desired state that no longer holds those
locks must replace the resident snapshot (stage_desired_locks), not drop them.
"""
import logging
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
sys.path.insert(0, str(ROOT / 'tests'))
# The static fake never applies a batch, so confirmation stays pending by design.
logging.disable(logging.WARNING)

from games.hades2 import preparation  # noqa: E402
from games.hades2.adapter import Hades2Adapter  # noqa: E402
from hades2_resident_session_fakes import FakeResidentSession, FakeTimeWarpController  # noqa: E402

HEROLESS_HUB = {
    'status': 'waiting', 'scene': 'crossroads',
    'capabilities': {
        'setFeature': True, 'setHealth': False, 'setMana': False, 'setArmor': False,
        'setResource': True, 'setRerolls': False, 'setSpellCharge': False,
        'setStats': True, 'setElements': False,
    },
    'statAvailable': {}, 'desiredFeatures': {}, 'activeFeatures': {}, 'dormantFeatures': {},
    'featureErrors': {}, 'stats': {}, 'resources': [], 'elements': [],
    'healthLocked': True, 'rerollsLocked': True,
    'residentDesiredLocks': {
        'statLocks': {}, 'vitalLocks': {'health': {'current': 40, 'max': 100}},
        'resourceLocks': {}, 'elementLocks': {}, 'rerollsLock': 2,
    },
}


def staged_snapshot(desired_update):
    with tempfile.TemporaryDirectory(prefix='hades2-stale-lock-') as directory:
        preparation.DATA = Path(directory)
        resident = FakeResidentSession(payload=HEROLESS_HUB)
        adapter = Hades2Adapter(resident_session=resident, time_warp_controller=FakeTimeWarpController())
        adapter.preferences = adapter._default_preferences()
        adapter.preferences.update(desired_update)
        adapter.preference_initialized = True
        adapter.preference_dirty = True
        adapter.execute('status', {})
        batches = [call['batch'] for call in resident.calls if call['kind'] == 'reconcile']
        assert batches, 'dirty desired state did not reconcile in the hub'
        staged = [params for command, params in batches[0] if command == 'stage_desired_locks']
        assert staged, 'retained resident locks were left for the next Hero: ' + repr(batches[0])
        unsafe = {'lock_vital', 'lock_rerolls', 'set_vital', 'set_rerolls'} & {c for c, _ in batches[0]}
        assert not unsafe, 'Hero-owned commands were sent without a Hero: ' + repr(unsafe)
        return staged[0]


# No locks desired: the staged snapshot clears every retained family.
snapshot = staged_snapshot({})
assert snapshot['vitalLocks'] == {} and snapshot['rerollsLock'] is None, snapshot

# An available owner's lock (Money) does not hide the absent owners' releases.
snapshot = staged_snapshot({'resourceLocks': {'Money': 500}})
assert snapshot['vitalLocks'] == {} and snapshot['rerollsLock'] is None, snapshot
assert snapshot['resourceLocks'] == {'Money': 500}, snapshot

# Nothing held anywhere: no staging round-trip is added.
with tempfile.TemporaryDirectory(prefix='hades2-stale-lock-') as directory:
    preparation.DATA = Path(directory)
    empty_hub = dict(HEROLESS_HUB, healthLocked=False, rerollsLocked=False, residentDesiredLocks={
        'statLocks': {}, 'vitalLocks': {}, 'resourceLocks': {}, 'elementLocks': {}, 'rerollsLock': None,
    })
    resident = FakeResidentSession(payload=empty_hub)
    adapter = Hades2Adapter(resident_session=resident, time_warp_controller=FakeTimeWarpController())
    adapter.preferences = adapter._default_preferences()
    adapter.preference_initialized = True
    adapter.preference_dirty = True
    adapter.execute('status', {})
    assert not any(command == 'stage_desired_locks'
                   for call in resident.calls if call['kind'] == 'reconcile'
                   for command, _ in call['batch'])

print('hades2_stale_resident_lock_release_ok')
