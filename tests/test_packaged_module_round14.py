import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
fixture = root / 'ContractFixtures/reference_module'
with tempfile.TemporaryDirectory(prefix='mgt-packaged-module-') as temporary:
    package = Path(temporary) / 'MacGamingTrainer.app/Contents/Resources'
    backend = package / 'Backend'
    games = backend / 'games'
    reference = games / 'reference_fixture'

    reference.parent.mkdir(parents=True)

    shutil.copytree(root / 'Backend/core', backend / 'core')
    shutil.copy2(root / 'Backend/games/__init__.py', games / '__init__.py')
    shutil.copytree(fixture / 'backend', reference)

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
    composition = source.split('cp -R "$ROOT/Backend/core"', 1)[1].split('\n"$PYTHON" - "$NORMALIZED_MANIFEST"', 1)[0]
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
