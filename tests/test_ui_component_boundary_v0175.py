import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HADES = ROOT / 'Sources/Hades2'
CORE = ROOT / 'Sources/Core/UI'
view_files = list((HADES / 'Views').rglob('*.swift')) + [HADES / 'Hades2View.swift']
hades_views = '\n'.join(view_path.read_text() for view_path in view_files)
save_views = '\n'.join(save_path.read_text() for save_path in (ROOT / 'Sources/Core/Save').rglob('*.swift'))
product_views = hades_views + '\n' + save_views
core_ui = '\n'.join(core_path.read_text() for core_path in CORE.rglob('*.swift'))

assert not (HADES / 'Views/Controls').exists()
for forbidden_shape in ('Capsule()', 'RoundedRectangle(', '.background('):
    assert forbidden_shape not in hades_views, forbidden_shape

for path in view_files:
    text = path.read_text()
    for name in re.findall(r'^(?:private )?struct\s+([A-Za-z_][A-Za-z0-9_]*)\s*:', text, re.M):
        if name in {'Hades2TrainerView','Hades2SaveManagerView','Hades2ProfileManagerView','Hades2DiagnosticsView','Hades2ShortcutSettingsView'}:
            continue
        assert not re.search(r'(Row|Card|Toggle|Button|Field|Metric|Editor|Picker|Control|Badge)$', name), (path, name)

required = (
    'TrainerFeatureToggleRow', 'TrainerMultiplierMetricCard',
    'TrainerFeatureMultiplierRow',
    'TrainerResourceEditor', 'TrainerGroupedOptionPicker',
    'TrainerVitalMetricCard', 'TrainerAmountMetricCard',
    'TrainerCounterMetricCard', 'TrainerStatMetricCard', 'TrainerMessageBanner',
    'TrainerPillBadge', 'TrainerEmptyState',
    'TrainerSheetScaffold', 'TrainerSection', 'TrainerMappedSlider',
    'TrainerSearchField',
)
for name in required:
    assert name in product_views, name

# Kept (lint): Core UI must stay game-agnostic and never reference game-specific identifiers.
for token in ('Hades2','invincibility','boonRarity','rerollsLocked','statAvailable','dormantFeatures','WeaponCast','CurrentRun'):
    assert token not in core_ui, token

management_view = (HADES / 'Views/Hades2ManagementViews.swift').read_text()
save_editor_view = (HADES / 'Views/Hades2SaveEditorView.swift').read_text()
assert not re.search(r'(?<![A-Za-z0-9_])TextField\(', hades_views), 'Hades views must use Core-owned input primitives'
assert 'TrainerSearchField(' in hades_views
assert '.buttonStyle(.borderedProminent)' not in hades_views
assert 'TrainerProfileManagerView(' in management_view
assert 'TrainerPrimaryActionButton(' in save_editor_view
assert 'theme.rowHorizontalPadding' in save_editor_view
assert 'theme.panelPadding' not in save_editor_view
assert 'theme.inlineRowVerticalPadding' in save_editor_view

print('ui_component_boundary_v0175_ok')

# The Host owns the connection card: TrainerHost renders the Context's composition.
assert 'TrainerConnectionStatusCard(' not in hades_views
