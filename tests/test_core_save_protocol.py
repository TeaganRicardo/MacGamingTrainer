from pathlib import Path
import logging
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from core.adapter import GameAdapter, GameAdapterContext
from core.module_manifest import SaveManagementSpec, SaveRootSpec
from core.protocol import JsonlRequestRouter


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

print('core_save_protocol_ok')
