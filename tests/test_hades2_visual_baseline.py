from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HADES = ROOT / 'Sources/Hades2'
all_hades = '\n'.join(hades_path.read_text() for hades_path in HADES.rglob('*.swift'))
view = (HADES / 'Hades2View.swift').read_text()
occurrence = (HADES / 'Views/Hades2OccurrenceSetting.swift').read_text()
save_editor = (HADES / 'Views/Hades2SaveEditorView.swift').read_text()
management = (HADES / 'Views/Hades2ManagementViews.swift').read_text()

# v0.17.5 keeps v0.11 visuals but the implementation now lives in Core.
assert not (HADES / 'Views/Controls').exists()
assert not (HADES / 'Views/Hades2BoonPicker.swift').exists()
for token in ('Capsule()', 'RoundedRectangle(', '.background('):
    assert token not in all_hades, f'game module still draws reusable visual primitive: {token}'

for component in (
    'TrainerFeatureToggleRow(', 'TrainerMultiplierMetricCard(', 'TrainerFeatureMultiplierRow(',
    'TrainerResourceEditor(', 'TrainerGroupedOptionPicker(',
'TrainerVitalMetricCard(', 'TrainerAmountMetricCard(',
    'TrainerCounterMetricCard(', 'TrainerStatMetricCard(',
):
    assert component in all_hades, component

assert 'TrainerDisclosureButton(' in view
assert 'TrainerSearchField(' in view
assert 'TrainerSaveEditorWorkbenchBar(' in save_editor
assert 'TrainerSecondaryActionButton(' in occurrence
assert 'TrainerPrimaryActionButton(' in save_editor
assert 'TrainerProfileManagerView(' in management
assert 'theme.rowHorizontalPadding' in save_editor
assert 'theme.panelPadding' not in save_editor
assert 'theme.inlineRowVerticalPadding' in save_editor

print('hades2_visual_baseline_v0175_ok')

# Connection chrome is globally hosted so every game gets identical layout/behavior.
assert 'TrainerConnectionStatusCard(' not in all_hades
