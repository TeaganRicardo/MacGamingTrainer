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
assert "override func layout()" not in picker
assert "private weak var cachedButton: NSPopUpButton?" in picker
assert "scheduleLookup(passes:" in picker
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

# The corrected presentation keeps the native control height and the app's
# dark identity. The previous redraw inflated every Picker to 34 pt and painted
# a near-white surface, which is the regression this contract now forbids.
assert "frame(minHeight: 34)" not in picker
assert ".frame(minHeight:" not in picker
assert "0.965" not in picker
assert ".padding(.leading, 4)" in picker
assert ".disabled(effectiveState != .interactive)" in picker

# Appearance is owned once at the AppKit application boundary. Re-forcing it on
# every NSPopUpButton would hide the real defect (per-view dark declarations do
# not cover windows, sheets, panels and reconstructed native controls) and would
# leave any other native control free to resolve the light system appearance.
app_source = (ROOT / "Sources/App.swift").read_text()
assert "applicationWillFinishLaunching" in app_source
assert "NSApp.appearance = NSAppearance(named: .darkAqua)" in app_source
assert "button.appearance" not in picker
assert "button.menu?.appearance" not in picker


def fill_luminance(name: str) -> float:
    match = re.search(
        rf"case \.{name}: Color\(red: ([\d.]+), green: ([\d.]+), blue: ([\d.]+)\)",
        picker,
    )
    assert match, f"{name} Picker fill is missing"
    red, green, blue = (float(value) for value in match.groups())
    return (red + green + blue) / 3


interactive_luminance = fill_luminance("interactive")
unavailable_luminance = fill_luminance("unavailable")
assert interactive_luminance < 0.32, "interactive Picker must use a dark surface"
assert unavailable_luminance < 0.32, "unavailable Picker must use a dark surface"
assert unavailable_luminance < interactive_luminance, (
    "unavailable Picker must read as a dimmed interactive surface"
)

# Every production visual Picker passes through the shared presentation owner.
# The language Picker lives inside a command menu rather than the app's control
# surfaces, so it intentionally remains native.
exceptions = {Path("Sources/Core/Host/TrainerLocalization.swift")}


def matching_delimiter_end(source: str, opening: int, left: str, right: str) -> int:
    # Return the index just after a balanced Swift delimiter, ignoring strings.
    depth = 0
    quoted = False
    escaped = False
    for index in range(opening, len(source)):
        char = source[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
            continue
        if char == left:
            depth += 1
        elif char == right:
            depth -= 1
            if depth == 0:
                return index + 1
    raise AssertionError(f"unterminated {left}{right} delimiter")


def picker_modifier_segment(source: str, picker_match: re.Match, owner_start: int) -> str:
    # A Picker may contain closures inside its argument list (for example a
    # Binding get/set pair). Skip the complete call and its trailing content
    # closure before inspecting only the Picker's modifier chain.
    call_end = matching_delimiter_end(source, picker_match.end() - 1, "(", ")")
    cursor = call_end
    while cursor < len(source) and source[cursor].isspace():
        cursor += 1
    if cursor < len(source) and source[cursor] == "{":
        cursor = matching_delimiter_end(source, cursor, "{", "}")
    return source[cursor:owner_start]


# Guard the scanner itself: disabled menu entries are valid and must not be
# confused with a raw disabled modifier on the Picker.
_fixture = """Picker("Section", selection: $section) {
    Text("Advanced").tag("advanced").disabled(true)
}
.labelsHidden()
.trainerPicker(.rowValue, state: .interactive)"""
_fixture_picker = re.search(r"(?<![A-Za-z])Picker\s*\(", _fixture)
_fixture_owner = re.search(r"\.trainerPicker\(", _fixture)
assert _fixture_picker and _fixture_owner
assert ".disabled(" not in picker_modifier_segment(_fixture, _fixture_picker, _fixture_owner.start())

_fixture_bad = """Picker("Section", selection: $section) { Text("A").tag("a") }
.labelsHidden()
.disabled(true)
.trainerPicker(.rowValue, state: .unavailable)"""
_fixture_picker = re.search(r"(?<![A-Za-z])Picker\s*\(", _fixture_bad)
_fixture_owner = re.search(r"\.trainerPicker\(", _fixture_bad)
assert _fixture_picker and _fixture_owner
assert ".disabled(" in picker_modifier_segment(_fixture_bad, _fixture_picker, _fixture_owner.start())

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
            modifier_segment = picker_modifier_segment(source, picker_match, owners[0].start())
            assert ".disabled(" not in modifier_segment, (
                f"{relative}: Picker #{index + 1} applies native disabled state before the Core owner"
            )
        assert ".trainerPickerWidth(" not in source, f"{relative}: width-only Picker path remains"
        assert not re.search(r"\.trainerPicker\([^\n]*\)\s*\.disabled\(", source), (
            f"{relative}: Picker availability bypasses the Core presentation state"
        )

print("picker_presentation_contract_ok")
