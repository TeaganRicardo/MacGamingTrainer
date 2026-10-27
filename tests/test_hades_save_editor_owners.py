"""Native saved-global shape, visible dialogue and physical entity ownership."""
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
sys.path.insert(0, str(ROOT / 'tests/fixtures'))
sys.path.insert(0, str(ROOT / 'Tools'))

from hades_save import Entries, build_save, environment, root_state
from games.hades.save_document import HadesSaveDocument
from games.hades.save_owners import NATIVE_OWNERS
from games.hades.save_workspace import HadesSaveWorkspace, logical, physical
from games.hades import save_values as values
from generate_hades_save_catalog import extract_scenes


def entry(workspace, keys):
    return values.identifier(physical(workspace.document, keys), workspace.baseline_generation)


with tempfile.TemporaryDirectory(prefix='mgt-hades-editor-owners-') as temporary:
    saves, service = environment(Path(temporary))
    source = {'rootId': 'main', 'relativePath': 'Profile1.sav'}
    target = {'rootId': 'main', 'relativePath': 'Profile2.sav'}
    workspace = HadesSaveWorkspace.open(service, source=source, target=target)
    assert set(workspace.document.lua_state) == {'GameState', 'CurrentRun', 'TextLinesRecord', 'CodexStatus'}
    for roots in NATIVE_OWNERS.values():
        for path in roots: logical(workspace.document, path)
    state = workspace.document.lua_state['GameState']
    assert not any(name in state for name in ('TextLinesRecord', 'CodexStatus', 'TextLinesChoiceRecord',
        'QuestsCompleted', 'WorldUpgrades', 'WorldUpgradesAdded', 'NPCInteractionsCheckRecord', 'GameplayTime', 'TotalTime'))
    assert ('TextLinesRecord',) in NATIVE_OWNERS['narrative']
    assert ('CodexStatus',) in NATIVE_OWNERS['narrative']
    assert ('GameState', 'RoomCountCache') in NATIVE_OWNERS['statistics']
    assert ('CurrentRun', 'GameplayTime') in NATIVE_OWNERS['statistics']
    narrative = workspace.query(domain='narrative', language='en', limit=200)['rows']
    nyx_id = entry(workspace, ('TextLinesRecord', 'NyxFirstMeeting'))
    nyx = next(row for row in narrative if row['id'] == nyx_id)
    assert nyx['owner'] == 'Nyx' and nyx['typedValue'] == values.typed(True)
    assert nyx['content'][0]['speaker'] == 'Nyx'
    assert nyx['content'][0]['text'].startswith('Do not despair, child.')
    assert nyx['content'][1]['speaker'] == 'Zagreus'
    chinese = workspace.query(domain='narrative', language='zh-CN', query='Such setbacks are inevitable')['rows']
    assert {row['id'] for row in chinese} == {nyx_id}
    assert chinese[0]['content'][0]['speaker'] == '倪克斯'
    assert chinese[0]['content'][0]['text'].startswith('不要绝望，孩子')
    assert any(row['id'] == nyx_id for row in workspace.query(domain='narrative', language='en', query='不要绝望')['rows'])
    assert not workspace.query(domain='narrative', query='RequiredMaxCompletedRuns')['rows']
    equipment = workspace.query(domain='equipment', limit=200)['rows']
    assert {entry(workspace, ('GameState', key)) for key in ('LastAwardTrait', 'LastAssistTrait')} <= {row['id'] for row in equipment}
    statistics = workspace.query(domain='statistics', limit=200)['rows']
    assert {entry(workspace, ('GameState', 'RoomCountCache')), entry(workspace, ('CurrentRun', 'GameplayTime'))} <= {row['id'] for row in statistics}
    for keys, value in ((('TextLinesRecord', 'NyxFirstMeeting'), False),
                        (('CodexStatus', 'ChthonicGods', 'NPC_Nyx_01', 'Amount'), 9),
                        (('GameState', 'Cosmetics', 'Cosmetic_DrapesRed'), False),
                        (('GameState', 'LastAwardTrait'), 'DirectionalArmorTrait'),
                        (('CurrentRun', 'GameplayTime'), 140)):
        workspace.stage(entry(workspace, keys), 'set', values.typed(value), baseline_generation=workspace.baseline_generation)
    workspace.apply(baseline_generation=workspace.baseline_generation)
    installed = HadesSaveDocument.load(saves / 'Profile2.sav')
    assert installed.lua_state['TextLinesRecord']['NyxFirstMeeting'] is False
    assert installed.lua_state['CodexStatus']['ChthonicGods']['NPC_Nyx_01']['Amount'] == 9
    assert installed.lua_state['GameState']['Cosmetics']['Cosmetic_DrapesRed'] is False
    assert installed.lua_state['GameState']['LastAwardTrait'] == 'DirectionalArmorTrait'
    assert installed.lua_state['CurrentRun']['GameplayTime'] == 140
    assert 'TextLinesRecord' not in installed.lua_state['GameState']

    # Table rows and their fields share one physical entity; a matching Nyx
    # never pulls Achilles into the same owner or search result.
    native = root_state()
    native['GameState']['Gift'] = Entries([
        ('NPC_Nyx_01', {'Value': 1, 'NewTraits': ['BackstabAlphaStrikeTrait']}),
        ('NPC_Nyx_01', {'Value': 4, 'NewTraits': ['BackstabAlphaStrikeTrait']}),
        ('NPC_Achilles_01', {'Value': 2, 'NewTraits': ['DirectionalArmorTrait']})])
    (saves / 'Profile1.sav').write_bytes(build_save(state=native))
    duplicate = HadesSaveWorkspace.open(service, source=source)
    rows = duplicate.query(domain='relationships', query='倪克斯', language='en', limit=200)['rows']
    gift = physical(duplicate.document, ('GameState', 'Gift'))
    expected_owners = {values.identifier(gift + (index * 2 + 1,), duplicate.baseline_generation) for index in (0, 1)}
    gift_rows = [row for row in rows if row['ownerId'] in expected_owners]
    assert {row['ownerId'] for row in gift_rows} == expected_owners
    assert all(row['owner'] == 'Nyx' for row in rows)
    assert not any('Achilles' in row['owner'] for row in rows)
    for owner in expected_owners:
        entity = [row for row in gift_rows if row['ownerId'] == owner]
        assert any(row['id'] == owner and row['hasChildren'] for row in entity)
        assert any(row['name'] == 'Gift progress' for row in entity)
    page = duplicate.query(domain='relationships', query='Nyx', limit=1)
    owner = page['rows'][0]['ownerId']
    assert {row['id'] for row in page['rows']} == {row['id'] for row in rows if row['ownerId'] == owner}
    assert page['nextOffset'] == page['offset'] + page['limit']

    # The static extractor admits visible line/choice content, never hidden
    # prerequisite tables or callbacks, even if those contain a Text field.
    native_text = Path(temporary) / 'NPCData.lua'
    native_text.write_text('''UnitSetData.NPCs = { NPC_Nyx_01 = { InteractTextLineSets = {
        VisibleScene = { RequiredTextLines = { { Text = "invisible prerequisite" } },
            EndVoiceLines = { { Text = "invisible callback metadata" } },
            { Cue = "/VO/Nyx_1", Text = "Visible English", Speaker = "NPC_Nyx_01",
              Choices = { { Text = "Visible choice", Speaker = "CharProtag" } } } }
    } } }''')
    text = {language: {'NPC_Nyx_01': {'DisplayName': 'Nyx' if language == 'en' else '倪克斯'},
                      'PlayerUnit': {'DisplayName': 'Zagreus' if language == 'en' else '扎格列欧斯'},
                      'Nyx_1': {'DisplayName': '可见中文'}} for language in ('en', 'zh-CN')}
    extracted = extract_scenes([native_text], text)['VisibleScene']['content']
    assert extracted['en'] == [{'speaker': 'Nyx', 'text': 'Visible English'}, {'speaker': 'Zagreus', 'text': 'Visible choice'}]
    assert extracted['zh-CN'][0] == {'speaker': '倪克斯', 'text': '可见中文'}
    assert 'invisible' not in str(extracted)

print('hades_save_editor_native_owners_visible_dialogue_and_complete_entities_ok')
