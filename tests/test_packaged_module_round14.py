from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
package = Path(tempfile.mkdtemp(prefix='mgt-packaged-module-')) / 'MacGamingTrainer.app/Contents/Resources'
backend = package / 'Backend'
games = backend / 'games'
other = games / 'other'
other.mkdir(parents=True)

# Packaged layout mirrors build.sh: generic core + games/__init__ + one module.
shutil.copytree(root/'Backend/core', backend/'core')
shutil.copy2(root/'Backend/games/__init__.py', games/'__init__.py')
(other/'__init__.py').write_text('', encoding='utf-8')
(other/'adapter.py').write_text('''
from core.adapter import GameAdapter
class OtherAdapter(GameAdapter):
    def __init__(self, context):
        super().__init__(context)
        self.state = {"connected": False}
    def dispatch(self, command, params, request_id):
        if command == "ping":
            return {"pong": True, "echo": params}
        raise ValueError("unknown fake command")
    def close(self):
        pass
''', encoding='utf-8')
# Sources/Other intentionally does not exist in the packaged app.
(other/'module.json').write_text(json.dumps({
    'schemaVersion': 1,
    'id': 'other',
    'displayName': 'Other Game',
    'protocolVersion': 23,
    'backend': {'adapter': 'games.other.adapter:OtherAdapter'},
        'targetApplication': {'processName':'Other Game','bundleIdentifier':'com.example.other'},
    'frontend': {
        'sourceDirectory': 'Sources/Other',
        'moduleType': 'OtherGameModule',
        'architectures': ['x86_64'],
        'minimumMacOS': '14.0',
    },
    'buildRequirements': {'lldbPython': False, 'debuggerEntitlement': False},
}), encoding='utf-8')

proc = subprocess.Popen(
    [sys.executable, '-u', str(backend/'core/server.py'), '--game', 'other'],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    env={**os.environ, 'HOME': str(package.parent.parent.parent / 'home')},
)
try:
    assert proc.stdin and proc.stdout
    proc.stdin.write(json.dumps({'id':'hello','command':'hello','params':{}}) + '\n')
    proc.stdin.flush()
    hello = json.loads(proc.stdout.readline())
    assert hello['ok'] is True
    assert hello['gameID'] == 'other'
    assert hello['moduleProtocolVersion'] == 23
    assert hello['result']['game']['displayName'] == 'Other Game'

    proc.stdin.write(json.dumps({'id':'ping','command':'ping','params':{'x':7}}) + '\n')
    proc.stdin.flush()
    ping = json.loads(proc.stdout.readline())
    assert ping['ok'] is True
    assert ping['result'] == {'pong': True, 'echo': {'x': 7}}
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill(); proc.wait(timeout=5)

print('packaged_module_round14_ok')
