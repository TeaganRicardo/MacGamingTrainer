import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
sys.path.insert(0, str(ROOT / 'tests'))

from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter
from games.hades2.persistence import PersistenceError
from hades2_resident_session_fakes import FakeResidentSession, FakeTimeWarpController

model = (ROOT/'Sources/Hades2/Hades2Model.swift').read_text()
api = (ROOT/'Sources/Hades2/Hades2API.swift').read_text()
router = (ROOT/'Backend/games/hades2/command_router.py').read_text()

termination = model[model.index('    private var runtimeCleanupRequired'):model.index('    private func finishExit')]
assert 'failExit' not in termination
assert 'let cleanupRequired = runtimeCleanupRequired' in termination
assert 'dormantFeatures.values.contains(true)' in termination
assert 'Hades2FeatureKey.allCases.contains(where: desiredFeatureEnabled)' in termination
assert 'desiredFeatureKeys' not in termination
assert 'sendBarrier(.resetDesired' in termination
assert 'guard self.connected, cleanupRequired else' in termination
assert 'sendBarrier(.disableAll' in termination
assert 'announceSuccess: false' in termination
assert 'self.finishExit(completion: completion)' in termination

# The exit-only desired reset remains a typed Hades command.
assert 'case resetDesired = "reset_desired"' in api
assert "elif command=='reset_desired':result=adapter.reset_desired()" in router


def make_adapter(prefix, session=None):
    base = Path(tempfile.mkdtemp(prefix=prefix))
    preparation.DATA = base
    session = session or FakeResidentSession()
    adapter = Hades2Adapter(
        resident_session=session,
        time_warp_controller=FakeTimeWarpController(),
    )
    return base, session, adapter


# reset_desired is persistence-only. It must not attach, observe, mutate or
# reconcile the resident session, even when Host state still says connected.
_, reset_session, reset_adapter = make_adapter('mgt-exit-reset-')
reset_session.live = False
reset_adapter.state.update(connected=True, status='ready', scene='run')
reset_adapter.preferences['invincibility'] = True
before_invalidations = reset_session.invalidations
reset_result = reset_adapter.reset_desired()
assert reset_session.calls == []
assert reset_session.invalidations == before_invalidations
assert reset_result['connected'] is False
assert reset_adapter.preferences['invincibility'] is False


# If the durable reset write fails, runtime teardown is still best-effort. The
# failure must happen before reattach/mutation, and it is surfaced only after
# the teardown boundary returns.
events = []


class ExitSession(FakeResidentSession):
    def __init__(self):
        super().__init__({
            'status': 'ready',
            'scene': 'run',
            'capabilities': {},
            'desiredFeatures': {},
            'activeFeatures': {},
            'dormantFeatures': {},
            'featureErrors': {},
            'resources': [],
            'elements': [],
            'stats': {},
            'boonRarity': {},
            'gatheringProbabilities': {},
            'chaosGateProbability': None,
        }, pid=None)
        self.live = False

    def attach(self, pid):
        events.append('attach')
        super().attach(pid)

    def mutate(self, command, params=None):
        events.append(('mutate', command))
        return super().mutate(command, params)


_, exit_session, exit_adapter = make_adapter('mgt-exit-disable-', ExitSession())
exit_adapter.state.update(connected=False, pid=None, status='disconnected', scene='unknown')
exit_adapter.preferences['invincibility'] = True
original_preferences = dict(exit_adapter.preferences)


def failing_save(preferences):
    events.append('persist-reset')
    raise PersistenceError('simulated durable reset failure')


exit_adapter.preference_store.save = failing_save


def fake_scan():
    events.append('scan')
    exit_adapter.state['pid'] = 4242
    exit_adapter.state['status'] = 'disconnected'
    return dict(exit_adapter.state)


exit_adapter.scan = fake_scan
try:
    exit_adapter.execute('disable_all', {})
except PersistenceError as error:
    assert 'simulated durable reset failure' in str(error)
else:
    raise AssertionError('durable teardown failure was hidden')

assert events[0] == 'persist-reset'
assert events.index('persist-reset') < events.index('attach')
assert events.index('attach') < events.index(('mutate', 'disable_all'))
assert exit_adapter.preferences == original_preferences, (
    'failed durable reset must not pretend in-memory desired state was cleared'
)

print('exit_semantics_ok')
