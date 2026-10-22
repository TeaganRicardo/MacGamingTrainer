import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HADES = ROOT / 'Sources/Hades2'
CORE = ROOT / 'Sources/Core/UI'
view_files = list((HADES / 'Views').rglob('*.swift')) + [HADES / 'Hades2View.swift']
hades_views = '\n'.join(p.read_text() for p in view_files)
save_views = '\n'.join(p.read_text() for p in (ROOT / 'Sources/Core/Save').rglob('*.swift'))
product_views = hades_views + '\n' + save_views
core_ui = '\n'.join(p.read_text() for p in CORE.rglob('*.swift'))

assert not (HADES / 'Views/Controls').exists()
for forbidden_shape in ('Capsule()', 'RoundedRectangle(', '.background('):
    assert forbidden_shape not in hades_views, forbidden_shape

for path in view_files:
    text = path.read_text()
    for name in re.findall(r'^(?:private )?struct\s+([A-Za-z_][A-Za-z0-9_]*)\s*:', text, re.M):
        if name in {'Hades2TrainerView','Hades2SaveManagerView','Hades2ProfileManagerView','Hades2DiagnosticsView','Hades2ShortcutSettingsView','Hades2SidebarActions','Hades2HeaderActions'}:
            continue
        assert not re.search(r'(Row|Card|Toggle|Button|Field|Metric|Editor|Picker|Control|Badge)$', name), (path, name)

required = (
    'TrainerFeatureToggleRow', 'TrainerMultiplierMetricCard',
    'TrainerCompactMultiplierRow',
    'TrainerResourceEditor', 'TrainerGroupedOptionPicker',
    'TrainerVitalMetricCard', 'TrainerAmountMetricCard',
    'TrainerCounterMetricCard', 'TrainerStatMetricCard', 'TrainerMessageBanner',
    'TrainerPillBadge', 'TrainerEmptyState',
    'TrainerSheetScaffold', 'TrainerSectionHeader', 'TrainerMappedSlider',
    'TrainerSearchField',
)
for name in required:
    assert f'struct {name}' in core_ui, name
    assert name in product_views, name

# The base card is the primitive the metric wrappers build on; the product
# renders through the wrappers, so only its existence is required.
assert 'struct TrainerMetricCard' in core_ui

assert 'struct TrainerSelectableListRow' not in core_ui

for token in ('Hades2','invincibility','boonRarity','rerollsLocked','statAvailable','dormantFeatures','WeaponCast','CurrentRun'):
    assert token not in core_ui, token

management_view = (HADES / 'Views/Hades2ManagementViews.swift').read_text()
save_editor_view = (HADES / 'Views/Hades2SaveEditorView.swift').read_text()
resource_controls = (CORE / 'Components/TrainerResourceControls.swift').read_text()
status_controls = (CORE / 'Components/TrainerStatusControls.swift').read_text()
assert not re.search(r'(?<![A-Za-z0-9_])TextField\(', hades_views), 'Hades views must use Core-owned input primitives'
assert 'TrainerSearchField(' in hades_views
assert '.buttonStyle(.borderedProminent)' not in hades_views
assert 'TrainerPrimaryActionButton(' in management_view
assert 'TrainerPrimaryActionButton(' in save_editor_view
assert 'TrainerSearchField(' in resource_controls
assert 'TrainerPrimaryActionButton(' in status_controls
assert '.buttonStyle(.borderedProminent)' not in status_controls
assert 'theme.rowHorizontalPadding' in save_editor_view
assert 'theme.panelPadding' not in save_editor_view
assert 'theme.inlineRowVerticalPadding' in save_editor_view

print('ui_component_boundary_v0175_ok')

host = (ROOT / 'Sources/Core/Host/TrainerHost.swift').read_text()
assert 'TrainerConnectionStatusCard(' in host
assert 'TrainerConnectionStatusCard(' not in hades_views
