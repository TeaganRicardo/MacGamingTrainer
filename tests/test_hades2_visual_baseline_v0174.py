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

# v0.17.5 keeps v0.11 visuals but the implementation now lives in Core.
assert not (HADES / 'Views/Controls').exists()
assert not (HADES / 'Views/Hades2BoonPicker.swift').exists()
for token in ('Capsule()', 'RoundedRectangle(', '.background('):
    assert token not in all_hades, f'game module still draws reusable visual primitive: {token}'

for component in (
    'TrainerFeatureToggleRow(', 'TrainerFeatureMultiplierRow(', 'TrainerCompactMultiplierRow(',
    'TrainerInlineStatEditor(', 'TrainerResourceEditor(', 'TrainerGroupedOptionPicker(',
'TrainerVitalMetricCard(', 'TrainerAmountMetricCard(',
    'TrainerCounterMetricCard(', 'TrainerStatMetricCard(', 'TrainerMessageBanner(',
):
    assert component in all_hades, component

# Core components must remain game-agnostic.
for semantic in ('Hades2', 'godMode', 'boonRarity', 'dormantFeatures', 'CurrentRun', 'WeaponCast'):
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

# Stat/resource geometry stays on the old baseline.
assert '.frame(width: 58)' in stats
assert 'TrainerRow(opacity:' in stats
assert 'TrainerLockButton' in stats
assert 'TrainerNumberField(text: $amount' in resource
assert 'Label(locked ? "已锁定" : "锁定"' in resource

print('hades2_visual_baseline_v0175_ok')

# Connection chrome is globally hosted so every game gets identical layout/behavior.
host = (ROOT / 'Sources/Core/Host/TrainerHost.swift').read_text()
assert 'TrainerConnectionStatusCard(' in host
assert 'TrainerConnectionStatusCard(' not in all_hades
