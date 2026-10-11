"""Consumed-source freshness and explicit browsing at the public Save seams."""

import hashlib
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend'))

from games.hades2.save_document import LuaTable
from games.hades2.save_investigation import NativeDialogueInvestigation
from games.hades2.save_workspace import Hades2SaveWorkspace


SCENE = 'NemesisPostTrueEnding01'
OTHER = 'NemesisNewScene'


def table(**entries):
    return LuaTable(0, len(entries), list(entries.items()))


def replace_preserving_time(path, content):
    before = path.stat()
    path.write_text(content, encoding='utf-8')
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))


def authored(scene, cue):
    return f'''NPC = {{
 InteractTextLineSets = {{
  {scene} = {{ {{ Cue = "/VO/{cue}" }} }}
 }}
}}'''


def translation(cue, text, event=''):
    return f'{{ Texts = [ {{ Id = "{cue}" DisplayName = "{text}" Event = "{event}" }} ] }}'


class DialogueSourceRefresh(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.game = Path(self.temporary.name)
        self.scripts = self.game / 'sources/Scripts'
        self.texts = self.game / 'sources/Text'
        for folder in (self.scripts, self.texts / 'en', self.texts / 'zh-CN'):
            folder.mkdir(parents=True)
        self.reset = self.scripts / 'StoryResetData.lua'
        self.reset.write_text('StoryResetData = {}', encoding='utf-8')
        self.checksum = hashlib.sha256(self.reset.read_bytes()).hexdigest()
        self.npc = self.scripts / 'NPCData_Nemesis.lua'
        self.npc.write_text(authored(SCENE, 'First'), encoding='utf-8')
        self.english = self.texts / 'en/Lines.sjson'
        self.chinese = self.texts / 'zh-CN/Lines.sjson'
        self.english.write_text(translation('First', 'Original English'), encoding='utf-8')
        self.chinese.write_text(translation('First', '原文'), encoding='utf-8')
        self.root = table(GameState=table(
            TextLinesRecord=table(**{SCENE: True}),
            GiftTextLinesOrderRecord=table(), TextLinesChoiceRecord=table(),
        ))
        self.finding = self.open_investigation()

    def open_investigation(self):
        return NativeDialogueInvestigation(self.game, expected_hash=self.checksum)

    def query(self, **changes):
        options = dict(search='', offset=0, limit=100, language='en', permissions={})
        options.update(changes)
        return self.finding.query(self.root, **options)

    def test_script_refresh_with_unchanged_reset_and_timestamp(self):
        self.assertEqual(self.finding.detail(self.root, SCENE, 'en', {})['lines'][0]['cueId'], 'First')
        replace_preserving_time(self.npc, authored(SCENE, 'Second'))
        for finding in (self.finding, self.open_investigation()):
            self.assertEqual(finding.detail(self.root, SCENE, 'en', {})['lines'][0]['cueId'], 'Second')
        self.assertEqual(hashlib.sha256(self.reset.read_bytes()).hexdigest(), self.checksum)

    def test_bilingual_addition_removal_and_root_selection(self):
        original_identity = self.query().get('sourceIdentity')
        replace_preserving_time(self.english, translation('First', 'Changed English'))
        replace_preserving_time(self.chinese, translation('First', '新文本'))
        detail = self.finding.detail(self.root, SCENE, 'zh-CN', {})
        self.assertEqual(detail['lines'][0]['en'], ['Changed English'])
        self.assertEqual(detail['lines'][0]['zhCN'], ['新文本'])
        self.assertNotEqual(original_identity, detail['sourceIdentity'])
        added = self.scripts / 'NPCData_New.lua'
        added.write_text(authored(OTHER, 'NewCue'), encoding='utf-8')
        extra = self.texts / 'zh-CN/Additional.sjson'
        extra.write_text(translation('NewCue', '新增文本', OTHER), encoding='utf-8')
        self.assertEqual(self.query(search='新增文本')['items'][0]['rawId'], OTHER)
        added.unlink()
        self.assertEqual(self.query(search=OTHER)['items'][0]['status'], 'unknown')
        extra.unlink()
        self.assertEqual(self.query(search=OTHER)['total'], 0)
        # A newly preferred installation root replaces the old source root.
        preferred = self.game / 'Content'
        (preferred / 'Scripts').mkdir(parents=True)
        (preferred / 'Game/Text/en').mkdir(parents=True)
        (preferred / 'Scripts/StoryResetData.lua').write_bytes(self.reset.read_bytes())
        (preferred / 'Scripts/NPCData_Nemesis.lua').write_text(authored(SCENE, 'Preferred'), encoding='utf-8')
        self.assertEqual(self.finding.detail(self.root, SCENE, 'en', {})['lines'][0]['cueId'], 'Preferred')

    def test_explicit_empty_filters_and_pagination(self):
        self.npc.write_text(authored(SCENE, 'First') + '\n' + authored(OTHER, 'NewCue'), encoding='utf-8')
        self.english.write_text(translation('Ambient', 'An event only', 'EventOnly'), encoding='utf-8')
        default = self.query()
        self.assertEqual([row['rawId'] for row in default['items']], [SCENE])
        absent = self.query(state_filter='notRecorded', limit=1)
        self.assertGreater(absent['total'], 0)
        self.assertEqual(absent['items'][0]['status'], 'notRecorded')
        page = self.query(state_filter='notRecorded', offset=1, limit=1)
        self.assertEqual(page['total'], absent['total'])
        self.assertNotEqual(page['items'][0]['rawId'], absent['items'][0]['rawId'])
        self.assertIn(OTHER, [row['rawId'] for row in self.query(state_filter='notRecorded', limit=10000)['items']])
        self.assertEqual([row['rawId'] for row in self.query(state_filter='unknown')['items']], ['EventOnly'])
        self.root['GameState']['TextLinesRecord'] = LuaTable(0, 2, [(SCENE, True), (SCENE, False)])
        self.assertEqual([row['rawId'] for row in self.query(state_filter='ambiguous')['items']], [SCENE])

    def test_partial_and_mismatched_evidence_is_reported_truthfully(self):
        original = self.query()
        self.assertEqual(original['sourceProvenance']['storyResetVerification'], 'matched')
        self.assertEqual(original['sourceProvenance']['buildVerification'], 'unverified')
        self.english.write_bytes(b'\xff')
        partial = self.finding.detail(self.root, SCENE, 'zh-CN', {})
        self.assertNotEqual(partial['sourceIdentity'], original['sourceIdentity'])
        self.assertEqual(partial['lines'][0]['en'], [])
        self.assertEqual(partial['lines'][0]['zhCN'], ['原文'])
        self.assertEqual(partial['sourceErrors'], [{'input': 'en/Lines.sjson', 'reason': 'invalidEncoding'}])
        self.chinese.unlink()
        self.assertEqual(self.finding.detail(self.root, SCENE, 'zh-CN', {})['lines'][0]['zhCN'], [])
        self.reset.write_text('Modified reset data', encoding='utf-8')
        mismatch = self.query(search=SCENE, permissions={SCENE: {'allowed': True}})
        self.assertEqual(mismatch['sourceStatus'], 'mismatch')
        self.assertEqual(mismatch['sourceProvenance']['storyResetVerification'], 'mismatch')
        self.assertFalse(mismatch['items'][0]['canStage'])

    def test_workspace_refresh_state_and_independent_write_authority(self):
        # Inject only the temporary supported-source identity at the workspace's
        # public investigation seam; exercise actual discovery and write owners.
        factory = lambda game: NativeDialogueInvestigation(game, expected_hash=self.checksum)
        with patch('games.hades2.save_workspace.NativeDialogueInvestigation', side_effect=factory):
            session = SimpleNamespace(document=SimpleNamespace(lua_state=self.root), relative_path='Profile1.sav')
            workspace = Hades2SaveWorkspace(session, 'Profile1', game_path=self.game)
            first = workspace.query(domain='discover', search=SCENE, language='en')
            first_row = next(row for row in first['items'] if row['id'] == 'investigate:' + SCENE)
            self.assertTrue(first_row['editable'])
            replace_preserving_time(self.english, translation('First', 'Workspace refreshed'))
            current = workspace.query(domain='investigate', search=SCENE, language='en')['items'][0]
            detail = workspace.investigate(current['id'], 'en')
            self.assertEqual(current['snippet'], 'Workspace refreshed')
            self.assertEqual(current['sourceIdentity'], detail['sourceIdentity'])
            self.assertTrue(detail['canStage'])
            self.assertEqual(detail['sourceProvenance']['buildVerification'], 'unverified')
            reopened = Hades2SaveWorkspace(session, 'Profile1', game_path=self.game)
            self.assertEqual(reopened.investigate(current['id'], 'en')['sourceIdentity'], detail['sourceIdentity'])
            self.npc.write_text(authored(OTHER, 'NewCue'), encoding='utf-8')
            absent = workspace.query(domain='discover', stateFilter='absent', language='en', limit=200)
            identities = [row['rawId'] for row in absent['items']]
            for offset in range(200, absent['total'], 200):
                page = workspace.query(domain='discover', stateFilter='absent', language='en', limit=200, offset=offset)
                self.assertEqual(page['total'], absent['total'])
                identities.extend(row['rawId'] for row in page['items'])
            self.assertIn(OTHER, identities)
            # New source evidence never grants a write outside existing native
            # reset/companion ownership, even if its save record becomes true.
            self.root['GameState']['TextLinesRecord'][OTHER] = True
            blocked = workspace.investigate('investigate:' + OTHER, 'en')
            self.assertFalse(blocked['canStage'])
            self.assertEqual(blocked['blockReasonCode'], 'notResettable')
            self.reset.unlink()
            self.assertEqual(workspace.investigate(current['id'], 'en')['sourceStatus'], 'missing')


if __name__ == '__main__':
    unittest.main()
