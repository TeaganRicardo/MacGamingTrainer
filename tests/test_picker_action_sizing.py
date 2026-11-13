"""Linux regression: native Picker allocation uses individual trailing widths."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
THEME = ROOT / 'Sources/Core/UI/TrainerTheme.swift'
ROW = ROOT / 'Sources/Core/UI/Primitives/TrainerRow.swift'
LAYOUT = ROOT / 'Sources/Core/UI/TrainerPickerActionLayout.swift'
HELPER = ROOT / 'Sources/Core/UI/TrainerPickerActionSizing.swift'

row = ROW.read_text()
layout = LAYOUT.read_text()
helper = HELPER.read_text()
if THEME.exists():
    theme = THEME.read_text()
    assert 'pickerActionMaxWidth: 420' in theme
    assert 'shortcutBadgeMinimumWidth: 52' in theme
    assert 'shortcutBadgeMinimumWidth' in (ROOT / 'Sources/Core/UI/Primitives/TrainerBadge.swift').read_text()
    assert 'case .rowAction:' in theme
    assert 'content.buttonSizing(.flexible)' in theme
    assert 'trainerPickerActionWidth' not in theme
    assert 'TrainerPickerAllocatedWidthKey' not in theme
assert 'TrainerPickerActionLayout(' in row
assert 'controls' in row
assert 'layout == .pickerAction' in row
assert 'TrainerPickerRowAvailableWidthKey' not in row
assert 'TrainerPickerRowControlWidthKey' not in row
assert 'private func trailingIndices' in layout
assert 'naturalSizes(of: subviews)' in layout
assert 'minimumIntermediateWidth' in layout
assert 'sizes[index].width = max(sizes[index].width, minimumIntermediateWidth)' in layout
assert 'minimumIntermediateWidth: theme.shortcutBadgeMinimumWidth' in row
assert 'minimumActionWidth: theme.compactActionWidth' in row
assert 'sizes[actionIndex].width = max(sizes[actionIndex].width, minimumActionWidth)' in layout
assert 'subviews[index].place(' in layout
assert 'TrainerPickerActionSizing.width(' in layout
assert 'groupWidth' not in helper
assert 'trailingWidths' in helper
assert 'visibleTrailing' in helper
assert 'CGRect' in layout

for path in [LAYOUT,ROW,HELPER]:
    subprocess.run(['swiftc','-frontend','-parse',str(path)],check=True,timeout=15)
if shutil.which('swiftc'):
    with tempfile.TemporaryDirectory(prefix='mgt-picker-native-width-') as tmp:
        executable = str(Path(tmp) / 'check')
        subprocess.run(['swiftc',str(HELPER),str(ROOT / 'tests/fixtures/swift/PickerActionSizingChecks.swift'),'-o',executable],check=True,timeout=40)
        subprocess.run([executable],check=True,timeout=10)
        # Exercise the production Layout against a small SwiftUI type shim on
        # Linux: an intrinsic 39pt shortcut must reserve a 52pt visual lane.
        shim_name = 'libSwiftUI.dylib' if sys.platform == 'darwin' else 'libSwiftUI.so'
        shim_library = str(Path(tmp) / shim_name)
        shim_module = str(Path(tmp) / 'SwiftUI.swiftmodule')
        swift_fixtures = ROOT / 'tests/fixtures/swift'
        build_shim = [
            'swiftc', '-emit-library', '-emit-module',
            '-module-name', 'SwiftUI',
            str(swift_fixtures / 'PickerActionLayoutMock.swift'),
            '-emit-module-path', shim_module,
            '-o', shim_library,
        ]
        if sys.platform == 'darwin':
            build_shim += ['-Xlinker', '-install_name', '-Xlinker', f'@rpath/{shim_name}']
        subprocess.run(build_shim, check=True, timeout=40)
        layout_executable = str(Path(tmp) / 'layout-check')
        subprocess.run(['swiftc', '-I', tmp, '-L', tmp, '-lSwiftUI',
                        '-Xlinker', '-rpath', '-Xlinker', tmp,
                        str(HELPER), str(LAYOUT),
                        str(swift_fixtures / 'PickerActionLayoutGeometryChecks.swift'),
                        '-o', layout_executable], check=True, timeout=40)
        subprocess.run([layout_executable], check=True, timeout=10)

print('picker_action_subview_geometry_contract_ok')
