from pathlib import Path
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
from core.adapter import AdapterError
from core.sidecar import JsonLineSidecarClient, SidecarTerminalError
from games.hades.client import HadesRuntimeClient
from games.hades.recovery import HadesRecoveryJournal, process_identity

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

# Recovery evidence also applies before the replacement backend reconnects.
# A known not-connected response must never replace and then erase the old
# lifetime's unknown action.
with tempfile.TemporaryDirectory(prefix='hades-before-connect-recovery-') as directory:
    journal = HadesRecoveryJournal(Path(directory) / 'pending.json')
    journal.begin(42, 'birth-A', 'set_value')
    original = journal.path.read_bytes()
    class NotConnected(Sidecar):
        def request(self, method, params, **options):
            self.calls.append((method, params))
            return {'error': {'code': 'not_connected', 'presentation': 'hades.error.notConnected'}}
    sidecar = NotConnected()
    restarted = HadesRuntimeClient(sidecar, recovery=journal, identity=lambda pid: 'birth-A')
    try:
        restarted.command('add_trait', {})
    except AdapterError as error:
        blocked_code = error.code
    else:
        raise AssertionError('a command ran before recovery was checked')
    assert journal.path.exists(), 'pre-connect command erased the prior unknown action'
    assert journal.path.read_bytes() == original
    assert blocked_code == 'restart_required' and not sidecar.calls
    assert not restarted.status()['connected']
    assert journal.path.read_bytes() == original
    try:
        restarted.connect(42, '/tmp/Hades/Game.macOS')
    except AdapterError as error:
        assert error.code == 'restart_required'
    else:
        raise AssertionError('pre-connect command permitted same-lifetime reconnect')
    assert not sidecar.calls
print('hades_pre_connect_commands_preserve_prior_recovery_ok')

# A failed identity probe cannot turn a prior unknown result into permission
# to reconnect, including when the backend itself was restarted.
for missing_identity in (None, '', '  ', 'birth-A\nbirth-B', ['birth-A']):
    with tempfile.TemporaryDirectory(prefix='hades-ambiguous-identity-') as directory:
        journal = HadesRecoveryJournal(Path(directory) / 'pending.json')
        journal.begin(42, 'birth-A', 'set_value')
        original = journal.path.read_bytes()
        for pid in (42, 43):
            replacement = Sidecar()
            restarted = HadesRuntimeClient(replacement, recovery=journal,
                                           identity=lambda pid: missing_identity)
            try:
                restarted.connect(pid, '/tmp/Hades/Game.macOS')
            except AdapterError as error:
                assert error.code == 'restart_required'
            else:
                raise AssertionError('ambiguous identity retired the recovery record')
            assert replacement.calls == []
            assert journal.path.read_bytes() == original
        verified = HadesRuntimeClient(Sidecar(), recovery=journal, identity=lambda pid: 'birth-B')
        assert verified.connect(42, '/tmp/Hades/Game.macOS')['connected']
        assert not journal.path.exists()

# A historical missing identity cannot prove that a reused PID is new. A
# different identified PID still establishes that the old game was replaced.
for prior_identity in (None, '', 'birth-A\nbirth-B'):
    with tempfile.TemporaryDirectory(prefix='hades-missing-prior-identity-') as directory:
        journal = HadesRecoveryJournal(Path(directory) / 'pending.json')
        journal.begin(42, prior_identity, 'set_value')
        original = journal.path.read_bytes()
        replacement = Sidecar()
        client = HadesRuntimeClient(replacement, recovery=journal, identity=lambda pid: 'birth-B')
        try:
            client.connect(42, '/tmp/Hades/Game.macOS')
        except AdapterError as error:
            assert error.code == 'restart_required'
        else:
            raise AssertionError('missing prior identity proved same-PID replacement')
        assert replacement.calls == [] and journal.path.read_bytes() == original
        assert client.connect(43, '/tmp/Hades/Game.macOS')['connected']
        assert not journal.path.exists()
print('hades_ambiguous_process_identity_preserves_recovery_ok')

