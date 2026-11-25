"""Recovery survives a backend restart without repeating a game operation."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from core.adapter import AdapterError
from games.hades2.adapter import Hades2Adapter
from games.hades2.resident_session import ResidentConnectionError
from games.hades2.preferences import Hades2PreferenceStore
from hades2_resident_session_fakes import FakeTimeWarpController, hades2_adapter_context


def observation(**changes):
    result = {
        'status': 'ready', 'scene': 'run', 'capabilities': {'setFeature': True},
        'desiredFeatures': {}, 'activeFeatures': {}, 'dormantFeatures': {},
        'featureSupport': {}, 'featureErrors': {}, 'resources': [], 'elements': [],
        'stats': {}, 'boonRarity': {}, 'gatheringProbabilities': {},
        'chaosGateProbability': None,
    }
    result.update(changes)
    return result


class FixtureTransport:
    """Only records calls and returns disposable resident observations."""
    def __init__(self, result=None, acknowledge=None):
        self.pid = os.getpid()
        self.live = True
        self.tainted = False
        self.last_duration = 0.001
        self.last_attach_profile = {}
        self.calls = []
        self.result = observation() if result is None else result
        self.acknowledge = acknowledge
        self.speed = FakeTimeWarpController()

    def alive(self):
        return self.live

    def attach(self, pid):
        self.pid = pid
        self.live = True

    def detach(self):
        self.pid = None
        self.live = False

    def close(self):
        self.detach()

    def execute(self, source, **kwargs):
        self.calls.append(source)
        if isinstance(self.result, BaseException):
            raise self.result
        result = self.result() if callable(self.result) else self.result
        return result if isinstance(result, str) else json.dumps(copy.deepcopy(result))

    def acknowledge_result(self):
        if self.acknowledge is not None:
            self.acknowledge()

    def create_time_warp_controller(self, *args):
        return self.speed


class DurableRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='mgt-hades2-recovery-')
        self.addCleanup(self.temporary.cleanup)
        self.context = hades2_adapter_context(self.temporary.name)

    def adapter(self, transport, identity=None):
        kwargs = {'identity': identity} if identity is not None else {}
        return Hades2Adapter(context=self.context, transport=transport, **kwargs)

    def test_unknown_reply_survives_backend_restart(self):
        failed = FixtureTransport(AdapterError('outcome_unknown', 'hades2.error.outcomeUnknownGeneric'))
        with self.assertRaises(AdapterError):
            self.adapter(failed).execute('spawn_reward', {'reward': 'Money', 'requestId': 'once'})
        restarted = FixtureTransport()
        adapter = self.adapter(restarted)
        with self.assertRaises(AdapterError) as raised:
            adapter.execute('set_rerolls', {'amount': 99, 'requestId': 'later'})
        self.assertEqual(raised.exception.code, 'outcome_unknown')
        self.assertEqual(restarted.calls, [], 'backend restart submitted a mutation after unknown outcome')
        self.assertEqual(adapter.state['status'], 'restart_required')
        self.assertEqual(adapter.state['recovery']['method'], 'spawn_reward')

    def test_confirmed_action_is_distinct_after_backend_restart(self):
        def lose_acknowledgement():
            raise OSError('connection failed after the action receipt was decoded')

        transport = FixtureTransport(observation(
            requestId='once', applied=True, actionOutcome='completed',
        ), acknowledge=lose_acknowledgement)
        with self.assertRaises(ResidentConnectionError):
            self.adapter(transport).execute('spawn_reward', {'reward': 'Money', 'requestId': 'once'})
        restarted = self.adapter(FixtureTransport())
        self.assertEqual(restarted.state.get('recovery', {}).get('outcome'), 'confirmed')
        self.assertEqual(restarted.state['recovery']['method'], 'spawn_reward')
        self.assertEqual(restarted.state['recovery']['requestId'], 'once')

    def test_crash_during_request_is_already_durable(self):
        class BackendExit(BaseException):
            pass

        def crash():
            raise BackendExit()

        transport = FixtureTransport(crash)
        with self.assertRaises(BackendExit):
            self.adapter(transport).execute('spawn_reward', {'requestId': 'once'})
        restarted = FixtureTransport()
        with self.assertRaises(AdapterError) as raised:
            self.adapter(restarted).observe_runtime()
        self.assertEqual(raised.exception.code, 'outcome_unknown')
        self.assertEqual(restarted.calls, [])

    def test_crash_during_ack_retains_confirmed_receipt(self):
        class BackendExit(BaseException):
            pass

        def crash():
            raise BackendExit()

        transport = FixtureTransport(observation(actionOutcome='completed'), acknowledge=crash)
        with self.assertRaises(BackendExit):
            self.adapter(transport).execute('spawn_reward', {'requestId': 'once'})
        restarted = self.adapter(FixtureTransport())
        self.assertEqual(restarted.state['recovery']['outcome'], 'confirmed')
        self.assertEqual(restarted.state['recovery']['receipt']['actionOutcome'], 'completed')

    def test_only_positive_new_lifetime_retires_unknown(self):
        failed = FixtureTransport(AdapterError('outcome_unknown', 'hades2.error.outcomeUnknownGeneric'))
        with self.assertRaises(AdapterError):
            self.adapter(failed, identity=lambda pid: 'birth-A').execute('spawn_reward', {})
        original = (self.context.data_dir / 'runtime-recovery.json').read_bytes()
        for identity in ('birth-A', None, '', '  ', 'birth-A\nbirth-B'):
            restarted = FixtureTransport()
            with self.assertRaises(AdapterError):
                self.adapter(restarted, identity=lambda pid: identity).observe_runtime()
            self.assertEqual(restarted.calls, [])
            self.assertEqual((self.context.data_dir / 'runtime-recovery.json').read_bytes(), original)
        replacement = FixtureTransport()
        self.adapter(replacement, identity=lambda pid: 'birth-B').observe_runtime()
        self.assertEqual(len(replacement.calls), 1)
        self.assertFalse((self.context.data_dir / 'runtime-recovery.json').exists())

    def test_backend_timezone_change_cannot_release_the_same_process(self):
        with patch.dict(os.environ, {'TZ': 'UTC', 'LC_ALL': 'C'}):
            transport = FixtureTransport(AdapterError('outcome_unknown', 'hades2.error.outcomeUnknownGeneric'))
            with self.assertRaises(AdapterError):
                self.adapter(transport).execute('spawn_reward', {'requestId': 'once'})
        path = self.context.data_dir / 'runtime-recovery.json'
        before = path.read_bytes()
        with patch.dict(os.environ, {'TZ': 'America/Los_Angeles', 'LC_ALL': 'C'}):
            restarted = FixtureTransport()
            with self.assertRaises(AdapterError):
                self.adapter(restarted).execute('spawn_reward', {'requestId': 'must-not-run'})
        self.assertEqual(restarted.calls, [])
        self.assertEqual(path.read_bytes(), before)

    def test_late_old_reply_cannot_clear_new_lifetime(self):
        new_transport = FixtureTransport(AdapterError('outcome_unknown', 'hades2.error.outcomeUnknownGeneric'))

        def reply_after_replacement():
            with self.assertRaises(AdapterError):
                self.adapter(new_transport, identity=lambda pid: 'birth-B').execute('spawn_reward', {'requestId': 'new'})
            return observation(actionOutcome='completed')

        old_transport = FixtureTransport(reply_after_replacement)
        with self.assertRaises(AdapterError):
            self.adapter(old_transport, identity=lambda pid: 'birth-A').execute('spawn_reward', {'requestId': 'old'})
        restored = self.adapter(FixtureTransport(), identity=lambda pid: 'birth-B')
        self.assertEqual(restored.state['recovery']['requestId'], 'new')
        self.assertEqual(restored.state['recovery']['outcome'], 'unknown')
        with self.assertRaises(AdapterError):
            restored.observe_runtime()

    def test_late_reply_terminalizes_superseded_session(self):
        def reply_after_replacement():
            self.adapter(FixtureTransport(), identity=lambda pid: 'birth-B').observe_runtime()
            return observation(actionOutcome='completed')

        transport = FixtureTransport(reply_after_replacement)
        adapter = self.adapter(transport, identity=lambda pid: 'birth-A')
        with self.assertRaises(AdapterError):
            adapter.execute('spawn_reward', {'requestId': 'old'})
        transport.result = observation()
        with self.assertRaises(AdapterError):
            adapter.execute('spawn_reward', {'requestId': 'stale-again'})
        self.assertEqual(len(transport.calls), 1, 'superseded session crossed a new game boundary')

    def test_confirmed_recovery_reapplies_only_durable_settings_after_ready(self):
        def lost_ack():
            raise OSError('receipt release lost')

        with self.assertRaises(ResidentConnectionError):
            self.adapter(FixtureTransport(observation(actionOutcome='completed'), lost_ack)).execute(
                'spawn_reward', {'reward': 'Money', 'requestId': 'never-replay'})
        desired = Hades2PreferenceStore.defaults()
        desired.update(invincibility=True, gameSpeed=2.0)
        Hades2PreferenceStore(self.context.data_dir / 'desired-state.json').save(desired)
        transport = FixtureTransport(AdapterError('waiting', 'hades2.error.notConnected'))
        adapter = self.adapter(transport)
        with self.assertRaises(AdapterError) as waiting:
            adapter.execute('status', {})
        self.assertEqual(waiting.exception.code, 'waiting')
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(transport.speed.calls, [])
        self.assertEqual(adapter.state['recovery']['outcome'], 'confirmed')
        transport.result = observation()
        recovered = adapter.dispatch('status', {}, 'ready-status')
        self.assertTrue(any('observeBatch' in source for source in transport.calls))
        self.assertTrue(any('invincibility' in source for source in transport.calls))
        self.assertEqual(transport.speed.calls, [('set', 2.0)])
        self.assertFalse(any('never-replay' in source or 'Money' in source and 'spawn_reward' in source.split('return __MacGamingTrainerV1.json')[-1]
                             for source in transport.calls))
        self.assertIn('recovery', recovered, 'full status snapshot did not clear the previous recovery notice')
        self.assertIsNone(recovered['recovery'])

    def test_resident_cleanup_restart_stop_survives_backend_restart(self):
        transport = FixtureTransport(AdapterError(
            'lua_error', 'MGT_RESIDENT_RESTART_REQUIRED: previous resident cleanup failed'))
        with self.assertRaises(AdapterError) as raised:
            self.adapter(transport).observe_runtime()
        self.assertEqual(raised.exception.code, 'restart_required')
        restarted = FixtureTransport()
        with self.assertRaises(AdapterError):
            self.adapter(restarted).execute('spawn_reward', {})
        self.assertEqual(restarted.calls, [])

    def test_status_decode_failure_blocks_after_restart(self):
        with self.assertRaises(AdapterError):
            self.adapter(FixtureTransport('{broken')).observe_runtime()
        transport = FixtureTransport()
        with self.assertRaises(AdapterError):
            self.adapter(transport).observe_runtime()
        self.assertEqual(transport.calls, [])

    def test_time_warp_unknown_survives_backend_restart(self):
        transport = FixtureTransport()
        adapter = self.adapter(transport)
        adapter.observe_runtime()
        transport.speed.error = AdapterError('outcome_unknown', 'hades2.error.outcomeUnknownGeneric')
        adapter.set_desired('gameSpeed', 2.0)
        restarted = FixtureTransport()
        with self.assertRaises(AdapterError):
            self.adapter(restarted).execute('status', {})
        self.assertEqual(restarted.calls, [])

    def test_post_execution_cleanup_failure_keeps_uncertainty(self):
        for code in ('resume_failed', 'process_timeout', 'stop_failed'):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as temporary:
                context = hades2_adapter_context(temporary)
                transport = FixtureTransport()

                def cleanup_failure():
                    transport.tainted = True
                    raise AdapterError(code, 'hades2.error.resumeUnverified')

                transport.result = cleanup_failure
                adapter = Hades2Adapter(context=context, transport=transport)
                with self.assertRaises(AdapterError):
                    adapter.execute('spawn_reward', {'requestId': 'ran-before-cleanup'})
                restarted = FixtureTransport()
                with self.assertRaises(AdapterError) as raised:
                    Hades2Adapter(context=context, transport=restarted).execute('spawn_reward', {})
                self.assertEqual(raised.exception.code, 'outcome_unknown')
                self.assertEqual(restarted.calls, [])

    def test_time_warp_cleanup_failure_keeps_uncertainty(self):
        transport = FixtureTransport()
        adapter = self.adapter(transport)
        adapter.observe_runtime()

        def cleanup_failure(value):
            transport.tainted = True
            raise AdapterError('resume_failed', 'hades2.error.resumeUnverified')

        transport.speed.set_speed = cleanup_failure
        adapter.set_desired('gameSpeed', 2.0)
        restarted = FixtureTransport()
        with self.assertRaises(AdapterError):
            self.adapter(restarted).execute('status', {})
        self.assertEqual(restarted.calls, [])

    def test_time_warp_confirmed_result_survives_journal_retirement_failure(self):
        transport = FixtureTransport()
        adapter = self.adapter(transport)
        adapter.observe_runtime()
        original_unlink = Path.unlink
        recovery_path = self.context.data_dir / 'runtime-recovery.json'

        def fail_recovery_retirement(path, *args, **kwargs):
            if path == recovery_path:
                raise OSError('fixture retirement failure')
            return original_unlink(path, *args, **kwargs)

        with patch.object(Path, 'unlink', fail_recovery_retirement):
            result = adapter.set_desired('gameSpeed', 2.0)
        self.assertEqual(transport.speed.speed, 2.0)
        self.assertEqual(result['status'], 'restart_required')
        self.assertEqual(result['recovery']['outcome'], 'confirmed')
        self.assertEqual(self.adapter(FixtureTransport()).state['recovery']['outcome'], 'confirmed')

    def test_late_time_warp_error_closes_the_superseded_session(self):
        transport = FixtureTransport()
        adapter = self.adapter(transport, identity=lambda pid: 'birth-A')
        adapter.observe_runtime()

        def stale_failure(value):
            self.adapter(FixtureTransport(), identity=lambda pid: 'birth-B').observe_runtime()
            raise AdapterError('time_warp_set_failed', 'hades2.error.notConnected')

        transport.speed.set_speed = stale_failure
        adapter.set_desired('gameSpeed', 2.0)
        calls = []
        transport.speed.set_speed = lambda value: calls.append(value) or value
        adapter.set_desired('gameSpeed', 3.0)
        self.assertEqual(calls, [], 'superseded Time Warp session crossed another mutation boundary')

    def test_future_schema_and_corruption_are_preserved(self):
        path = self.context.data_dir / 'runtime-recovery.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        for content in ('{"schemaVersion": 999}', '{broken'):
            path.write_text(content)
            transport = FixtureTransport()
            adapter = self.adapter(transport)
            with self.assertRaises(AdapterError) as raised:
                adapter.execute('status', {})
            self.assertEqual(raised.exception.code, 'recovery_failed')
            self.assertEqual(path.read_text(), content)
            self.assertEqual(transport.calls, [])


if __name__ == '__main__':
    unittest.main()
