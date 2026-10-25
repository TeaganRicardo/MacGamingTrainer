from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
from core.adapter import AdapterError
from core.sidecar import SidecarTerminalError
from games.hades.client import HadesRuntimeClient
from games.hades.recovery import HadesRecoveryJournal


class Sidecar:
    started = True
    terminal = False
    lose = False

    def __init__(self):
        self.calls = []

    def request(self, method, params, **options):
        self.calls.append((method, params))
        if self.lose:
            self.terminal = True
            raise SidecarTerminalError('lost native completion', outcome_unknown=True)
        return {'result': {'connected': method != 'disconnect', 'pid': params.get('pid', 42)}}

    def close(self):
        self.started = False


with tempfile.TemporaryDirectory(prefix='hades-recovery-') as directory:
    journal = HadesRecoveryJournal(Path(directory) / 'pending.json')
    sidecar = Sidecar()
    client = HadesRuntimeClient(sidecar, recovery=journal, identity=lambda pid: 'birth-A')
    client.connect(42, '/tmp/Hades/Game.macOS')
    assert not journal.path.exists()
    sidecar.lose = True
    try:
        client.command('set_value', {'field': 'money', 'value': 500, 'target': {'heroId': 'hero'}})
    except AdapterError as error:
        assert error.code == 'outcome_unknown'
    else:
        raise AssertionError('lost acknowledgement must remain unknown')
    assert journal.path.exists()
    calls = len(sidecar.calls)
    try:
        client.command('add_trait', {'trait': 'ZeusWeaponTrait'})
    except AdapterError as error:
        assert error.code == 'restart_required'
    else:
        raise AssertionError('the current client continued after an unknown outcome')
    assert len(sidecar.calls) == calls
    replacement = Sidecar()
    restarted = HadesRuntimeClient(replacement, recovery=journal, identity=lambda pid: 'birth-A')
    try:
        restarted.connect(42, '/tmp/Hades/Game.macOS')
    except AdapterError as error:
        assert error.code == 'restart_required'
    else:
        raise AssertionError('backend restart bypassed the pending native request')
    assert replacement.calls == []
    new_game = HadesRuntimeClient(replacement, recovery=journal, identity=lambda pid: 'birth-B')
    assert new_game.connect(42, '/tmp/Hades/Game.macOS')['connected']
    assert not journal.path.exists(), 'PID reuse must resolve by actual target lifetime'
    journal.begin(42, 'birth-B', 'add_trait')
    after_crash = HadesRuntimeClient(Sidecar(), recovery=journal, identity=lambda pid: 'birth-B')
    try:
        after_crash.connect(42, '/tmp/Hades/Game.macOS')
    except AdapterError as error:
        assert error.code == 'restart_required'
    else:
        raise AssertionError('in-flight backend crash evidence was discarded')

with tempfile.TemporaryDirectory(prefix='hades-recovery-response-') as directory:
    journal = HadesRecoveryJournal(Path(directory) / 'pending.json')
    class UnknownResponse(Sidecar):
        def request(self, method, params, **options):
            if method == 'connect':
                return super().request(method, params, **options)
            self.calls.append((method, params))
            return {'error': {'code': 'outcome_unknown', 'presentation': 'hades.error.outcomeUnknown'}}
    sidecar = UnknownResponse()
    client = HadesRuntimeClient(sidecar, recovery=journal, identity=lambda pid: 'first')
    client.connect(42, '/tmp/Hades/Game.macOS')
    try:
        client.command('add_trait', {})
    except AdapterError:
        pass
    assert not client.connected and journal.path.exists()
    client.identity = lambda pid: 'second'
    assert client.connect(42, '/tmp/Hades/Game.macOS')['connected']

print('hades_native_request_crash_recovery_and_pid_reuse_ok')
