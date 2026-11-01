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
sidebar = read("Sources/Core/UI/TrainerSidebar.swift")
controls = read("Sources/Core/UI/Components/TrainerListControls.swift")
lock = read("Sources/Core/UI/Primitives/TrainerToggleControl.swift")
hades = read("Sources/Hades/HadesTrainerView.swift")
hades2 = read("Sources/Hades2/Hades2View.swift")
theme = read("Sources/Core/UI/TrainerTheme.swift")

# Game selection changes visible pages immediately rather than animating a
# heavy stack/sidebar layout when retained models and native controls update.
assert '.animation(TrainerMotion.animation(.selection, reduceMotion: reduceMotion), value: application.selectedGameID)' not in pages
card = section(sidebar, "struct TrainerSidebarCard", "struct TrainerSidebar<")
selection_motion = '.animation(TrainerMotion.animation(.selection, reduceMotion: reduceMotion), value: selected)'
assert card.count(selection_motion) == 1
assert card.index(selection_motion) < card.index(".frame(width: 24)")
assert ".opacity(context.id == application.selectedGameID ? 1 : 0)" in pages
assert ".allowsHitTesting(context.id == application.selectedGameID)" in pages

# Shared primary and secondary labeled actions render verb text without an
# ornamental leading symbol, including existing call sites still passing one.
label = section(controls, "private struct TrainerActionButtonLabel", "struct TrainerPrimaryActionButton")
assert "Text(title)" in label
assert "Label(title, systemImage:" not in label
assert "Image(systemName:" not in label
assert "TrainerActionButtonLabel(" in section(controls, "struct TrainerPrimaryActionButton", "struct TrainerSecondaryActionButton")
assert "TrainerActionButtonLabel(" in section(controls, "struct TrainerSecondaryActionButton", "struct TrainerInlineNameEditor")

# Both modules' metric-card lock controls use Core's borderless icon action.
lock_button = section(lock, "struct TrainerLockButton")
assert ".buttonStyle(.plain)" in lock_button
assert ".buttonStyle(.bordered)" not in lock_button
assert '.frame(width: 26, height: 24)' in lock_button
assert ".accessibilityLabel(" in lock_button
assert "TrainerLockButton(" in read("Sources/Core/UI/Components/TrainerStatControls.swift")

# The Hades I workbench should not show a persistent waiting/hero-ready banner
# above its actual sections. Error presentations remain intentionally separate.
root = section(section(hades, "struct HadesTrainerView"), "var body: some View", "private var runDataSection")
assert 'if !model.heroReady {' not in root
assert 'runDataSection.trainerSectionTarget(' in root
assert "if !error.isEmpty" in root

# Labeled action widths belong to one Core semantic policy, not game call sites.
assert "enum TrainerActionWidthRole" in controls
width_owner = section(controls, "private struct TrainerActionWidthModifier", "struct TrainerPrimaryActionButton")
assert "case .compactRow:" in width_owner and "theme.compactActionWidth" in width_owner
assert "case .connection:" in width_owner and "theme.connectionActionWidth" in width_owner
assert "case .sheet:" in width_owner
primary = section(controls, "struct TrainerPrimaryActionButton", "struct TrainerSecondaryActionButton")
secondary = section(controls, "struct TrainerSecondaryActionButton", "struct TrainerInlineNameEditor")
for action in (primary, secondary):
    assert "widthRole: TrainerActionWidthRole = .compactRow" in action
    assert "TrainerActionWidthModifier(role: widthRole)" in action
assert 'compactActionWidth: 88' in theme
assert "TrainerSecondaryActionButton(" in read("Sources/Hades/HadesRoomsPanel.swift")
assert "TrainerSecondaryActionButton(" in hades2
print("module_motion_actions_lock_banner_widths_ok")
