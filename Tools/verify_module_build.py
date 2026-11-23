#!/usr/bin/env python3
import argparse
import json
import plistlib
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
ROOT = TOOLS_DIR.parent
BACKEND = ROOT / 'Backend'
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(BACKEND))

from core.module_manifest import ManifestError
from module_inventory import discover_module_ids
from package_app import verify_python_runtime_metadata
from product_support import load_selection


def expected_app_path(game_id, dist_dir):
    manifest = load_selection(game_id)
    return Path(dist_dir).resolve() / f'{manifest.app.display_name}.app', manifest


def verify_python_runtime(resources, manifest):
    source_path = ROOT / 'Tools/python_runtime.json'
    runtime_root = resources / 'Python'
    metadata_path = runtime_root / 'runtime.json'
    if runtime_root.is_symlink() or not metadata_path.is_file() or metadata_path.is_symlink():
        raise ValueError(f'Python runtime metadata is missing or unsafe: {metadata_path}')
    source = json.loads(source_path.read_text(encoding='utf-8'))
    packaged = json.loads(metadata_path.read_text(encoding='utf-8'))
    architectures = list(manifest.architectures)
    try:
        verify_python_runtime_metadata(source, packaged, expected_architectures=architectures)
    except ValueError as error:
        raise ValueError(f'Python runtime metadata differs from pinned build input: {metadata_path}: {error}') from error
    for arch in architectures:
        executable = runtime_root / arch / 'bin/python3'
        if not executable.is_file():
            raise ValueError(f'Python runtime interpreter is missing or unsafe: {executable}')
        try:
            executable.resolve().relative_to(runtime_root.resolve())
        except ValueError as error:
            raise ValueError(f'Python runtime interpreter escapes package: {executable}') from error
        if executable.stat().st_mode & 0o111 == 0:
            raise ValueError(f'Python runtime interpreter is not executable: {executable}')