# ps may fail while returning text, or return multiple candidate starts. Only
# a successful single identity is evidence that a game process was replaced.
for result, expected in (
    (types.SimpleNamespace(returncode=0, stdout=' birth-A\n'), 'ps-utc-v1:birth-A'),
    (types.SimpleNamespace(returncode=1, stdout='birth-B'), None),
    (types.SimpleNamespace(returncode=0, stdout=''), None),
    (types.SimpleNamespace(returncode=0, stdout='birth-A\nbirth-B\n'), None),
):
    with patch('games.hades.recovery.bounded_run', return_value=result):
        assert process_identity(42) == expected
with patch('games.hades.recovery.bounded_run', side_effect=OSError('fixture probe unavailable')):
    assert process_identity(42) is None

# The worker's status path calls runtime.status(), which installs hooks and
# world state. A missing status reply therefore has the same recovery policy.
with tempfile.TemporaryDirectory(prefix='hades-status-recovery-') as directory:
    journal = HadesRecoveryJournal(Path(directory) / 'pending.json')
    sidecar = Sidecar()
    client = HadesRuntimeClient(sidecar, recovery=journal, identity=lambda pid: 'birth-A')
    client.connect(42, '/tmp/Hades/Game.macOS')
    sidecar.lose = True
    try:
        client.status()
    except AdapterError as error:
        assert error.code == 'outcome_unknown'
    else:
        raise AssertionError('status lost recovery protection')
    assert json.loads(journal.path.read_text()) == {'pid': 42, 'identity': 'birth-A', 'method': 'status'}
    restarted_sidecar = Sidecar()
    restarted = HadesRuntimeClient(restarted_sidecar, recovery=journal, identity=lambda pid: 'birth-A')
    try:
        restarted.connect(42, '/tmp/Hades/Game.macOS')
    except AdapterError as error:
        assert error.code == 'restart_required'
    else:
        raise AssertionError('backend restart bypassed unknown status maintenance')
    assert not restarted_sidecar.calls
print('hades_status_maintenance_keeps_recovery_protection_ok')

# Complete an old request only after another lifetime has connected and left
# its own unknown request. This exercises the client reply path, including a
# late reply held by the backend that existed before replacement.
for reuse_client in (False, True):
    with tempfile.TemporaryDirectory(prefix='hades-late-reply-') as directory:
        journal = HadesRecoveryJournal(Path(directory) / 'pending.json')
        newer = Sidecar()
        new_record = []
        class LateReply(Sidecar):
            def request(self, method, params, **options):
                if method != 'add_trait':
                    return super().request(method, params, **options)
                self.calls.append((method, params))
                current = client if reuse_client else HadesRuntimeClient(newer, recovery=journal)
                current.sidecar = newer
                current.identity = lambda pid: 'birth-B'
                current.connect(42, '/tmp/Hades/Game.macOS')
                newer.lose = True
                try:
                    current.command('set_value', {'field': 'money', 'value': 500})
                except AdapterError as error:
                    assert error.code == 'outcome_unknown'
                else:
                    raise AssertionError('fixture failed to leave a new unknown request')
                new_record.append(journal.path.read_bytes())
                return {'result': {'connected': True, 'pid': 42}}
        older = LateReply()
        client = HadesRuntimeClient(older, recovery=journal, identity=lambda pid: 'birth-A')
        client.connect(42, '/tmp/Hades/Game.macOS')
        try:
            client.command('add_trait', {})
        except AdapterError as error:
            assert reuse_client and error.code == 'debugger_lost'
        assert journal.path.exists(), 'late success erased the new lifetime recovery record'
        assert journal.path.read_bytes() == new_record[0]
        assert json.loads(new_record[0]) == {'pid': 42, 'identity': 'birth-B', 'method': 'set_value'}
        if reuse_client:
            assert not client.connected and client.uncertain_pid == 42
        else:
            calls = len(older.calls)
            try:
                client.command('set_value', {'field': 'money', 'value': 100})
            except AdapterError as error:
                assert error.code == 'restart_required'
            else:
                raise AssertionError('obsolete client replaced the newer pending action')
            assert len(older.calls) == calls and journal.path.read_bytes() == new_record[0]
        replacement = HadesRuntimeClient(Sidecar(), recovery=journal, identity=lambda pid: 'birth-B')
        try:
            replacement.connect(42, '/tmp/Hades/Game.macOS')
        except AdapterError as error:
            assert error.code == 'restart_required'
        else:
            raise AssertionError('late success unblocked the newer game lifetime')

