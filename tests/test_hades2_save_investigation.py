"""Source-backed dialogue investigation across absent, duplicate and transient owners."""

import hashlib
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from unittest.mock import patch

from games.hades2.save_document import Hades2SaveDocument, Hades2SaveHeader, LuaTable
from games.hades2.save_workspace import Hades2SaveWorkspace
from games.hades2 import save_narrative
from games.hades2.save_investigation import NativeDialogueInvestigation


def source_tree(folder):
    scripts = folder / 'sources/Scripts'
    english = folder / 'sources/Text/en'
    chinese = folder / 'sources/Text/zh-CN'
    for path in (scripts, english, chinese):
        path.mkdir(parents=True)
    reset = scripts / 'StoryResetData.lua'
    reset.write_text('''StoryResetData = {
 TextLines = {
 "NemesisPostTrueEnding01", "NemesisAboutChronosBossFights01",
 "HecateAboutUltimateProgress03", "HecateAboutUltimateProgress03_A",
 "HecateAboutUltimateProgress04", "PreTrueEnding01", "HadesWithPersephone01",
 "HecateAboutTyphonFight03",
 }
}
''', encoding='utf-8')
    (scripts / 'NPCData_Nemesis.lua').write_text('''UnitSetData = {
  NemesisPostTrueEnding01 = {
    GameStateRequirements = {{PathTrue = {"CurrentRun", "TextLinesRecord", "TrueEndingFinale01"}}},
    { Cue = "/VO/Nemesis_0407", Text = "English authored line" },
    { Cue = "/VO/Nemesis_0408", Text = "Second authored line" },
  },
  NemesisAboutChronosBossFights01 = {
    GameStateRequirements = {
      {PathTrue = {"CurrentRun", "RoomsEntered", "I_Boss01"}},
      {PathTrue = {"CurrentRun", "Cleared"}},
      {Path = {"GameState", "EnemyKills", "Chronos"}, Comparison = ">=", Value = 3},
      {PathTrue = {"GameState", "TextLinesRecord", "NemesisGift03"}},
    },
    { Cue = "/VO/Nemesis_0252", Text = "Many prerequisites" },
  },
  NPC_Nemesis_01 = {
    InteractVoiceLines = {
      { Cue = "/VO/Nemesis_Ambient9001", Text = "Ambient only" },
    },
    GiftTextLineSets = {
      NemesisBathHouseRepeatable01 = {
        GameStateRequirements = {{PathTrue = {"GameState", "WorldUpgradesAdded", "WorldUpgradeBathHouse"}}},
        { Cue = "/VO/Nemesis_Bath9001", Text = "Repeatable bathhouse scene" },
      },
    },
  },
}
''', encoding='utf-8')
    (scripts / 'NPCData_Hecate.lua').write_text('''UnitSetData = {
  HecateAboutUltimateProgress03_A = {
    GameStateRequirements = { {NamedRequirements = {"HecateMissing"}} },
    { Cue = "/VO/Hecate_0795", Text = "Shared scene cue" },
  },
  HecateAboutUltimateProgress03 = {
    GameStateRequirements = { {OrRequirements = {
      { PathTrue = {"GameState", "TextLinesRecord", "SeenPrequel"}},
      { PathFalse = {"GameState", "TextLinesRecord", "OtherVersion"}} } } },
    { Cue = "/VO/Hecate_0795", Text = "Shared scene cue" },
  },
  HecateAboutUltimateProgress04 = {
    { Cue = "/VO/Hecate_0942", Text = "Localized in other file" },
  },
  HecateAboutTyphonFight03 = {
    { Cue = "/VO/Melinoe_0585_A", Text = "Only source English" },
    { Cue = "/VO/Melinoe_0585_B", Text = "Only source English" },
  },
  NPC_Hecate_01 = {
    InteractTextLineSets = {
      HecateAboutTyphonFight02_B = {
        PlayOnce = true,
        { Cue = "/VO/Hecate_Typhon9001", Text = "Scene without a localization Event" },
      },
    },
  },
}
''', encoding='utf-8')
    (scripts / 'NPCData_Hermes.lua').write_text('''UnitSetData = {
  HermesFieldAboutTyphon03 = {
    { Cue = "/VO/MelinoeField_4215", Text = "Only unlocalized script text" },
    -- { Cue = "/VO/DisabledHermes_0001", Text = "Commented out" },
  },
}
''', encoding='utf-8')
    (scripts / 'NPCData_Hades.lua').write_text('''FirstOwner = {
  HadesWithPersephone01 = {Partner = "Persephone", { Cue = "/VO/Hades_0001" }},
}
SecondOwner = {
  HadesWithPersephone01 = {CopyDataFromPartner = true, { Cue = "/VO/Persephone_0001" }},
}
''', encoding='utf-8')
    (english / '_NPCData_Nemesis.en.sjson').write_text('''{
 Texts = [
  { Id = "Nemesis_0408" DisplayName = "Second authored line" Speaker = "Nemesis" Event = "NemesisPostTrueEnding01" }
  { Id = "Nemesis_0407" DisplayName = "My father has returned" Speaker = "Nemesis" Event = "NemesisPostTrueEnding01"
    // Id = "InjectedCue"
    // DisplayName = "INJECTED TRANSLATION"
  }
  { Id = "Nemesis_0252" DisplayName = "Fought Chronos repeatedly" Speaker = "Nemesis" Event = "NemesisAboutChronosBossFights01" }
  { Id = "Nemesis_GenericVoice01" DisplayName = "Unrelated ambient speech" Event = "NPC_Nemesis_01.InteractVoiceLines" }
  { Id = "Nemesis_EventOnly01" DisplayName = "Unresolved event wording" Event = "NemesisOnlyLocalizationEvent01" }
  { Id = "Nemesis_Bath9001" DisplayName = "The springs again" }
  // { Id = "Commented_01" DisplayName = "Not live" Event = "NemesisPostTrueEnding01" }
 ]
}
''', encoding='utf-8')
    (english / '_NPCData_Hecate.en.sjson').write_text('''{ Texts = [
 { Id = "Hecate_0795" DisplayName = "Shared" Event = "HecateAboutUltimateProgress03_A" }
 { Id = "Hecate_Typhon9001" DisplayName = "Typhon follow-up" }
] }''', encoding='utf-8')
    (english / '_EnemyData_Hecate.en.sjson').write_text('''{ Texts = [
 { Id = "Hecate_0942" DisplayName = "From enemy text" Event = "HecateBossAboutEndingPath04" }
] }''', encoding='utf-8')
    (chinese / '_NPCData_Nemesis.zh-CN.sjson').write_text('''{ Texts = [
 { Id = "Nemesis_0407" DisplayName = "我的父亲回来了" }
 { Id = "Nemesis_0252" DisplayName = "多次击败克洛诺斯" }
 { Id = "Nemesis_Bath9001" DisplayName = "再次泡温泉" }
] }''', encoding='utf-8')
    (chinese / '_NPCData_Hecate.zh-CN.sjson').write_text('''{ Texts = [
 { Id = "Hecate_0795" DisplayName = "同一台词" }
 { Id = "Hecate_Typhon9001" DisplayName = "台风之后" }
 { Id = "Hecate_ZHOnly9001" DisplayName = "仅中文场景" Event = "HecateChineseEventOnly01" Speaker = "赫卡忒" }
] }''', encoding='utf-8')
    (chinese / '_EnemyData_Hecate.zh-CN.sjson').write_text('''{ Texts = [
 { Id = "Hecate_0942" DisplayName = "跨文件翻译" }
] }''', encoding='utf-8')
    (english / 'HelpText.en.sjson').write_text(
        '{ Texts = [ { Id = "NPC_Nemesis_01" DisplayName = "Nemesis" } ] }',
        encoding='utf-8')
    (chinese / 'HelpText.zh-CN.sjson').write_text(
        '{ Texts = [ { Id = "NPC_Nemesis_01" DisplayName = "涅墨西斯" } ] }',
        encoding='utf-8')
    return hashlib.sha256(reset.read_bytes()).hexdigest()


