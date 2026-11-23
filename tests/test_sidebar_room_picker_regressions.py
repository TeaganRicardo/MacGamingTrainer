"""Regressions for Hades I and Hades II sidebar and Rooms & Rewards picker roles.

Shared Core sidebar, section-button, and picker-action layout behaviors are verified
natively in test_core_ui_primitives_macos.py and room_picker_alignment_harness.py.
"""
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text()


def region(text: str, start: str, end: str | None = None) -> str:
    assert start in text, f"missing owner: {start}"
    remainder = text.split(start, 1)[1]
    return remainder.split(end, 1)[0] if end else remainder


# The native fixture measures the marker under the current display contrast.
# SwiftUI's contrast environment is read-only, so retain the link to it here.
section_controls = source("Sources/Core/UI/Components/TrainerListControls.swift")
section = region(section_controls, "struct TrainerSectionButton", "enum TrainerActionWidthRole")
assert "theme.selectionMarkerWidth(for: contrast)" in section


# Both sidebar navigation sets start with the first visible Values section
# selected; subsequent navigation transfers the marker to the chosen row.
trainer_host = source("Sources/Core/Host/TrainerHost.swift")
assert "selectedSection == section.id" in trainer_host
assert "section.id == sections.first?.id" in trainer_host
assert "TrainerSectionButton(" in trainer_host
for path in ("Sources/Hades/HadesModule.swift", "Sources/Hades2/Hades2Module.swift"):
    module_source = source(path)
    assert "static func workbenchSections(" in module_source, path
    assert "separatedFromPrevious: section == .management" in module_source, path

# Room/reward Pickers in both modules share the Core row-action role regardless
# of option-title lengths. Non-inline picker groups remain expanding editors.
hades2 = source("Sources/Hades2/Hades2View.swift")
world_exit = region(hades2, "private var worldExitPanel", "private var nextOccurrencePanel")
next_occurrence = region(hades2, "private var nextOccurrencePanel", "private var resourcePanel")
assert "TrainerDualPickerActionRow(" in world_exit
assert world_exit.count(".trainerPicker(.layoutAllocated") == 2
assert "model.canSelectWorldExitTarget" in world_exit
assert "latched: model.selectedWorldExitLease != nil" in world_exit
assert "subduedLatched: true" in world_exit
assert "TrainerLabeledControlRow(" in next_occurrence
assert "layout: .pickerAction" in next_occurrence
assert "latched: pending" in next_occurrence

hades1_rooms = source("Sources/Hades/HadesRoomsPanel.swift")
hades1_exit = region(hades1_rooms, "private var worldExitRow", "private var worldOccurrenceRow")
hades1_occurrence = region(hades1_rooms, "private var worldOccurrenceRow", "var body: some View")
assert "TrainerDualPickerActionRow(" in hades1_exit
assert hades1_exit.count(".trainerPicker(") == 2
assert hades1_exit.count(".layoutAllocated") == 2
assert "latched: model.selectedWorldExitLease != nil" in hades1_exit
assert "subduedLatched: true" in hades1_exit
assert "TrainerLabeledControlRow(" in hades1_occurrence
assert "layout: .pickerAction" in hades1_occurrence
assert ".rowAction," in hades1_occurrence

print("sidebar_and_room_picker_regressions_ok")
