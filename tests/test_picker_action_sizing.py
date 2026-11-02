"""Linux ownership and actual Swift geometry checks for native picker/action rows."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
row = (root / "Sources/Core/UI/Primitives/TrainerRow.swift").read_text()
theme = (root / "Sources/Core/UI/TrainerTheme.swift").read_text()
sizing = (root / "Sources/Core/UI/TrainerPickerActionSizing.swift").read_text()

assert "pickerActionMaxWidth: 420" in theme
assert "private struct TrainerNativeFlexiblePickerSizing: ViewModifier" in theme
assert "if #available(macOS 26.0, *)" in theme
assert "content.buttonSizing(.flexible)" in theme
assert "case .rowAction:" in theme
assert "rowActionWidth ?? theme.pickerStandardWidth" in theme
assert "TrainerPickerAllocatedWidthKey" in theme
assert "case .form:" in theme and "idealWidth: theme.pickerWideWidth" in theme
assert "TrainerPickerActionSizing.width(" in row
assert "controls.environment(\\.trainerPickerActionWidth, allocatedPickerWidth)" in row
assert "TrainerPickerRowControlWidthKey" in row
assert "TrainerPickerRowAvailableWidthKey" in row
assert "onPreferenceChange(TrainerPickerAllocatedWidthKey.self)" in row
assert row.index("Spacer(minLength: 8)") < row.index("controls.environment(\\.trainerPickerActionWidth")
assert "groupWidth - pickerWidth" in sizing
assert "max(minimum, min(maximumWidth, available))" in sizing
assert "CATransition" not in row
assert "hades" not in sizing.lower()

swiftc = shutil.which("swiftc")
if swiftc:
    with tempfile.TemporaryDirectory(prefix="mgt-picker-action-") as tmp:
        executable = str(Path(tmp) / "check")
        subprocess.run([
            swiftc,
            str(root / "Sources/Core/UI/TrainerPickerActionSizing.swift"),
            str(root / "tests/fixtures/swift/PickerActionSizingChecks.swift"),
            "-o", executable,
        ], check=True, timeout=60)
        subprocess.run([executable], check=True, timeout=10)
else:
    print("picker_action_swift_runtime_skipped_no_swiftc")

print("responsive_picker_action_ownership_ok")
