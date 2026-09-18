from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HADES = ROOT / 'Sources/Hades2'
CORE_UI = ROOT / 'Sources/Core/UI'
hades = '\n'.join(p.read_text() for p in HADES.rglob('*.swift'))
core = '\n'.join(p.read_text() for p in CORE_UI.rglob('*.swift'))
toggle = (CORE_UI / 'Primitives/TrainerToggleControl.swift').read_text()
features = (CORE_UI / 'Components/TrainerFeatureControls.swift').read_text()
stats = (CORE_UI / 'Components/TrainerStatControls.swift').read_text()
presentation = (HADES / 'Presentation/Hades2FeaturePresentation.swift').read_text()
theme = (CORE_UI / 'TrainerTheme.swift').read_text()
view = (HADES / 'Hades2View.swift').read_text()

# Hades owns no Toggle rendering path at all. Switches and checkboxes come from Core.
assert 'Toggle(' not in hades
assert 'TrainerToggleControl(' in view
assert 'TrainerCheckboxControl(' in view

# Exactly one switch-style implementation exists in the shared UI library.
switch_files = []
for path in CORE_UI.rglob('*.swift'):
    if '.toggleStyle(.switch)' in path.read_text():
        switch_files.append(path.relative_to(ROOT).as_posix())
assert switch_files == ['Sources/Core/UI/Primitives/TrainerToggleControl.swift'], switch_files

# Shared switch is native regular and animated. Purple remains the default, but
# feature rows may pass the same neutral phase tint used by their icon.
for token in ('.toggleStyle(.switch)', '.controlSize(.regular)', '.tint(tint ?? theme.accent)', '.fixedSize()', '.animation(.easeInOut(duration: 0.16), value: isOn)'):
    assert token in toggle, token
assert 'Capsule()' not in toggle
assert 'let tint: Color?' in toggle
assert features.count('tint: state.indicatorColor') >= 3
assert 'toggleColor' not in core
assert 'toggleColor' not in presentation
assert 'toggleTint' not in presentation

# Waiting/detached indication is orange outside the switch; obsolete green deferred state is gone.
assert 'deferred: .orange' in theme
assert 'case .detached: return theme.warning' in presentation
assert 'Color(red: 0.43, green: 0.56, blue: 0.48)' not in theme

# Every shared switch-using row routes through TrainerToggleControl.
assert features.count('TrainerToggleControl(') >= 3
assert 'TrainerToggleControl(' in stats
assert '.toggleStyle(.switch)' not in features
assert '.toggleStyle(.switch)' not in stats

# Shortcut badge is identical in normal and multiplier rows and occupies one fixed column.
assert features.count('TrainerShortcutBadgeSlot(text: shortcutText)') >= 3
assert 'Text(shortcutText)' not in features
badge = (CORE_UI / 'Primitives/TrainerBadge.swift').read_text()
assert 'struct TrainerShortcutBadgeSlot' in badge
assert '.frame(width: 52, alignment: .center)' in badge
assert 'TrainerShortcutBadge(text: text)' in badge

print('toggle_unification_v0178_ok')
