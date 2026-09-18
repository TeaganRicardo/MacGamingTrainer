from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

shared_paths = [
    ROOT / 'Sources/App.swift',
    ROOT / 'build.sh',
]
shared_paths += sorted((ROOT / 'Sources/Core').rglob('*.swift'))
shared_paths += sorted((ROOT / 'Backend/core').rglob('*.py'))
shared_paths += [
    ROOT / 'Tools/module_support.py',
    ROOT / 'Tools/generate_game_binding.py',
    ROOT / 'Tools/validate_game_module.py',
]

shared = '\n'.join(path.read_text() for path in shared_paths)

# Shared Host/Core/build code may know "game module", but never Hades business
# names, transport types, commands or runtime data structures.
for token in (
    'Hades2',
    'Hades II',
    'games.hades2',
    'Hades2Adapter',
    'CurrentRun',
    'godMode',
    'boonRarity',
    'SpellDrop',
    'TalentDrop',
    'TraitData',
    'WeaponCast',
):
    assert token not in shared, token

fixture_root = ROOT / 'ContractFixtures/reference_module'
fixture = '\n'.join(path.read_text() for path in fixture_root.rglob('*') if path.is_file())
hades = '\n'.join(path.read_text() for path in (ROOT / 'Sources/Hades2').rglob('*.swift'))
hades += '\n' + '\n'.join(
    path.read_text(errors='ignore')
    for path in (ROOT / 'Backend/games/hades2').rglob('*')
    if path.is_file() and path.suffix in {'.py', '.json', '.lua'}
)

# Game modules are peers; neither may depend on the other's implementation.
for token in ('Hades2', 'Hades II', 'hades2', 'CurrentRun', 'boonRarity'):
    assert token not in fixture, token
for token in ('ReferenceFixture', 'reference_fixture'):
    assert token not in hades, token

# The permanent fixture stays outside runtime discovery. Tests/CI install it
# temporarily into the standard module locations.
assert not (ROOT / 'Backend/games/reference_fixture').exists()
assert not (ROOT / 'Sources/ReferenceFixture').exists()

print('cross_game_isolation_ok')


# Shared propagation is structural: every selected module is compiled with
# Sources/App.swift + every Sources/Core Swift file, then only its own frontend.
# There must be no game switch/case in this source-graph assembly.
build = (ROOT / 'build.sh').read_text()
assert 'SWIFT_SOURCES=("$ROOT/Sources/App.swift")' in build
assert 'find "$ROOT/Sources/Core" -type f -name' in build
assert 'find "$FRONTEND_DIR" -type f -name' in build
assert build.index('find "$ROOT/Sources/Core"') < build.index('find "$FRONTEND_DIR"')
for forbidden in ('case "$ACTIVE_GAME_ID"', 'if [[ "$ACTIVE_GAME_ID"', 'hades2)', 'reference_fixture)'):
    assert forbidden not in build, forbidden

core_ui = '\n'.join(path.read_text() for path in (ROOT / 'Sources/Core/UI').rglob('*.swift'))
hades_ui = '\n'.join(path.read_text() for path in (ROOT / 'Sources/Hades2').rglob('*.swift'))
assert 'struct TrainerFeatureToggleRow' in core_ui
assert 'TrainerFeatureToggleRow(' in hades_ui
assert 'TrainerFeatureToggleRow(' in fixture

print('shared_core_propagation_ok')