# A late failure likewise belongs to its original lifetime and cannot taint
# the newer connection after a same-PID game replacement.
with tempfile.TemporaryDirectory(prefix='hades-late-failure-') as directory:
    journal = HadesRecoveryJournal(Path(directory) / 'pending.json')
    newer = Sidecar()
    class LateFailure(Sidecar):
        def request(self, method, params, **options):
            if method != 'add_trait':
                return super().request(method, params, **options)
            client.sidecar = newer
            client.identity = lambda pid: 'birth-B'
            client.connect(42, '/tmp/Hades/Game.macOS')
            raise SidecarTerminalError('late failure from birth-A', outcome_unknown=True)
    client = HadesRuntimeClient(LateFailure(), recovery=journal, identity=lambda pid: 'birth-A')
    client.connect(42, '/tmp/Hades/Game.macOS')
    try:
        client.command('add_trait', {})
    except AdapterError as error:
        assert error.code == 'debugger_lost'
    else:
        raise AssertionError('late failure was accepted')
    assert client.connected and client.uncertain_pid is None and client.sidecar is newer
    assert not journal.path.exists()
print('hades_late_reply_keeps_request_lifetime_attribution_ok')

# Serialize a late completion's compare/delete with a new lifetime's guard and
# publication. Two journal objects model the old and replacement backends.
with tempfile.TemporaryDirectory(prefix='hades-retirement-race-') as directory:
    journal = HadesRecoveryJournal(Path(directory) / 'pending.json')
    pending = journal.begin(42, 'birth-A', 'add_trait')
    replacement = HadesRecoveryJournal(journal.path)
    old_read = threading.Event()
    release_old = threading.Event()
    replacement_started = threading.Event()
    replacement_finished = threading.Event()
    failures = []
    read_text = Path.read_text
    def paused_read(path, *args, **kwargs):
        value = read_text(path, *args, **kwargs)
        if path == journal.path and threading.current_thread() is old_reply:
            old_read.set()
            if not release_old.wait(5):
                raise AssertionError('late-reply fixture was not released')
        return value
    def finish_old():
        try:
            journal.complete(pending)
        except BaseException as error:
            failures.append(error)
    def start_new():
        replacement_started.set()
        try:
            replacement.guard(42, 'birth-B')
            replacement.begin(42, 'birth-B', 'set_value')
        except BaseException as error:
            failures.append(error)
        finally:
            replacement_finished.set()
    old_reply = threading.Thread(target=finish_old, daemon=True)
    new_lifetime = threading.Thread(target=start_new, daemon=True)
    with patch.object(Path, 'read_text', paused_read):
        old_reply.start()
        try:
            assert old_read.wait(5), 'old reply did not reach its pending-record comparison'
            new_lifetime.start()
            assert replacement_started.wait(5)
            replacement_finished.wait(0.25)
        finally:
            release_old.set()
            old_reply.join(5)
            new_lifetime.join(5)
    assert not old_reply.is_alive() and not new_lifetime.is_alive()
    assert not failures, failures
    assert journal.path.exists(), 'late compare/delete erased the newer lifetime recovery'
    assert json.loads(journal.path.read_text()) == {'pid': 42, 'identity': 'birth-B', 'method': 'set_value'}
print('hades_concurrent_lifetime_retirement_preserves_new_recovery_ok')

with tempfile.TemporaryDirectory(prefix='hades-recovery-lock-failure-') as directory:
    journal = HadesRecoveryJournal(Path(directory) / 'pending.json')
    journal.path.write_text(json.dumps({'pid': 42, 'identity': 'birth-A', 'method': 'set_value'}))
    original = journal.path.read_bytes()
    journal.path.with_name(journal.path.name + '.lock').mkdir()
    sidecar = Sidecar()
    client = HadesRuntimeClient(sidecar, recovery=journal, identity=lambda pid: 'birth-B')
    for action in (lambda: client.command('add_trait', {}),
                   lambda: client.connect(42, '/tmp/Hades/Game.macOS')):
        try:
            action()
        except AdapterError as error:
            assert error.code == 'recovery_failed'
        else:
            raise AssertionError('unavailable recovery lock allowed game execution')
        assert not sidecar.calls and journal.path.read_bytes() == original
print('hades_recovery_lock_failure_preserves_evidence_ok')

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
