from pathlib import Path
import json
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
fixture = root / 'ContractFixtures/reference_module'
game_id = 'reference_fixture'
backend_module = root / 'Backend/games' / game_id
frontend = root / 'Sources/ReferenceFixture'

assert fixture.is_dir()
assert not backend_module.exists() and not frontend.exists()

shutil.copytree(fixture / 'backend', backend_module)
shutil.copytree(fixture / 'frontend', frontend)
try:
    normalized = json.loads(subprocess.check_output([
        'python3', str(root / 'Tools/validate_game_module.py'), game_id, '--json'
    ], text=True))
    assert normalized['id'] == game_id
    assert normalized['frontend']['moduleType'] == 'ReferenceFixtureGameModule'
    assert normalized['buildRequirements'] == {
        'lldbPython': False,
        'debuggerEntitlement': False,
        'entitlements': '',
    }

    generated = Path(tempfile.mkstemp(suffix='.swift')[1])
    try:
        subprocess.run([
            'python3', str(root / 'Tools/generate_game_binding.py'), game_id, str(generated)
        ], check=True)
        text = generated.read_text()
        assert 'typealias ActiveGameModule = ReferenceFixtureGameModule' in text
        assert 'expectedHostProtocolVersion: 5' in text
        assert 'expectedModuleProtocolVersion: 1' in text

        # The fixture consumes the exact same App/Core source graph. No
        # reference-game condition belongs in shared production sources.
        core = sorted((root / 'Sources/Core').rglob('*.swift'))
        sources = [root / 'Sources/App.swift'] + core + [
            frontend / 'ReferenceFixtureModule.swift',
            generated,
        ]
        if shutil.which('swiftc'):
            subprocess.run(['swiftc', '-frontend', '-parse', *map(str, sources)], check=True)
    finally:
        generated.unlink(missing_ok=True)

    generic = (
        (root / 'Sources/App.swift').read_text()
        + '\n'
        + '\n'.join(path.read_text() for path in (root / 'Sources/Core').rglob('*.swift'))
        + '\n'
        + (root / 'build.sh').read_text()
    )
    assert 'ReferenceFixture' not in generic
    assert 'reference_fixture' not in generic
finally:
    shutil.rmtree(backend_module, ignore_errors=True)
    shutil.rmtree(frontend, ignore_errors=True)

print('module_contract_round13_ok')
