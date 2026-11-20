from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HADES = ROOT / 'Sources/Hades2'
CORE_UI = ROOT / 'Sources/Core/UI'
hades = '\n'.join(hades_path.read_text() for hades_path in HADES.rglob('*.swift'))
toggle = (CORE_UI / 'Primitives/TrainerToggleControl.swift').read_text()
features = (CORE_UI / 'Components/TrainerFeatureControls.swift').read_text()

# Hades owns no Toggle rendering path at all. Switches and checkboxes come from Core.
assert 'Toggle(' not in hades
assert 'TrainerToggleControl(' in hades
assert 'TrainerCheckboxControl(' in hades

# Kept (lint): single-owner boundary ensuring only TrainerToggleControl declares .toggleStyle(.switch) across Core UI.
switch_files = []
for core_path in CORE_UI.rglob('*.swift'):
    if '.toggleStyle(.switch)' in core_path.read_text():
        switch_files.append(core_path.relative_to(ROOT).as_posix())
assert switch_files == ['Sources/Core/UI/Primitives/TrainerToggleControl.swift'], switch_files

# Kept (no headless render hook): macOS renders native NSSwitch tint neutral gray in inactive headless windows, so switch tint forwarding has no PR-safe render hook.
assert '.tint(tint ?? theme.accent)' in toggle
assert features.count('tint: state.indicatorColor') >= 2

print('toggle_unification_v0178_ok')
