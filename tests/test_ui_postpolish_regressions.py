"""Requested 2026-11-01 UI regressions 5-9 on their production owners.

These contracts are deliberately narrow and run without the game or real saves.
Native UI interaction and exact-head typecheck are separate evidence.
"""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text()


def section(contents, start, stop=None):
    assert start in contents, start
    result = contents.split(start, 1)[1]
    return result.split(stop, 1)[0] if stop is not None else result


pages = read("Sources/Core/Host/TrainerGamePages.swift")
hades = read("Sources/Hades/HadesTrainerView.swift")
hades2 = read("Sources/Hades2/Hades2View.swift")

# Retained workbench content crossfades at its own opacity boundary; the
# actual selection/hotkey/AX owner still switches immediately.
# Kept (motion policy): SwiftUI does not expose .animation(.selection, ...) transactions to AX/AppKit; TrainerMotion.animation(.selection, ...) itself is verified in management_ui_harness.py.
assert '.animation(TrainerMotion.animation(.selection, reduceMotion: reduceMotion), value: application.selectedGameID)' in pages

# The Hades I workbench shows no persistent banner above its actual sections,
# neither for waiting/hero-ready nor for errors. As in Hades II, operation
# feedback is the transient notice and retained failures are current issues
# (asserted natively by test_hades_frontend.py).
root = section(section(hades, "struct HadesTrainerView"), "var body: some View", "private var runDataSection")
assert 'if !model.heroReady {' not in root
assert 'runDataSection.trainerSectionTarget(' in root
assert "TrainerMessageBanner(" not in root

assert "TrainerSecondaryActionButton(" in read("Sources/Hades/HadesRoomsPanel.swift")
assert "TrainerSecondaryActionButton(" in hades2
print("module_motion_actions_lock_banner_widths_ok")
