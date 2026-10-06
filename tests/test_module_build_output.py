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
PYTHON_RUNTIME_SOURCE = json.loads((ROOT / 'Tools/python_runtime.json').read_text())

def install_runtime_fixture(resources, architectures=('arm64',)):
    runtime = resources / 'Python'
    runtime.mkdir(parents=True, exist_ok=True)
    metadata = {
        'schemaVersion': PYTHON_RUNTIME_SOURCE['schemaVersion'],
        'provider': PYTHON_RUNTIME_SOURCE['provider'],
        'release': PYTHON_RUNTIME_SOURCE['release'],
        'version': PYTHON_RUNTIME_SOURCE['version'],
        'architectures': list(architectures),
        'distributions': {
            arch: PYTHON_RUNTIME_SOURCE['distributions'][arch]
            for arch in architectures
        },
    }
    (runtime / 'runtime.json').write_text(json.dumps(metadata))
    for arch in architectures:
        executable = runtime / arch / 'bin/python3'
        executable.parent.mkdir(parents=True)
        executable.write_text('#!/bin/sh\nexit 0\n')
        executable.chmod(0o755)


# A stale app alphabetically before the selected target must not win discovery.
assert 'Tools/verify_module_build.py' in WORKFLOW
assert 'find dist' not in WORKFLOW
BUILD2 = (ROOT / '.github/workflows/build2-macos.yml').read_text()
assert 'dist/Mac Gaming Trainer.app' not in BUILD2
assert 'Tools/verify_module_build.py hades2 --print-app' in BUILD2
assert 'Tools/write_build_provenance.py' in WORKFLOW
assert 'actions/upload-artifact@v4' in WORKFLOW

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
        'CFBundleDisplayName': MANIFEST['app']['displayName'],
        'CFBundleExecutable': plistlib.loads((ROOT / 'Info.plist').read_bytes())['CFBundleExecutable'],
    }
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
    binary = app / 'Contents/MacOS' / info['CFBundleExecutable']
    binary.parent.mkdir()
    binary.write_bytes(b'temporary executable fixture')
    install_runtime_fixture(resources)

    # The package verifier owns the bundled-runtime contract. Missing runtime
    # metadata or interpreter must fail before app selection can be accepted.
    runtime_manifest = resources / 'Python/runtime.json'
    runtime_manifest.unlink()
    missing_runtime = subprocess.run(
        [sys.executable, str(VERIFY), 'hades2', '--dist-dir', str(dist)],
        text=True,
        capture_output=True,
    )
    assert missing_runtime.returncode != 0
    assert 'Python runtime' in missing_runtime.stderr
    install_runtime_fixture(resources)

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
        assert f"{MANIFEST['app']['displayName']}.app" in missing.stderr

print('module_build_output_ok')
