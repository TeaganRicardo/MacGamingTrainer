"""Resource browsing exposes reliable observed fields and creates absent owners."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
from core.module_manifest import SaveManagementSpec, SaveRootSpec
from core.save_service import CoreSaveService
from games.hades2 import save_advanced
from games.hades2.save_document import Hades2SaveDocument, Hades2SaveHeader, LuaTable
from games.hades2.save_workspace import Hades2SaveWorkspace


def table(values=()):
    pairs = list(values.items()) if isinstance(values, dict) else list(values)
    return LuaTable(0, len(pairs), pairs)


class ResourceMutationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mgt-resource-mutations-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name).resolve()
        self.saves = self.folder / 'saves'; self.saves.mkdir()
        self.path = self.saves / 'Profile1.sav'
        self.state = table({'Resources': table({'MetaCurrency': 2}), 'Flags': table()})
        self.current = table({'ResourcesGained': table({'MetaCurrency': 8})})
        self.write()
        spec = SaveManagementSpec((SaveRootSpec('main', str(self.saves), ('Profile*.sav',)),),
                                  None, True, 'stoppedOnly', True)
        self.service = CoreSaveService('hades2', spec, self.folder / 'data', lambda: False)
        self.editor = self.open()

    def write(self):
        header = Hades2SaveHeader(0x12, 0, 123, 'Crossroads', 1, 2, 3, 4, 5, 0, 0,
                                  ('GameState', 'CurrentRun'), 'Hub_Main', 'F_Opening01')
        self.path.write_bytes(Hades2SaveDocument(header, [table({
            'GameState': self.state, 'CurrentRun': self.current,
        })]).to_bytes())

    def open(self):
        target = {'rootId': 'main', 'relativePath': 'Profile1.sav'}
        return Hades2SaveWorkspace.open(self.service, source=target, target=target)

    def browse(self, search):
        return [row for entity in self.editor.query(domain='entities', scope='resources',
                search=search, language='en', limit=100)['entities'] for row in entity['items']]

    def test_absent_inventory_is_created_only_by_confirmed_apply_including_zero(self):
        self.state.pop('Resources'); self.write(); self.editor = self.open()
        source = self.path.read_bytes()
        row = next(row for row in self.browse('MetaCurrency') if row['id'] == 'resource:MetaCurrency')
        self.assertTrue(row['editable'], 'a missing resource table is a creatable owner')
        self.assertFalse(row['beforePresent'])
        self.assertNotIn('Resources', self.editor.document.lua_state['GameState'])
        self.editor.stage(row['id'], 'set', 0)
        action = self.editor.review()['actions'][0]
        self.assertFalse(action['beforePresent']); self.assertTrue(action['afterPresent'])
        self.assertEqual(action['after'], 0)
        self.assertEqual(self.path.read_bytes(), source)
        result = self.editor.apply()
        self.service.store.load_verified_snapshot(result['previousSnapshotId'])
        saved = Hades2SaveDocument.load(self.path).lua_state
        self.assertEqual(saved['GameState']['Resources']['MetaCurrency'], 0)
        self.assertEqual(save_advanced.typed_value(saved['CurrentRun']), save_advanced.typed_value(self.current))

    def test_observed_unknown_resources_use_actual_types_and_apply_without_native_events(self):
        unknown = {'FutureCount': 3, 'FutureFlag': True, 'FutureFraction': 1.25,
                   'FutureText': 'old', 'FutureMembers': table({'kept': True})}
        for key, value in unknown.items():
            self.state['Resources'][key] = value
        self.write(); self.editor = self.open()
        desired = {'FutureCount': 11, 'FutureFlag': False, 'FutureFraction': 9.125,
                   'FutureText': '  exact text  ', 'FutureMembers': table({'new': True})}
        original = self.path.read_bytes()
        for key, after in desired.items():
            rows = self.browse(key)
            self.assertEqual(len(rows), 1, key)
            row = rows[0]
            self.assertTrue(row['editable'], key)
            self.assertEqual(row['domain'], 'advanced')
            self.assertTrue(row.get('warning'), 'unknown native meaning must be explained')
            self.assertEqual(row['path'], ['GameState', 'Resources', key])
            self.editor.stage(row['id'], 'set', save_advanced.typed_value(after))
        review = self.editor.review()
        self.assertEqual(review['actionCount'], len(desired)); self.assertEqual(review['effectCount'], 0)
        self.assertEqual(self.path.read_bytes(), original)
        self.editor.apply()
        saved = Hades2SaveDocument.load(self.path).lua_state
        for key, after in desired.items():
            self.assertEqual(save_advanced.typed_value(saved['GameState']['Resources'][key]),
                             save_advanced.typed_value(after))
        self.assertEqual(saved['GameState']['Resources']['MetaCurrency'], 2)
        self.assertEqual(save_advanced.typed_value(saved['CurrentRun']), save_advanced.typed_value(self.current))

    def test_known_resource_with_actual_noninteger_value_can_be_repaired_as_typed_field(self):
        self.state['Resources']['MetaCurrency'] = 'malformed legacy value'
        self.write(); self.editor = self.open()
        row = next(row for row in self.browse('MetaCurrency') if row['path'] == ['GameState', 'Resources', 'MetaCurrency'])
        self.assertTrue(row['editable'])
        self.assertEqual(row['valueType'], 'string')
        self.editor.stage(row['id'], 'set', {'luaType': 'number', 'value': 10})
        self.editor.apply()
        self.assertEqual(Hades2SaveDocument.load(self.path).lua_state['GameState']['Resources']['MetaCurrency'], 10)
        self.editor = self.open()
        self.assertTrue(any(row['id'] == 'resource:MetaCurrency' and row['editable'] for row in self.browse('MetaCurrency')))

    def test_duplicate_physical_resource_is_diagnosed_without_blocking_unique_sibling(self):
        self.state['Resources'] = table([('FutureCount', 1), ('FutureCount', 2), ('OtherCount', 3)])
        self.write(); self.editor = self.open()
        rows = self.browse('FutureCount')
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(not row['editable'] and row.get('readOnlyReason') for row in rows))
        self.assertEqual(len({row['id'] for row in rows}), 2)
        for row in rows:
            with self.assertRaises(ValueError):
                self.editor.stage(row['id'], 'set', 7)
        sibling = self.browse('OtherCount')[0]
        self.editor.stage(sibling['id'], 'set', 9); self.editor.apply()
        resources = Hades2SaveDocument.load(self.path).lua_state['GameState']['Resources']
        self.assertEqual([value for key, value in resources.entries() if key == 'FutureCount'], [1, 2])
        self.assertEqual(resources['OtherCount'], 9)


if __name__ == '__main__':
    unittest.main()
