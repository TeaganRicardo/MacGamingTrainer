import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / 'Tools'
sys.path.insert(0, str(TOOLS))
from clean_signing_metadata import clean_signing_metadata

with tempfile.TemporaryDirectory(prefix='mgt-signing-scope-') as temporary:
    root = Path(temporary)
    stage = root / 'staging'
    stage.mkdir()
    app = stage / 'Selected.app'
    app.mkdir()
    outside = root / 'Outside.app'
    outside.mkdir()
    nested = stage / 'nested' / 'Nested.app'
    nested.parent.mkdir()
    nested.mkdir()
    source = root / 'source.txt'
    source.write_text('do not modify this source')
    linked_app = stage / 'Linked.app'
    linked_app.symlink_to(outside, target_is_directory=True)
    linked_stage = root / 'linked-staging'
    linked_stage.symlink_to(stage, target_is_directory=True)

    for target, allowed_root in (
        (source, root),
        (outside, stage),
        (nested, stage),
        (linked_app, stage),
        (linked_stage / app.name, linked_stage),
    ):
        try:
            clean_signing_metadata(target, allowed_root)
        except ValueError:
            pass
        else:
            raise AssertionError(f'cleanup accepted a non-staged app: {target}')
    assert source.read_text() == 'do not modify this source'

# Execute build.sh's own staging/output paragraph: the App is staged under the
# private build directory, published to MGT_BUILD_OUTPUT_DIR (default
# ROOT/dist), and a symlinked output directory is refused before any work.
ROOT = TOOLS.parent
build = (ROOT / 'build.sh').read_text(encoding='utf-8')
layout = 'DIST=' + build.split('\nDIST=', 1)[1].split('\n\n', 1)[0]
APP_NAME = 'Fixture Trainer'


def resolve_layout(root, output=None):
    env = {key: value for key, value in os.environ.items() if key != 'MGT_BUILD_OUTPUT_DIR'}
    env.update(ROOT=str(root), GENERATED_DIR=str(root / 'generated'), APP_NAME=APP_NAME)
    if output is not None:
        env['MGT_BUILD_OUTPUT_DIR'] = str(output)
    return subprocess.run(['bash', '-c', 'set -eu\n' + layout + '\nprintf "%s\\n" "$APP" "$PUBLISH_DIST"'],
                          env=env, capture_output=True, text=True)


def preserved_outside(root):
    outside = root / 'outside'
    sentinel = outside / 'Existing.app/keep.txt'
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text('preserved')
    return outside, sentinel


with tempfile.TemporaryDirectory(prefix='mgt-build-layout-') as temporary:
    root = Path(temporary)
    default = resolve_layout(root)
    assert default.returncode == 0, default.stderr
    assert default.stdout.splitlines() == [str(root / 'generated/dist' / f'{APP_NAME}.app'), str(root / 'dist')]
    chosen = resolve_layout(root, root / 'local-output')
    assert chosen.returncode == 0 and chosen.stdout.splitlines()[1] == str(root / 'local-output'), chosen
    outside, sentinel = preserved_outside(root)
    link = root / 'linked-output'
    link.symlink_to(outside, target_is_directory=True)
    refused = resolve_layout(root, link)
    assert refused.returncode != 0 and not refused.stdout, refused
    assert sentinel.read_text() == 'preserved'

# Execute build.sh from the Time Warp helper through publication with recording
# stand-ins for clang, lipo, codesign and the bundled Python. codesign rejects
# the FinderInfo/ResourceFork that file-provider checkouts attach, so every
# signature must follow cleanup of the staged App (scoped to its staging root)
# with no bundle change in between, and only the signed staged App is published.
RECORDER = f'#!{sys.executable}\n' + r"""
import json, os, pathlib, sys
tool, args = pathlib.Path(sys.argv[0]).name, sys.argv[1:]
with open(os.environ['MGT_TOOL_LOG'], 'a', encoding='utf-8') as log:
    log.write(json.dumps([tool, *args]) + '\n')
if tool == 'xcrun' and args[:1] == ['--find']:
    print(pathlib.Path(sys.argv[0]).parent / args[1])
elif tool in ('clang', 'lipo'):
    pathlib.Path(args[args.index('-o' if tool == 'clang' else '-output') + 1]).write_bytes(b'fixture')
elif tool == 'file':
    print(f'{args[0]}: Mach-O 64-bit executable arm64')
elif tool == 'codesign' and '-d' in args:
    print('com.apple.security.cs.debugger')
"""
CLEAN, PUBLISH, VERIFY = (str(TOOLS / name) for name in (
    'clean_signing_metadata.py', 'publish_module_build.py', 'verify_module_build.py'))
