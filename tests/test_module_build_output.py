import json
import plistlib
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / '.github/workflows/module-build-matrix.yml').read_text()
MANIFEST_PATH = ROOT / 'Backend/games/hades2/module.json'
MANIFEST = json.loads(MANIFEST_PATH.read_text())
VERIFY = ROOT / 'Tools/verify_module_build.py'

# A stale app alphabetically before the selected target must not win discovery.
assert 'Tools/verify_module_build.py' in WORKFLOW
assert 'find dist' not in WORKFLOW

with tempfile.TemporaryDirectory(prefix='mgt-dirty-dist-') as temporary:
    dist = Path(temporary)
    (dist / 'A-Stale.app').mkdir()
    app = dist / f"{MANIFEST['app']['displayName']}.app"
    resources = app / 'Contents/Resources'
    games = resources / 'Backend/games/hades2'
    games.mkdir(parents=True)
    (resources / 'Backend/games/__init__.py').write_text('')
    (games / 'module.json').write_text(MANIFEST_PATH.read_text())
    (resources / 'ACTIVE_GAME_ID').write_text('hades2\n')
    info = {
        'CFBundleIdentifier': MANIFEST['app']['bundleIdentifier'],
        'CFBundleName': MANIFEST['app']['displayName'],
    }
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))

    command = [sys.executable, str(VERIFY), 'hades2', '--dist-dir', str(dist), '--print-app']
    selected = subprocess.check_output(command, text=True).strip()
    assert selected == str(app.resolve()), selected

    # A stale app alone is not an acceptable fallback when the target is absent.
    with tempfile.TemporaryDirectory(prefix='mgt-stale-only-') as stale_only:
        (Path(stale_only) / 'A-Stale.app').mkdir()
        missing = subprocess.run(
            [sys.executable, str(VERIFY), 'hades2', '--dist-dir', stale_only],
            text=True,
            capture_output=True,
        )
        assert missing.returncode != 0
        assert 'Mac Gaming Trainer.app' in missing.stderr

print('module_build_output_ok')
