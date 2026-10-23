"""Narrative record edits and native resets have distinct, writable owners."""
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
from core.module_manifest import SaveManagementSpec, SaveRootSpec
from core.save_service import CoreSaveService
from games.hades2.save_document import Hades2SaveDocument, Hades2SaveHeader, LuaTable
from games.hades2.save_provider import Hades2SaveProvider
from games.hades2.save_workspace import Hades2SaveWorkspace


def table(values):
    return LuaTable(0, len(values), list(values.items()))


def document():
    header = Hades2SaveHeader(game_version=0x12, save_flags=0, timestamp=100,
        location='Crossroads', completed_runs=1, accumulated_meta_points=0,
        active_shrine_points=0, meta_upgrade_level=0, cosmetics_points=0,
        easy_mode=0, hard_mode=0, notable_lua_data=('GameState', 'CurrentRun'),
        map_name='Hub_Main', next_map_name='F_Opening01')
    state = table({
        'Resources': table({'GiftPoints': 2}),
        'Flags': table({'UncataloguedBoolean': True}),
        'QuestStatus': table({'QuestHelpDora': 'CashedOut', 'QuestUnlockMoros': 'Unlocked'}),
        'QuestsCompleted': table({'QuestHelpDora': True}),
        'QuestsViewed': table({'QuestHelpDora': True}),
        'TextLinesRecord': table({'GiftLine': True, 'UnverifiedScene': False, 'HecatePostTrueEnding01': True}),
        'TextLinesChoiceRecord': table({'UnverifiedScene': ' Choice A '}),
        'GiftTextLinesOrderRecord': table({'Hecate': table({1: 'GiftLine'})}),
        'SpeechRecord': table({'/VO/Unknown_0001': 3, '/VO/Legacy_0001': True}),
        'KeepOpaque': table({'Future': 'unchanged'}),
    })
    run = table({'TextLinesRecord': table({'GiftLine': True}), 'SpeechRecord': table({'/VO/Unknown_0001': 1})})
    return Hades2SaveDocument(header, [table({'GameState': state, 'CurrentRun': run})])


