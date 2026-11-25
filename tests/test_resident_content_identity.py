"""Loaded resident content changes cannot silently reuse a stale game module."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from core.adapter import AdapterError
from games.hades.lldb_worker import HadesLLDBWorker
from games.hades2.recovery import Hades2RecoveryJournal
from games.hades2.resident_session import Hades2ResidentSession
from games.hades2.runtime_error_presentation import present_runtime_error
from hades_lua_fixture import PersistentGameLua
from hades2_lua_observation_fixture import LuaObservationTransport


class ResidentContentIdentity(unittest.TestCase):
    @staticmethod
    def configure_async_sell(transport, *, fails):
        transport.evaluate(
            'SessionState.fixturePending={}; SessionState.fixtureSellCalls=0; '
            'thread=function(fn) table.insert(SessionState.fixturePending,fn) end; '
            'AreScreensActive=function() return false end; ShowRerollUI=function() end; '
            'for _, name in ipairs({"AltAspectRatioFramesHide","OnScreenCloseStarted","SetAnimation",'
            '"UseableOff","CloseScreen","GetAllIds","OnScreenCloseFinished","ShowCombatUI",'
            '"SetPlayerVulnerable","SetupCostume"}) do _G[name]=function() end end; '
            'ScreenData.SellTraits={ComponentData={ActionBar={Children={CloseButton={Data={}}}}}}; '
            'OpenSellTraitMenu=function() SessionState.fixtureSellCalls=SessionState.fixtureSellCalls+1; '
            'CurrentRun.Hero.Health=25; ' + ('error("native fault after commit"); ' if fails else '') + 'end'
        )

    def test_hades_same_content_retains_resident_and_changed_content_requires_restart(self):
        game = PersistentGameLua()
        game.attach(42, '/fixture/Hades')
        original = HadesLLDBWorker(game)
        original.dispatch('status', {})
        game.native('local resident=MacGamingTrainerHades; '
                    'GameState.fixtureResident=resident; '
                    'local status=resident.status; '
                    'resident.status=function() GameState.fixtureObserved=true; return status() end')
        restarted_backend = HadesLLDBWorker(game)
        restarted_backend.dispatch('status', {})
        self.assertEqual(game.value('MacGamingTrainerHades==GameState.fixtureResident'), 'true')
        changed_source = (ROOT / 'Backend/games/hades/runtime.lua').read_text() + '\n-- updated local build\n'
        with patch('games.hades.lldb_worker.Path.read_text', return_value=changed_source):
            updated_backend = HadesLLDBWorker(game)
        game.native('GameState.fixtureObserved=nil')
        with self.assertRaises(AdapterError) as raised:
            updated_backend.dispatch('status', {})
        self.assertEqual(raised.exception.code, 'restart_required')
        self.assertEqual(game.value('GameState.fixtureObserved==nil'), 'true')
        self.assertEqual(game.value('MacGamingTrainerHades==GameState.fixtureResident'), 'true')
        game.lua_reset()
        updated_backend.dispatch('status', {})
        self.assertEqual(game.value('MacGamingTrainerHades.revision'),
                         hashlib.sha256(changed_source.encode('utf-8')).hexdigest())

    def test_hades2_same_content_retains_resident_and_changed_content_replaces_once(self):
        transport = LuaObservationTransport()
        self.addCleanup(transport.close)
        source = (ROOT / 'Backend/games/hades2/runtime/hades.lua').read_text()
        Hades2ResidentSession(transport, bootstrap=source).status()
        transport.evaluate('SessionState.fixtureResident=__MacGamingTrainerV1; '
                           'SessionState.fixtureCleanupCount=0; '
                           'local dispatch=__MacGamingTrainerV1.dispatch; '
                           '__MacGamingTrainerV1.dispatch=function(command, ...) '
                           'if command=="cleanup" then SessionState.fixtureCleanupCount=SessionState.fixtureCleanupCount+1 end; '
                           'return dispatch(command, ...) end')
        Hades2ResidentSession(transport, bootstrap=source).status()
        self.assertEqual(transport.execute('return tostring(__MacGamingTrainerV1==SessionState.fixtureResident)'), 'true')
        self.assertEqual(transport.execute('return tostring(SessionState.fixtureCleanupCount)'), '0')
        changed_source = source + '\n-- updated local build\n'
        Hades2ResidentSession(transport, bootstrap=changed_source).status()
        self.assertEqual(transport.execute('return tostring(__MacGamingTrainerV1==SessionState.fixtureResident)'), 'false')
        self.assertEqual(transport.execute('return tostring(SessionState.fixtureCleanupCount)'), '1')
        expected = hashlib.sha256(changed_source.encode('utf-8')).hexdigest()
        self.assertEqual(transport.execute('return __MacGamingTrainerV1.revision'), expected)
        transport.evaluate('SessionState.fixtureResident=__MacGamingTrainerV1')
        Hades2ResidentSession(transport, bootstrap=changed_source).status()
        self.assertEqual(transport.execute('return tostring(__MacGamingTrainerV1==SessionState.fixtureResident)'), 'true')
        self.assertEqual(transport.execute('return tostring(SessionState.fixtureCleanupCount)'), '1')


    def test_hades2_legacy_revision_upgrades_without_discarding_receipts(self):
        transport = LuaObservationTransport()
        self.addCleanup(transport.close)
        Hades2ResidentSession(transport).status()
        transport.evaluate('__MacGamingTrainerV1.revision=143; __MacGamingTrainerV1.retainsPendingActions=nil; '
                           '__MacGamingTrainerV1.requests.fixture={state="complete",command="spawn_reward"}; '
                           'SessionState.fixtureReceipts=__MacGamingTrainerV1.requests; '
                           'SessionState.fixtureResident=__MacGamingTrainerV1')
        Hades2ResidentSession(transport).status()
        self.assertEqual(transport.execute('return tostring(__MacGamingTrainerV1==SessionState.fixtureResident)'), 'false')
        self.assertEqual(transport.execute('return tostring(__MacGamingTrainerV1.requests==SessionState.fixtureReceipts)'), 'true')
        self.assertEqual(transport.execute('return __MacGamingTrainerV1.requests.fixture.state'), 'complete')

    def test_hades2_failed_cleanup_preserves_old_ownership(self):
        transport = LuaObservationTransport()
        self.addCleanup(transport.close)
        Hades2ResidentSession(transport).status()
        transport.evaluate('SessionState.fixtureResident=__MacGamingTrainerV1; '
                           'local dispatch=__MacGamingTrainerV1.dispatch; '
                           '__MacGamingTrainerV1.dispatch=function(command, ...) '
                           'if command=="cleanup" then error("fixture cleanup failure") end; '
                           'return dispatch(command, ...) end')
        source = (ROOT / 'Backend/games/hades2/runtime/hades.lua').read_text() + '\n-- update\n'
        with self.assertRaises(AdapterError) as raised:
            Hades2ResidentSession(transport, bootstrap=source).status()
        self.assertEqual(raised.exception.code, 'restart_required')
        self.assertEqual(raised.exception.presentation, 'hades2.error.residentCleanupFailed')
        self.assertEqual(transport.execute('return tostring(__MacGamingTrainerV1==SessionState.fixtureResident)'), 'true')

    def test_hades2_unknown_async_action_refuses_replacement_before_native_cleanup(self):
        transport = LuaObservationTransport()
        self.addCleanup(transport.close)
        source = (ROOT / 'Backend/games/hades2/runtime/hades.lua').read_text()
        with tempfile.TemporaryDirectory(prefix='mgt-content-recovery-') as temporary:
            path = Path(temporary) / 'recovery.json'

            def session(bootstrap):
                return Hades2ResidentSession(
                    transport, bootstrap=bootstrap,
                    recovery=Hades2RecoveryJournal(path, identity=lambda pid: 'birth-A'),
                )

            original = session(source)
            original.status()
            transport.evaluate(
                'SessionState.fixtureSpeed=100; SessionState.fixtureNativeCalls=0; '
                'SetUnitProperty=function(args) if args.Property=="Speed" then '
                'SessionState.fixtureNativeCalls=SessionState.fixtureNativeCalls+1; '
                'SessionState.fixtureSpeed=SessionState.fixtureSpeed*args.Value end end'
            )
            original.mutate('set_stat', {'stat': 'moveSpeed', 'locked': True, 'value': 200})
            self.assertEqual(transport.execute('return tostring(SessionState.fixtureSpeed)'), '200')
            self.configure_async_sell(transport, fails=True)
            accepted = original.mutate('open_sell_traits', {'requestId': 'async'})
            self.assertEqual(accepted.payload['actionOutcome'], 'accepted')
            self.assertFalse(path.exists())
            # An accepted asynchronous action can turn unknown before the next
            # Host observation, after its accepted receipt left the journal.
            transport.evaluate(
                'SessionState.fixtureResident=__MacGamingTrainerV1; SessionState.fixtureNativeCalls=0; '
                'SessionState.fixturePending[1]()'
            )
            changed_source = source + '\n-- updated local build\n'
            with self.assertRaises(AdapterError) as raised:
                session(changed_source).status()
            self.assertEqual(raised.exception.code, 'outcome_unknown')
            state = json.loads(transport.execute(
                'return __MacGamingTrainerV1.json({'
                'sameOwner=__MacGamingTrainerV1==SessionState.fixtureResident,'
                'unknown=__MacGamingTrainerV1.terminalActionUnknown,'
                'nativeCalls=SessionState.fixtureNativeCalls,speed=SessionState.fixtureSpeed,'
                'receipt=__MacGamingTrainerV1.lastActionReceipt})'
            ))
            self.assertTrue(state['sameOwner'])
            self.assertTrue(state['unknown'])
            self.assertEqual(state['nativeCalls'], 0)
            self.assertEqual(state['speed'], 200)
            self.assertEqual(state['receipt']['requestId'], 'async')
            self.assertEqual(state['receipt']['outcome'], 'outcome_unknown')
            self.assertEqual(Hades2RecoveryJournal(path).describe()['outcome'], 'unknown')
            pending = path.read_bytes()
            restarted = session(changed_source)
            with patch.object(transport, 'execute', wraps=transport.execute) as execute:
                for operation in (
                    restarted.status,
                    lambda: restarted.mutate('set_stat', {'stat': 'moveSpeed', 'locked': True, 'value': 300}),
                ):
                    with self.assertRaises(AdapterError) as blocked:
                        operation()
                    self.assertEqual(blocked.exception.code, 'outcome_unknown')
                execute.assert_not_called()
            self.assertEqual(path.read_bytes(), pending)

    def test_hades2_pending_action_keeps_its_resident_until_the_callback_finishes(self):
        source = (ROOT / 'Backend/games/hades2/runtime/hades.lua').read_text()
        for fails, completed_count in ((True, 1), (False, 1), (True, 128), (False, 128)):
            with self.subTest(fails=fails, completed_count=completed_count), \
                    tempfile.TemporaryDirectory(prefix='mgt-content-pending-') as temporary:
                transport = LuaObservationTransport()
                self.addCleanup(transport.close)
                path = Path(temporary) / 'recovery.json'

                def session(bootstrap):
                    return Hades2ResidentSession(
                        transport, bootstrap=bootstrap,
                        recovery=Hades2RecoveryJournal(path, identity=lambda pid: 'birth-A'),
                    )

                original = session(source)
                original.status()
                self.configure_async_sell(transport, fails=fails)
                accepted = original.mutate('open_sell_traits', {'requestId': 'modal'})
                self.assertEqual(accepted.payload['actionOutcome'], 'accepted')
                # A later completed request replaces lastAction, while the
                # modal action still belongs to its original queued callback.
                completed = original.mutate('set_rerolls', {'amount': 77, 'requestId': 'later'})
                self.assertEqual(completed.payload['actionOutcome'], 'completed')
                transport.evaluate(
                    'for i=2,' + str(completed_count) + ' do '
                    '__MacGamingTrainerV1.dispatch("set_rerolls",{amount=77,requestId="later-"..i}) end'
                )
                transport.evaluate(
                    'SessionState.fixtureResident=__MacGamingTrainerV1; SessionState.fixtureCleanupCalls=0; '
                    'local dispatch=__MacGamingTrainerV1.dispatch; '
                    '__MacGamingTrainerV1.dispatch=function(command, ...) '
                    'if command=="cleanup" then SessionState.fixtureCleanupCalls=SessionState.fixtureCleanupCalls+1 end; '
                    'return dispatch(command, ...) end'
                )
                changed_source = source + '\n-- pending-action update\n'
                updated = session(changed_source)
                with self.assertRaises(AdapterError) as refused:
                    updated.status()
                self.assertEqual(refused.exception.code, 'lua_error')
                self.assertEqual(present_runtime_error('status', refused.exception).presentation,
                                 'hades2.error.residentActionPending')
                self.assertFalse(transport.tainted)
                self.assertFalse(path.exists(), 'pending acceptance was classified as unknown')
                state = json.loads(transport.execute(
                    'return __MacGamingTrainerV1.json({'
                    'sameOwner=__MacGamingTrainerV1==SessionState.fixtureResident,'
                    'unknown=__MacGamingTrainerV1.terminalActionUnknown,'
                    'cleanupCalls=SessionState.fixtureCleanupCalls,sellCalls=SessionState.fixtureSellCalls})'
                ))
                self.assertTrue(state['sameOwner'])
                self.assertFalse(state['unknown'])
                self.assertEqual(state['cleanupCalls'], 0)
                self.assertEqual(state['sellCalls'], 0)
                self.assertEqual(transport.execute('return tostring(#__MacGamingTrainerV1.requestOrder)'),
                                 str(completed_count + 1))

                transport.evaluate('SessionState.fixturePending[1]()')
                observed = session(source).status()
                self.assertEqual(observed.outcome_unknown, fails)
                self.assertEqual(observed.payload['lastAction']['requestId'], 'modal')
                self.assertEqual(observed.payload['lastAction']['outcome'], 'outcome_unknown' if fails else 'opened')
                self.assertEqual(transport.execute('return tostring(SessionState.fixtureSellCalls)'), '1')
                self.assertEqual(transport.execute('return tostring(CurrentRun.Hero.Health)'), '25')
                self.assertEqual(transport.execute('return tostring(#__MacGamingTrainerV1.requestOrder)'),
                                 str(min(completed_count + 1, 128)))
                if fails:
                    self.assertEqual(Hades2RecoveryJournal(path).describe()['outcome'], 'unknown')
                    pending = path.read_bytes()
                    restarted = session(changed_source)
                    with patch.object(transport, 'execute', wraps=transport.execute) as execute:
                        for operation in (
                            restarted.status,
                            lambda: restarted.mutate('set_rerolls', {'amount': 99, 'requestId': 'blocked'}),
                        ):
                            with self.assertRaises(AdapterError) as blocked:
                                operation()
                            self.assertEqual(blocked.exception.code, 'outcome_unknown')
                        execute.assert_not_called()
                    self.assertEqual(path.read_bytes(), pending)
                else:
                    updated.status()
                    self.assertEqual(transport.execute(
                        'return tostring(__MacGamingTrainerV1==SessionState.fixtureResident)'), 'false')
                    self.assertEqual(transport.execute('return tostring(SessionState.fixtureCleanupCalls)'), '1')
                    duplicate = updated.mutate('open_sell_traits', {'requestId': 'modal'})
                    self.assertTrue(duplicate.payload['duplicate'])
                    self.assertEqual(duplicate.payload['actionOutcome'], 'opened')
                    self.assertEqual(transport.execute('return tostring(SessionState.fixtureSellCalls)'), '1')
                    self.assertFalse(path.exists())

    def test_hades2_full_legacy_ledger_requires_restart_before_replacement(self):
        transport = LuaObservationTransport()
        self.addCleanup(transport.close)
        source = (ROOT / 'Backend/games/hades2/runtime/hades.lua').read_text()
        with tempfile.TemporaryDirectory(prefix='mgt-content-legacy-') as temporary:
            path = Path(temporary) / 'recovery.json'

            def session():
                return Hades2ResidentSession(
                    transport, bootstrap=source,
                    recovery=Hades2RecoveryJournal(path, identity=lambda pid: 'birth-A'),
                )

            original = session()
            original.status()
            transport.evaluate(
                'SessionState.fixtureSpeed=100; SessionState.fixtureNativeCalls=0; '
                'SetUnitProperty=function(args) if args.Property=="Speed" then '
                'SessionState.fixtureNativeCalls=SessionState.fixtureNativeCalls+1; '
                'SessionState.fixtureSpeed=SessionState.fixtureSpeed*args.Value end end'
            )
            original.mutate('set_stat', {'stat': 'moveSpeed', 'locked': True, 'value': 200})
            # Before pending retention existed, the same full ledger could
            # have silently discarded an accepted callback. Its remaining
            # terminal receipts cannot prove that the old owner is idle.
            transport.evaluate(
                'ShowRerollUI=function() end; '
                'for i=1,128 do __MacGamingTrainerV1.dispatch("set_rerolls",'
                '{amount=77,requestId="legacy-"..i}) end; '
                '__MacGamingTrainerV1.revision=143; __MacGamingTrainerV1.retainsPendingActions=nil; '
                'SessionState.fixtureResident=__MacGamingTrainerV1; SessionState.fixtureNativeCalls=0'
            )
            with self.assertRaises(AdapterError) as refused:
                session().status()
            self.assertEqual(refused.exception.code, 'restart_required')
            self.assertEqual(refused.exception.presentation, 'hades2.error.residentCleanupFailed')
            self.assertEqual(transport.execute(
                'return tostring(__MacGamingTrainerV1==SessionState.fixtureResident)'), 'true')
            self.assertEqual(transport.execute('return tostring(SessionState.fixtureNativeCalls)'), '0')
            self.assertEqual(transport.execute('return tostring(SessionState.fixtureSpeed)'), '200')
            self.assertEqual(Hades2RecoveryJournal(path).describe()['outcome'], 'unknown')
            pending = path.read_bytes()
            restarted = session()
            with patch.object(transport, 'execute', wraps=transport.execute) as execute:
                for operation in (
                    restarted.status,
                    lambda: restarted.mutate('set_rerolls', {'amount': 99, 'requestId': 'blocked'}),
                ):
                    with self.assertRaises(AdapterError) as blocked:
                        operation()
                    self.assertEqual(blocked.exception.code, 'outcome_unknown')
                execute.assert_not_called()
            self.assertEqual(path.read_bytes(), pending)

    def test_hades2_legacy_unknown_receipt_survives_a_missing_terminal_flag(self):
        transport = LuaObservationTransport()
        self.addCleanup(transport.close)
        with tempfile.TemporaryDirectory(prefix='mgt-content-legacy-unknown-') as temporary:
            path = Path(temporary) / 'recovery.json'

            def session():
                return Hades2ResidentSession(
                    transport, recovery=Hades2RecoveryJournal(path, identity=lambda pid: 'birth-A'),
                )

            original = session()
            original.status()
            self.configure_async_sell(transport, fails=True)
            self.assertEqual(original.mutate('open_sell_traits', {'requestId': 'modal'}).payload['actionOutcome'],
                             'accepted')
            transport.evaluate('SessionState.fixturePending[1]()')
            # A legacy replacement shared request rows, while an old callback
            # still updated its old resident's terminal flag and last receipt.
            # Preserve the exact incomplete evidence left in the replacement.
            transport.evaluate(
                '__MacGamingTrainerV1.terminalActionUnknown=false; __MacGamingTrainerV1.lastActionReceipt=nil; '
                '__MacGamingTrainerV1.revision=143; __MacGamingTrainerV1.retainsPendingActions=nil; '
                'SessionState.fixtureResident=__MacGamingTrainerV1'
            )
            self.assertEqual(transport.execute('return __MacGamingTrainerV1.requests.modal.status'), 'outcome_unknown')
            with self.assertRaises(AdapterError) as refused:
                session().status()
            self.assertEqual(refused.exception.code, 'outcome_unknown')
            self.assertEqual(transport.execute(
                'return tostring(__MacGamingTrainerV1==SessionState.fixtureResident)'), 'true')
            self.assertEqual(Hades2RecoveryJournal(path).describe()['outcome'], 'unknown')
            with patch.object(transport, 'execute', wraps=transport.execute) as execute:
                with self.assertRaises(AdapterError) as blocked:
                    session().mutate('set_rerolls', {'amount': 99, 'requestId': 'blocked'})
                self.assertEqual(blocked.exception.code, 'outcome_unknown')
                execute.assert_not_called()


if __name__ == '__main__':
    unittest.main()
