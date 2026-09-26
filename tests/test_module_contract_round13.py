import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
fixture = root / 'ContractFixtures/reference_module'
game_id = 'reference_fixture'
checkout_backend_module = root / 'Backend/games' / game_id
checkout_frontend = root / 'Sources/ReferenceFixture'

assert fixture.is_dir()
assert not checkout_backend_module.exists() and not checkout_frontend.exists()

with tempfile.TemporaryDirectory(prefix='mgt-module-contract-') as td:
    project = Path(td) / 'project'
    backend_module = project / 'Backend/games' / game_id
    frontend = project / 'Sources/ReferenceFixture'
    tools = project / 'Tools'

    (project / 'Backend/games').mkdir(parents=True)
    (project / 'Sources').mkdir(parents=True)
    tools.mkdir(parents=True)

    # Install the reference fixture and the minimum shared project surface into
    # an isolated temporary project. The repository checkout is never mutated.
    shutil.copytree(fixture / 'backend', backend_module)
    shutil.copytree(fixture / 'frontend', frontend)
    shutil.copytree(root / 'Backend/core', project / 'Backend/core')
    shutil.copytree(root / 'Sources/Core', project / 'Sources/Core')
    shutil.copy2(root / 'Sources/App.swift', project / 'Sources/App.swift')
    for name in ('module_support.py', 'validate_game_module.py', 'generate_game_binding.py'):
        shutil.copy2(root / 'Tools' / name, tools / name)

    env = os.environ.copy()
    env['PYTHONDONTWRITEBYTECODE'] = '1'

    normalized = json.loads(subprocess.check_output([
        'python3', str(tools / 'validate_game_module.py'), game_id, '--json'
    ], text=True, cwd=project, env=env))
    assert normalized['id'] == game_id
    assert normalized['frontend']['moduleType'] == 'ReferenceFixtureGameModule'
    assert normalized['appResources'] == []  # No Hades-specific resource required by a second module.
    assert normalized['buildRequirements'] == {
        'lldbPython': False,
        'debuggerEntitlement': False,
        'entitlements': '',
    }
    assert 'saveManagement' not in normalized

    generated = project / 'Generated/ActiveGameModule.swift'
    subprocess.run([
        'python3', str(tools / 'generate_game_binding.py'), game_id, str(generated)
    ], check=True, cwd=project, env=env)
    text = generated.read_text()
    assert 'typealias ActiveGameModule = ReferenceFixtureGameModule' in text
    assert 'expectedHostProtocolVersion: 6' in text
    assert 'expectedModuleProtocolVersion: 1' in text
    assert 'supportsSaveManagement: false' in text

    core = sorted((project / 'Sources/Core').rglob('*.swift'))
    sources = [project / 'Sources/App.swift'] + core + [
        frontend / 'ReferenceFixtureModule.swift',
        generated,
    ]
    swiftc = shutil.which('swiftc')
    if not swiftc:
        raise SystemExit('swiftc required for module contract test')
    subprocess.run(
        [swiftc, '-frontend', '-parse', *map(str, sources)],
        check=True,
        cwd=project,
    )

    generic = (
        (project / 'Sources/App.swift').read_text()
        + '\n'
        + '\n'.join(path.read_text() for path in (project / 'Sources/Core').rglob('*.swift'))
        + '\n'
        + (root / 'build.sh').read_text()
        + '\n'
        + (root / 'Tools/module_support.py').read_text()
    )
    assert 'ReferenceFixture' not in generic
    assert 'reference_fixture' not in generic
    assert 'hades2' not in generic
    assert 'ui_terminology.json' not in generic

# Even successful execution must leave the source checkout untouched.
assert not checkout_backend_module.exists()
assert not checkout_frontend.exists()

print('module_contract_round13_ok')
