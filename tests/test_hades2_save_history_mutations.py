"""Stored statistics are editable without replaying runs or unrelated totals."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
from core.module_manifest import SaveManagementSpec, SaveRootSpec
from core.save_service import CoreSaveService
from games.hades2.save_document import Hades2SaveDocument, Hades2SaveHeader, LuaTable
from games.hades2.save_workspace import Hades2SaveWorkspace
from games.hades2.save_provider import Hades2SaveProvider
from games.hades2 import save_advanced


def table(values):
    values = list(values.items()) if isinstance(values, dict) else list(values)
    return LuaTable(0, len(values), values)


class HistoryMutationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mgt-history-mutations-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name).resolve()
        self.game = self.folder / 'native-game'
        self.game.mkdir()
        (self.game / 'History.en.sjson').write_text('\n'.join(
            'Id = "' + identity + '" DisplayName = "' + label + '"'
            for identity, label in [('UnknownBoon', 'Historic Boon'), ('UnknownFish', 'Silver Carp'),
                                    ('UnknownShade', 'Quiet Shade')]), encoding='utf-8')
        self.saves = self.folder / 'saves'; self.saves.mkdir()
        self.path = self.saves / 'Profile1.sav'
        self.state = table({
            'Resources': table({}), 'Flags': table({}), 'FishingFails': 2,
            'FishingSuccesses': 9, 'FishingSuccessesManual': 4, 'FishingSuccessesFamiliar': 5,
            'FishCaught': table({'UnknownFish': 3}), 'ExorcisedNames': table({'UnknownShade': 2}),
            'LifetimeTraitStats': table({'UnknownBoon': table({'UseCount': 5, 'ClearCount': 2,
                'FastestTimeSurface': 9.75, 'HighestShrinePointsSurface': 12, 'FutureMeasure': 999})}),
            'RunHistory': table({1: table({'RunResult': 2, 'GameplayTime': 123.5,
                'ShrinePointsCache': 4, 'EndingRoomName': 'F_Boss01', 'ActiveBounty': 'BountyFixture',
                'TraitCache': table({'UnknownBoon': 2}), 'UnknownBoolean': True})}),
            'FutureStat': table({'Counter': 42, 'Boolean': True, 'String': 'old'}),
        })
        self.current = table({'RunResult': 2, 'GameplayTime': 999, 'TraitCache': table({'UnknownBoon': 88})})
        self.write()
        spec = SaveManagementSpec((SaveRootSpec('main', str(self.saves), ('Profile*.sav',)),), None,
                                  True, 'stoppedOnly', True)
        self.service = CoreSaveService('hades2', spec, self.folder / 'data', lambda: False)
        self.service.provider = Hades2SaveProvider(game_path=self.game)
        self.editor = self.open()

    def write(self):
        header = Hades2SaveHeader(0x12, 0, 123, 'Crossroads', 1, 2, 3, 4, 5, 0, 0,
                                 ('GameState', 'CurrentRun'), 'Hub_Main', 'F_Opening01')
        self.path.write_bytes(Hades2SaveDocument(header, [table({'GameState': self.state, 'CurrentRun': self.current})]).to_bytes())

    def open(self):
        target = {'rootId': 'main', 'relativePath': 'Profile1.sav'}
        return Hades2SaveWorkspace.open(self.service, source=target, target=target)

    def row(self, identity):
        return next(row for group in self.editor.query(domain='entities', scope='records', limit=100,
                    language='en')['entities'] for row in group['items'] if row['id'] == identity)

    def test_fishing_failures_edit_through_stage_review_apply_and_reopen(self):
        row = self.row('history:gathering:fishing:FishingFails')
        self.assertTrue(row['editable'], 'FishingFails is a concrete stored counter and must be editable')
        original = self.path.read_bytes()
        self.editor.stage(row['id'], 'set', 7)
        self.assertEqual(self.path.read_bytes(), original)
        review = self.editor.review()
        self.assertEqual(review['actionCount'], 1)
        self.assertEqual(review['effectCount'], 0, 'a statistic edit must not fabricate linked historical events')
        self.assertEqual(review['actions'][0]['before'], 2)
        self.assertEqual(review['actions'][0]['after'], 7)
        result = self.editor.apply()
        self.assertTrue(result['applied'])
        self.service.store.load_verified_snapshot(result['previousSnapshotId'])
        reopened = Hades2SaveDocument.load(self.path).lua_state
        self.assertEqual(reopened['GameState']['FishingFails'], 7)
        self.assertEqual(reopened['GameState']['FishingSuccesses'], 9)
        self.assertEqual(reopened['CurrentRun']['GameplayTime'], 999)

    def test_run_lifetime_and_named_measures_apply_only_requested_values(self):
        edits = {
            'history:run:1:GameplayTime': 17.25,
            'history:run:1:ShrinePointsCache': 30,
            'history:run:1:trait:UnknownBoon': 11,
            'history:run:1:EndingRoomName': '  Future_Room  ',
            'history:run:1:ActiveBounty': '',
            'history:trait:UnknownBoon:UseCount': 3,
            'history:trait:UnknownBoon:ClearCount': 20,
            'history:trait:UnknownBoon:FastestTimeSurface': 5.125,
            'history:trait:UnknownBoon:HighestShrinePointsSurface': 22,
            'history:collection:FishCaught:UnknownFish': 0,
            'history:collection:ExorcisedNames:UnknownShade': 8,
        }
        for identity, value in edits.items():
            row = self.row(identity)
            self.assertTrue(row['editable'], identity)
            self.editor.stage(identity, 'set', value)
        outcome = self.row('history:run:1:RunResult')
        self.assertEqual(outcome['value'], 2)
        self.assertEqual(outcome['choiceNames']['3'], 'Surface · Cleared')
        self.editor.stage(outcome['id'], 'setEnum', '3')
        review = self.editor.review(language='zh-CN')
        action = next(action for action in review['actions'] if action['entryId'] == outcome['id'])
        self.assertEqual(action['after'], 3)
        self.assertEqual(action['choiceNames']['3'], '地表 · 通关')
        self.assertEqual(review['effectCount'], 0)
        self.editor.apply()
        saved = Hades2SaveDocument.load(self.path).lua_state
        for identity, value in edits.items():
            self.assertEqual(save_advanced.resolve_path(saved, self.row(identity)['path']), value)
        self.assertEqual(saved['GameState']['RunHistory'][1]['RunResult'], 3)
        self.assertEqual(saved['GameState']['LifetimeTraitStats']['UnknownBoon']['FutureMeasure'], 999)
        self.assertEqual(saved['GameState']['RunHistory'][1]['UnknownBoolean'], True)
        self.assertEqual(saved['GameState']['FishingFails'], 2)
        self.assertEqual(save_advanced.typed_value(saved['CurrentRun']), save_advanced.typed_value(self.current))
        # Independently correcting ClearCount above UseCount is deliberate, not
        # an event replay or an invented sum constraint.
        self.assertEqual(saved['GameState']['LifetimeTraitStats']['UnknownBoon']['UseCount'], 3)
        self.assertEqual(saved['GameState']['LifetimeTraitStats']['UnknownBoon']['ClearCount'], 20)

    def test_observed_zero_and_missing_native_default_are_distinct_writable_owners(self):
        self.state.pop('FishingFails')
        self.write(); self.editor = self.open()
        row = self.row('history:gathering:fishing:FishingFails')
        self.assertEqual(row['value'], 0)
        self.assertFalse(row['beforePresent'])
        self.assertEqual(row['ownerState'], 'absent')
        self.assertIn('Not recorded', row['reason'])
        self.editor.stage(row['id'], 'set', 0)
        action = self.editor.review()['actions'][0]
        self.assertFalse(action['beforePresent'])
        self.assertTrue(action['afterPresent'])
        self.editor.apply()
        self.assertEqual(Hades2SaveDocument.load(self.path).lua_state['GameState']['FishingFails'], 0)
        self.editor = self.open()
        self.assertTrue(self.row(row['id'])['beforePresent'])
        self.editor.stage(row['id'], 'set', 4)
        self.editor.apply()
        self.assertEqual(Hades2SaveDocument.load(self.path).lua_state['GameState']['FishingFails'], 4)

    def test_type_range_and_finite_checks_reject_without_polluting_the_basket(self):
        identity = 'history:gathering:fishing:FishingFails'
        for value in (-1, 1.5, True, '4', float('inf'), float('nan'), 9007199254740993):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.editor.stage(identity, 'set', value)
        for value in (-0.1, True, '2.5', float('inf'), float('nan')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.editor.stage('history:run:1:GameplayTime', 'set', value)
        for value in (True, 1.5, 'not-a-result', 77):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.editor.stage('history:run:1:RunResult', 'setEnum', value)
        self.assertEqual(self.editor.review()['actionCount'], 0)
        self.editor.stage(identity, 'set', 7)
        advanced = next(row for row in self.editor.query(domain='advanced', path=['GameState'])['items']
                        if row['rawId'] == 'FishingFails')
        with self.assertRaises(ValueError):
            self.editor.stage(advanced['id'], 'set', 8)
        self.assertEqual(self.editor.review()['actionCount'], 1)

    def test_unknown_scalar_statistics_remain_typed_advanced_editable(self):
        edits = {'Counter': -3.5, 'Boolean': False, 'String': '  new  '}
        rows = self.editor.query(domain='advanced', path=['GameState', 'FutureStat'])['items']
        for row in rows:
            self.assertTrue(row['editable'])
            self.editor.stage(row['id'], 'set', edits[row['rawId']])
        # Unknown lifetime measure and unknown run result also retain their
        # technical scalar edit path rather than acquiring invented semantics.
        for path, key, value in ((['GameState', 'LifetimeTraitStats', 'UnknownBoon'], 'FutureMeasure', 12),
                                 (['GameState', 'RunHistory', 1], 'RunResult', 777)):
            row = next(row for row in self.editor.query(domain='advanced', path=path)['items'] if row['rawId'] == key)
            self.editor.stage(row['id'], 'set', value)
        self.editor.stage('history:gathering:fishing:FishingFails', 'set', 6)
        self.editor.apply()
        saved = Hades2SaveDocument.load(self.path).lua_state
        for key, value in edits.items():
            self.assertEqual(saved['GameState']['FutureStat'][key], value)
        self.assertEqual(saved['GameState']['LifetimeTraitStats']['UnknownBoon']['FutureMeasure'], 12)
        self.assertEqual(saved['GameState']['RunHistory'][1]['RunResult'], 777)
        self.assertEqual(saved['GameState']['FishingFails'], 6)
        self.assertEqual(save_advanced.typed_value(saved['CurrentRun']), save_advanced.typed_value(self.current))
        self.editor = self.open()
        self.assertEqual(self.row('history:run:1:RunResult')['value'], 777)

    def test_ambiguous_or_unsupported_sources_are_specific_and_do_not_block_other_statistics(self):
        self.state = table(list(self.state.entries()) + [('FishingFails', 4)])
        self.state['RunHistory'][1]['GameplayTime'] = table({'malformed': True})
        self.write(); self.editor = self.open()
        rows = [row for group in self.editor.query(domain='entities', scope='records', limit=100)['entities']
                for row in group['items']]
        ambiguous = next(row for row in rows if row['id'] == 'history:unavailable:FishingFails')
        self.assertFalse(ambiguous['editable'])
        self.assertTrue(ambiguous['reason'])
        self.assertEqual(ambiguous['reasonCode'], 'ambiguousHistoryPath')
        unsupported = self.row('history:run:1:GameplayTime')
        self.assertFalse(unsupported['editable'])
        self.assertEqual(unsupported['reasonCode'], 'unsupportedHistoryValue')
        with self.assertRaises(ValueError):
            self.editor.stage('history:gathering:fishing:FishingFails', 'set', 7)
        self.editor.stage('history:gathering:fishing:FishingSuccesses', 'set', 12)
        self.editor.apply()
        saved = Hades2SaveDocument.load(self.path).lua_state['GameState']
        self.assertEqual(saved['FishingSuccesses'], 12)
        self.assertEqual([value for key, value in saved.entries() if key == 'FishingFails'], [2, 4])

    def test_missing_default_creation_rejects_a_changed_presence_before_review(self):
        self.state.pop('FishingFails')
        self.write(); self.editor = self.open()
        self.editor.stage('history:gathering:fishing:FishingFails', 'set', 0)
        self.editor.document.lua_state['GameState']['FishingFails'] = 0
        with self.assertRaises(ValueError):
            self.editor.review()


if __name__ == '__main__':
    unittest.main()