packaging_tail = build[build.index('\nTIME_WARP_ROOT='):]


def run_packaging_tail(root, replace_output_with_symlink=None):
    fakebin = root / 'bin'
    fakebin.mkdir()
    for name in ('xcrun', 'clang', 'lipo', 'codesign', 'plutil', 'file', 'python'):
        (fakebin / name).write_text(RECORDER)
        (fakebin / name).chmod(0o755)
    generated = root / 'generated'
    generated.mkdir()
    log = root / 'tools.jsonl'
    env = {
        **os.environ, 'PATH': f"{fakebin}{os.pathsep}{os.environ['PATH']}", 'MGT_TOOL_LOG': str(log),
        'ROOT': str(ROOT), 'GENERATED_DIR': str(generated), 'MGT_BUILD_OUTPUT_DIR': str(root / 'output'),
        'APP_NAME': APP_NAME, 'EXECUTABLE': 'FixtureTrainer', 'APP_BUNDLE_ID': 'com.example.fixture',
        'ACTIVE_GAME_ID': 'all', 'BUILD_SELECTION': 'all', 'MIN_MACOS': '14.0', 'SDK': '/synthetic/sdk',
        'CLANG': str(fakebin / 'clang'), 'PYTHON': str(fakebin / 'python'),
        'CLEAN_SIGNING_METADATA': CLEAN, 'MODULE_VALIDATOR': str(TOOLS / 'validate_game_module.py'),
        'NORMALIZED_MANIFEST': str(generated / 'module.normalized.json'),
        'ASSET_INFO_PLIST': str(generated / 'asset-catalog-info.plist'),
        'ENTITLEMENTS_REL': 'fixture.entitlements', 'REQUIRES_DEBUGGER_ENTITLEMENT': '1',
        'MGT_REPLACE_OUTPUT': str(replace_output_with_symlink or ''),
    }
    script = '\n'.join((
        'set -euo pipefail', 'record_build_timing() { :; }', 'ARCHITECTURES=(arm64)', 'GAME_IDS=(fixture)',
        layout, 'PYTHON_RESOURCES="$CONTENTS/Resources/Python"',
        'mkdir -p "$CONTENTS/MacOS" "$BACKEND" "$PYTHON_RESOURCES/arm64/bin"',
        'touch "$CONTENTS/MacOS/$EXECUTABLE" "$CONTENTS/Info.plist" "$PYTHON_RESOURCES/arm64/bin/python3"',
        'if [[ -n "$MGT_REPLACE_OUTPUT" ]]; then ln -s "$MGT_REPLACE_OUTPUT" "$PUBLISH_DIST"; fi',
        packaging_tail,
    ))
    result = subprocess.run(['bash', '-c', script], env=env, capture_output=True, text=True)
    events = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
    dist = generated / 'dist'
    return result, events, str(dist), str(dist / f'{APP_NAME}.app'), str(root / 'output')


with tempfile.TemporaryDirectory(prefix='mgt-build-signing-order-') as temporary:
    result, events, dist, app, output = run_packaging_tail(Path(temporary))
    assert result.returncode == 0, result.stdout + '\n' + result.stderr
    cleanups = [index for index, event in enumerate(events) if event == ['python', CLEAN, app, '--staging-root', dist]]
    signatures = [index for index, event in enumerate(events) if event[:2] == ['codesign', '--force']]
    bundle_changes = [
        index for index, event in enumerate(events)
        if event[0] not in ('codesign', 'plutil', 'file') and not {CLEAN, PUBLISH, VERIFY} & set(event)
        and any(argument.startswith(app) for argument in event[1:])
    ]
    assert len(signatures) >= 3 and events[signatures[-1]][-1] == app, events
    for signature in signatures:
        cleaned = [index for index in cleanups if index < signature]
        assert cleaned, f'signed before signing-metadata cleanup: {events[signature]}'
        assert not [index for index in bundle_changes if cleaned[-1] < index < signature], (
            f'bundle changed between cleanup and signing: {events[signature]}')
    published = [event for event in events if PUBLISH in event]
    assert published == [['python', PUBLISH, app, output, APP_NAME]], published
    verified = events.index(['codesign', '--verify', '--deep', '--strict', app])
    assert signatures[-1] < verified < events.index(published[0]), events

with tempfile.TemporaryDirectory(prefix='mgt-build-publish-symlink-') as temporary:
    root = Path(temporary)
    outside, sentinel = preserved_outside(root)
    result, events, *_ = run_packaging_tail(root, replace_output_with_symlink=outside)
    assert result.returncode != 0, 'a symlinked output directory reached publication'
    assert not [event for event in events if PUBLISH in event], events
    assert sentinel.read_text() == 'preserved'

print('build_signing_scope_ok')