with tempfile.TemporaryDirectory(prefix='mgt-narrative-editing-') as temporary:
    base = Path(temporary)
    saves = base / 'saves'
    saves.mkdir()
    profile = b'Profile1'
    (saves / 'activeProfile').write_bytes(b'SGB1' + struct.pack('<I', len(profile)) + profile)
    path = saves / 'Profile1.sav'
    path.write_bytes(document().to_bytes())
    original = path.read_bytes()
    spec = SaveManagementSpec(roots=(SaveRootSpec('main', str(saves), ('Profile*.sav', 'activeProfile')),),
        provider='games.hades2.save_provider:Hades2SaveProvider', hot_backup=True,
        restore_policy='hotPreferred', staged_restore=True)
    service = CoreSaveService('hades2', spec, base / 'data', lambda: False,
        provider_loader=lambda _: Hades2SaveProvider())
    work = Hades2SaveWorkspace.open(service)
    work.stage('quest:QuestCatchFish', 'setEnum', 'Unrecorded')
    assert work.review()['actionCount'] == 0, 'absent→unrecorded created a no-op basket that Apply cannot write'
    work.stage('resource:GiftPoints', 'set', 1_000_000)
    assert work.review()['actions'][0]['after'] == 1_000_000
    work.unstage('resource:GiftPoints')
    # A claimed status is a saved value, not a license to fabricate a reward.
    quests = work.query(domain='progression', search='QuestHelpDora', language='en')['items']
    row = next(r for r in quests if r['id'] == 'quest:QuestHelpDora')
    assert row['editable'], 'a valid claimed quest status still has blanket read-only policy'
    work.stage('quest:QuestHelpDora', 'setEnum', 'Unlocked')
    work.stage('quest:QuestUnlockMoros', 'setEnum', 'CashedOut')
    work.stage('quest:QuestCatchFish', 'setEnum', 'Complete')
    work.stage('flag:UncataloguedBoolean', 'set', False)
    work.stage('dialogue:GiftLine', 'set', False)
    work.stage('dialogue:UnverifiedScene', 'set', True)
    work.stage('dialogueChoice:UnverifiedScene', 'set', ' Choice B ')
    work.stage('questObservation:QuestsViewed:QuestHelpDora', 'set', False)
    work.stage('questObservation:QuestsUpdated:QuestHelpDora', 'set', True)
    work.stage('speech:/VO/Unknown_0001', 'set', 12)
    work.stage('speech:/VO/Legacy_0001', 'set', False)
    for identifier, after in (('questObservation:QuestsCompleted:QuestCatchFish', False),
                              ('dialogueReset:GiftLine', False)):
        try:
            work.stage(identifier, 'set', after)
        except ValueError:
            pass
        else:
            raise AssertionError('conflicting explicit action overwrote the accepted basket')
    changes = work.review(language='en')
    assert changes['actionCount'] == 11
    assert changes['effectCount'] >= 2  # completion facts for the status owner
    assert path.read_bytes() == original, 'stage touched the pinned physical source'
    assert work.document.lua_state['GameState']['TextLinesRecord']['GiftLine'] is True
    # Invalid counter/string inputs leave every accepted action intact.
    for identifier, value in (('speech:/VO/Unknown_0001', 1.5), ('speech:/VO/Unknown_0001', -1),
                               ('speech:/VO/Legacy_0001', 1), ('dialogueChoice:UnverifiedScene', True)):
        try:
            work.stage(identifier, 'set', value)
        except ValueError:
            pass
        else:
            raise AssertionError('wrong native record type was accepted')
    assert work.review()['actionCount'] == 11
    applied = work.apply()
    assert applied['applied'] and applied['runtimeReloaded'] is False
    reopened = Hades2SaveWorkspace.open(service)
    saved = reopened.document.lua_state
    state = saved['GameState']
    assert state['QuestStatus']['QuestHelpDora'] == 'Unlocked'
    assert state['QuestsCompleted'].get('QuestHelpDora') is None
    assert state['QuestStatus']['QuestUnlockMoros'] == 'CashedOut'
    assert state['QuestsCompleted']['QuestUnlockMoros'] is True
    assert state['QuestStatus']['QuestCatchFish'] == 'Complete'
    assert state['Resources']['GiftPoints'] == 2, 'record editing fabricated a reward acquisition'
    assert state['Flags']['UncataloguedBoolean'] is False
    assert state['TextLinesRecord']['GiftLine'] is False
    assert state['TextLinesRecord']['UnverifiedScene'] is True
    assert state['TextLinesChoiceRecord']['UnverifiedScene'] == ' Choice B '
    assert state['QuestsViewed']['QuestHelpDora'] is False
    assert state['QuestsUpdated']['QuestHelpDora'] is True
    assert state['SpeechRecord']['/VO/Unknown_0001'] == 12
    assert state['SpeechRecord']['/VO/Legacy_0001'] is False
    assert saved['CurrentRun']['TextLinesRecord']['GiftLine'] is True
    assert saved['CurrentRun']['SpeechRecord']['/VO/Unknown_0001'] == 1
    assert state['GiftTextLinesOrderRecord']['Hecate'][1] == 'GiftLine'
    assert state['KeepOpaque']['Future'] == 'unchanged'
    previous = service.store.load_verified_snapshot(applied['previousSnapshotId'])
    assert (previous['root'] / 'files/main/Profile1.sav').read_bytes() == original
    assert reopened.review()['actionCount'] == 0
    # Native reset is still a complete distinct operation, including run/choice
    # owners, and refuses unknown/gift-linked reset semantics. Direct field
    # editing above remains available regardless of that separate capability.
    reopened.stage('dialogueReset:HecatePostTrueEnding01', 'set', False)
    try:
        reopened.stage('dialogueReset:UnverifiedScene', 'set', False)
    except ValueError:
        pass
    else:
        raise AssertionError('an unknown event acquired native reset semantics')
    reopened.apply()
    final = Hades2SaveDocument.load(path).lua_state['GameState']
    assert final['TextLinesRecord'].get('HecatePostTrueEnding01') is None
    assert final['TextLinesRecord']['UnverifiedScene'] is True
    repair_document = Hades2SaveDocument.load(path)
    repair_document.lua_state['GameState']['QuestsCompleted'].pop('QuestCatchFish')
    path.write_bytes(repair_document.to_bytes())
    repair = Hades2SaveWorkspace.open(service)
    repair.stage('quest:QuestCatchFish', 'setEnum', 'Complete')
    assert repair.review()['actionCount'] == 1, 'same status suppressed a necessary completion repair'
    repair.apply()
    assert Hades2SaveDocument.load(path).lua_state['GameState']['QuestsCompleted']['QuestCatchFish'] is True
print('hades2_save_narrative_editing_ok')
