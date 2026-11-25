"""The same lifetime/no-replay contract through both games' public boundaries."""
from contextlib import contextmanager
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from core.adapter import AdapterError
from lua_recovery_fixtures import BackendExit, GAME_FIXTURES


class LuaRuntimeRecoveryContract(unittest.TestCase):
    @contextmanager
    def game(self, fixture):
        with tempfile.TemporaryDirectory(prefix='mgt-lua-recovery-contract-') as directory:
            yield fixture(directory)

    def assert_blocked(self, operation):
        with self.assertRaises(AdapterError) as raised:
            operation()
        self.assertIn(raised.exception.code, ('restart_required', 'outcome_unknown'))

    def lose_action(self, backend, request_id='once'):
        backend.boundary.failure = 'unknown'
        self.assert_blocked(lambda: backend.action(request_id))

    def test_backend_restart_and_preconnect_mutation_preserve_unknown(self):
        for fixture in GAME_FIXTURES:
            with self.subTest(game=fixture.game_id), self.game(fixture) as game:
                backend = game.backend()
                backend.open()
                self.lose_action(backend)
                pending = game.pending_bytes()
                self.assertIsNotNone(pending)
                boundary_count = len(game.calls)
                self.assert_blocked(lambda: backend.action('current-later'))
                restarted = game.backend()
                self.assert_blocked(lambda: restarted.action('restart-before-open'))
                self.assert_blocked(restarted.open)
                self.assertEqual(game.pending_bytes(), pending)
                self.assertEqual(len(game.calls), boundary_count)
                self.assertEqual([call.request_id for call in game.actions()], ['once'])

    def test_missing_or_ambiguous_identity_never_retires_recovery(self):
        for fixture in GAME_FIXTURES:
            with self.subTest(game=fixture.game_id), self.game(fixture) as game:
                backend = game.backend()
                backend.open()
                self.lose_action(backend)
                pending = game.pending_bytes()
                boundary_count = len(game.calls)
                for identity in (None, '', '  ', 'birth-A\nbirth-B', ['birth-A']):
                    for pid in (4242, 4343):
                        with self.subTest(identity=identity, pid=pid):
                            game.identity, game.pid = identity, pid
                            self.assert_blocked(game.backend().open)
                            self.assertEqual(game.pending_bytes(), pending)
                            self.assertEqual(len(game.calls), boundary_count)

    def test_positive_pid_reuse_or_new_pid_retires_only_old_lifetime(self):
        for fixture in GAME_FIXTURES:
            for pid, identity in ((4242, 'birth-B'), (4343, 'birth-A')):
                with self.subTest(game=fixture.game_id, pid=pid), self.game(fixture) as game:
                    backend = game.backend()
                    backend.open()
                    self.lose_action(backend)
                    game.pid, game.identity = pid, identity
                    replacement = game.backend()
                    replacement.open()
                    self.assertIsNone(game.pending_bytes())
                    self.assertEqual([call.request_id for call in game.actions()], ['once'])
                    replacement.action('explicit-new-action')
                    self.assertEqual([call.request_id for call in game.actions()], ['once', 'explicit-new-action'])

    def test_missing_prior_identity_requires_a_positively_identified_new_pid(self):
        for fixture in GAME_FIXTURES:
            with self.subTest(game=fixture.game_id), self.game(fixture) as game:
                game.identity = None
                backend = game.backend()
                backend.open()
                self.lose_action(backend)
                pending = game.pending_bytes()
                game.identity = 'birth-B'
                self.assert_blocked(game.backend().open)
                self.assertEqual(game.pending_bytes(), pending)
                game.pid = 4343
                game.backend().open()
                self.assertIsNone(game.pending_bytes())
                self.assertEqual([call.request_id for call in game.actions()], ['once'])

    def test_legacy_wall_clock_cannot_be_compared_with_tagged_utc_at_the_same_pid(self):
        for fixture in GAME_FIXTURES:
            with self.subTest(game=fixture.game_id), self.game(fixture) as game:
                backend = game.backend()
                backend.open()
                self.lose_action(backend)
                # Model the identity field written by an older backend, using
                # the real journal's remaining format and pending request.
                legacy = json.loads(game.pending_bytes())
                legacy['identity'] = 'Wed Nov 25 09:00:00 2026'
                game.journal_path.write_text(json.dumps(legacy), encoding='utf-8')
                pending = game.pending_bytes()
                game.identity = 'ps-utc-v1:Wed Nov 25 17:00:00 2026'
                restarted = game.backend()
                self.assert_blocked(restarted.open)
                self.assertEqual(restarted.boundary.calls, [])
                self.assertEqual(game.pending_bytes(), pending)
                game.pid = 4343
                game.backend().open()
                self.assertIsNone(game.pending_bytes())
                self.assertEqual([call.request_id for call in game.actions()], ['once'])

    def test_crash_before_reply_has_already_persisted_uncertainty(self):
        for fixture in GAME_FIXTURES:
            with self.subTest(game=fixture.game_id), self.game(fixture) as game:
                backend = game.backend()
                backend.open()
                observed_at_boundary = []
                backend.boundary.before_reply = lambda: observed_at_boundary.append(game.pending_bytes())
                backend.boundary.failure = 'crash'
                with self.assertRaises(BackendExit):
                    backend.action('crashed-action')
                self.assertIsNotNone(observed_at_boundary[0])
                pending = game.pending_bytes()
                self.assertEqual(observed_at_boundary, [pending])
                restarted = game.backend()
                self.assert_blocked(restarted.open)
                self.assertEqual(restarted.boundary.calls, [])
                self.assertEqual(game.pending_bytes(), pending)
                self.assertEqual([call.request_id for call in game.actions()], ['crashed-action'])

    def test_status_maintenance_is_protected_against_a_lost_reply(self):
        for fixture in GAME_FIXTURES:
            with self.subTest(game=fixture.game_id), self.game(fixture) as game:
                backend = game.backend()
                backend.open()
                backend.boundary.failure = 'unknown'
                self.assert_blocked(backend.status)
                self.assertEqual(game.calls[-1].method, 'status')
                pending = game.pending_bytes()
                self.assertIsNotNone(pending)
                restarted = game.backend()
                self.assert_blocked(restarted.open)
                self.assertEqual(restarted.boundary.calls, [])
                self.assertEqual(game.pending_bytes(), pending)
                self.assertEqual(game.actions(), [])

    def test_late_old_reply_cannot_clear_replacement_lifetime_journal(self):
        for fixture in GAME_FIXTURES:
            with self.subTest(game=fixture.game_id), self.game(fixture) as game:
                old = game.backend()
                old.open()
                replacement_records = []

                def replace_before_reply():
                    game.identity = 'birth-B'
                    replacement = game.backend()
                    replacement.open()
                    self.lose_action(replacement, 'replacement-action')
                    replacement_records.append(game.pending_bytes())

                old.boundary.before_reply = replace_before_reply
                try:
                    old.action('old-action')
                except AdapterError:
                    # A client can reject its obsolete reply. The shared rule
                    # is that it cannot retire the replacement's uncertainty.
                    pass
                self.assertEqual(len(replacement_records), 1)
                self.assertIsNotNone(replacement_records[0])
                self.assertEqual(game.pending_bytes(), replacement_records[0])
                boundary_count = len(game.calls)
                with self.assertRaises(AdapterError) as raised:
                    old.action('late-followup')
                self.assertIn(raised.exception.code, ('restart_required', 'outcome_unknown', 'disconnected'))
                restarted = game.backend()
                self.assert_blocked(restarted.open)
                self.assertEqual(len(game.calls), boundary_count)
                self.assertEqual(game.pending_bytes(), replacement_records[0])
                self.assertEqual([call.request_id for call in game.actions()], ['old-action', 'replacement-action'])

    def test_completed_action_is_never_replayed_on_backend_restart(self):
        for fixture in GAME_FIXTURES:
            with self.subTest(game=fixture.game_id), self.game(fixture) as game:
                backend = game.backend()
                backend.open()
                backend.action('confirmed-once')
                self.assertIsNone(game.pending_bytes())
                restarted = game.backend()
                restarted.open()
                restarted.status()
                self.assertIsNone(game.pending_bytes())
                self.assertEqual([call.request_id for call in game.actions()], ['confirmed-once'])


if __name__ == '__main__':
    unittest.main()
