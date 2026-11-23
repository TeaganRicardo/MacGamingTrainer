import json
import os
import plistlib
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
# The bundled Python runs build.sh's inline (stdin) blocks for real, so their
# effect on the staged App is observable; tool scripts are only recorded.
RECORDER = f'#!{sys.executable}\n' + r"""
import json, os, pathlib, sys
tool, args = pathlib.Path(sys.argv[0]).name, sys.argv[1:]
with open(os.environ['MGT_TOOL_LOG'], 'a', encoding='utf-8') as log:
    log.write(json.dumps([tool, *args]) + '\n')
if tool == 'python' and args[:1] == ['-']:
    sys.argv = args
    exec(compile(sys.stdin.read(), '<build.sh stdin>', 'exec'), {'__name__': '__main__'})
elif tool == 'python' and args and pathlib.Path(args[0]).name == 'validate_game_module.py' and '--json' in args:
    print(json.dumps({'nativeLibraries': []}))
elif tool == 'python' and args and pathlib.Path(args[0]).name in ('build_module_native.py', 'package_app.py'):
    import runpy
    sys.executable = sys.argv[0]
    sys.argv = args
    runpy.run_path(args[0], run_name='__main__')
elif tool == 'xcrun' and args[:1] == ['--find']:
    print(pathlib.Path(sys.argv[0]).parent / args[1])
elif tool == 'xcrun' and args[:1] == ['lipo']:
    pathlib.Path(args[args.index('-output') + 1]).write_bytes(b'fixture')
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
# Kept: the two markers are the seam that executes build.sh's own staging and
# packaging paragraphs until WP5.4 moves them into an importable Python owner.
# The executed slices must be the only staging layout and hold every signing
# command; a codesign moved above the tail would escape the cleanup-order check.
assert build.count('\nDIST=') == 1 and build.count('\nTIME_WARP_ROOT=') == 1, 'build.sh slice markers must be unique'
assert not [line for line in build[:build.index('\nTIME_WARP_ROOT=')].splitlines()
            if line.lstrip().startswith('codesign ')], 'build.sh signs outside the executed packaging tail'


def run_packaging_tail(root, replace_output_with_symlink=None, process_time_warp=True):
    fakebin = root / 'bin'
    fakebin.mkdir()
    for name in ('xcrun', 'clang', 'lipo', 'codesign', 'plutil', 'file', 'python'):
        (fakebin / name).write_text(RECORDER)
        (fakebin / name).chmod(0o755)
    generated = root / 'generated'
    generated.mkdir()
    (generated / 'module.normalized.json').write_text(json.dumps({
        'moduleIDs': ['fixture'],
        'buildRequirements': {'processTimeWarp': process_time_warp, 'entitlements': []},
    }))
    # actool's partial Info.plist is the accent owner; a non-default name proves
    # the packaged declaration is copied from it rather than restated.
    (generated / 'asset-catalog-info.plist').write_bytes(plistlib.dumps({'NSAccentColorName': 'FixtureAccent'}))
    staged_info = generated / 'dist' / f'{APP_NAME}.app/Contents/Info.plist'
    staged_info.parent.mkdir(parents=True)
    staged_info.write_bytes(plistlib.dumps({'CFBundleExecutable': 'FixtureTrainer'}))
    log = root / 'tools.jsonl'
    env = {
        **os.environ, 'PATH': f"{fakebin}{os.pathsep}{os.environ['PATH']}", 'MGT_TOOL_LOG': str(log),
        'ROOT': str(ROOT), 'GENERATED_DIR': str(generated), 'MGT_BUILD_OUTPUT_DIR': str(root / 'output'),
        'APP_NAME': APP_NAME, 'EXECUTABLE': 'FixtureTrainer', 'APP_BUNDLE_ID': 'com.example.fixture',
        'ACTIVE_GAME_ID': 'all', 'BUILD_SELECTION': 'all', 'MIN_MACOS': '14.0', 'SDK': '/synthetic/sdk',
        'CLANG': str(fakebin / 'clang'), 'PYTHON': str(fakebin / 'python'),
        'CLEAN_SIGNING_METADATA': CLEAN, 'PACKAGE_APP': str(TOOLS / 'package_app.py'),
        'MODULE_VALIDATOR': str(TOOLS / 'validate_game_module.py'),
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

    # The Process Time Warp helper is built through build_module_native.py from
    # its production source and the bundled fishhook for the declared Host
    # architectures only when opted in (no forced x86_64 slice), with warnings
    # visible, ad-hoc signed after metadata cleanup and shipped with the licence.
    native = Path(app) / 'Contents/Resources/Backend/core/native'
    helper = str(native / 'libMGTTimeWarp.dylib')
    time_warp = ROOT / 'Native/ProcessTimeWarp'
    compiles = {event[event.index('-arch') + 1]: event for event in events if event[0] == 'clang'}
    assert set(compiles) == {'arm64'}, compiles
    for arch, compile_args in compiles.items():
        flags = set(compile_args)
        assert {'-dynamiclib', '-Wall', '-Wextra'} <= flags and '-Werror' not in flags, compile_args
        assert compile_args[compile_args.index('-isysroot') + 1] == '/synthetic/sdk', compile_args
        assert compile_args[compile_args.index('-framework') + 1] == 'QuartzCore', compile_args
        assert {str(time_warp / 'ProcessTimeWarp.c'), str(time_warp / 'vendor/fishhook/fishhook.c')} <= flags
    assert Path(helper).is_file(), helper
    assert ['codesign', '--force', '--sign', '-', '--timestamp=none', helper] in events, events
    assert (native / 'LICENSE.fishhook').read_bytes() == (time_warp / 'vendor/fishhook/LICENSE').read_bytes()
    # AppKit native chrome resolves the product accent from the packaged Info.plist.
    packaged_info = plistlib.loads((Path(app) / 'Contents/Info.plist').read_bytes())
    assert packaged_info['NSAccentColorName'] == 'FixtureAccent', packaged_info

with tempfile.TemporaryDirectory(prefix='mgt-build-no-time-warp-') as temporary:
    result, events, _dist, app, _output = run_packaging_tail(Path(temporary), process_time_warp=False)
    assert result.returncode == 0, result.stdout + '\n' + result.stderr
    assert not [event for event in events if event[0] == 'clang'], events
    assert not (Path(app) / 'Contents/Resources/Backend/core/native').exists()

with tempfile.TemporaryDirectory(prefix='mgt-build-publish-symlink-') as temporary:
    root = Path(temporary)
    outside, sentinel = preserved_outside(root)
    result, events, *_ = run_packaging_tail(root, replace_output_with_symlink=outside)
    assert result.returncode != 0, 'a symlinked output directory reached publication'
    assert not [event for event in events if PUBLISH in event], events
    assert sentinel.read_text() == 'preserved'

# Execute build.sh's own Host localization packaging & byte-verification paragraph.
loc_start = '\nfor language in en zh-CN; do\n'
loc_end = '\n# The product purple'
# Kept (build slice): these markers select build.sh's localization paragraph until WP5.4 moves packaging into Python.
assert build.count(loc_start) == 1 and build.count(loc_end) == 1, 'build.sh localization slice markers must be unique'
loc_packaging = build[build.index(loc_start) + 1:build.index(loc_end)]


def run_localization_packaging(root, corrupt_cp=False):
    fakebin = root / 'bin'
    fakebin.mkdir()
    if corrupt_cp:
        cp_bin = fakebin / 'cp'
        cp_bin.write_text('#!/bin/sh\necho corrupted > "$2"\n', encoding='utf-8')
        cp_bin.chmod(0o755)
    loc_root = root / 'Localization'
    for lang in ('en', 'zh-CN'):
        d = loc_root / f'{lang}.lproj'
        d.mkdir(parents=True)
        (d / 'Host.strings').write_text(f'"host.ok" = "{lang}";\n', encoding='utf-8')
    contents = root / 'Contents'
    (contents / 'Resources').mkdir(parents=True)
    env = {
        **os.environ,
        'PATH': f'{fakebin}{os.pathsep}{os.environ["PATH"]}',
        'LOCALIZATION_ROOT': str(loc_root),
        'CONTENTS': str(contents),
        'PACKAGE_APP': str(TOOLS / 'package_app.py'),
        'PYTHON': sys.executable,
    }
    return subprocess.run(['bash', '-c', 'set -euo pipefail\n' + loc_packaging],
                          env=env, capture_output=True, text=True), loc_root, contents


with tempfile.TemporaryDirectory(prefix='mgt-build-loc-ok-') as temporary:
    root = Path(temporary)
    res, loc_root, contents = run_localization_packaging(root)
    assert res.returncode == 0, res.stdout + '\n' + res.stderr
    for lang in ('en', 'zh-CN'):
        src = loc_root / f'{lang}.lproj/Host.strings'
        dst = contents / 'Resources' / f'{lang}.lproj/Host.strings'
        assert dst.is_file() and dst.read_bytes() == src.read_bytes(), dst

with tempfile.TemporaryDirectory(prefix='mgt-build-loc-missing-') as temporary:
    root = Path(temporary)
    loc_root = root / 'Localization'
    (loc_root / 'en.lproj').mkdir(parents=True)
    (loc_root / 'en.lproj/Host.strings').write_text('"host.ok" = "en";\n', encoding='utf-8')
    contents = root / 'Contents'
    (contents / 'Resources').mkdir(parents=True)
    res = subprocess.run(
        ['bash', '-c', 'set -euo pipefail\n' + loc_packaging],
        env={
            **os.environ,
            'LOCALIZATION_ROOT': str(loc_root),
            'CONTENTS': str(contents),
            'PACKAGE_APP': str(TOOLS / 'package_app.py'),
            'PYTHON': sys.executable,
        },
        capture_output=True, text=True,
    )
    assert res.returncode != 0 and 'Missing Host localization table' in res.stderr, res.stderr

with tempfile.TemporaryDirectory(prefix='mgt-build-loc-drift-') as temporary:
    res, *_ = run_localization_packaging(Path(temporary), corrupt_cp=True)
    assert res.returncode != 0 and 'Host localization package mismatch' in res.stderr, res.stderr

# Execute build.sh's own asset-catalog compilation & NSAccentColorName check paragraph.
asset_start = '\nASSET_CATALOG='
asset_end = '\nrecord_build_timing "package-runtime"'
# Kept (build slice): these markers select build.sh's asset-catalog paragraph until WP5.4 moves packaging into Python.
assert build.count(asset_start) == 1 and build.count(asset_end) == 1, 'build.sh asset-catalog slice markers must be unique'
asset_packaging = build[build.index(asset_start) + 1:build.index(asset_end)]

ACTOOL_FAKE = f'#!{sys.executable}\n' + r"""
import json, os, plistlib, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ['MGT_ACTOOL_LOG'], 'a', encoding='utf-8') as log:
    log.write(json.dumps(args) + '\n')
