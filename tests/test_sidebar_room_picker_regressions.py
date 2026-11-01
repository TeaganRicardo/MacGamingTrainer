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
indicator = region(card, "private var statusIndicator", "var body: some View")
section_controls = source("Sources/Core/UI/Components/TrainerListControls.swift")
section = region(section_controls, "struct TrainerSectionButton", "private struct TrainerActionButtonLabel")

# The header remains a real keyboard/AX button without any focus-only paint.
assert ".focusEffectDisabled()" in card
assert ".focused($headerFocused)" not in card
assert "headerFocused" not in card
assert ".accessibilityIdentifier(\"host.game." in card
assert ".accessibilityLabel(descriptor.displayName)" in card

# Connection state occupies one constant-sized dot; no glyph, spinner, or
# module-level selection stripe may substitute for the plain status marker.
assert "Circle()" in indicator and ".fill(" in indicator
assert ".frame(width: 8, height: 8)" in indicator
assert "Image(systemName:" not in indicator
assert "ProgressView(" not in indicator
for state in ("busy", "connected", "targetRunning", "theme.info", "theme.success", "theme.warning", "theme.inactive"):
    assert state in indicator, state
assert ".accessibilityLabel(" in indicator and ".accessibilityValue(" in indicator
assert "selectionMarkerWidth(" not in card
assert ".overlay(alignment: .leading)" in section
assert "selectionMarkerWidth(for: contrast)" in section
assert ".accessibilityAddTraits(selected ? .isSelected : [])" in section

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
assert "TrainerLabeledControlRow(" in region(grouped, "if inline {", "} else {")
assert "inline: true" in region(hades2, "private func spawnRow(", "private func multiplierRow(")
assert "spawnRow(" in region(hades2, "private var rewardSpawningPanel", "private var boonAcquisitionPanel")
hades1_rooms = source("Sources/Hades/HadesRoomsPanel.swift")
assert hades1_rooms.count(".trainerPickerWidth(.rowAction)") >= 6

print("sidebar_and_room_picker_regressions_ok")
