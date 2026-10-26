"""The Hades sidecar carries process speed separately from Lua feature state."""
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
from core.adapter import AdapterError
from core.sidecar import SidecarTerminalError
from games.hades.client import HadesRuntimeClient
from games.hades.preferences import HadesPreferenceStore
from games.hades.recovery import HadesRecoveryJournal
from games.hades.schema import DEFAULT_FEATURES


class Sidecar:
    started = True
    terminal = False

    def __init__(self):
        self.calls = []
        self.speed = 1.0
        self.fail_speed_unknown = False
        self.fail_detach_unknown = False

    def request(self, method, params, **options):
        self.calls.append((method, params, options))
        if method == 'time_warp.current_speed':
            return {'result': {'connected': True, 'pid': 42, 'gameSpeed': self.speed}}
        if method == 'time_warp.set_speed':
            if self.fail_speed_unknown:
                self.terminal = True
                self.started = False
                raise SidecarTerminalError('speed acknowledgement lost', outcome_unknown=True)
            self.speed = params['value']
            return {'result': {'connected': True, 'pid': 42, 'gameSpeed': self.speed}}
        if method == 'disconnect':
            self.speed = 1.0
            if self.fail_detach_unknown:
                self.terminal = True
                self.started = False
                raise SidecarTerminalError('native speed reset acknowledgement lost', outcome_unknown=True)
            return {'result': {'connected': False, 'pid': None}}
        return {'result': {'connected': True, 'pid': 42, 'heroReady': True}}

    def close(self):
        self.started = False


with tempfile.TemporaryDirectory(prefix='hades-speed-client-') as temp:
    sidecar = Sidecar()
    client = HadesRuntimeClient(
        sidecar,
        recovery=HadesRecoveryJournal(Path(temp) / 'recovery.json'),
        identity=lambda pid: str(pid),
    )
    client.connect(42, '/tmp/Hades/Game.macOS', features={**DEFAULT_FEATURES, 'gameSpeed': 2.5})
    connect = next(call for call in sidecar.calls if call[0] == 'connect')
    assert 'gameSpeed' not in connect[1]['features'], 'process speed entered the resident Lua configuration'
    assert client.current_game_speed() == 1.0
    current = next(call for call in sidecar.calls if call[0] == 'time_warp.current_speed')
    assert current[2]['outcome_unknown_on_loss'] is False
    assert client.set_game_speed(2.5) == 2.5
    set_call = next(call for call in sidecar.calls if call[0] == 'time_warp.set_speed')
    assert set_call[2]['outcome_unknown_on_loss'] is True
    assert client.game_speed_actual == 2.5
    client.disconnect()
    assert client.game_speed_actual == 1.0 and not client.connected
    detach_request = next(call for call in sidecar.calls if call[0] == 'disconnect')
    assert detach_request[2]['outcome_unknown_on_loss'] is True, 'native speed reset detach must be risk-classified'

    unknown_sidecar = Sidecar()
    unknown_client = HadesRuntimeClient(
        unknown_sidecar,
        recovery=HadesRecoveryJournal(Path(temp) / 'unknown-recovery.json'),
        identity=lambda pid: str(pid),
    )
    unknown_client.connect(42, '/tmp/Hades/Game.macOS', features=DEFAULT_FEATURES)
    unknown_sidecar.fail_speed_unknown = True
    try:
        unknown_client.set_game_speed(3.0)
    except AdapterError as error:
        assert error.code == 'outcome_unknown'
    else:
        raise AssertionError('lost speed acknowledgement was reported as success')
    sent = len(unknown_sidecar.calls)
    try:
        unknown_client.set_game_speed(4.0)
    except AdapterError as error:
        assert error.code == 'restart_required'
    else:
        raise AssertionError('uncertain speed mutation was automatically retried')
    assert len(unknown_sidecar.calls) == sent

    lost_detach_sidecar = Sidecar()
    lost_detach_client = HadesRuntimeClient(
        lost_detach_sidecar,
        recovery=HadesRecoveryJournal(Path(temp) / 'lost-detach-recovery.json'),
        identity=lambda pid: str(pid),
    )
    lost_detach_client.connect(42, '/tmp/Hades/Game.macOS', features=DEFAULT_FEATURES)
    lost_detach_client.set_game_speed(2.0)
    lost_detach_sidecar.fail_detach_unknown = True
    try:
        lost_detach_client.disconnect()
    except AdapterError as error:
        assert error.code == 'outcome_unknown'
    else:
        raise AssertionError('native speed reset with lost detach acknowledgement was reported as safe')
    assert not lost_detach_client.connected
    try:
        lost_detach_client.connect(42, '/tmp/Hades/Game.macOS', features=DEFAULT_FEATURES)
    except AdapterError as error:
        assert error.code == 'restart_required'
    else:
        raise AssertionError('uncertain detach incorrectly permitted same-process reconnection')

print('hades_game_speed_client_recovery_and_rpc_contract_ok')