def verify_module_build(game_id, dist_dir):
    app, manifest = expected_app_path(game_id, dist_dir)
    if app.is_symlink() or not app.is_dir():
        raise ValueError(f'Expected built app is missing or not a real app directory: {app}')
    contents = app / 'Contents'
    resources = contents / 'Resources'
    info_path = contents / 'Info.plist'
    game_marker = resources / 'ACTIVE_GAME_ID'
    games_dir = resources / 'Backend/games'
    if not info_path.is_file() or not game_marker.is_file():
        raise ValueError(f'Expected app is missing selected module/build metadata: {app}')
    with info_path.open('rb') as stream:
        info = plistlib.load(stream)
    for key, expected in {
        'CFBundleIdentifier': manifest.app.bundle_identifier,
        'CFBundleName': manifest.app.display_name,
        'CFBundleDisplayName': manifest.app.display_name,
        'CFBundleExecutable': manifest.app.executable,
    }.items():
        if info.get(key) != expected:
            raise ValueError(f'{key} mismatch in {info_path}')
    executable = contents / 'MacOS' / manifest.app.executable
    if not executable.is_file() or executable.is_symlink():
        raise ValueError(f'Expected packaged executable is missing or unsafe: {executable}')
    if game_marker.read_text(encoding='utf-8').strip() != manifest.selection_id:
        raise ValueError(f'Selected module marker mismatch in {game_marker}')
    expected_paths = {games_dir / module.id / 'module.json' for module in manifest.modules}
    if set(games_dir.rglob('module.json')) != expected_paths:
        raise ValueError(f'Expected exactly the selected module manifests in {app}')
    for module in manifest.modules:
        packaged = games_dir / module.id / 'module.json'
        if packaged.is_symlink() or packaged.read_bytes() != module.runtime.source_path.read_bytes():
            raise ValueError(f'Packaged module differs from source: {packaged}')
    marker = resources / 'GAME_MODULES.json'
    if manifest.product and (not marker.is_file() or json.loads(marker.read_text()) != list(manifest.ids)):
        raise ValueError(f'Packaged module set differs from product: {marker}')
    verify_python_runtime(resources, manifest)
    if any(module.requirements.lldb_python for module in manifest.modules):
        source = ROOT / 'Backend/debugger'
        packaged = resources / 'Backend/debugger'
        expected = {path.relative_to(source): path for path in source.rglob('*.py')}
        actual = {path.relative_to(packaged): path for path in packaged.rglob('*.py')}
        if packaged.is_symlink() or not expected or actual.keys() != expected.keys():
            raise ValueError(f'Packaged debugger backend is missing or differs from source: {packaged}')
        for relative, path in actual.items():
            if path.is_symlink() or path.read_bytes() != expected[relative].read_bytes():
                raise ValueError(f'Packaged debugger backend differs from source: {path}')
    time_warp_native = resources / 'Backend/core/native'
    if any(module.requirements.process_time_warp for module in manifest.modules):
        helper = time_warp_native / 'libMGTTimeWarp.dylib'
        license_path = time_warp_native / 'LICENSE.fishhook'
        expected_license = ROOT / 'Native/ProcessTimeWarp/vendor/fishhook/LICENSE'
        if (
            time_warp_native.is_symlink()
            or not helper.is_file()
            or helper.is_symlink()
            or not license_path.is_file()
            or license_path.is_symlink()
            or license_path.read_bytes() != expected_license.read_bytes()
        ):
            raise ValueError(f'Packaged Process Time Warp helper is missing or unsafe: {time_warp_native}')
    elif time_warp_native.exists() or time_warp_native.is_symlink():
        raise ValueError(f'Unrequested Process Time Warp helper was packaged: {time_warp_native}')
    for module in manifest.modules:
        for library in module.native_libraries:
            native = games_dir / module.id / 'native' / library.filename
            if not native.is_file() or native.is_symlink():
                raise ValueError(f'Declared module native library is missing or unsafe: {native}')
        for resource in module.app_resources:
            packaged = resources / 'Modules' / module.id / resource.destination
            expected_source = ROOT / resource.source
            if not packaged.is_file() or packaged.is_symlink() or packaged.read_bytes() != expected_source.read_bytes():
                raise ValueError(f'Declared module app resource is missing or differs from source: {packaged}')
            flat_leak = resources / resource.destination
            if flat_leak.exists() or flat_leak.is_symlink():
                raise ValueError(f'Declared module app resource leaked at flat bundle root: {flat_leak}')
        if module.app_resources:
            module_dir = resources / 'Modules' / module.id
            expected_files = {Path(resource.destination) for resource in module.app_resources}
            actual_files = {
                entry.relative_to(module_dir)
                for entry in module_dir.rglob('*')
                if entry.is_file() or entry.is_symlink()
            }
            if actual_files != expected_files:
                raise ValueError(
                    f'Packaged resources for {module.id} differ from declared appResources: '
                    f'{sorted(str(item) for item in actual_files)}'
                )
    modules_resources = resources / 'Modules'
    if modules_resources.exists():
        if modules_resources.is_symlink() or not modules_resources.is_dir():
            raise ValueError(f'Packaged module resource root is unsafe: {modules_resources}')
        expected_resource_dirs = {module.id for module in manifest.modules if module.app_resources}
        actual_resource_dirs = {entry.name for entry in modules_resources.iterdir()}
        if actual_resource_dirs != expected_resource_dirs:
            raise ValueError(
                f'Packaged module resource directories differ from selection: {sorted(actual_resource_dirs)}'
            )
    selected_ids = {module.id for module in manifest.modules}
    other_ids = sorted(set(discover_module_ids(ROOT)) - selected_ids)
    for other_id in other_ids:
        foreign_dir = resources / 'Modules' / other_id
        if foreign_dir.exists() or foreign_dir.is_symlink():
            raise ValueError(f'Non-selected module resource directory leaked into package: {foreign_dir}')
        other_manifest = json.loads((ROOT / 'Backend/games' / other_id / 'module.json').read_text(encoding='utf-8'))
        for entry in other_manifest.get('appResources', ()):
            destination = entry.get('destination', '')
            if not destination:
                continue
            namespaced_leak = resources / 'Modules' / other_id / destination
            flat_leak = resources / destination
            if (
                namespaced_leak.exists()
                or namespaced_leak.is_symlink()
                or flat_leak.exists()
                or flat_leak.is_symlink()
            ):
                raise ValueError(f'Non-selected module resource leaked into package: {other_id}/{destination}')
    return app


def main(argv=None):
    parser = argparse.ArgumentParser(description='Verify the exact module app output.')
    parser.add_argument('game_id')
    parser.add_argument('--dist-dir', type=Path, default=Path('dist'))
    parser.add_argument('--print-app', action='store_true', help='print the verified app path')
    args = parser.parse_args(argv)
    try:
        app = verify_module_build(args.game_id, args.dist_dir)
    except (ManifestError, OSError, ValueError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    if args.print_app:
        print(app)
    else:
        print(f'{args.game_id}: verified {app}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
