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
assert "Color.white.opacity" not in picker
assert "case .interactive: Color(red:" in picker
assert "case .unavailable: Color(red:" in picker

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
        picker_matches = list(re.finditer(r"(?<![A-Za-z])Picker\s*\(", source))
        if not picker_matches:
            continue
        if relative in exceptions:
            assert ".trainerPicker(" not in source
            continue
        owner_matches = list(re.finditer(r"\.trainerPicker\(", source))
        assert len(picker_matches) == len(owner_matches), (
            f"{relative}: {len(picker_matches)} Pickers but {len(owner_matches)} presentation owners"
        )
        for index, picker_match in enumerate(picker_matches):
            next_picker = picker_matches[index + 1].start() if index + 1 < len(picker_matches) else len(source)
            owners = [owner for owner in owner_matches if picker_match.end() < owner.start() < next_picker]
            assert len(owners) == 1, (
                f"{relative}: Picker #{index + 1} does not have exactly one adjacent Core owner"
            )
            pre_owner = source[picker_match.end():owners[0].start()]
            assert ".disabled(" not in pre_owner, (
                f"{relative}: Picker #{index + 1} applies native disabled state before the Core owner"
            )
        assert ".trainerPickerWidth(" not in source, f"{relative}: width-only Picker path remains"
        assert not re.search(r"\.trainerPicker\([^\n]*\)\s*\.disabled\(", source), (
            f"{relative}: Picker availability bypasses the Core presentation state"
        )

print("picker_presentation_contract_ok")
