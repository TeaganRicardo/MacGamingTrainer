"""Disposable transport fixtures for the two public recovery boundaries.

Only framing, observations and connection faults are simulated. Both fixtures
run the real game client/adapter and its durable recovery implementation.
"""
from dataclasses import dataclass
import json
from pathlib import Path
import re

from core.adapter import AdapterError
from core.sidecar import SidecarTerminalError
from games.hades.client import HadesRuntimeClient
from games.hades.recovery import HadesRecoveryJournal
from games.hades2.adapter import Hades2Adapter
from hades2_resident_session_fakes import FakeTimeWarpController, hades2_adapter_context


class BackendExit(BaseException):
    """Abrupt backend exit after dispatch, before a reply can be accepted."""


@dataclass(frozen=True)
class BoundaryCall:
    pid: int
    method: str
    request_id: str = None


def ready_observation():
    return {
        'status': 'ready', 'scene': 'run', 'capabilities': {'setFeature': True},
        'desiredFeatures': {}, 'activeFeatures': {}, 'dormantFeatures': {},
        'featureSupport': {}, 'featureErrors': {}, 'resources': [], 'elements': [],
        'stats': {}, 'boonRarity': {}, 'gatheringProbabilities': {},
        'chaosGateProbability': None,
    }


class FixtureBoundary:
    def __init__(self, game):
        self.game = game
        self.pid = game.pid
        self.calls = []
        self.failure = None
        self.before_reply = None

    def cross(self, method, request_id=None):
        call = BoundaryCall(self.pid, method, request_id)
        self.calls.append(call)
        self.game.calls.append(call)
        callback, self.before_reply = self.before_reply, None
        if callback is not None:
            callback()
        failure, self.failure = self.failure, None
        if failure == 'crash':
            raise BackendExit()
        if failure == 'unknown':
            raise self.unknown_error()


class HadesSidecar(FixtureBoundary):
    started = True
    terminal = False

    def request(self, method, params, **options):
        self.cross(method, params.get('requestId'))
        return {'result': {'connected': method != 'disconnect', 'pid': self.pid}}

    def unknown_error(self):
        self.terminal = True
        return SidecarTerminalError('fixture reply lost after dispatch', outcome_unknown=True)

    def close(self):
        self.started = False


class Hades2Transport(FixtureBoundary):
    last_duration = 0.001
    last_expression_duration = 0.0
    last_attach_profile = {}
    tainted = False

    def __init__(self, game):
        super().__init__(game)
        self.live = True
        self.speed = FakeTimeWarpController()

    def alive(self):
        return self.live

    def attach(self, pid):
        self.pid = pid
        self.live = True

    def detach(self):
        self.live = False
        self.pid = None

    def close(self):
        self.detach()

    def create_time_warp_controller(self, *args):
        return self.speed

    def execute(self, source, **options):
        # Decode the semantic operation at the existing Lua transport boundary.
        # The resident bootstrap may contain many command names of its own.
        calls = re.findall(r'__MacGamingTrainerV1\.observe\("([^"]+)",', source)
        if calls:
            method = calls[-1]
        elif '__MacGamingTrainerV1.observeBatch(' in source:
            method = 'replay_preferences'
        else:
            raise AssertionError('fixture received an unrecognized resident operation')
        identifier = re.search(r'\["requestId"\]="([^"]+)"', source)
        self.cross(method, identifier.group(1) if identifier else None)
        return json.dumps(ready_observation())

    def acknowledge_result(self):
        pass

    def unknown_error(self):
        self.tainted = True
        return AdapterError('outcome_unknown', 'hades2.error.outcomeUnknownGeneric')


class HadesBackend:
    def __init__(self, game):
        self.game = game
        self.boundary = HadesSidecar(game)
        self.client = HadesRuntimeClient(
            self.boundary, recovery=HadesRecoveryJournal(game.journal_path),
            identity=lambda pid: game.identity,
        )

    def open(self):
        return self.client.connect(self.game.pid, '/fixture/Hades/Game.macOS')

    def status(self):
        return self.client.status()

    def action(self, request_id):
        return self.client.command('spawn_reward', {
            'reward': 'RoomMoneyDrop', 'requestId': request_id, 'target': {'heroId': 'fixture-hero'},
        })


class Hades2Backend:
    def __init__(self, game):
        self.boundary = Hades2Transport(game)
        self.adapter = Hades2Adapter(
            context=game.context, transport=self.boundary, identity=lambda pid: game.identity,
        )

    def open(self):
        # The fixture transport already owns an acknowledged attachment. Probe
        # through the adapter, so readiness and journal checks stay production-owned.
        return self.adapter.observe_runtime()

    def status(self):
        return self.adapter.observe_runtime()

    def action(self, request_id):
        return self.adapter.execute('spawn_reward', {'reward': 'RoomMoneyDrop', 'requestId': request_id})


class HadesRecoveryFixture:
    game_id = 'hades'
    backend_type = HadesBackend

    def __init__(self, directory):
        self.pid = 4242
        self.identity = 'birth-A'
        self.calls = []
        self.journal_path = Path(directory) / 'runtime-recovery.json'

    def backend(self):
        return self.backend_type(self)

    def pending_bytes(self):
        return self.journal_path.read_bytes() if self.journal_path.exists() else None

    def actions(self):
        return [call for call in self.calls if call.method == 'spawn_reward']


class Hades2RecoveryFixture(HadesRecoveryFixture):
    game_id = 'hades2'
    backend_type = Hades2Backend

    def __init__(self, directory):
        super().__init__(directory)
        self.context = hades2_adapter_context(Path(directory) / 'home')
        self.journal_path = self.context.data_dir / 'runtime-recovery.json'


GAME_FIXTURES = (HadesRecoveryFixture, Hades2RecoveryFixture)
