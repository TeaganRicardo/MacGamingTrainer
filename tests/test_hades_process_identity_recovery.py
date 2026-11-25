"""Process identity is stable across environments and preserves legacy recovery."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from core.adapter import AdapterError
from core.target_probe import BoundedCommandTimeoutError
from games.hades.client import HadesRuntimeClient
from games.hades.recovery import HadesRecoveryJournal, process_identity


class Sidecar:
    started = True
    terminal = False

    def __init__(self):
        self.calls = []

    def request(self, method, params, **options):
        self.calls.append((method, params))
        return {'result': {'connected': True, 'pid': params.get('pid')}}

    def close(self):
        self.started = False


class ProcessIdentityRecoveryTests(unittest.TestCase):
    def test_probe_timeout_propagates_without_retiring_pending_request(self):
        with tempfile.TemporaryDirectory(prefix='hades-probe-timeout-') as temporary:
            journal = HadesRecoveryJournal(Path(temporary) / 'recovery.json')
            journal.begin(42, 'birth-A', 'spawn_reward')
            pending = journal.path.read_bytes()
            sidecar = Sidecar()
            client = HadesRuntimeClient(sidecar, recovery=journal)
            with patch('core.target_probe.subprocess.run', side_effect=subprocess.TimeoutExpired(['/bin/ps'], 2)):
                with self.assertRaises(BoundedCommandTimeoutError):
                    client.connect(42, '/fixture/Hades')
            self.assertEqual(journal.path.read_bytes(), pending)
            self.assertEqual(sidecar.calls, [])

    def test_same_real_process_identity_ignores_timezone_and_locale(self):
        with patch.dict(os.environ, {'TZ': 'UTC', 'LC_ALL': 'C'}):
            utc_identity = process_identity(os.getpid())
        with patch.dict(os.environ, {'TZ': 'America/Los_Angeles', 'LC_ALL': 'C.UTF-8'}):
            local_identity = process_identity(os.getpid())
        self.assertIsNotNone(utc_identity)
        self.assertEqual(local_identity, utc_identity)

    def test_timezone_change_cannot_retire_same_process_recovery(self):
        with tempfile.TemporaryDirectory(prefix='hades-timezone-recovery-') as temporary:
            pid = os.getpid()
            journal = HadesRecoveryJournal(Path(temporary) / 'recovery.json')
            with patch.dict(os.environ, {'TZ': 'UTC', 'LC_ALL': 'C'}):
                journal.begin(pid, process_identity(pid), 'spawn_reward')
            pending = journal.path.read_bytes()
            sidecar = Sidecar()
            client = HadesRuntimeClient(sidecar, recovery=journal)
            with patch.dict(os.environ, {'TZ': 'America/Los_Angeles', 'LC_ALL': 'C.UTF-8'}):
                with self.assertRaises(AdapterError) as raised:
                    client.connect(pid, '/fixture/Hades')
            self.assertEqual(raised.exception.code, 'restart_required')
            self.assertEqual(journal.path.read_bytes(), pending)
            self.assertEqual(sidecar.calls, [])

    def test_legacy_local_time_record_requires_a_different_identified_pid(self):
        with tempfile.TemporaryDirectory(prefix='hades-legacy-identity-') as temporary:
            pid = os.getpid()
            # This reproduces the untagged lstart value written by earlier
            # backends. Its timezone is absent from the unchanged disk format.
            legacy = subprocess.check_output(
                ['/bin/ps', '-p', str(pid), '-o', 'lstart='], text=True,
                env={**os.environ, 'TZ': 'America/Los_Angeles', 'LC_ALL': 'C'},
            ).strip()
            journal = HadesRecoveryJournal(Path(temporary) / 'recovery.json')
            journal.begin(pid, legacy, 'spawn_reward')
            pending = journal.path.read_bytes()
            sidecar = Sidecar()
            client = HadesRuntimeClient(sidecar, recovery=journal)
            with patch.dict(os.environ, {'TZ': 'UTC', 'LC_ALL': 'C'}):
                with self.assertRaises(AdapterError) as raised:
                    client.connect(pid, '/fixture/Hades')
            self.assertEqual(raised.exception.code, 'restart_required')
            self.assertEqual(journal.path.read_bytes(), pending)
            self.assertEqual(sidecar.calls, [])
            # The legacy start cannot distinguish same-PID reuse. A positive
            # identity at a different PID still proves a replacement lifetime.
            replacement = HadesRuntimeClient(
                sidecar, recovery=journal, identity=lambda target: process_identity(pid),
            )
            self.assertTrue(replacement.connect(pid + 1, '/fixture/Hades')['connected'])
            self.assertFalse(journal.path.exists())
            self.assertEqual(len(sidecar.calls), 1)


if __name__ == '__main__':
    unittest.main()
