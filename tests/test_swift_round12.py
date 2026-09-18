from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
core_files = sorted((root/'Sources/Core').rglob('*.swift'))
core = '\n'.join(path.read_text() for path in core_files)
model = (root/'Sources/Hades2/Hades2Model.swift').read_text()
view = (root/'Sources/Hades2/Hades2View.swift').read_text()
module = (root/'Sources/Hades2/Hades2Module.swift').read_text()
app = (root/'Sources/App.swift').read_text()

for required in (
    'Sources/Core/Runtime/BackendProcess.swift',
    'Sources/Core/Runtime/BackendClient.swift',
    'Sources/Core/Runtime/TrainerBackendSession.swift',
    'Sources/Core/Host/TrainerGameModule.swift',
    'Sources/Core/Host/TrainerHost.swift',
    'Sources/Core/Input/GlobalHotkeys.swift',
    'Sources/Core/UI/TrainerTheme.swift',
    'Sources/Core/UI/TrainerShell.swift',
    'Sources/Core/UI/Primitives/TrainerCard.swift',
    'Sources/Core/UI/Primitives/TrainerToggleControl.swift',
):
    assert (root/required).is_file(), required

# Core owns infrastructure/chrome/primitives only, never Hades business state.
for token in ('Hades2','godMode','boonRarity','dormantFeatures','statSupport','statAvailable','rerollsLocked','enemyHealth'):
    assert token not in core, token
for token in ('TrainerFeatureState','desiredFeatures','dormantFeatures','statAvailable','boonRarity','enemyHealth'):
    assert token not in core, token
assert 'protocol TrainerGameModule' in core
assert 'struct TrainerHostView' in core
assert 'struct TrainerTheme' in core

# Host shell/theme/termination are mandatory at App/Core level.
assert 'TrainerHostView<ActiveGameModule>' in app
assert '.trainerTheme(.standard)' in app
assert 'NSApp.reply(toApplicationShouldTerminate:' in app
assert 'NSApp.reply' not in model + view
assert 'TrainerShell' not in view and 'TrainerSidebar' not in view

# Hades owns its business presentation and typed protocol boundary.
assert 'struct Hades2GameModule: TrainerGameModule' in module
assert 'Hades2FeaturePresentation' in (root/'Sources/Hades2/Presentation/Hades2FeaturePresentation.swift').read_text()
assert 'Hades2Request' in (root/'Sources/Hades2/Hades2API.swift').read_text()
assert 'Hades2StatePatch' in (root/'Sources/Hades2/Hades2BackendState.swift').read_text()
assert 'model.send' not in view
assert 'activationGraceFeatures' in model
assert 'statAvailable' in model
assert 'Hades2ShortcutStore' in model
assert (root/'Sources/Hades2/Views/Hades2ManagementViews.swift').is_file()

# Binding generator carries identity/protocol only; presentation stays Swift-local.
generated = Path(tempfile.mkstemp(suffix='.swift')[1])
try:
    subprocess.run(['python3', str(root/'Tools/generate_game_binding.py'), 'hades2', str(generated)], check=True)
    text = generated.read_text()
    assert 'typealias ActiveGameModule = Hades2GameModule' in text
    assert 'expectedHostProtocolVersion: 5' in text
    assert 'expectedModuleProtocolVersion: 5' in text
    for token in ('sidebarIconSystemName','platformLabel','headerTitle'):
        assert token not in text, token
    swiftc = shutil.which('swiftc')
    if swiftc:
        sources = [root/'Sources/App.swift'] + core_files + sorted((root/'Sources/Hades2').rglob('*.swift')) + [generated]
        subprocess.run([swiftc, '-frontend', '-parse', *map(str, sources)], check=True)
finally:
    generated.unlink(missing_ok=True)
print('swift_round12_ok')
