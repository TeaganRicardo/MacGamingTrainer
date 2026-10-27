"""Ordinary native purpose boundaries retain complete typed Advanced editing."""
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
sys.path.insert(0, str(ROOT / 'tests/fixtures'))

from hades_save import Entries, build_save, environment, root_state
from games.hades.save_document import HadesSaveDocument
from games.hades.save_workspace import HadesSaveWorkspace, physical
from games.hades import save_values as values


def entry(workspace, keys):
    return values.identifier(physical(workspace.document, keys), workspace.baseline_generation)


with tempfile.TemporaryDirectory(prefix='mgt-hades-editor-purpose-') as temporary:
    saves, service = environment(Path(temporary))
    native = root_state()
    hero = native['CurrentRun']['Hero']
    hero['UnknownFutureField'] = {'Health': 7, 'Bytes': b'\xff\x00'}
    hero['Traits'] = [{'Name': 'AttackMissileTrait', 'Rarity': 'Rare',
                       'UnknownTraitField': {'RequiredTextLines': ['NyxFirstMeeting']}}]
    native['CurrentRun']['RoomHistory'] = [{'Name': 'RoomOpening', 'Encounter': {'Name': 'OpeningEmpty'}}]
    native['CurrentRun']['UnknownRunField'] = {'GameplayTime': 9}
    native['GameState']['Gift']['NPC_Nyx_01']['UnknownGiftField'] = {'Value': 4}
    native['GameState']['RunHistory'][0]['RoomHistory'] = [{'Name': 'RoomOpening'}]
    native['GameState']['RoomCountCache']['UnknownRoomField'] = 5
    # Arbitrary encoded keys also stay Advanced without disrupting ordinary browsing.
    hero['UnknownKeys'] = Entries([(True, 1), (Entries([('key', 2)]), 3)])
    (saves / 'Profile1.sav').write_bytes(build_save(state=native))
    source = {'rootId': 'main', 'relativePath': 'Profile1.sav'}
    target = {'rootId': 'main', 'relativePath': 'Profile2.sav'}
    workspace = HadesSaveWorkspace.open(service, source=source, target=target)
    original_hash = workspace.session.source_sha256
    original_bytes = (saves / 'Profile1.sav').read_bytes()
    unresolved = [
        ('CurrentRun', 'Hero', 'UnknownFutureField'),
        ('CurrentRun', 'Hero', 'UnknownFutureField', 'Health'),
        ('CurrentRun', 'Hero', 'Traits', 1, 'UnknownTraitField'),
        ('CurrentRun', 'RoomHistory'), ('CurrentRun', 'RoomHistory', 1, 'Name'),
        ('CurrentRun', 'UnknownRunField', 'GameplayTime'),
        ('GameState', 'Gift', 'NPC_Nyx_01', 'UnknownGiftField', 'Value'),
        ('GameState', 'RunHistory', 1, 'RoomHistory'),
        ('GameState', 'RoomCountCache', 'UnknownRoomField'),
    ]
    unresolved_ids = {entry(workspace, path) for path in unresolved}
    for domain in ('equipment', 'relationships', 'statistics', 'history'):
        for language in ('en', 'zh-CN'):
            rows = workspace.query(domain=domain, language=language, limit=200)['rows']
            assert not unresolved_ids.intersection(row['id'] for row in rows)
            assert not workspace.query(domain=domain, language=language, query='Unknown')['rows']
            assert not workspace.query(domain=domain, language=language, query='RoomHistory')['rows']
    hero_id = entry(workspace, ('CurrentRun', 'Hero'))
    browsed = workspace.query(domain='equipment', parentId=hero_id)['rows']
    health_id = entry(workspace, ('CurrentRun', 'Hero', 'Health'))
    assert next(row for row in browsed if row['id'] == health_id)['name'] == 'Life'
    assert not unresolved_ids.intersection(row['id'] for row in browsed)
    known_room = entry(workspace, ('GameState', 'RoomCountCache', 'RoomOpening'))
    assert known_room in {row['id'] for row in workspace.query(domain='statistics')['rows']}
    try:
        workspace.query(domain='history', parentId=entry(workspace, ('CurrentRun', 'RoomHistory')))
    except ValueError as error:
        assert 'Advanced' in str(error)
    else: raise AssertionError('An unresolved ordinary parent exposed its raw descendants')

    advanced = workspace.query(domain='advanced', query='UnknownFutureField', limit=200)['rows']
    unknown_id = entry(workspace, ('CurrentRun', 'Hero', 'UnknownFutureField', 'Health'))
    assert unknown_id in {row['id'] for row in advanced}
    unknown = workspace.detail(unknown_id)['row']
    assert unknown['editable'] and unknown['typedValue'] == values.typed(7)
    assert unknown['warning']
    room_history_id = entry(workspace, ('CurrentRun', 'RoomHistory'))
    room_fields = workspace.query(domain='advanced', parentId=room_history_id)['rows']
    assert any(row['hasChildren'] for row in room_fields)
    room_name_id = entry(workspace, ('CurrentRun', 'RoomHistory', 1, 'Name'))
    for identifier, value in ((unknown_id, 13), (room_name_id, 'RoomPreRun'), (health_id, 41)):
        workspace.stage(identifier, 'set', values.typed(value), baseline_generation=workspace.baseline_generation)
    review = workspace.review()
    assert {action['id'] for action in review['actions']} == {unknown_id, room_name_id, health_id}
    assert all(action['typedValue'] for action in review['actions'])
    receipt = workspace.apply(baseline_generation=workspace.baseline_generation)
    assert receipt['applied'] and receipt['verified']
    reread = HadesSaveDocument.load(saves / 'Profile2.sav').lua_state
    assert reread['CurrentRun']['Hero']['Health'] == 41
    assert reread['CurrentRun']['Hero']['UnknownFutureField']['Health'] == 13
    assert reread['CurrentRun']['Hero']['UnknownFutureField']['Bytes'].encode('utf-8', errors='surrogateescape') == b'\xff\x00'
    assert reread['CurrentRun']['RoomHistory'][1]['Name'] == 'RoomPreRun'
    assert reread['GameState']['RunHistory'][1]['RoomHistory'][1]['Name'] == 'RoomOpening'
    assert workspace.summary()['sourceSHA256'] == original_hash
    assert (saves / 'Profile1.sav').read_bytes() == original_bytes

print('hades_save_editor_purpose_boundary_and_unrestricted_advanced_journey_ok')
