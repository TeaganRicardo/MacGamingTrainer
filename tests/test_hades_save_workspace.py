"""Complete synthetic Hades I journeys over temporary Core Save transactions."""
import hashlib
import json
from pathlib import Path
import stat
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
sys.path.insert(0, str(ROOT / 'tests/fixtures'))

from hades_save import Entries, build_save, environment, root_state, sized
from core.adapter import GameAdapterContext
from core.errors import PresentableError
from core.protocol import JsonlRequestRouter
from games.hades.adapter import HadesAdapter
from games.hades.preferences import HadesPreferenceStore
from games.hades.save_document import HadesSaveDocument
from games.hades.save_workspace import HadesSaveWorkspace, physical
from games.hades import save_values as values


def stage(workspace, *args):
    return workspace.stage(*args, baseline_generation=workspace.baseline_generation)


def unstage(workspace, *args):
    return workspace.unstage(*args, baseline_generation=workspace.baseline_generation)


def set_target(workspace, target):
    return workspace.set_target(target, baseline_generation=workspace.baseline_generation)


def apply(workspace):
    return workspace.apply(baseline_generation=workspace.baseline_generation)


def rejects(kind, action):
    try: action()
    except kind as error: return error
    raise AssertionError('Invalid editor operation succeeded')


def scalar(value): return values.typed(value)


def entry(workspace, keys): return values.identifier(physical(workspace.document, keys), workspace.baseline_generation)


def state(path): return HadesSaveDocument.load(path).lua_state['GameState']


