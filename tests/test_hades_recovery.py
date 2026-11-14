from pathlib import Path
import io
import os
import subprocess
import sys
import tempfile
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
from core.adapter import AdapterError
from core.sidecar import JsonLineSidecarClient, SidecarTerminalError
from games.hades.client import HadesRuntimeClient
from games.hades.recovery import HadesRecoveryJournal

assert HadesRuntimeClient._new_sidecar().child_owns_cleanup


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

for malformed in (False, True):
    with tempfile.TemporaryDirectory(prefix='hades-recovery-response-') as directory:
        journal = HadesRecoveryJournal(Path(directory) / 'pending.json')
        class UnsafeResponse(Sidecar):
            def request(self, method, params, **options):
                if method == 'connect':
                    return super().request(method, params, **options)
                self.calls.append((method, params))
                if malformed:
                    return {'result': {'connected': 'invalid'}}
                return {'error': {'code': 'outcome_unknown', 'presentation': 'hades.error.outcomeUnknown'}}
        sidecar = UnsafeResponse()
        client = HadesRuntimeClient(sidecar, recovery=journal, identity=lambda pid: 'first')
        client.connect(42, '/tmp/Hades/Game.macOS')
        try:
            client.command('add_trait', {})
        except AdapterError as error:
            assert error.code == ('debugger_protocol' if malformed else 'outcome_unknown')
        else:
            raise AssertionError('an unsafe reply retained runtime trust')
        assert not client.connected and journal.path.exists()
        replacement = Sidecar()
        restarted = HadesRuntimeClient(replacement, recovery=journal, identity=lambda pid: 'first')
        try:
            restarted.connect(42, '/tmp/Hades/Game.macOS')
        except AdapterError as error:
            assert error.code == 'restart_required'
        else:
            raise AssertionError('backend restart bypassed an unsafe native reply')
        assert replacement.calls == []
        client.identity = lambda pid: 'second'
        assert client.connect(42, '/tmp/Hades/Game.macOS')['connected']

print('hades_native_request_crash_recovery_and_pid_reuse_ok')

for reply in (b'{"id":"1","error":{"code":"outcome_unknown","presentation":"hades.error.luaTerminationFailed"}}\n',
              b'not-json\n'):
    with tempfile.TemporaryDirectory(prefix='hades-termination-recovery-') as directory:
        terminated = []
        process = types.SimpleNamespace(stdin=io.BytesIO(), stdout=io.BytesIO(reply), poll=lambda: None,
                                        terminate=lambda: terminated.append('terminate'),
                                        kill=lambda: terminated.append('kill'), wait=lambda **kwargs: None)
        sidecar = JsonLineSidecarClient(['fixture'], reply_timeout_seconds=1,
                                       process_factory=lambda *args, **kwargs: process, child_owns_cleanup=True)
        sidecar.start()
        journal = HadesRecoveryJournal(Path(directory) / 'pending.json')
        client = HadesRuntimeClient(sidecar, recovery=journal, identity=lambda pid: 'unsafe-life')
        client.pid, client.process_identity, client.connected = 42, 'unsafe-life', True
        try:
            client.command('update_trait', {})
        except AdapterError as error:
            assert error.code == 'outcome_unknown'
        else:
            raise AssertionError('failed/lost termination reply was accepted')
        assert journal.path.is_file()
        try:
            client.close()
        except AdapterError as error:
            assert error.code == 'restart_required'
        assert not terminated and process.stdin.closed and process.stdout.closed
        try:
            client.connect(42, '/tmp/Hades/Game.macOS')
        except AdapterError as error:
            assert error.code == 'restart_required'
        else:
            raise AssertionError('child cleanup permitted same-process reconnection')
print('hades_failed_termination_survives_client_close_ok')

# Lost reply through the real client/Core process seam: EOF reaches the actual
# game-owned shutdown loop, which outlives client.close and completes cleanup.
with tempfile.TemporaryDirectory(prefix='hades-child-cleanup-') as directory:
    events = Path(directory) / 'events'
    children = []
    def start_child(*args, **kwargs):
        process = subprocess.Popen(*args, **kwargs)
        children.append(process)
        return process
    source = '''import sys
from pathlib import Path
from types import SimpleNamespace
from core.adapter import AdapterError
from games.hades.lldb_worker import close_worker
events=Path(sys.argv[1])
transport=SimpleNamespace(vm_interrupted=True)
attempts=0
def close():
    global attempts
    attempts+=1
    with events.open('a') as out: out.write('kill\\n')
    if attempts<3: raise AdapterError('outcome_unknown','hades.error.luaTerminationFailed')
    transport.vm_interrupted=False
    with events.open('a') as out: out.write('exited\\n')
sys.stdin.readline()
print('lost-native-reply',flush=True)
sys.stdin.read()
close_worker(SimpleNamespace(transport=transport,close=close))
'''
    sidecar = JsonLineSidecarClient([sys.executable, '-u', '-c', source, str(events)],
                                   env={**os.environ, 'PYTHONPATH': str(ROOT / 'Backend')},
                                   reply_timeout_seconds=3, child_owns_cleanup=True, process_factory=start_child)
    sidecar.start()
    journal = HadesRecoveryJournal(Path(directory) / 'pending.json')
    client = HadesRuntimeClient(sidecar, recovery=journal)
    client.pid, client.process_identity, client.connected = 42, 'isolated-life', True
    try:
        client.command('update_trait', {})
    except AdapterError as error:
        assert error.code == 'outcome_unknown'
    else:
        raise AssertionError('lost child reply was accepted')
    client.close()
    assert children[0].wait(timeout=6) == 0
    assert events.read_text().splitlines() == ['kill', 'kill', 'kill', 'exited']
    assert journal.path.is_file()
print('hades_lost_reply_child_cleanup_completes_after_client_exit_ok')
