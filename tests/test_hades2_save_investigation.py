"""Source-backed dialogue investigation across absent, duplicate and transient owners."""

import hashlib
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from games.hades2.save_document import LuaTable
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
  // { Id = "Commented_01" DisplayName = "Not live" Event = "NemesisPostTrueEnding01" }
 ]
}
''', encoding='utf-8')
    (english / '_NPCData_Hecate.en.sjson').write_text('''{ Texts = [
 { Id = "Hecate_0795" DisplayName = "Shared" Event = "HecateAboutUltimateProgress03_A" }
] }''', encoding='utf-8')
    (english / '_EnemyData_Hecate.en.sjson').write_text('''{ Texts = [
 { Id = "Hecate_0942" DisplayName = "From enemy text" Event = "HecateBossAboutEndingPath04" }
] }''', encoding='utf-8')
    (chinese / '_NPCData_Nemesis.zh-CN.sjson').write_text('''{ Texts = [
 { Id = "Nemesis_0407" DisplayName = "我的父亲回来了" }
 { Id = "Nemesis_0252" DisplayName = "多次击败克洛诺斯" }
] }''', encoding='utf-8')
    (chinese / '_NPCData_Hecate.zh-CN.sjson').write_text('''{ Texts = [
 { Id = "Hecate_0795" DisplayName = "同一台词" }
 { Id = "Hecate_ZHOnly9001" DisplayName = "仅中文场景" Event = "HecateChineseEventOnly01" Speaker = "赫卡忒" }
] }''', encoding='utf-8')
    (chinese / '_EnemyData_Hecate.zh-CN.sjson').write_text('''{ Texts = [
 { Id = "Hecate_0942" DisplayName = "跨文件翻译" }
] }''', encoding='utf-8')
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
    finding = NativeDialogueInvestigation(root, game, expected_hash=checksum)
    assert finding.native['status'] == 'available'
    assert finding.query(search='', offset=0, limit=30, language='en', writable=set())['total'] == 2
    found = finding.query(search='Nemesis', offset=0, limit=100, language='zh-CN', writable=set())
    assert found['total'] >= 2
    assert {row['rawId'] for row in found['items']} >= {'NemesisPostTrueEnding01', 'NemesisAboutChronosBossFights01'}
    assert finding.query(search='我的父亲', offset=0, limit=10, language='zh-CN', writable=set())['total'] == 1
    # A zh-CN-only Event/Id is still discoverable; its English counterpart
    # is explicitly missing, not silently copied or synthesized.
    chinese_only = finding.query(search='仅中文场景', offset=0, limit=10, language='zh-CN', writable=set())
    assert [row['rawId'] for row in chinese_only['items']] == ['HecateChineseEventOnly01']
    only_line = finding.detail('HecateChineseEventOnly01', 'zh-CN', set())['lines'][0]
    assert only_line['zhCN'] == ['仅中文场景'] and only_line['en'] == []
    assert only_line['speaker'] == '赫卡忒'
    assert only_line['events'] == ['HecateChineseEventOnly01']
    assert finding.query(search='My father has returned', offset=0, limit=10, language='en', writable=set())['total'] == 1
    assert finding.query(search='Nemesis_0407', offset=0, limit=10, language='en', writable=set())['total'] == 1
    assert finding.query(search='TrueEndingFinale01', offset=0, limit=10, language='en', writable=set())['total'] >= 1
    # Native SJSON comments are not fields: the active cue must survive,
    # and the commented words must never enter the searchable text index.
    assert finding.query(search='INJECTED TRANSLATION', offset=0, limit=10, language='en', writable=set())['total'] == 0
    assert finding.query(search='InjectedCue', offset=0, limit=10, language='en', writable=set())['total'] == 0
    # Event keys can be generic voice entrypoints, not scripted scenes.
    # An Event without an authored scene/reset identity is only a clue.
    for token in ('NPC_Nemesis_01.InteractVoiceLines', 'NemesisOnlyLocalizationEvent01'):
        event_only = finding.query(search=token, offset=0, limit=10, language='en', writable=set())
        assert event_only['total'] == 1
        assert event_only['items'][0]['status'] == 'unknown'
        assert not event_only['items'][0]['canStage']
        unresolved = finding.detail(event_only['items'][0]['rawId'], 'en', set())
        assert unresolved['sourceResolution'] == 'unresolved'
        assert not unresolved['canStage']
    assert finding.query(search='NemesisOnlyLocalizationEvent01', offset=0, limit=10,
                         language='en', writable=set(), state_filter='notRecorded')['total'] == 0
    assert finding.query(search='PreTrueEnding01', offset=0, limit=10, language='en', writable=set())['items'][0]['status'] == 'notRecorded'
    assert finding.query(search='Nemesis', offset=1, limit=1, language='en', writable=set())['total'] == found['total']

    nemesis = finding.detail('NemesisPostTrueEnding01', 'en', set())
    assert [item['cueId'] for item in nemesis['lines'][:2]] == ['Nemesis_0407', 'Nemesis_0408']
    assert nemesis['status'] == 'recorded' and nemesis['futureEligibility'] == 'unknown'
    n = flatten(nemesis['definitions'][0]['requirements'][0]['tree'])
    assert any('CurrentRun.TextLinesRecord.TrueEndingFinale01' in entry['text'] and entry['evidence'] == 'unknown' for entry in n)
    and_nodes = finding.detail('NemesisAboutChronosBossFights01', 'en', set())['definitions'][0]['requirements'][0]['tree']
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

    variant = finding.detail('HecateAboutUltimateProgress03', 'zh-CN', set())
    variant_a = finding.detail('HecateAboutUltimateProgress03_A', 'zh-CN', set())
    assert variant['lines'][0]['cueId'] == variant_a['lines'][0]['cueId'] == 'Hecate_0795'
    assert variant['lines'][0]['zhCN'] == ['同一台词']
    assert any(entry['kind'] == 'or' for entry in flatten(variant['definitions'][0]['requirements'][0]['tree']))
    assert finding.detail('HecateAboutUltimateProgress04', 'zh-CN', set())['lines'][0]['zhCN'] == ['跨文件翻译']
    assert finding.detail('PreTrueEnding01', 'en', set())['definitions'] == []
    assert len(finding.detail('HadesWithPersephone01', 'en', set())['definitions']) == 2
    no_translation = finding.detail('HecateAboutTyphonFight03', 'zh-CN', set())['lines']
    assert len(no_translation) == 2 and all(not v['en'] and not v['zhCN'] for v in no_translation)
    hermes_missing = finding.detail('HermesFieldAboutTyphon03', 'zh-CN', set())['lines']
    assert [line['cueId'] for line in hermes_missing] == ['MelinoeField_4215']
    assert not hermes_missing[0]['zhCN'] and not hermes_missing[0]['en']

    allowed = finding.query(search='NemesisPostTrueEnding01', offset=0, limit=10,
                            language='en', writable={'NemesisPostTrueEnding01'})['items'][0]
    assert allowed['canStage'] and allowed['stageID'] == 'dialogue:NemesisPostTrueEnding01'
    duplicated = LuaTable(0, 2, [('NemesisPostTrueEnding01', True), ('NemesisPostTrueEnding01', False)])
    conflicting_root = lua(GameState=lua(TextLinesRecord=duplicated))
    conflict = NativeDialogueInvestigation(conflicting_root, game, expected_hash=checksum)
    conflicted = conflict.query(search='NemesisPostTrueEnding01', offset=0, limit=20,
                                language='en', writable={'NemesisPostTrueEnding01'})['items'][0]
    assert conflicted['status'] == 'ambiguous' and not conflicted['canStage']
    assert conflict.detail('NemesisPostTrueEnding01', 'en', {'NemesisPostTrueEnding01'})['canStage'] is False
    missing = NativeDialogueInvestigation(root, game / 'missing', expected_hash=checksum)
    assert missing.query(search='', offset=0, limit=10, language='en', writable={'NemesisPostTrueEnding01'})['items'][0]['canStage'] is False
    assert missing.native['status'] == 'missing'
    wrong = NativeDialogueInvestigation(root, game, expected_hash='f' * 64)
    assert wrong.native['status'] == 'mismatch' and not wrong.detail('NemesisPostTrueEnding01', 'en', set())['definitions']

print('hades2_save_investigation_ok')
