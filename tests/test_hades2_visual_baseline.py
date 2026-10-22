from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HADES = ROOT / 'Sources/Hades2'
CORE_UI = ROOT / 'Sources/Core/UI'
all_hades = '\n'.join(p.read_text() for p in HADES.rglob('*.swift'))
all_core_ui = '\n'.join(p.read_text() for p in CORE_UI.rglob('*.swift'))
view = (HADES / 'Hades2View.swift').read_text()
theme = (CORE_UI / 'TrainerTheme.swift').read_text()
toggle = (CORE_UI / 'Primitives/TrainerToggleControl.swift').read_text()
features = (CORE_UI / 'Components/TrainerFeatureControls.swift').read_text()
stats = (CORE_UI / 'Components/TrainerStatControls.swift').read_text()
resource = (CORE_UI / 'Components/TrainerResourceControls.swift').read_text()
row = (CORE_UI / 'Primitives/TrainerRow.swift').read_text()
card = (CORE_UI / 'Primitives/TrainerCard.swift').read_text()
search_field = (CORE_UI / 'Components/TrainerSearchField.swift').read_text()
action_buttons = (CORE_UI / 'Components/TrainerListControls.swift').read_text()
occurrence = (HADES / 'Views/Hades2OccurrenceSetting.swift').read_text()
save_editor = (HADES / 'Views/Hades2SaveEditorView.swift').read_text()
resource_controls = (CORE_UI / 'Components/TrainerResourceControls.swift').read_text()
lock_button = (CORE_UI / 'Primitives/TrainerToggleControl.swift').read_text()
status_controls = (CORE_UI / 'Components/TrainerStatusControls.swift').read_text()
management = (HADES / 'Views/Hades2ManagementViews.swift').read_text()

# v0.17.5 keeps v0.11 visuals but the implementation now lives in Core.
assert not (HADES / 'Views/Controls').exists()
assert not (HADES / 'Views/Hades2BoonPicker.swift').exists()
for token in ('Capsule()', 'RoundedRectangle(', '.background('):
    assert token not in all_hades, f'game module still draws reusable visual primitive: {token}'

for component in (
    'TrainerFeatureToggleRow(', 'TrainerMultiplierMetricCard(', 'TrainerCompactMultiplierRow(',
    'TrainerResourceEditor(', 'TrainerGroupedOptionPicker(',
'TrainerVitalMetricCard(', 'TrainerAmountMetricCard(',
    'TrainerCounterMetricCard(', 'TrainerStatMetricCard(',
):
    assert component in all_hades, component

# Core components must remain game-agnostic.
for semantic in ('Hades2', 'invincibility', 'boonRarity', 'dormantFeatures', 'CurrentRun', 'WeaponCast'):
    assert semantic not in all_core_ui, semantic

# Shared switch baseline: old purple native regular switch, one implementation.
assert 'accent: Color(red: 0.64, green: 0.51, blue: 1.0)' in theme
assert 'deferred: .orange' in theme
assert 'Capsule()' not in toggle
assert '.toggleStyle(.switch)' in toggle
assert '.controlSize(.regular)' in toggle
assert '.tint(tint ?? theme.accent)' in toggle
assert features.count('tint: state.indicatorColor') >= 3
assert '.animation(.easeInOut(duration: 0.16), value: isOn)' in toggle
assert 'HStack(spacing: 16)' in features
assert 'TrainerIconLabel(' in features
assert '.frame(width: 40, height: 40)' in row
assert 'theme.rowHorizontalPadding' in row
assert 'theme.rowMinimumHeight' in row
assert '.background(theme.panel)' in row

# Normal and multiplier rows share the exact same shortcut badge slot and switch.
assert features.count('TrainerShortcutBadgeSlot(text: shortcutText)') >= 3
assert features.count('TrainerToggleControl(') >= 3
assert 'Text(shortcutText)' not in features

# Compact metric-card and stat geometry stays on the old baseline.
metric_block = card[card.index('struct TrainerMetricCard'):]
assert '.padding(.top, 6)' in metric_block
assert '.padding(.bottom, 8)' in metric_block
assert 'minHeight: 82' not in metric_block
assert '.frame(maxWidth: .infinity, alignment: .leading)' in metric_block
assert 'HStack(spacing: 2)' in stats
assert stats.count('.frame(width: 54)') >= 2
assert 'HStack(spacing: 3)' in stats
assert '.frame(width: 58)' in stats
assert 'HStack(spacing: 5)' in view
assert '.contentShape(Rectangle())' in view

# Search controls and primary actions use the same Core-owned presentation.
assert 'theme.compactControlSpacing' in search_field
assert 'theme.controlPadding' in search_field
assert '.trainerSurface(.subtle, cornerRadius: theme.controlCornerRadius)' in search_field
assert 'TrainerSearchField(' in view
assert 'TrainerSearchField(' in save_editor
assert 'struct TrainerSecondaryActionButton' in action_buttons
assert 'TrainerSecondaryActionButton(' in occurrence
assert 'TrainerSearchField(' in resource_controls
assert 'TrainerPrimaryActionButton(' in save_editor
assert 'TrainerPrimaryActionButton(' in status_controls
assert 'TrainerPrimaryActionButton(' in management
assert '.buttonStyle(.borderedProminent)' not in status_controls
assert 'theme.rowHorizontalPadding' in save_editor
assert 'theme.panelPadding' not in save_editor
assert 'theme.inlineRowVerticalPadding' in save_editor

# Stat/resource geometry stays on the old baseline.
assert '.frame(width: 58)' in stats
assert 'TrainerRow(opacity:' in stats
assert 'TrainerLockButton' in stats
assert 'TrainerNumberField(text: $amount' in resource
assert 'TrainerLockButton(' in resource
assert 'localization.localized(locked ? "host.unlock" : "host.lock")' in lock_button

print('hades2_visual_baseline_v0175_ok')

# Connection chrome is globally hosted so every game gets identical layout/behavior.
host = (ROOT / 'Sources/Core/Host/TrainerHost.swift').read_text()
assert 'TrainerConnectionStatusCard(' in host
assert 'TrainerConnectionStatusCard(' not in all_hades