compile_dir = Path(args[args.index('--compile') + 1])
plist_path = Path(args[args.index('--output-partial-info-plist') + 1])
if not os.environ.get('MGT_OMIT_CAR'):
    (compile_dir / 'Assets.car').write_bytes(b'fixture-car')
accent = args[args.index('--accent-color') + 1] if '--accent-color' in args else None
payload = {} if os.environ.get('MGT_OMIT_ACCENT') else ({'NSAccentColorName': accent} if accent else {})
plist_path.write_bytes(plistlib.dumps(payload))
"""

PLUTIL_FAKE = f'#!{sys.executable}\n' + r"""
import plistlib, sys
assert sys.argv[1] == '-extract' and sys.argv[3] == 'raw' and sys.argv[4] == '-o' and sys.argv[5] == '-', sys.argv
key, path = sys.argv[2], sys.argv[6]
data = plistlib.loads(open(path, 'rb').read())
if key not in data:
    raise SystemExit(1)
print(data[key])
"""

XCRUN_ASSET_FAKE = f'#!{sys.executable}\n' + r"""
import pathlib, sys
assert sys.argv[1:3] == ['--find', 'actool'], sys.argv
print(pathlib.Path(sys.argv[0]).parent / 'actool')
"""


def run_asset_catalog_packaging(root, create_colorset=True, extra_env=None):
    fakebin = root / 'bin'
    fakebin.mkdir()
    for name, body in (('xcrun', XCRUN_ASSET_FAKE), ('actool', ACTOOL_FAKE), ('plutil', PLUTIL_FAKE)):
        p = fakebin / name
        p.write_text(body, encoding='utf-8')
        p.chmod(0o755)
    project_root = root / 'project'
    if create_colorset:
        colorset = project_root / 'Resources/Assets.xcassets/AccentColor.colorset'
        colorset.mkdir(parents=True)
        (colorset / 'Contents.json').write_text('{"colors":[]}\n', encoding='utf-8')
    generated = root / 'generated'
    generated.mkdir()
    contents = root / 'Contents'
    (contents / 'Resources').mkdir(parents=True)
    log = root / 'actool.jsonl'
    env = {
        **os.environ,
        'PATH': f'{fakebin}{os.pathsep}{os.environ["PATH"]}',
        'MGT_ACTOOL_LOG': str(log),
        'ROOT': str(project_root),
        'GENERATED_DIR': str(generated),
        'CONTENTS': str(contents),
        'MIN_MACOS': '14.0',
    }
    if extra_env:
        env.update(extra_env)
    res = subprocess.run(['bash', '-c', 'set -euo pipefail\n' + asset_packaging],
                         env=env, capture_output=True, text=True)
    calls = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()] if log.exists() else []
    return res, calls, generated, contents


with tempfile.TemporaryDirectory(prefix='mgt-build-asset-ok-') as temporary:
    res, calls, generated, contents = run_asset_catalog_packaging(Path(temporary))
    assert res.returncode == 0, res.stdout + '\n' + res.stderr
    assert len(calls) == 1, calls
    argv = calls[0]
    assert argv[argv.index('--accent-color') + 1] == 'AccentColor', argv
    assert argv[argv.index('--platform') + 1] == 'macosx', argv
    assert argv[argv.index('--minimum-deployment-target') + 1] == '14.0', argv
    assert argv[argv.index('--compile') + 1] == str(contents / 'Resources'), argv
    assert argv[argv.index('--output-partial-info-plist') + 1] == str(generated / 'asset-catalog-info.plist'), argv
    assert (contents / 'Resources/Assets.car').is_file()

with tempfile.TemporaryDirectory(prefix='mgt-build-asset-missing-colorset-') as temporary:
    res, calls, *_ = run_asset_catalog_packaging(Path(temporary), create_colorset=False)
    assert res.returncode != 0 and 'Missing application accent color' in res.stderr and not calls, res.stderr

with tempfile.TemporaryDirectory(prefix='mgt-build-asset-missing-car-') as temporary:
    res, *_ = run_asset_catalog_packaging(Path(temporary), extra_env={'MGT_OMIT_CAR': '1'})
    assert res.returncode != 0 and 'produced no Assets.car' in res.stderr, res.stderr

with tempfile.TemporaryDirectory(prefix='mgt-build-asset-missing-accent-') as temporary:
    res, *_ = run_asset_catalog_packaging(Path(temporary), extra_env={'MGT_OMIT_ACCENT': '1'})
    assert res.returncode != 0 and 'did not declare the application accent color' in res.stderr, res.stderr

# WP5.4: build.sh contains no inline Python heredoc blocks; Tools/package_app.py
# owns the importable packaging helpers and the shared runtime.json schema.
import package_app  # noqa: E402

assert "<<'PY'" not in build and '<<"PY"' not in build and '<<PY' not in build

with tempfile.TemporaryDirectory(prefix='mgt-package-app-unit-') as temporary:
    root = Path(temporary)
    manifest_path = root / 'normalized.json'
    manifest_path.write_text(json.dumps({
        'id': 'all',
        'moduleIDs': ['hades2', 'hades'],
        'buildRequirements': {
            'lldbPython': True,
            'processTimeWarp': False,
            'entitlements': ['e1.plist', 'e2.plist'],
        },
        'appResources': [{'source': 'res/item.json', 'destination': 'Modules/hades/item.json'}],
    }), encoding='utf-8')
    assert package_app.manifest_field(manifest_path, 'moduleIDs') == 'hades2 hades'
    assert package_app.manifest_field(manifest_path, 'buildRequirements.lldbPython') == '1'
    assert package_app.manifest_field(manifest_path, 'buildRequirements.processTimeWarp') == '0'
    assert package_app.manifest_field(manifest_path, 'missing.field') == ''

    runtime_src = json.loads((ROOT / 'Tools/python_runtime.json').read_text(encoding='utf-8'))
    runtime_out = root / 'runtime.json'
    built_meta = package_app.write_python_runtime_metadata(ROOT / 'Tools/python_runtime.json', runtime_out, ['arm64'])
    assert package_app.verify_python_runtime_metadata(
        runtime_src,
        json.loads(runtime_out.read_text(encoding='utf-8')),
        expected_architectures=['arm64'],
    ) == built_meta

    (root / 'e1.plist').write_bytes(plistlib.dumps({'com.apple.security.cs.debugger': True}))
    (root / 'e2.plist').write_bytes(plistlib.dumps({'com.apple.security.cs.debugger': False}))
    try:
        package_app.merge_entitlements(manifest_path, root, root / 'merged.plist')
    except ValueError as err:
        assert 'Incompatible module entitlement' in str(err), err
    else:
        raise AssertionError('conflicting entitlement values were accepted')

print('build_signing_scope_ok')
