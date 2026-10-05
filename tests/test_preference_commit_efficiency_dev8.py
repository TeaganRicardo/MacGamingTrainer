import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
sys.path.insert(0, str(ROOT / 'tests'))

from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter
from hades2_resident_session_fakes import FakeResidentSession, FakeTimeWarpController

base = Path(tempfile.mkdtemp(prefix='mgt-dev8-pref-commit-'))
preparation.DATA = base
session = FakeResidentSession({
    'status':'ready', 'scene':'run',
    'capabilities':{'setFeature':True},
    'desiredFeatures':{}, 'activeFeatures':{}, 'dormantFeatures':{},
    'featureErrors':{}, 'resources':[], 'elements':[], 'stats':{},
    'boonRarity':{}, 'gatheringProbabilities':{}, 'chaosGateProbability':None,
}, pid=123)
adapter = Hades2Adapter(
    resident_session=session,
    time_warp_controller=FakeTimeWarpController(),
)
adapter.state.update(status='ready', connected=True, capabilities={'setFeature':True})

save_count = 0
original_save = adapter.preference_store.save
def counted_save(preferences):
    global save_count
    save_count += 1
    return original_save(preferences)
adapter.preference_store.save = counted_save

# These three commands are internal applications of already-durable desired
# state. Each user edit must fsync exactly once before it crosses the Lua boundary.
save_count = 0
adapter.set_desired('invincibility', True)
assert save_count == 1, save_count
assert json.loads((base/'desired-state.json').read_text())['invincibility'] is True

save_count = 0
adapter.set_boon_rarity_desired({'target':'Epic','multiplier':100,'forceLegendary':True,'forceDuo':False})
assert save_count == 1, save_count
assert json.loads((base/'desired-state.json').read_text())['boonRarity']['forceLegendary'] is True

save_count = 0
adapter.set_next_room_reward_desired('WeaponUpgrade')
assert save_count == 1, save_count
assert json.loads((base/'desired-state.json').read_text())['nextRoomReward'] == 'WeaponUpgrade'

# Programming/schema failures after the durable commit are surfaced instead of
# being misreported as a normal deferred transport application.
original_execute = adapter.execute
def broken_execute(*args, **kwargs):
    raise ValueError('decode bug')
adapter.execute = broken_execute
save_count = 0
try:
    adapter.set_desired('infiniteHealth', True)
except ValueError as error:
    assert str(error) == 'decode bug'
else:
    raise AssertionError('non-transport desired apply error was hidden')
assert save_count == 1
adapter.execute = original_execute

print('preference_commit_efficiency_dev8_ok')
