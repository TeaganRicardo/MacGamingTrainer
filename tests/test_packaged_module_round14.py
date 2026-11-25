import json
import os
import shutil
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
fixture = root / 'ContractFixtures/reference_module'
sys.path.insert(0, str(root / 'Tools'))
from package_app import build_python_runtime_metadata, smoke_packaged_adapters, verify_python_runtime_metadata

runtime_source = json.loads((root / 'Tools/python_runtime.json').read_text())
architecture = next(iter(runtime_source['distributions']))
runtime_metadata = build_python_runtime_metadata(runtime_source, [architecture])
assert verify_python_runtime_metadata(runtime_source, runtime_metadata) == runtime_metadata
for field in ('schemaVersion', 'provider', 'release', 'version'):
    invalid = deepcopy(runtime_source)
    del invalid[field]
    try:
        build_python_runtime_metadata(invalid, [architecture])
    except ValueError:
        pass
    else:
        raise AssertionError(f'missing runtime {field} was accepted')
for field, value in (('target', ''), ('url', ''), ('sha256', 'invalid')):
    invalid = deepcopy(runtime_source)
    invalid['distributions'][architecture][field] = value
    copied_invalid = {**runtime_metadata, 'distributions': {architecture: invalid['distributions'][architecture]}}
    try:
        verify_python_runtime_metadata(invalid, copied_invalid)
    except ValueError:
        pass
    else:
        raise AssertionError(f'invalid matching runtime {field} was accepted')

with tempfile.TemporaryDirectory(prefix='mgt-packaged-module-') as temporary:
    package = Path(temporary) / 'MacGamingTrainer.app/Contents/Resources'
    backend = package / 'Backend'
    games = backend / 'games'
    reference = games / 'reference_fixture'

    reference.parent.mkdir(parents=True)

    shutil.copytree(root / 'Backend/core', backend / 'core')
    shutil.copy2(root / 'Backend/games/__init__.py', games / '__init__.py')
    shutil.copytree(fixture / 'backend', reference)

    # Repeated importable calls must validate each requested tree. The second
    # call cannot reuse the first call's registry/adapter module cache.
    empty_backend = Path(temporary) / 'empty-backend'
    empty_backend.mkdir()
    with patch.dict(os.environ, {'HOME': str(Path(temporary) / 'smoke-home')}):
        smoke_packaged_adapters(backend, False, ['reference_fixture'])
        try:
            smoke_packaged_adapters(empty_backend, False, ['reference_fixture'])
        except ValueError as error:
            assert 'core' in str(error)
        else:
            raise AssertionError('empty staged backend reused the preceding adapter imports')

    proc = subprocess.Popen(
        [sys.executable, '-u', str(backend / 'core/server.py'), '--game', 'reference_fixture'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, 'HOME': str(package.parent.parent.parent / 'home')},
    )
    try:
        assert proc.stdin and proc.stdout

        def request(request_id, command, params=None):
            proc.stdin.write(json.dumps({
                'id': request_id,
                'command': command,
                'params': params or {},
            }) + '\n')
            proc.stdin.flush()
            return json.loads(proc.stdout.readline())

        hello = request('hello', 'hello')
        assert hello['ok'] is True
        assert hello['gameID'] == 'reference_fixture'
        assert hello['moduleProtocolVersion'] == 1
        assert hello['result']['game']['displayName'] == 'Reference Fixture'
        assert 'saveManagement' not in hello['result']['game']

        unsupported_save = request('save-list', 'core.save.list')
        assert unsupported_save['ok'] is False
        assert unsupported_save['error']['code'] == 'save_unsupported'

        connect = request('connect', 'connect')
        assert connect['ok'] is True
        assert connect['result'] == {'connected': True, 'enabled': False}

        enabled = request('enable', 'set_enabled', {'value': True})
        assert enabled['ok'] is True
        assert enabled['result'] == {'connected': True, 'enabled': True}

        disabled = request('disable', 'disable_all')
        assert disabled['ok'] is True
        assert disabled['result'] == {'connected': True, 'enabled': False}

        profiles = request('profiles-list', 'list_profiles')
        assert profiles['ok'] is True
        assert profiles['result'] == {'profiles': []}

        saved = request('profiles-save', 'save_profile', {
            'name': 'default',
            'shortcuts': {'_layoutVersion': 1, 'toggleFeature': {'keyCode': 18, 'modifiers': 2304, 'keyLabel': '1'}},
        })
        assert saved['ok'] is True
        assert [row['name'] for row in saved['result']['profiles']] == ['default']

        assert request('enable-before-load', 'set_enabled', {'value': True})['result']['enabled'] is True
        loaded = request('profiles-load', 'load_profile', {'name': 'default'})
        assert loaded['ok'] is True
        assert loaded['result']['enabled'] is False
        assert loaded['result']['shortcuts'] == {
            '_layoutVersion': 1,
            'toggleFeature': {'keyCode': 18, 'modifiers': 2304, 'keyLabel': '1'},
        }

        diagnostics = request('diag', 'diagnostics')
        assert diagnostics['ok'] is True
        assert [check['id'] for check in diagnostics['result']['diagnostics']['checks']] == [
            'backend_session',
            'profile_store',
        ]
        assert diagnostics['result']['diagnostics']['checks'][1]['detailArguments'] == ['1']

        deleted = request('profiles-delete', 'delete_profile', {'name': 'default'})
        assert deleted['ok'] is True
        assert deleted['result'] == {'profiles': []}

        status = request('status', 'status')
        assert status['ok'] is True
        assert status['result'] == {'connected': True, 'enabled': False}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

with tempfile.TemporaryDirectory(prefix='mgt-packaged-debugger-') as temporary:
    backend = Path(temporary) / 'Backend'
    backend.mkdir()
    source = (root / 'build.sh').read_text()
    composition = source.split('cp -R "$ROOT/Backend/core"', 1)[1].split('\n"$PYTHON" "$PACKAGE_APP" package-app-resources', 1)[0]
    subprocess.run(['bash', '-eu', '-c', 'GAME_IDS=(hades hades2)\ncp -R "$ROOT/Backend/core"' + composition],
                   env={**os.environ, 'ROOT': str(root), 'BACKEND': str(backend), 'REQUIRES_LLDB': '1'}, check=True)
    imported = subprocess.run([sys.executable, '-I', '-c', '''
import pathlib,sys
backend=pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0,str(backend))
import debugger.lldb_time_warp as driver
import games.hades.time_warp_worker
import games.hades2.lldb_worker
assert pathlib.Path(driver.__file__).resolve()==backend/'debugger/lldb_time_warp.py'
assert 'lldb' not in sys.modules, 'Importing a packaged worker should not attach or load LLDB'
''', str(backend)], cwd=temporary, text=True, capture_output=True)
    assert imported.returncode == 0, imported.stdout + '\n' + imported.stderr

print('packaged_module_round14_and_debugger_imports_ok')
