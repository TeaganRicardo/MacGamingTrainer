from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from core.module_manifest import SaveManagementSpec, SaveRootSpec
from core.save_resolution import SaveResolutionError, resolve_save_files


base = Path(tempfile.mkdtemp(prefix='mgt-save-resolution-'))
saves = base / 'saves'
saves.mkdir()
(saves / 'Profile1.sav').write_bytes(b'p1')
(saves / 'Profile2.sav').write_bytes(b'p2')
(saves / 'activeProfile').write_bytes(b'Profile1')
(saves / 'settings.json').write_bytes(b'not-save')
(saves / 'logs').mkdir()
(saves / 'logs' / 'runtime.log').write_bytes(b'not-save')

spec = SaveManagementSpec(
    roots=(SaveRootSpec('main', str(saves), ('Profile*.sav', 'activeProfile')),),
    provider=None,
    hot_backup=True,
    restore_policy='hotPreferred',
    staged_restore=True,
)
rows = resolve_save_files(spec)
assert [(row.root_id, row.relative_path) for row in rows] == [
    ('main', 'Profile1.sav'),
    ('main', 'Profile2.sav'),
    ('main', 'activeProfile'),
]
assert all(row.source_path.is_file() for row in rows)
assert not any('settings.json' in row.relative_path or 'runtime.log' in row.relative_path for row in rows)

(saves / 'profiles').mkdir()
(saves / 'profiles' / 'slot.sav').write_bytes(b'nested')
nested = SaveManagementSpec(
    roots=(SaveRootSpec('main', str(saves), ('profiles/*.sav',)),),
    provider=None, hot_backup=False, restore_policy='stoppedOnly', staged_restore=False,
)
assert [(row.root_id, row.relative_path) for row in resolve_save_files(nested)] == [('main', 'profiles/slot.sav')]

real = base / 'real'; real.mkdir(); (real / 'Profile1.sav').write_bytes(b'x')
root_link = base / 'root-link'; root_link.symlink_to(real, target_is_directory=True)
unsafe_root = SaveManagementSpec(
    roots=(SaveRootSpec('main', str(root_link), ('Profile*.sav',)),), provider=None,
    hot_backup=False, restore_policy='stoppedOnly', staged_restore=False,
)
try:
    resolve_save_files(unsafe_root)
except SaveResolutionError:
    pass
else:
    raise AssertionError('symlink save root was accepted')

link = saves / 'linked.sav'; link.symlink_to(saves / 'Profile1.sav')
unsafe_file = SaveManagementSpec(
    roots=(SaveRootSpec('main', str(saves), ('linked.sav',)),), provider=None,
    hot_backup=False, restore_policy='stoppedOnly', staged_restore=False,
)
try:
    resolve_save_files(unsafe_file)
except SaveResolutionError:
    pass
else:
    raise AssertionError('symlink save file was accepted')

(saves / 'dynamic.bin').write_bytes(b'dynamic')
class Provider:
    def resolve(self, roots, declared):
        assert set(roots) == {'main'}
        assert any(row.relative_path == 'Profile1.sav' for row in declared)
        return [('main', 'dynamic.bin'), ('main', 'Profile1.sav'), ('main', 'Profile1.sav')]

provider_spec = SaveManagementSpec(
    roots=(SaveRootSpec('main', str(saves), ('Profile*.sav',)),),
    provider='games.example.save_provider:Provider', hot_backup=True,
    restore_policy='hotPreferred', staged_restore=True,
)
provider_rows = resolve_save_files(provider_spec, provider_loader=lambda target: Provider())
assert [(row.root_id, row.relative_path) for row in provider_rows] == [
    ('main', 'Profile1.sav'), ('main', 'dynamic.bin')
]

class EscapeProvider:
    def resolve(self, roots, declared):
        return [('main', '../outside.sav')]

(base / 'outside.sav').write_bytes(b'outside')
try:
    resolve_save_files(provider_spec, provider_loader=lambda target: EscapeProvider())
except SaveResolutionError:
    pass
else:
    raise AssertionError('provider escaped declared root')

print('core_save_resolution_ok')
