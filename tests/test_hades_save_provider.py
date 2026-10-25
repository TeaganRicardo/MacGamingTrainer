"""Hades I native save members use generic verified backup and staged restore."""
from dataclasses import replace
from pathlib import Path
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from core.module_manifest import GameModuleManifest
from core.save_resolution import ResolvedSaveFile
from core.save_service import CoreSaveService
from games.hades.save_provider import HadesSaveProvider


manifest = GameModuleManifest.load(ROOT / 'Backend/games/hades/module.json')
assert manifest.module_protocol_version == 2
assert manifest.save_management.provider == 'games.hades.save_provider:HadesSaveProvider'
assert manifest.save_management.restore_policy == 'stoppedOnly'
assert manifest.save_management.staged_restore

with tempfile.TemporaryDirectory(prefix='mgt-hades-save-') as directory:
    temporary = Path(directory)
    saves = temporary / 'saves'
    saves.mkdir()
    files = {
        'Profile1.sav': b'native-current-profile',
        'Profile1_Temp.sav': b'native-current-temp',
        'Profile1.v.sav': b'native-current-validation',
        'Profile1.sjson': b'native-profile-settings',
        'Profile1.ctrls': b'native-controller-settings',
        'activeProfile': b'SGB1' + struct.pack('<I', 8) + b'Profile1',
    }
    for name, raw in files.items():
        (saves / name).write_bytes(raw)
    (saves / 'Hades.log').write_bytes(b'unowned-native-log')
    spec = replace(manifest.save_management,
        roots=(replace(manifest.save_management.roots[0], path=str(saves)),))
    running = False
    service = CoreSaveService('hades', spec, temporary / 'trainer', lambda: running)
    assert {row.relative_path for row in service.resolved_files()} == set(files)
    target = service.backup()
    assert service.list_state()['snapshots'][0]['valid']
    assert target['localizedPresentation']['en']['details'] == ['Save Slot 1']
    for name in files:
        if name != 'activeProfile':
            (saves / name).write_bytes(b'changed:' + name.encode())
    running = True
    live = service.backup()
    assert live['hot']
    staged = service.restore(target['id'])
    assert staged['staged']
    assert (saves / 'Profile1.sav').read_bytes() == b'changed:Profile1.sav'
    assert (saves / 'Hades.log').read_bytes() == b'unowned-native-log'
    reloaded = CoreSaveService('hades', spec, temporary / 'trainer', lambda: running)
    assert reloaded.pending_restore()['snapshotId'] == target['id']
    running = False
    assert reloaded.apply_staged()['applied']
    assert reloaded.pending_restore() is None
    assert {name: (saves / name).read_bytes() for name in files} == files
    assert (saves / 'Hades.log').read_bytes() == b'unowned-native-log'
    recovery = [row for row in reloaded.list_state()['snapshots'] if row['id'] not in (target['id'], live['id'])]
    assert recovery, 'restore must preserve a recoverable copy of the prior live files'

    provider = HadesSaveProvider()
    rows = (ResolvedSaveFile('main', 'activeProfile', saves / 'activeProfile'),)
    description = provider.describe_snapshot(rows, '2026-10-25T15:42:00')
    assert description['defaultName'] == '2026-10-25 15:42 · 存档 1'
    assert description['localizedPresentation']['en']['name'] == '2026-10-25 15:42 · Save Slot 1'
    (saves / 'activeProfile').write_bytes(b'not-an-active-profile')
    assert provider.describe_snapshot(rows, '2026-10-25T15:42:00')['defaultName'] is None
    (saves / 'activeProfile').write_bytes(b'SGB1' + struct.pack('<I', 10) + b'../Profile')
    assert provider.describe_snapshot(rows, '2026-10-25T15:42:00')['defaultName'] is None

print('hades_save_provider_ok')
