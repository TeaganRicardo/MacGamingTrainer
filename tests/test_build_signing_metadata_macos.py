import plistlib
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'Tools'
sys.path.insert(0, str(TOOLS))
from clean_signing_metadata import CLEANUP_XATTRS, clean_signing_metadata

if sys.platform != 'darwin':
    print('SKIP build_signing_metadata: real macOS xattrs/codesign required')
    raise SystemExit(0)

with tempfile.TemporaryDirectory(prefix='mgt-signing-metadata-') as temporary:
    app = Path(temporary) / 'Metadata Test.app'
    contents = app / 'Contents'
    executable = contents / 'MacOS/metadata-test'
    executable.parent.mkdir(parents=True)
    executable.write_text('#!/bin/sh\nexit 0\n')
    executable.chmod(0o755)
    (contents / 'Info.plist').write_bytes(plistlib.dumps({
        'CFBundleIdentifier': 'com.example.metadata-test',
        'CFBundleName': 'Metadata Test',
        'CFBundleExecutable': 'metadata-test',
    }))
    resource = contents / 'Resources/data.txt'
    resource.parent.mkdir(parents=True)
    source = Path(temporary) / 'module-source/data.txt'
    source.parent.mkdir()
    source.write_text('temporary signing fixture\\n')

    attributes = {
        'com.apple.FinderInfo': 'F' * 32,
        'com.apple.ResourceFork': 'temporary resource fork',
    }
    for name, value in attributes.items():
        subprocess.run(['xattr', '-w', name, value, str(source)], check=True)

    # Provenance is allowed build provenance, not Finder attached data. Some
    # macOS versions reserve it to the system, so retain it if settable and
    # otherwise report that one distinction as unavailable on this host.
    try:
        subprocess.run(
            ['xattr', '-wx', 'com.apple.provenance', '0102', str(source)],
            check=True,
        )
        provenance_set = True
    except subprocess.CalledProcessError as error:
        provenance_set = False
        print(f'SKIP setting com.apple.provenance on this host: {error}')

    copied = Path(temporary) / 'staging/data.txt'
    copied.parent.mkdir()
    subprocess.run(['cp', '-R', str(source), str(copied)], check=True)
    resource.write_bytes(copied.read_bytes())
    for name in subprocess.check_output(['xattr', str(copied)], text=True).splitlines():
        value = subprocess.check_output(['xattr', '-px', name, str(copied)], text=True).split()
        subprocess.run(['xattr', '-wx', name, ''.join(value), str(resource)], check=True)

    clean_signing_metadata(app, Path(temporary))
    remaining = set(subprocess.check_output(['xattr', str(resource)], text=True).splitlines())
    assert not (set(attributes) & remaining), remaining
    assert set(attributes) <= set(subprocess.check_output(
        ['xattr', str(source)], text=True
    ).splitlines())
    assert 'com.apple.provenance' not in CLEANUP_XATTRS
    if provenance_set:
        assert subprocess.check_output(
            ['xattr', '-px', 'com.apple.provenance', str(resource)], text=True
        ).strip().split()[0:2] == ['01', '02']

    subprocess.run([
        'codesign', '--force', '--sign', '-', '--timestamp=none', str(app),
    ], check=True)
    subprocess.run([
        'codesign', '--verify', '--deep', '--strict', str(app),
    ], check=True)

print('build_signing_metadata_ok')
