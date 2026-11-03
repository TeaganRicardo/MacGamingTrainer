"""Root regression for issue #653: workbench Pickers have one Core presentation owner."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

picker = (ROOT / "Sources/Core/UI/Primitives/TrainerPicker.swift").read_text()
assert "enum TrainerPickerPresentationState" in picker
assert "case interactive" in picker and "case unavailable" in picker
assert "@Environment(\\.isEnabled)" in picker
assert "func trainerPicker(" in picker
assert "TrainerNativePickerPresentationBridge" in picker
assert "button.isBordered = false" in picker
assert "button.focusRingType = .none" in picker
assert "button.contentTintColor" in picker
assert "TrainerPickerIndicator" in picker
assert "theme.accent" in picker
assert "NSColor.controlAccentColor" not in picker
assert "Color.accentColor" not in picker

# Every production visual Picker passes through the shared presentation owner.
# The language Picker lives inside a command menu rather than the app's control
# surfaces, so it intentionally remains native.
exceptions = {Path("Sources/Core/Host/TrainerLocalization.swift")}
for source_root in (ROOT / "Sources/Core", ROOT / "Sources/Hades", ROOT / "Sources/Hades2"):
    for swift_path in source_root.rglob("*.swift"):
        relative = swift_path.relative_to(ROOT)
        source = swift_path.read_text()
        if relative == Path("Sources/Core/UI/Primitives/TrainerPicker.swift"):
            continue
        raw = len(re.findall(r"(?<![A-Za-z])Picker\\s*\\(", source))
        if not raw:
            continue
        if relative in exceptions:
            assert ".trainerPicker(" not in source
            continue
        owned = source.count(".trainerPicker(")
        assert raw == owned, f"{relative}: {raw} Pickers but {owned} Core presentation owners"
        assert ".trainerPickerWidth(" not in source, f"{relative}: width-only Picker path remains"
        assert not re.search(r"\.trainerPicker\([^\n]*\)\s*\.disabled\(", source), (
            f"{relative}: Picker availability bypasses the Core presentation state"
        )

print("picker_presentation_contract_ok")