with tempfile.TemporaryDirectory(prefix='mgt-hades-editor-journeys-') as temporary:
    base = Path(temporary)
    saves, service = environment(base / 'main', running=True)
    other_saves, other_service = environment(base / 'other', game_id='hades2')
    untouched_other = {path.name: path.read_bytes() for path in other_saves.iterdir()}
    original = (saves / 'Profile1.sav').read_bytes()
    target_original = (saves / 'Profile2.sav').read_bytes()
    source = {'rootId': 'main', 'relativePath': 'Profile1.sav'}
    target = {'rootId': 'main', 'relativePath': 'Profile2.sav'}
    inventory = HadesSaveWorkspace.inventory(service)
    assert inventory['defaultSource'] == source
    assert not any(row['relativePath'].endswith('.v.sav') for row in inventory['sources'])
    assert any(row['relativePath'] == 'Profile1_Temp.sav' for row in inventory['sources'])
    workspace = HadesSaveWorkspace.open(service, source=source)
    assert workspace.summary()['target'] is None
    rejects(ValueError, lambda: apply(workspace))
    set_target(workspace, target)
    original_hash = workspace.summary()['sourceSHA256']
    assert original_hash == hashlib.sha256(original).hexdigest()
    assert workspace.summary()['domains'][0] == 'all'
    for domain in workspace.summary()['domains']:
        page = workspace.query(domain=domain, language='zh-CN')
        assert page['rows'], domain
        assert all(row['editable'] and row['ownerId'] and row['groupId'] for row in page['rows'])
        assert all('set' in row['operations'] for row in page['rows'])
    global_ids = {row['id'] for row in workspace.query(domain='all', language='en', limit=200)['rows']}
    assert {'resource:MetaPoints', 'mirror:1', 'aspectSelection:SwordWeapon'} <= global_ids
    assert any(row['id'] == 'mirror:1' for row in workspace.query(domain='all', language='en', query='影子袭击')['rows'])
    assert any(row['id'] == 'mirror:1' for row in workspace.query(domain='progression', language='en', query='影子袭击')['rows'])
    # Every returned owner is complete, even with a one-row request.
    complete = workspace.query(domain='equipment', language='en', limit=200)
    page = workspace.query(domain='equipment', language='en', limit=1)
    owner = page['rows'][0]['ownerId']
    assert {row['id'] for row in page['rows']} == {row['id'] for row in complete['rows'] if row['ownerId'] == owner}
    assert page['nextOffset'] == page['offset'] + page['limit']

    stage(workspace, 'resource:MetaPoints', 'set', scalar(20))
    revised = stage(workspace, 'resource:MetaPoints', 'set', scalar(25))
    assert revised['count'] == 1 and revised['actions'][0]['after'] == '25'
    assert unstage(workspace, 'resource:MetaPoints')['count'] == 0
    stage(workspace, 'resource:MetaPoints', 'set', scalar(18))
    stage(workspace, 'mirror:1', 'set', scalar(True))
    mirror_review = next(action for action in workspace.review()['actions'] if action['id'] == 'mirror:1')
    assert len(mirror_review['effects']) == 2
    stage(workspace, 'aspectRank:SwordWeapon:2', 'set', scalar(3))
    rank_review = next(action for action in workspace.review()['actions'] if action['id'].startswith('aspectRank:'))
    assert len(rank_review['effects']) == 3
    pending_before_error = workspace.review()
    rejects(ValueError, lambda: stage(workspace, 'aspectSelection:SwordWeapon', 'set', scalar(4)))
    assert workspace.review() == pending_before_error
    stage(workspace, entry(workspace, ('GameState', 'TimesCleared')), 'set', scalar(50))
    stage(workspace, entry(workspace, ('GameState', 'CompletedRunsCache')), 'set', scalar(6))
    stage(workspace, entry(workspace, ('GameState', 'Gift', 'NPC_Nyx_01', 'Value')), 'set', scalar(4))
    stage(workspace, entry(workspace, ('TextLinesRecord', 'NyxFirstMeeting')), 'set', scalar(False))
    stage(workspace, entry(workspace, ('GameState', 'UnknownFutureField', 'Marker')), 'set', scalar('edited-fixed-source'))
    bad_header = rejects(ValueError, lambda: stage(workspace, 'h:completed_runs', 'set', scalar(99)))
    assert 'overlap' in str(bad_header) or 'conflict' in str(bad_header)
    assert not any(action['id'] == 'h:completed_runs' for action in workspace.review()['actions'])

    # Source slot switching and newer external target bytes cannot redirect or
    # rebase this already-read document.
    (saves / 'activeProfile').write_bytes(b'SGB1' + sized('Profile2'))
    external_target = build_save(999, 'external-newer-target')
    (saves / 'Profile2.sav').write_bytes(external_target)
    (saves / 'Profile2.sav').chmod(0o600)
    receipt = apply(workspace)
    assert receipt['applied'] and receipt['verified'] and receipt['hot']
    assert not receipt['runtimeReloaded'] and receipt['target'] == target
    assert receipt['source'] == {'kind': 'currentFile', **source}
    assert receipt['sourceSHA256'] == original_hash
    assert receipt['installedSHA256'] == hashlib.sha256((saves / 'Profile2.sav').read_bytes()).hexdigest()
    assert stat.S_IMODE((saves / 'Profile2.sav').stat().st_mode) == 0o600
    installed = state(saves / 'Profile2.sav')
    assert installed['Resources']['MetaPoints'] == 18
    assert installed['LifetimeResourcesGained']['MetaPoints'] == 100
    assert installed['LifetimeResourcesSpent']['MetaPoints'] == 88
    assert installed['MetaUpgradesUnlocked']['BackstabMetaUpgrade'] is True
    assert installed['MetaUpgradesUnlocked']['FirstStrikeMetaUpgrade'] is True
    assert installed['WeaponUnlocks']['SwordWeapon'][2] == 3
    assert installed['LastWeaponUpgradeData']['SwordWeapon']['Index'] == 2
    assert installed['LastInteractedWeaponUpgrade']['WeaponName'] == 'SwordWeapon'
    assert installed['LastInteractedWeaponUpgrade']['ItemIndex'] == 2
    assert installed['TimesCleared'] == 50 and len(installed['RunHistory']) == 2
    assert installed['CompletedRunsCache'] == 6 and HadesSaveDocument.load(saves / 'Profile2.sav').header.completed_runs == 6
    assert installed['Gift']['NPC_Nyx_01']['Value'] == 4
    assert HadesSaveDocument.load(saves / 'Profile2.sav').lua_state['TextLinesRecord']['NyxFirstMeeting'] is False
    assert installed['UnknownFutureField']['Marker'] == 'edited-fixed-source'
    assert (saves / 'Profile1.sav').read_bytes() == original
    previous = service.store.load_verified_snapshot(receipt['previousSnapshotId'])
    assert (previous['root'] / 'files/main/Profile2.sav').read_bytes() == external_target
    assert workspace.review()['count'] == 0

    # A successful plan becomes the in-memory baseline; the originally read
    # source/hash remain fixed for later edits in this workspace.
    stage(workspace, 'aspectSelection:SwordWeapon', 'set', scalar(1))
    unknown = entry(workspace, ('GameState', 'UnknownFutureField'))
    appended = stage(workspace, unknown, 'append', {'key': scalar(True),
        'value': {'luaType': 'string', 'encoding': 'base64', 'value': '/wA='}})
    action = next(action for action in appended['actions'] if action['id'] == unknown)
    assert action['typedKey'] == scalar(True) and action['typedValue']['encoding'] == 'base64'
    json.dumps(appended, ensure_ascii=False, allow_nan=False).encode('utf-8')
    foreign_again = build_save(700, 'do-not-rebase')
    (saves / 'Profile2.sav').write_bytes(foreign_again)
    second = apply(workspace)
    assert second['sourceSHA256'] == original_hash and workspace.session.source == {'kind': 'currentFile', **source}
    installed = state(saves / 'Profile2.sav')
    assert installed['Resources']['MetaPoints'] == 18 and installed['TimesCleared'] == 50
    assert installed['UnknownFutureField']['Marker'] == 'edited-fixed-source'
    assert installed['UnknownFutureField'][True].encode('utf-8', errors='surrogateescape') == b'\xff\x00'
    assert installed['LastWeaponUpgradeData']['SwordWeapon']['Index'] == 1
    previous = service.store.load_verified_snapshot(second['previousSnapshotId'])
    assert (previous['root'] / 'files/main/Profile2.sav').read_bytes() == foreign_again

    # Verified backups are independently pinned documents, not live aliases.
    snapshot = service.backup()
    backup = HadesSaveWorkspace.open(service, snapshot_id=snapshot['id'], source=source)
    live = HadesSaveWorkspace.open(service, source=source)
    stage(backup, 'resource:MetaPoints', 'set', scalar(81))
    assert backup.identifier != live.identifier and live.review()['count'] == 0
    (saves / 'Profile1.sav').write_bytes(build_save(88, 'later-live-source'))
    assert backup.session.source['snapshotId'] == snapshot['id']
    assert backup.document.lua_state['GameState']['Resources']['MetaPoints'] == 12
    set_target(backup, target)
    apply(backup)
    assert state(saves / 'Profile2.sav')['Resources']['MetaPoints'] == 81
    assert state(saves / 'Profile2.sav')['UnknownFutureField']['Marker'] == 'fixed-source'
    assert state(saves / 'Profile1.sav')['Resources']['MetaPoints'] == 88
    assert {path.name: path.read_bytes() for path in other_saves.iterdir()} == untouched_other
    assert other_service.list_state()['snapshots'] == []

    # Duplicate/typed keys keep physical identities through mixed set/removal,
    # and malformed semantic records stay writable through their typed owner.
    special = root_state()
    special['GameState']['UnknownFutureField'] = Entries([
        ('Duplicate', 1), ('Duplicate', 2), (True, 'bool'), (1, 'numeric'), ('Last', 3)])
    special['GameState']['WeaponUnlocks'] = {'SwordWeapon': Entries([(2, 1), (2, 2), (3, 'malformed')])}
    (saves / 'Profile1.sav').write_bytes(build_save(state=special))
    physical_workspace = HadesSaveWorkspace.open(service, source=source, target=target)
    assert not any(row['id'] == 'aspectRank:SwordWeapon:2'
                   for row in physical_workspace.query(domain='equipment')['rows'])
    path = physical(physical_workspace.document, ('GameState', 'UnknownFutureField'))
    stage(physical_workspace, values.identifier(path + (1,), physical_workspace.baseline_generation), 'unset')
    stage(physical_workspace, values.identifier(path + (3,), physical_workspace.baseline_generation), 'set', scalar(17))
    stage(physical_workspace, values.identifier(path + (9,), physical_workspace.baseline_generation), 'set',
        {'luaType': 'string', 'encoding': 'base64', 'value': '/wA='})
    apply(physical_workspace)
    physical_table = state(saves / 'Profile2.sav')['UnknownFutureField']
    assert physical_table.entries()[0] == ('Duplicate', 17)
    assert physical_table[True] == 'bool' and physical_table[1] == 'numeric'
    assert physical_table['Last'].encode('utf-8', errors='surrogateescape') == b'\xff\x00'
    rejects(ValueError, lambda: set_target(physical_workspace, {'rootId': 'main', 'relativePath': '../Profile2.sav'}))
    rejects(ValueError, lambda: stage(physical_workspace, 'h:notable_lua_data', 'set', {
        'luaType': 'table', 'arraySize': 0, 'hashSize': 1, 'entries': [
            {'key': scalar(True), 'value': scalar('not a numeric sequence')}] }))

    # Native control requests use the real adapter surface without a runtime.
    class NoRuntime:
        def __getattr__(self, name): raise AssertionError('Editor touched native runtime: ' + name)
    context = GameAdapterContext('hades', 'Hades', 2, ROOT / 'Backend/games/hades', {}, save_management=service.spec)
    adapter = HadesAdapter(context, runtime=NoRuntime(), preferences=HadesPreferenceStore(base / 'prefs.json'))
    router = JsonlRequestRouter(adapter, save_data_root=base / 'router-data', target_running_probe=lambda: False)
    opened = json.loads(router.handle_encoded({'id': 'open', 'command': 'save_editor_open', 'params': {'source': source}}))
    identifier = opened['result']['workspaceId']
    other = HadesAdapter(context, runtime=NoRuntime(), preferences=HadesPreferenceStore(base / 'other-prefs.json'))
    other.bind_save_service(service)
    cross_err = rejects(PresentableError, lambda: other.dispatch('save_editor_review', {'workspaceId': identifier}, 'cross-game-workspace'))
    assert cross_err.presentation == 'hades.saveEditor.error.notOpen'
    request = {'id': 'stage', 'command': 'save_editor_stage', 'params':
               {'workspaceId': identifier, 'baselineGeneration': opened['result']['baselineGeneration'], 'entryId': 'resource:MetaPoints', 'operation': 'set', 'value': scalar(3)}}
    encoded = router.handle_encoded(request)
    assert encoded == router.handle_encoded(request), 'Delivery replay executed a new edit'
    assert json.loads(encoded)['result']['count'] == 1
    generation = opened['result']['baselineGeneration']
    assert json.loads(encoded)['result']['baselineGeneration'] == generation
    missing_generation = json.loads(router.handle_encoded({'id': 'missing-baseline', 'command': 'save_editor_stage',
        'params': {'workspaceId': identifier, 'entryId': 'resource:MetaPoints', 'operation': 'set', 'value': scalar(8)}}))
    assert not missing_generation['ok']
    assert missing_generation['error']['presentation'] == 'hades.saveEditor.error.staleBaseline'
    assert 'arguments' not in missing_generation['error']
    selected = router.handle_encoded({'id': 'target', 'command': 'save_editor_target', 'params':
        {'workspaceId': identifier, 'target': target, 'baselineGeneration': generation}})
    assert json.loads(selected)['ok']
    (saves / 'Profile2.sav').chmod(0o600)
    applied = json.loads(router.handle_encoded({'id': 'apply', 'command': 'save_editor_apply', 'params':
        {'workspaceId': identifier, 'baselineGeneration': generation}}))
    assert applied['ok'] and applied['result']['baselineGeneration'] != generation
    assert stat.S_IMODE((saves / 'Profile2.sav').stat().st_mode) == 0o600
    stale = json.loads(router.handle_encoded({'id': 'stale-after-apply', 'command': 'save_editor_stage', 'params':
        {**request['params'], 'value': scalar(8)}}))
    assert not stale['ok']
    assert stale['error']['presentation'] == 'hades.saveEditor.error.staleBaseline'
    assert 'arguments' not in stale['error']
    assert adapter.save_workspaces[identifier].review()['count'] == 0
    # Old delivery acknowledgements stay idempotent and carry their old
    # generation, so the UI can discard them after accepting the Apply receipt.
    assert router.handle_encoded(request) == encoded
    assert adapter.save_workspaces[identifier].review()['count'] == 0
    closed = router.handle_encoded({'id': 'close', 'command': 'save_editor_close', 'params': {'workspaceId': identifier}})
    assert json.loads(closed)['result']['closed']
    closed_review = json.loads(router.handle_encoded({'id': 'closed', 'command': 'save_editor_review',
        'params': {'workspaceId': identifier}}))
    assert not closed_review['ok']
    assert closed_review['error']['presentation'] == 'hades.saveEditor.error.notOpen'
    assert 'arguments' not in closed_review['error']

    precision_saves, precision_service = environment(base / 'precision')
    precision_state = root_state()
    precision_state['GameState']['UnknownFutureField']['Precise'] = 1.0
    (precision_saves / 'Profile1.sav').write_bytes(build_save(state=precision_state))
    precision = HadesSaveWorkspace.open(precision_service, source=source)
    set_target(precision, target)
    precise_id = entry(precision, ('GameState', 'UnknownFutureField', 'Precise'))
    other_phys = entry(precision, ('GameState', 'Resources', 'MetaPoints'))
    review = stage(precision, precise_id, 'set', scalar(1.0000000000000002))
    action = review['actions'][0]
    assert action['before'] == '1' and action['after'] == '1.0000000000000002'
    assert action['effects'] == [], 'A raw physical edit has no linked semantic effects'
    assert action['owner'] and action['group'] and 'set' in action['operations']
    precise_receipt = precision.apply(
        baseline_generation=precision.baseline_generation,
        draft_entry_ids=('resource:Gems', other_phys, precise_id),
    )
    assert precise_receipt['changeCount'] == 1
    assert precise_receipt['continuousDraftEntryIds'] == ['resource:Gems']
    assert state(precision_saves / 'Profile2.sav')['UnknownFutureField']['Precise'] == 1.0000000000000002

    def assert_typed_error(response_json, expected_key):
        payload = json.loads(response_json)
        assert not payload['ok'], payload
        err = payload['error']
        assert err['presentation'] == 'hades.saveEditor.error.' + expected_key, err
        assert 'arguments' not in err, err
        assert err.get('diagnostic'), err

    unconfigured_context = GameAdapterContext('hades', 'Hades', 2, ROOT / 'Backend/games/hades', {})
    unconfigured = HadesAdapter(unconfigured_context, runtime=NoRuntime(), preferences=HadesPreferenceStore(base / 'unconfigured-prefs.json'))
    unavail_err = rejects(PresentableError, lambda: unconfigured.dispatch('save_editor_open', {'source': source}, 'unavail'))
    assert unavail_err.presentation == 'hades.saveEditor.error.unavailable'
    assert not unavail_err.arguments
    assert unavail_err.diagnostic

    err_saves, err_service = environment(base / 'typed-errors')
    err_context = GameAdapterContext('hades', 'Hades', 2, ROOT / 'Backend/games/hades', {}, save_management=err_service.spec)
    err_adapter = HadesAdapter(err_context, runtime=NoRuntime(), preferences=HadesPreferenceStore(base / 'err-prefs.json'))
    err_router = JsonlRequestRouter(err_adapter, save_data_root=base / 'err-router-data', target_running_probe=lambda: False)
    (err_saves / 'Profile1.sav').write_bytes(b'NOT_SGB1_FORMAT')
    assert_typed_error(err_router.handle_encoded({'id': 'bad-fmt', 'command': 'save_editor_open', 'params': {'source': source}}), 'invalidFormat')
    bad_sum = bytearray(build_save())
    bad_sum[4] ^= 0xFF
    (err_saves / 'Profile1.sav').write_bytes(bytes(bad_sum))
    assert_typed_error(err_router.handle_encoded({'id': 'bad-sum', 'command': 'save_editor_open', 'params': {'source': source}}), 'checksumMismatch')
    from hades_save import container, lua
    (err_saves / 'Profile1.sav').write_bytes(container(b'\x01' + lua(root_state()), version=15))
    assert_typed_error(err_router.handle_encoded({'id': 'bad-ver', 'command': 'save_editor_open', 'params': {'source': source}}), 'unsupportedVersion')

    (err_saves / 'Profile1.sav').write_bytes(build_save())
    err_open = json.loads(err_router.handle_encoded({'id': 'err-open', 'command': 'save_editor_open', 'params': {'source': source}}))
    assert err_open['ok'], err_open
    err_id = err_open['result']['workspaceId']
    err_gen = err_open['result']['baselineGeneration']
    assert_typed_error(err_router.handle_encoded({'id': 'bad-query', 'command': 'save_editor_detail', 'params': {'workspaceId': err_id, 'baselineGeneration': err_gen, 'entryId': 'unknown:missing'}}), 'invalidQuery')
    raw_unknown = entry(err_adapter.save_workspaces[err_id], ('GameState', 'UnknownFutureField'))
    assert_typed_error(err_router.handle_encoded({'id': 'req-adv', 'command': 'save_editor_query', 'params': {
        'workspaceId': err_id, 'baselineGeneration': err_gen, 'domain': 'resources', 'parentId': raw_unknown}}), 'requiresAdvanced')
    assert_typed_error(err_router.handle_encoded({'id': 'bad-mut', 'command': 'save_editor_stage', 'params': {
        'workspaceId': err_id, 'baselineGeneration': err_gen, 'entryId': 'resource:MetaPoints', 'operation': 'delete'}}), 'invalidMutation')
    assert json.loads(err_router.handle_encoded({'id': 'sel-target', 'command': 'save_editor_target', 'params': {
        'workspaceId': err_id, 'target': target, 'baselineGeneration': err_gen}}))['ok']
    assert_typed_error(err_router.handle_encoded({'id': 'no-changes', 'command': 'save_editor_apply', 'params': {
        'workspaceId': err_id, 'baselineGeneration': err_gen}}), 'noChanges')
    assert json.loads(err_router.handle_encoded({'id': 'stage-1', 'command': 'save_editor_stage', 'params': {
        'workspaceId': err_id, 'baselineGeneration': err_gen, 'entryId': 'resource:MetaPoints', 'operation': 'set', 'value': scalar(5)}}))['ok']
    raw_meta = entry(err_adapter.save_workspaces[err_id], ('GameState', 'Resources', 'MetaPoints'))
    assert_typed_error(err_router.handle_encoded({'id': 'overlap', 'command': 'save_editor_stage', 'params': {
        'workspaceId': err_id, 'baselineGeneration': err_gen, 'entryId': raw_meta, 'operation': 'set', 'value': scalar(6), 'advanced': True}}), 'overlappingActions')

print('hades_save_workspace_complete_pinned_journeys_and_isolation_ok')
