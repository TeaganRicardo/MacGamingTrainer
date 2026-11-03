"""Linux regression: native Picker allocation uses individual trailing widths."""
from pathlib import Path
import shutil
import subprocess
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
print('picker_action_subview_geometry_contract_ok')
