from pathlib import Path
import json
import plistlib
import subprocess

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root/'Backend/games/hades2/module.json').read_text())
build = (root/'build.sh').read_text()
runtime_manifest = (root/'Backend/core/module_manifest.py').read_text()
tool_support = (root/'Tools/module_support.py').read_text()
base_plist = plistlib.loads((root/'Info.plist').read_bytes())

assert manifest['frontend']['architectures'] == ['arm64']
assert manifest['frontend']['minimumMacOS'] == '14.0'
assert manifest['app']['bundleIdentifier'] == 'com.gao.macgamingtrainer'
assert manifest['app']['displayName'] == 'Mac Gaming Trainer'
assert 'ui' not in manifest

# Runtime core cannot grow into a universal build/UI schema again. Check the
# actual dataclass surface, not comments that document the boundary.
import sys
from dataclasses import fields
sys.path.insert(0, str(root/'Backend'))
from core.module_manifest import GameModuleManifest
assert {field.name for field in fields(GameModuleManifest)} == {
    'id','display_name','module_protocol_version','adapter','process_name','bundle_identifier','source_path','save_management'
}
for token in ('FrontendBuildSpec','AppBuildSpec','BuildRequirements','architectures','bundle_identifier','entitlements'):
    assert token in tool_support, token

assert 'LSArchitecturePriority' not in base_plist
assert '-target arm64-apple-macosx14.0' not in build
assert 'Tools/validate_game_module.py' in build
assert 'Tools/generate_game_binding.py' in build
assert 'cp -R "$ROOT/Backend/core"' in build
assert 'cp -R "$ROOT/Backend/games/$ACTIVE_GAME_ID"' in build
assert '-typecheck' in build and build.index('-typecheck') < build.index('-O \\')
for token in ('Hades II','1145350','Supergiant'):
    assert token not in build, token

normalized = json.loads(subprocess.check_output(
    ['python3', str(root/'Tools/validate_game_module.py'), 'hades2', '--json'], text=True
))
assert normalized['frontend']['architectures'] == ['arm64']
assert normalized['app']['bundleIdentifier'] == 'com.gao.macgamingtrainer'
assert normalized['backend']['adapter'] == 'games.hades2.adapter:Hades2Adapter'
assert normalized['saveManagement'] == {
    'supported': True,
    'hotBackup': True,
    'restorePolicy': 'hotPreferred',
    'stagedRestore': True,
}
assert 'ui' not in normalized
print('build_contract_round14_ok')