def lua(**entries):
    return LuaTable(0, len(entries), list(entries.items()))


def flatten(tree):
    return [tree] + [part for child in tree['children'] for part in flatten(child)]


with tempfile.TemporaryDirectory(prefix='mgt-investigation-') as directory:
    game = Path(directory)
    checksum = source_tree(game)
    root = lua(GameState=lua(
        TextLinesRecord=lua(NemesisPostTrueEnding01=True, NemesisGift03=True),
        EnemyKills=lua(Chronos=8),
    ))
    finding = NativeDialogueInvestigation(game, expected_hash=checksum)
    assert finding.native['status'] == 'available'
    assert finding.query(root, search='', offset=0, limit=30, language='en', permissions={})['total'] == 2
    found = finding.query(root, search='Nemesis', offset=0, limit=100, language='zh-CN', permissions={})
    assert found['total'] >= 2
    assert {row['rawId'] for row in found['items']} >= {'NemesisPostTrueEnding01', 'NemesisAboutChronosBossFights01', 'NemesisBathHouseRepeatable01'}
    # Two real native scenes lack both StoryReset and a matching SJSON Event.
    # Their immediate owners are authored TextLineSets, not voice-line lists.
    bath = finding.query(root, search='NemesisBathHouseRepeatable01', offset=0, limit=10, language='zh-CN', permissions={})
    typhon = finding.query(root, search='HecateAboutTyphonFight02_B', offset=0, limit=10, language='zh-CN', permissions={})
    assert [row['rawId'] for row in bath['items']] == ['NemesisBathHouseRepeatable01']
    assert [row['rawId'] for row in typhon['items']] == ['HecateAboutTyphonFight02_B']
    assert all(row['status'] == 'notRecorded' and not row['canStage'] for row in bath['items'] + typhon['items'])
    assert finding.detail(root, 'NemesisBathHouseRepeatable01', 'zh-CN', {})['lines'][0]['zhCN'] == ['再次泡温泉']
    assert finding.detail(root, 'HecateAboutTyphonFight02_B', 'en', {})['lines'][0]['en'] == ['Typhon follow-up']
    voice_clues = finding.query(root, search='InteractVoiceLines', offset=0, limit=20, language='en', permissions={})['items']
    assert not any(row['rawId'] == 'InteractVoiceLines' for row in voice_clues)
    assert any(row['rawId'] == 'NPC_Nemesis_01.InteractVoiceLines' and row['status'] == 'unknown'
               for row in voice_clues)
    # Searching the same bilingual character label shown in result headings
    # must find her scenes even when none of their dialogue contains that name.
    localized = finding.query(root, search='涅墨西斯', offset=0, limit=100, language='zh-CN', permissions={})
    assert {'NemesisPostTrueEnding01', 'NemesisBathHouseRepeatable01'} <= {row['rawId'] for row in localized['items']}
    assert finding.query(root, search='我的父亲', offset=0, limit=10, language='zh-CN', permissions={})['total'] == 1
    # A zh-CN-only Event/Id is still discoverable; its English counterpart
    # is explicitly missing, not silently copied or synthesized.
    chinese_only = finding.query(root, search='仅中文场景', offset=0, limit=10, language='zh-CN', permissions={})
    assert [row['rawId'] for row in chinese_only['items']] == ['HecateChineseEventOnly01']
    only_line = finding.detail(root, 'HecateChineseEventOnly01', 'zh-CN', {})['lines'][0]
    assert only_line['zhCN'] == ['仅中文场景'] and only_line['en'] == []
    assert only_line['speaker'] == '赫卡忒'
    assert only_line['events'] == ['HecateChineseEventOnly01']
    assert finding.query(root, search='My father has returned', offset=0, limit=10, language='en', permissions={})['total'] == 1
    assert finding.query(root, search='Nemesis_0407', offset=0, limit=10, language='en', permissions={})['total'] == 1
    assert finding.query(root, search='TrueEndingFinale01', offset=0, limit=10, language='en', permissions={})['total'] >= 1
    # Native SJSON comments are not fields: the active cue must survive,
    # and the commented words must never enter the searchable text index.
    assert finding.query(root, search='INJECTED TRANSLATION', offset=0, limit=10, language='en', permissions={})['total'] == 0
    assert finding.query(root, search='InjectedCue', offset=0, limit=10, language='en', permissions={})['total'] == 0
    # Event keys can be generic voice entrypoints, not scripted scenes.
    # An Event without an authored scene/reset identity is only a clue.
    for token in ('NPC_Nemesis_01.InteractVoiceLines', 'NemesisOnlyLocalizationEvent01'):
        event_only = finding.query(root, search=token, offset=0, limit=10, language='en', permissions={})
        assert event_only['total'] == 1
        assert event_only['items'][0]['status'] == 'unknown'
        assert not event_only['items'][0]['canStage']
        unresolved = finding.detail(root, event_only['items'][0]['rawId'], 'en', {})
        assert unresolved['sourceResolution'] == 'unresolved'
        assert not unresolved['canStage']
    assert finding.query(root, search='NemesisOnlyLocalizationEvent01', offset=0, limit=10,
                         language='en', permissions={}, state_filter='notRecorded')['total'] == 0
    assert finding.query(root, search='PreTrueEnding01', offset=0, limit=10, language='en', permissions={})['items'][0]['status'] == 'notRecorded'
    assert finding.query(root, search='Nemesis', offset=1, limit=1, language='en', permissions={})['total'] == found['total']

    nemesis = finding.detail(root, 'NemesisPostTrueEnding01', 'en', {})
    assert [item['cueId'] for item in nemesis['lines'][:2]] == ['Nemesis_0407', 'Nemesis_0408']
    assert nemesis['status'] == 'recorded' and nemesis['futureEligibility'] == 'unknown'
    n = flatten(nemesis['definitions'][0]['requirements'][0]['tree'])
    assert any('CurrentRun.TextLinesRecord.TrueEndingFinale01' in entry['text'] and entry['evidence'] == 'unknown' for entry in n)
    and_nodes = finding.detail(root, 'NemesisAboutChronosBossFights01', 'en', {})['definitions'][0]['requirements'][0]['tree']
    all_nodes = flatten(and_nodes)
    assert any('CurrentRun.RoomsEntered.I_Boss01' in entry['text'] for entry in all_nodes)
    # The authored comparison is not an eligibility prediction; the actual
    # cold-save scalar must nevertheless be inspectable alongside its threshold.
    observed_chronos = next(entry for entry in all_nodes if 'GameState.EnemyKills.Chronos' in entry['text'])
    assert observed_chronos['evidence'] == 'recorded'
    assert observed_chronos['observation'] == '8'
    assert observed_chronos['text'].endswith('Comparison: >=, Value: 3')
    current_run = next(entry for entry in all_nodes if 'CurrentRun.Cleared' in entry['text'])
    assert current_run['evidence'] == 'unknown' and current_run['observation'] is None
    assert any('CurrentRun.Cleared' in entry['text'] for entry in all_nodes)
    assert any('GameState.EnemyKills.Chronos' in entry['text'] and 'Comparison: >=' in entry['text'] for entry in all_nodes)
    assert any('GameState.TextLinesRecord.NemesisGift03' in entry['text'] for entry in all_nodes)

    variant = finding.detail(root, 'HecateAboutUltimateProgress03', 'zh-CN', {})
    variant_a = finding.detail(root, 'HecateAboutUltimateProgress03_A', 'zh-CN', {})
    assert variant['lines'][0]['cueId'] == variant_a['lines'][0]['cueId'] == 'Hecate_0795'
    assert variant['lines'][0]['zhCN'] == ['同一台词']
    assert any(entry['kind'] == 'or' for entry in flatten(variant['definitions'][0]['requirements'][0]['tree']))
    assert finding.detail(root, 'HecateAboutUltimateProgress04', 'zh-CN', {})['lines'][0]['zhCN'] == ['跨文件翻译']
    assert finding.detail(root, 'PreTrueEnding01', 'en', {})['definitions'] == []
    assert len(finding.detail(root, 'HadesWithPersephone01', 'en', {})['definitions']) == 2
    no_translation = finding.detail(root, 'HecateAboutTyphonFight03', 'zh-CN', {})['lines']
    assert len(no_translation) == 2 and all(not v['en'] and not v['zhCN'] for v in no_translation)
    hermes_missing = finding.detail(root, 'HermesFieldAboutTyphon03', 'zh-CN', {})['lines']
    assert [line['cueId'] for line in hermes_missing] == ['MelinoeField_4215']
    assert not hermes_missing[0]['zhCN'] and not hermes_missing[0]['en']

    allowed = finding.query(root, search='NemesisPostTrueEnding01', offset=0, limit=10,
                            language='en', permissions={'NemesisPostTrueEnding01': {'allowed': True, 'code': None, 'diagnostic': None}})['items'][0]
    assert allowed['canStage'] and allowed['stageID'] == 'dialogue:NemesisPostTrueEnding01'
    duplicated = LuaTable(0, 2, [('NemesisPostTrueEnding01', True), ('NemesisPostTrueEnding01', False)])
    conflicting_root = lua(GameState=lua(TextLinesRecord=duplicated))
    conflict = NativeDialogueInvestigation(game, expected_hash=checksum)
    conflicted = conflict.query(conflicting_root, search='NemesisPostTrueEnding01', offset=0, limit=20,
                                language='en', permissions={'NemesisPostTrueEnding01': {'allowed': True, 'code': None, 'diagnostic': None}})['items'][0]
    assert conflicted['status'] == 'ambiguous' and not conflicted['canStage']
    assert conflict.detail(conflicting_root, 'NemesisPostTrueEnding01', 'en', {'NemesisPostTrueEnding01': {'allowed': True, 'code': None, 'diagnostic': None}})['canStage'] is False
    missing = NativeDialogueInvestigation(game / 'missing', expected_hash=checksum)
    assert missing.query(root, search='', offset=0, limit=10, language='en', permissions={'NemesisPostTrueEnding01': {'allowed': True, 'code': None, 'diagnostic': None}})['items'][0]['canStage'] is False
    assert missing.native['status'] == 'missing'
    wrong = NativeDialogueInvestigation(game, expected_hash='f' * 64)
    assert wrong.native['status'] == 'mismatch' and not wrong.detail(root, 'NemesisPostTrueEnding01', 'en', {})['definitions']


    # A scene can be real and recorded yet forbidden as a standalone reset.
    # The actual Hades narrative write owner supplies the diagnosis displayed
    # by the investigation; the latter must not independently grant a write.
    protected_root = lua(GameState=lua(
        TextLinesRecord=lua(NemesisPostTrueEnding01=True, NemesisBathHouseRepeatable01=True),
        GiftTextLinesOrderRecord=lua(Nemesis=LuaTable(
            1, 0, [(1.0, 'NemesisPostTrueEnding01')]
        )),
        TextLinesChoiceRecord=lua(),
    ))
    narrative_rows = save_narrative.rows(protected_root, 'dialogue', 'en')
    decisions = {
        row['rawId']: {
            'allowed': row['editable'],
            'code': row['blockReasonCode'],
            'diagnostic': row['blockReasonDiagnostic'],
        } for row in narrative_rows
    }
    assert decisions['NemesisPostTrueEnding01']['code'] == 'giftLinked'
    assert decisions['NemesisBathHouseRepeatable01']['code'] == 'notResettable'
    for scene, code in (
        ('NemesisPostTrueEnding01', 'giftLinked'),
        ('NemesisBathHouseRepeatable01', 'notResettable'),
    ):
        summary = finding.query(
            protected_root, search=scene, offset=0, limit=10,
            language='en', permissions=decisions,
        )['items'][0]
        detail = finding.detail(protected_root, scene, 'en', decisions)
        assert summary['status'] == detail['status'] == 'recorded'
        assert not summary['canStage'] and not detail['canStage']
        assert summary['blockReasonCode'] == detail['blockReasonCode'] == code
        assert summary['reason'] == decisions[scene]['diagnostic']

    # The workspace must use the currently committed cold-save document, not
    # a LuaTable retained when investigation was first opened. Use the real
    # document serialization and workspace stage/review/apply path, but replace
    # the physical save writer with a temporary-file transaction double.
    save_root = lua(GameState=lua(
        TextLinesRecord=lua(NemesisPostTrueEnding01=True),
        GiftTextLinesOrderRecord=lua(),
        TextLinesChoiceRecord=lua(),
    ))
    header = Hades2SaveHeader(
        game_version=0x12, save_flags=3, timestamp=1,
        location='Crossroads', completed_runs=4, accumulated_meta_points=0,
        active_shrine_points=0, meta_upgrade_level=0, cosmetics_points=0,
        easy_mode=0, hard_mode=0, notable_lua_data=(),
        map_name='Hub_Main', next_map_name='F_Opening01',
    )
    initial_bytes = Hades2SaveDocument(header, [save_root]).to_bytes()
    target = game / 'Profile1.sav'
    target.write_bytes(initial_bytes)

    class TestColdSession:
        relative_path = 'Profile1.sav'

        def __init__(self):
            self.document = Hades2SaveDocument.from_bytes(target.read_bytes())

        def apply(self):
            encoded = self.document.to_bytes()
            Hades2SaveDocument.from_bytes(encoded)
            target.write_bytes(encoded)
            self.document = Hades2SaveDocument.load(target)
            return {'applied': True, 'replaced': True}

    # Match the installed-source gate to this *temporary* native-like fixture;
    # production keeps the fixed version hash and current Save policy.
    with patch('games.hades2.save_investigation._cached', return_value=finding.native):
        session = TestColdSession()
        workspace = Hades2SaveWorkspace(session, 'Profile1', game_path=game)
        first = workspace.query(domain='investigate', search='NemesisPostTrueEnding01', language='en')['items'][0]
        assert first['status'] == 'recorded' and first['canStage']
        before_detail = workspace.investigate(first['id'], 'en')
        assert before_detail['status'] == 'recorded' and before_detail['canStage']
        preview = workspace.stage('dialogue:NemesisPostTrueEnding01', 'set', False)
        assert preview['count'] >= 1
        assert target.read_bytes() == initial_bytes
        applied = workspace.apply()
        assert applied['applied']
        assert 'NemesisPostTrueEnding01' not in Hades2SaveDocument.load(target).lua_state['GameState']['TextLinesRecord']
        second = workspace.query(domain='investigate', search='NemesisPostTrueEnding01', language='en')['items'][0]
        after_detail = workspace.investigate(first['id'], 'en')
        assert second['status'] == 'notRecorded' and not second['canStage']
        assert after_detail['status'] == 'notRecorded' and not after_detail['canStage']
        assert after_detail['sourceStatus'] == 'available'
        assert workspace.review()['count'] == 0

print('hades2_save_investigation_ok')
