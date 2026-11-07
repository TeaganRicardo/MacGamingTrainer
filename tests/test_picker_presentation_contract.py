"""Root regression for issue #653: workbench Pickers have one Core presentation owner."""

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

picker = (ROOT / "Sources/Core/UI/Primitives/TrainerPicker.swift").read_text()
assert "enum TrainerPickerPresentationState" in picker
assert "case interactive" in picker and "case unavailable" in picker
assert "func trainerPicker(" in picker
assert ".trainerPickerWidth(role)" in picker
assert ".disabled(!state.allowsInteraction)" in picker

# The accepted baseline (v0.5.1) is the native popup: AppKit draws the bezel,
# title, indicator and disabled state. #654/#675 repainted it with SwiftUI
# fills, borders, a masking indicator and an AppKit view-tree bridge; the native
# body still showed through, so the surface never filled the control. The owner
# may select geometry, availability and accent only.
picker_code = "\n".join(line.split("//", 1)[0] for line in picker.splitlines())
for repaint in (
    "NSViewRepresentable", "NSPopUpButton", "isBordered", "bezelColor",
    "focusRingType", "contentTintColor", ".background", ".overlay", ".clipShape",
    "Color(red:", ".padding(", "minHeight", "Image(systemName",
):
    assert repaint not in picker_code, f"shared Picker owner repaints native chrome: {repaint}"

# The product purple reaches the native indicator through SwiftUI tint and,
# for chrome AppKit redraws by itself, through the application accent color.
assert ".tint(theme.accent)" in picker


def srgb_triplet(text: str) -> tuple[float, float, float]:
    match = re.search(
        r"accent: Color\(red: ([\d.]+), green: ([\d.]+), blue: ([\d.]+)\)", text
    )
    assert match, "TrainerTheme accent declaration is missing"
    return tuple(float(value) for value in match.groups())


theme_accent = srgb_triplet((ROOT / "Sources/Core/UI/TrainerTheme.swift").read_text())
colorset = json.loads(
    (ROOT / "Resources/Assets.xcassets/AccentColor.colorset/Contents.json").read_text()
)
(entry,) = colorset["colors"]
assert entry["idiom"] == "universal"
assert "appearances" not in entry, "the dark-only product declares one accent"
assert entry["color"]["color-space"] == "srgb"
components = entry["color"]["components"]
asset_accent = tuple(float(components[name]) for name in ("red", "green", "blue"))
assert float(components["alpha"]) == 1.0
assert all(abs(a - b) < 0.0005 for a, b in zip(asset_accent, theme_accent)), (
    f"application accent {asset_accent} diverged from TrainerTheme accent {theme_accent}"
)

build_script = (ROOT / "build.sh").read_text()
assert '--accent-color "$ACCENT_COLOR_NAME"' in build_script
assert "data['NSAccentColorName'] = asset_info['NSAccentColorName']" in build_script

# Appearance is owned once at the AppKit application boundary, so windows,
# sheets, panels, menus and reconstructed popups never resolve the light bezel.
app_source = (ROOT / "Sources/App.swift").read_text()
assert "applicationWillFinishLaunching" in app_source
assert "NSApp.appearance = NSAppearance(named: .darkAqua)" in app_source

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
