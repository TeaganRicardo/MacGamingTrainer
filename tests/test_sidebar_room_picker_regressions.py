"""Regressions for the shared sidebar and Hades II Rooms & Rewards picker roles.

These source-ownership checks supplement native focus/layout tests; they do not
claim a rendered screenshot or a real-game observation.
"""
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "Sources/Core/UI"


def source(path: str) -> str:
    return (ROOT / path).read_text()


def region(text: str, start: str, end: str | None = None) -> str:
    assert start in text, f"missing owner: {start}"
    remainder = text.split(start, 1)[1]
    return remainder.split(end, 1)[0] if end else remainder


sidebar = source("Sources/Core/UI/TrainerSidebar.swift")
card = region(sidebar, "struct TrainerSidebarCard", "struct TrainerSidebar<")
status_color = region(card, "private var statusColor", "private var statusIndicator")
indicator = region(card, "private var statusIndicator", "var body: some View")
section_controls = source("Sources/Core/UI/Components/TrainerListControls.swift")
section = region(section_controls, "struct TrainerSectionButton", "private struct TrainerActionButtonLabel")

# The header stays a real SwiftUI keyboard/AX button while disabling the
# system focus effect. The native visual fixture compares only this header's
# rendered frame so focus changes elsewhere in the window cannot create noise.
assert ".buttonStyle(.plain)" in card
assert ".focusable(true, interactions: .activate)" in card
assert ".focusEffectDisabled()" in card
assert ".focused($headerFocused)" not in card
assert "headerFocused" not in card
assert ".accessibilityIdentifier(\"host.game." in card
assert ".accessibilityLabel(descriptor.displayName)" in card
assert "NSViewRepresentable" not in sidebar

# Connection state occupies one constant-sized dot; no glyph, spinner, or
# module-level selection stripe may substitute for the plain status marker.
assert "Circle()" in indicator and ".fill(" in indicator
assert ".frame(width: 8, height: 8)" in indicator
assert "Image(systemName:" not in indicator
assert "ProgressView(" not in indicator
for state in ("busy", "connected", "targetRunning", "theme.info", "theme.success", "theme.warning", "theme.inactive"):
    assert state in status_color, state
assert ".fill(statusColor)" in indicator
assert ".accessibilityLabel(" in indicator and ".accessibilityValue(" in indicator
assert "selectionMarkerWidth(" not in card
assert ".overlay(alignment: .leading)" in section
assert "selectionMarkerWidth(for: contrast)" in section
assert ".accessibilityAddTraits(selected ? .isSelected : [])" in section
# The marker lives inside the Button label. Keeping it outside the Button turns
# the caller's accessibility identifier into a composite wrapper that cannot be
# re-pressed after selection; the native multi-game journey protects this.
assert section.index(".overlay(alignment: .leading)") < section.index(".buttonStyle(.plain)")

# Selected Section keeps its thin position marker and a real AX button. The
# large purple Focus Block behind the chevron is intentionally absent.
assert ".focusEffectDisabled()" in section
assert "RoundedRectangle(cornerRadius: theme.compactCornerRadius" not in section

# Module changes use a coordinated accordion: retained action stacks clip
# open/closed while the header icon has no independent flying animation.
assert ".animation(TrainerMotion.animation(.disclosure, reduceMotion: reduceMotion), value: selected)" in card
assert ".animation(TrainerMotion.animation(.selection, reduceMotion: reduceMotion), value: selected)" not in card
pages = source("Sources/Core/Host/TrainerGamePages.swift")
assert "transition.prepare(" not in pages
assert "TrainerGamePageTransition" not in pages

# The picker/action role is trailing-anchored. The flexible column belongs
# between the label and the picker, never after the button group.
row = source("Sources/Core/UI/Primitives/TrainerRow.swift")
labeled = region(row, "struct TrainerLabeledControlRow")
assert "Spacer(minLength: 8)" in labeled
assert labeled.index("Spacer(minLength: 8)") < labeled.index("controls.environment(\\.trainerPickerActionWidth, allocatedPickerWidth)")
assert "TrainerPickerActionSizing.width(" in labeled
assert "if layout == .pickerAction" in labeled
assert ".frame(maxWidth: .infinity, alignment: .leading)" in labeled
assert "Spacer(minLength: 0)" not in labeled


# Both sidebar navigation sets start with the first visible Values section
# selected; subsequent navigation transfers the marker to the chosen row.
for path in ("Sources/Hades/HadesWorkbenchNavigation.swift", "Sources/Hades2/Views/Hades2HostActions.swift"):
    actions = source(path)
    assert "selectedSection == section.id || (selectedSection == nil && section == .values)" in actions, path
    assert "TrainerSectionButton(" in actions, path

# Room/reward Pickers in both modules share the Core row-action role regardless
# of option-title lengths. Non-inline picker groups remain expanding editors.
hades2 = source("Sources/Hades2/Hades2View.swift")
next_room = region(hades2, "private var nextRoomRewardPanel", "private var nextOccurrencePanel")
next_occurrence = region(hades2, "private var nextOccurrencePanel", "private var resourcePanel")
for block in (next_room, next_occurrence):
    assert "TrainerLabeledControlRow(" in block
    assert ".trainerPickerWidth(.rowAction)" in block
grouped = region(source("Sources/Core/UI/Components/TrainerResourceControls.swift"),
                 "struct TrainerGroupedOptionPicker")
assert ".trainerPickerWidth(inline ? .rowAction : .expanding)" in grouped
inline_group = region(grouped, "if inline {", "} else {")
assert "TrainerLabeledControlRow(" in inline_group
assert "layout: .pickerAction" in inline_group
assert "inline: true" in region(hades2, "private func spawnRow(", "private func multiplierRow(")
assert "spawnRow(" in region(hades2, "private var rewardSpawningPanel", "private var boonAcquisitionPanel")
hades1_rooms = source("Sources/Hades/HadesRoomsPanel.swift")
assert hades1_rooms.count(".trainerPickerWidth(.rowAction)") >= 6
assert hades1_rooms.count("layout: .pickerAction") >= 6

print("sidebar_and_room_picker_regressions_ok")
