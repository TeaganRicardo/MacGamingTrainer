import sys
import tempfile
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
sys.path.insert(0, str(ROOT / 'tests'))

from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter
from games.hades2.persistence import PersistenceError
from hades2_resident_session_fakes import FakeResidentSession, FakeTimeWarpController

model = (ROOT/'Sources/Hades2/Hades2Model.swift').read_text()

start = model.index('    private func detachForTermination')
termination = model[start:model.index('\n}\n\nprivate extension Hades2FeatureKey', start)]
swift = r'''
import Foundation
final class Session {
    var isRunning = true
    var stopped = false
    func stop(suppressTerminationError: Bool) { stopped = true }
}
final class ExitHarness {
    var connected = true, exiting = false, shuttingDown = false
    var backendSession = Session()
    var commands: [Hades2Command] = []
    var activeFeatures: [String: Bool] = [:], dormantFeatures: [String: Bool] = [:]
    var gatheringProbabilities: [String: Double] = [:]
    var chaosGateProbability: Double?
    var gameSpeed = 1.0
    var nextRoomReward: String?
    var healthLocked = false, manaLocked = false, armorLocked = false
    var failReset = false, failCleanup = false
    func invalidatePendingMutations() {}
    func sendBarrier(_ command: Hades2Command, title: String, announceSuccess: Bool,
                     completion: @escaping (Bool) -> Void) {
        commands.append(command)
        completion(command == .resetDesired ? !failReset : !failCleanup)
    }
''' + termination + r'''
}
@main struct Main {
    static func main() {
        for family in ["gathering", "chaos", "nextRoom", "speed", "lock", "default"] {
            for failure in ["none", "reset", "cleanup"] {
                let model = ExitHarness()
                switch family {
                case "gathering": model.gatheringProbabilities = ["fishing": 100]
                case "chaos": model.chaosGateProbability = 100
                case "nextRoom": model.nextRoomReward = "Money"
                case "speed": model.gameSpeed = 2
                case "lock": model.healthLocked = true
                default: break
                }
                model.failReset = failure == "reset"
                model.failCleanup = failure == "cleanup"
                var finished = false
                model.prepareForTermination { finished = $0 }
                precondition(model.commands == [.resetDesired, .disableAll, .disconnect],
                    "\(family)/\(failure): verified connection skipped resident teardown: \(model.commands)")
                precondition(finished && model.backendSession.stopped)
            }
        }
        let disconnected = ExitHarness()
        disconnected.connected = false
        disconnected.prepareForTermination { _ in }
        precondition(disconnected.commands == [.resetDesired])
        let stopped = ExitHarness()
        stopped.backendSession.isRunning = false
        stopped.prepareForTermination { _ in }
        precondition(stopped.commands.isEmpty && stopped.backendSession.stopped)
    }
}
'''
with tempfile.TemporaryDirectory(prefix='mgt-exit-swift-') as temporary:
    source = Path(temporary) / 'Exit.swift'
    executable = Path(temporary) / 'exit'
    source.write_text(swift)
    subprocess.run(['swiftc', str(ROOT/'Sources/Hades2/Hades2Types.swift'),
                    str(ROOT/'Sources/Hades2/Generated/Hades2Command.generated.swift'),
                    str(source), '-o', str(executable)], check=True)
    result = subprocess.run([str(executable)], text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr

# reset_desired command identity/routing is covered at the Hades Host
# command-contract seam. This test owns only exit/reset behavior.


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
