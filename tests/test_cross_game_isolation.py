import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Tools'))
from swift_module_layout import SWIFT_APP_MODULE, SWIFT_CORE_MODULE  # noqa: E402
from product_support import load_selection  # noqa: E402

# Swift isolation is the compiler's: build.sh gives each Swift module only the
# swiftmodules of its declared dependencies, so Core cannot import a game and a
# game cannot import another game. This asserts that declared layout; the build
# preflight test asserts build.sh passes exactly these search paths.
selection = load_selection('all')
layout = {module['name']: module for module in selection.normalized()['frontend']['swift']['modules']}
games = [module.frontend.swift_module for module in selection.modules]
assert list(layout) == [SWIFT_CORE_MODULE, *games, SWIFT_APP_MODULE], list(layout)
assert layout[SWIFT_CORE_MODULE]['dependencies'] == []
for game in games:
    assert layout[game]['dependencies'] == [SWIFT_CORE_MODULE], (game, layout[game])
assert layout[SWIFT_APP_MODULE]['dependencies'] == [SWIFT_CORE_MODULE, *games]
for module in selection.modules:
    isolated = load_selection(module.id).normalized()['frontend']['swift']['modules']
    assert [item['name'] for item in isolated] == [SWIFT_CORE_MODULE, module.frontend.swift_module, SWIFT_APP_MODULE]

# The Python boundary keeps its vocabulary check until #771 replaces it.
shared_paths = sorted((ROOT / 'Backend/core').rglob('*.py'))
shared_paths += [
    ROOT / 'Tools/module_support.py',
    ROOT / 'Tools/generate_game_binding.py',
    ROOT / 'Tools/validate_game_module.py',
]

shared = '\n'.join(path.read_text() for path in shared_paths)

for token in (
    'Hades2',
    'Hades II',
    'games.hades2',
    'Hades2Adapter',
    'CurrentRun',
    'invincibility',
    'boonRarity',
    'SpellDrop',
    'TalentDrop',
    'TraitData',
    'WeaponCast',
):
    assert token not in shared, token

fixture_root = ROOT / 'ContractFixtures/reference_module/backend'
fixture = '\n'.join(path.read_text() for path in fixture_root.rglob('*') if path.is_file())
hades = '\n'.join(
    path.read_text(errors='ignore')
    for path in (ROOT / 'Backend/games/hades2').rglob('*')
    if path.is_file() and path.suffix in {'.py', '.json', '.lua'}
)

for token in ('Hades2', 'Hades II', 'hades2', 'CurrentRun', 'boonRarity'):
    assert token not in fixture, token
for token in ('ReferenceFixture', 'reference_fixture'):
    assert token not in hades, token

assert not (ROOT / 'Backend/games/reference_fixture').exists()
assert not (ROOT / 'Sources/ReferenceFixture').exists()

# The reference fixture keeps exercising a shared Core control, so a Core
# change reaches a second module. That the Core declaration still serves the
# call sites is the compiler's (typecheck and the fixture's module build).
fixture_ui = (ROOT / 'ContractFixtures/reference_module/frontend/ReferenceFixtureModule.swift').read_text()
assert 'TrainerFeatureToggleRow(' in fixture_ui

print('cross_game_isolation_ok')
