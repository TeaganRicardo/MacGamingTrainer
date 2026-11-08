"""Captured native health and mounted damage status use observed Hades owners."""
import math
import tempfile
import unittest
from unittest.mock import patch

from hades_lua_fixture import adapter_for
from core.adapter import AdapterError
from games.hades.schema import preference_value


class HadesLockObservation(unittest.TestCase):
    def test_fractional_capture_persistence_profile_and_reconnect(self):
        with tempfile.TemporaryDirectory(prefix='hades-fractional-lock-') as directory:
            adapter, runtime, game, store = adapter_for(directory)
            state = adapter.dispatch('connect', {}, 'connect')
            game.native('CurrentRun.Hero.Health=99.5; CurrentRun.Hero.MaxHealth=100.5')
            state = adapter.dispatch('lock_vital', {
                'vital': 'health', 'locked': True, 'target': state['target'],
            }, 'capture')
            pair = {'current': 99.5, 'max': 100.5}
            self.assertEqual(state['healthLock'], pair)
            self.assertEqual(store.load()['healthLock'], pair)
            adapter.dispatch('save_profile', {'name': 'Fractional'}, 'save-profile')
            self.assertEqual(adapter.profiles.load('Fractional')['healthLock'], pair)
            adapter.dispatch('disconnect', {}, 'detach')
            fresh, _, _, fresh_store = adapter_for(directory, game)
            state = fresh.dispatch('connect', {}, 'reconnect')
            self.assertEqual(state['healthLock'], pair)
            self.assertEqual(fresh_store.load()['healthLock'], pair)
            game.lua_reset()
            state = fresh.dispatch('status', {}, 'reset')
            self.assertEqual(state['healthLock'], pair)
            self.assertEqual(state['health'], 99.5)
            self.assertEqual(state['maxHealth'], 100.5)
            fresh.dispatch('disable_all', {}, 'clear')
            state = fresh.dispatch('load_profile', {'name': 'Fractional'}, 'restore-profile')
            self.assertEqual(state['healthLock'], pair)
            # Explicit edits retain their existing integer-only contract.
            with self.assertRaises(AdapterError):
                fresh.dispatch('set_value', {
                    'field': 'health', 'value': 70.5, 'target': state['target'],
                }, 'fractional-edit')
            self.assertEqual(fresh_store.load()['healthLock'], pair)

    def test_invalid_captured_reply_preserves_confirmed_intent(self):
        with tempfile.TemporaryDirectory(prefix='hades-invalid-lock-') as directory:
            adapter, runtime, _, store = adapter_for(directory)
            state = adapter.dispatch('connect', {}, 'connect')
            state = adapter.dispatch('lock_vital', {
                'vital': 'health', 'locked': True, 'target': state['target'],
            }, 'lock')
            confirmed = store.load()
            command = runtime.command

            def invalid_reply(method, params):
                result = command(method, params)
                if method == 'lock_vital':
                    result['healthLock'] = {'current': 3, 'max': 2}
                return result

            with patch.object(runtime, 'command', side_effect=invalid_reply):
                with self.assertRaises(AdapterError) as raised:
                    adapter.dispatch('lock_vital', {
                        'vital': 'health', 'locked': True, 'target': state['target'],
                    }, 'invalid-capture')
            self.assertEqual(raised.exception.code, 'debugger_protocol')
            self.assertEqual(store.load(), confirmed)
            self.assertEqual(runtime.status()['healthLock'], confirmed['healthLock'])

    def test_health_pair_domain(self):
        for pair in ({'current': 1, 'max': 1}, {'current': 1.25, 'max': 2.5},
                     {'current': 1_000_000_000.5, 'max': 1_000_000_001.5}):
            self.assertEqual(preference_value('healthLock', pair), pair)
        for pair in ({'current': 0.5, 'max': 1}, {'current': 2, 'max': 1},
                     {'current': math.nan, 'max': 2}, {'current': 1, 'max': math.inf},
                     {'current': True, 'max': 2}, {'current': 1, 'max': 10 ** 400},
                     {'current': 1}, {'current': 1, 'max': 2, 'extra': 3}):
            with self.subTest(pair=pair), self.assertRaises(AdapterError):
                preference_value('healthLock', pair)

    def test_damage_status_observes_modifier_identity_value_and_hero(self):
        with tempfile.TemporaryDirectory(prefix='hades-damage-observation-') as directory:
            adapter, runtime, game, _ = adapter_for(directory)
            adapter.dispatch('connect', {}, 'connect')
            for feature, collection in (
                ('damageMultiplier', 'OutgoingDamageModifiers'),
                ('incomingDamageMultiplier', 'IncomingDamageModifiers'),
            ):
                with self.subTest(feature=feature):
                    state = adapter.dispatch('set_feature', {'feature': feature, 'value': 2}, 'enable')
                    self.assertTrue(state['activeFeatures'][feature])
                    game.native('CurrentRun.Hero.' + collection + '[1].GlobalMultiplier=3')
                    state = adapter.dispatch('status', {}, 'changed-value')
                    self.assertFalse(state['activeFeatures'][feature])
                    self.assertEqual(state['features'][feature], 2)
                    # A live hero whose modifier drifted is not waiting for an
                    # environment: the intent is unconfirmed, not dormant.
                    self.assertFalse(state['dormantFeatures'][feature])
                    adapter.dispatch('set_feature', {'feature': feature, 'value': 2}, 'reconcile')
                    # A same-name clone is a replacement, not the mounted receipt.
                    game.native('CurrentRun.Hero.' + collection + '[1]={Name="MacGamingTrainer.Hades",'
                                'GlobalMultiplier=2,Multiplicative=true}')
                    self.assertFalse(adapter.dispatch('status', {}, 'replaced-owner')['activeFeatures'][feature])
                    adapter.dispatch('set_feature', {'feature': feature, 'value': 2}, 'remount')
                    self.assertTrue(adapter.dispatch('status', {}, 'mounted')['activeFeatures'][feature])
                    game.native('CurrentRun.Hero.' + collection + '={}')
                    self.assertFalse(adapter.dispatch('status', {}, 'missing')['activeFeatures'][feature])
                    adapter.dispatch('set_feature', {'feature': feature, 'value': 2}, 'restore')
                    game.native('local previous=CurrentRun.Hero; local replacement={}; '
                                'for key,value in pairs(previous) do replacement[key]=value end; '
                                'CurrentRun.Hero=replacement')
                    self.assertFalse(adapter.dispatch('status', {}, 'replacement-hero')['activeFeatures'][feature])
                    adapter.dispatch('set_feature', {'feature': feature, 'value': 2}, 'replacement-mount')
                    game.native('CurrentRun.Hero.IsDead=true')
                    dead = adapter.dispatch('status', {}, 'dead')
                    self.assertFalse(dead['activeFeatures'][feature])
                    self.assertTrue(dead['dormantFeatures'][feature])
                    game.native('CurrentRun.Hero.IsDead=false; CurrentRun.Hero.ObjectId=40001')
                    self.assertFalse(adapter.dispatch('status', {}, 'new-object')['activeFeatures'][feature])
                    adapter.dispatch('set_feature', {'feature': feature, 'value': 2}, 'new-object-mount')
                    self.assertTrue(adapter.dispatch('status', {}, 'new-object-mounted')['activeFeatures'][feature])
                    adapter.dispatch('disable_all', {}, 'disable')
                    disabled = adapter.dispatch('status', {}, 'disabled')
                    self.assertFalse(disabled['activeFeatures'][feature])
                    self.assertFalse(disabled['dormantFeatures'][feature])
                    game.native('CurrentRun.Hero.ObjectId=40000')


if __name__ == '__main__':
    unittest.main()
