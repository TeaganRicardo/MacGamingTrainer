import logging
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

import core.protocol as protocol_module
from core.adapter import GameAdapter, GameAdapterContext
from core.module_manifest import SaveManagementSpec, SaveRootSpec
from core.protocol import JsonlRequestRouter
from core.save_restore import SaveRollbackError


class FakeAdapter(GameAdapter):
    def __init__(self, context):
        super().__init__(context)
        self.calls = []
        self.state = {}
    def dispatch(self, command, params, request_id):
        self.calls.append((command, params, request_id))
        return {'gameCommand': command}
    def close(self):
        pass


base = Path(tempfile.mkdtemp(prefix='mgt-save-protocol-'))
saves = base / 'saves'; saves.mkdir()
(saves / 'Profile1.sav').write_bytes(b'one')
spec = SaveManagementSpec(
    roots=(SaveRootSpec('main', str(saves), ('*.sav',)),), provider=None,
    hot_backup=True, restore_policy='hotPreferred', staged_restore=True,
)
context = GameAdapterContext(
    game_id='fake', display_name='Fake', module_protocol_version=1,
    module_dir=base, public_metadata={
        'id':'fake','displayName':'Fake','protocolVersion':1,
        'targetApplication':{'processName':'Fake','bundleIdentifier':'com.example.fake'},
        'saveManagement':{'supported':True,'hotBackup':True,'restorePolicy':'hotPreferred','stagedRestore':True},
    },
    process_name='Fake', save_management=spec,
)
adapter = FakeAdapter(context)
router = JsonlRequestRouter(adapter, save_data_root=base/'data', target_running_probe=lambda: False)

backup = router.handle({'id':'b1','command':'core.save.backup','params':{'name':'First'}})
assert backup['ok'] is True
assert backup['result']['operation']['name'] == 'First'
assert len(backup['result']['snapshots']) == 1
assert adapter.calls == []
snapshot_id = backup['result']['operation']['id']

listed = router.handle({'id':'l1','command':'core.save.list','params':{}})
assert listed['ok'] is True and listed['result']['snapshots'][0]['id'] == snapshot_id
assert adapter.calls == []

renamed = router.handle({'id':'r1','command':'core.save.rename','params':{'snapshotId':snapshot_id,'name':'Renamed'}})
assert renamed['ok'] is True and renamed['result']['operation']['name'] == 'Renamed'
assert adapter.calls == []

folder = router.handle({'id':'f1','command':'core.save.open_folder','params':{'snapshotId':snapshot_id}})
assert folder['ok'] is True and Path(folder['result']['folder']).name == snapshot_id
assert adapter.calls == []

# Catastrophic rollback failure must expose the preserved recovery copy path
# through the Core JSONL error envelope so Host can tell the user where the
# last recoverable bytes live.
recovery_path = base / 'data/fake/saves/transactions/.rollback-preserved'
real_restore = router.save_service.restore
def fail_with_preserved_rollback(snapshot_id, preserve_current=True):
    raise SaveRollbackError('restore and rollback failed', recovery_path)
router.save_service.restore = fail_with_preserved_rollback
logging.disable(logging.CRITICAL)
try:
    rollback_failed = router.handle({
        'id':'rr1',
        'command':'core.save.restore',
        'params':{'snapshotId':snapshot_id,'preserveCurrent':True},
    })
finally:
    logging.disable(logging.NOTSET)
    router.save_service.restore = real_restore
assert rollback_failed['ok'] is False
assert rollback_failed['error'] == {
    'code':'rollback_failed',
    'message':'restore and rollback failed',
    'recoveryPath':str(recovery_path),
}
assert adapter.calls == []

# Ordinary game command routing is unchanged.
game = router.handle({'id':'g1','command':'poke','params':{'x':1}})
assert game['ok'] is True and game['result']['gameCommand'] == 'poke'
assert [call[0] for call in adapter.calls] == ['poke']

# Reserved unknown/invalid Core save requests never fall through to the game adapter.
logging.disable(logging.CRITICAL)
try:
    unknown = router.handle({'id':'u1','command':'core.save.unknown','params':{}})
    assert unknown['ok'] is False
    invalid = router.handle({'id':'i1','command':'core.save.restore','params':{'snapshotId':snapshot_id,'preserveCurrent':'yes'}})
    assert invalid['ok'] is False and invalid['error']['code'] == 'invalid_request'

    # Unsupported module produces the generic Core capability error, not a game dispatch.
    plain_context = GameAdapterContext(
        game_id='plain', display_name='Plain', module_protocol_version=1,
        module_dir=base, public_metadata={'id':'plain','displayName':'Plain','protocolVersion':1},
    )
    plain_adapter = FakeAdapter(plain_context)
    plain_router = JsonlRequestRouter(plain_adapter, save_data_root=base/'plain-data', target_running_probe=lambda: False)
    unsupported = plain_router.handle({'id':'x1','command':'core.save.list','params':{}})
    assert unsupported['ok'] is False and unsupported['error']['code'] == 'save_unsupported'
    assert plain_adapter.calls == []
finally:
    logging.disable(logging.NOTSET)
assert [call[0] for call in adapter.calls] == ['poke']

# Delete is Core-owned too.
deleted = router.handle({'id':'d1','command':'core.save.delete','params':{'snapshotId':snapshot_id}})
assert deleted['ok'] is True and deleted['result']['operation']['deleted'] is True
assert [call[0] for call in adapter.calls] == ['poke']

# No resolved game-save files is a different user condition from a corrupt
# snapshot and must have its own stable Core error code.
(saves / 'Profile1.sav').unlink()
logging.disable(logging.CRITICAL)
try:
    empty_backup = router.handle({'id':'empty1','command':'core.save.backup','params':{}})
finally:
    logging.disable(logging.NOTSET)
assert empty_backup['ok'] is False
assert empty_backup['error']['code'] == 'save_not_found'
assert 'save' in empty_backup['error']['message'].lower()

# Process-query failure is not evidence that the game stopped. Core Save must
# fail closed before a hotPreferred restore can mutate real save bytes.
(saves / 'Profile1.sav').write_bytes(b'probe-target')
probe_seed = JsonlRequestRouter(adapter, save_data_root=base/'probe-data', target_running_probe=lambda: False)
probe_backup = probe_seed.handle({'id':'probe-backup','command':'core.save.backup','params':{}})
assert probe_backup['ok'] is True
probe_snapshot_id = probe_backup['result']['operation']['id']
(saves / 'Profile1.sav').write_bytes(b'probe-current')
probe_router = JsonlRequestRouter(adapter, save_data_root=base/'probe-data')
real_run = protocol_module.subprocess.run
class FailedProcessQuery:
    returncode = 2
try:
    protocol_module.subprocess.run = lambda *args, **kwargs: FailedProcessQuery()
    logging.disable(logging.CRITICAL)
    probe_restore = probe_router.handle({
        'id':'probe-restore',
        'command':'core.save.restore',
        'params':{'snapshotId':probe_snapshot_id,'preserveCurrent':False},
    })
finally:
    logging.disable(logging.NOTSET)
    protocol_module.subprocess.run = real_run
assert probe_restore['ok'] is False
assert probe_restore['error']['code'] == 'save_busy'
assert (saves / 'Profile1.sav').read_bytes() == b'probe-current'

print('core_save_protocol_ok')
