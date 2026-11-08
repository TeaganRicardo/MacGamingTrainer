"""An attached Hades runtime refuses changed definitions before another command."""
import tempfile
import unittest
from unittest.mock import patch

from hades_lua_fixture import adapter_for
from core.adapter import AdapterError
from games.hades.world import runtime_definitions, runtime_definitions_identity


class HadesWorldRuntimeIdentity(unittest.TestCase):
    def test_presentation_names_are_outside_runtime_identity(self):
        semantic = {'kind': 'fixture', 'doorAllowed': False}
        with patch('games.hades.world.REWARDS', {'Fixture': {**semantic, 'names': {'en': 'Before'},
                                                             'group': 'pickup', 'section': 'before'}}):
            before = runtime_definitions_identity(runtime_definitions())
        # Names and Generate-row grouping are presentation; regrouping a reward
        # must not require restarting an attached resident.
        with patch('games.hades.world.REWARDS', {'Fixture': {**semantic, 'names': {'en': 'After'},
                                                             'group': 'special', 'section': 'after',
                                                             'sectionNames': {'en': 'After'}}}):
            self.assertEqual(runtime_definitions_identity(runtime_definitions()), before)

    def test_changed_definitions_refuse_existing_runtime_before_mutation(self):
        with tempfile.TemporaryDirectory(prefix='hades-world-identity-') as directory:
            adapter, runtime, game, _ = adapter_for(directory)
            adapter.dispatch('connect', {}, 'first-definitions')
            original = runtime_definitions()
            changed = {**original, 'IdentityFixture': {'kind': 'fixture', 'doorAllowed': False}}
            game.native('MacGamingTrainerHades.set_feature=function() GameState.worldMutation=true; '
                        'return MacGamingTrainerHades.status() end')
            with patch('games.hades.lldb_worker.runtime_definitions', return_value=changed):
                with self.assertRaises(AdapterError) as raised:
                    runtime.worker.dispatch('set_feature', {'feature': 'invincibility', 'value': True})
            self.assertEqual(raised.exception.code, 'restart_required')
            self.assertIn('hades.error.restartRequired', raised.exception.diagnostic)
            self.assertEqual(game.value('GameState.worldMutation==nil'), 'true')
            # Failed compatibility did not overwrite the established definitions.
            self.assertEqual(game.value('MacGamingTrainerHades.worldDefinitions.IdentityFixture==nil'), 'true')

    def test_existing_definitions_without_matching_identity_require_restart(self):
        with tempfile.TemporaryDirectory(prefix='hades-world-identity-') as directory:
            adapter, runtime, game, _ = adapter_for(directory)
            adapter.dispatch('connect', {}, 'connect')
            game.native('MacGamingTrainerHades.worldDefinitionsIdentity=nil')
            with self.assertRaises(AdapterError) as raised:
                runtime.worker.dispatch('status', {})
            self.assertEqual(raised.exception.code, 'restart_required')

    def test_order_reset_and_new_process(self):
        with tempfile.TemporaryDirectory(prefix='hades-world-identity-') as directory:
            adapter, runtime, game, _ = adapter_for(directory)
            adapter.dispatch('connect', {}, 'first-definitions')
            original = runtime_definitions()
            reordered = {key: dict(reversed(list(row.items())))
                         for key, row in reversed(list(original.items()))}
            with patch('games.hades.lldb_worker.runtime_definitions', return_value=reordered):
                self.assertTrue(runtime.worker.dispatch('status', {})['connected'])
            changed = {**original, 'IdentityFixture': {'kind': 'fixture', 'doorAllowed': False}}
            game.lua_reset()
            with patch('games.hades.lldb_worker.runtime_definitions', return_value=changed):
                self.assertTrue(runtime.worker.dispatch('status', {})['connected'])
                self.assertEqual(game.value('MacGamingTrainerHades.worldDefinitions.IdentityFixture.kind'), 'fixture')
                fresh, _, fresh_game, _ = adapter_for(directory)
                self.assertTrue(fresh.dispatch('connect', {}, 'new-process')['connected'])
                self.assertEqual(fresh_game.value('MacGamingTrainerHades.worldDefinitions.IdentityFixture.kind'), 'fixture')


if __name__ == '__main__':
    unittest.main()
