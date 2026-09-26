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
from module_support import load_manifest


def expected_app_path(game_id, dist_dir):
    manifest = load_manifest(game_id)
    return Path(dist_dir).resolve() / f'{manifest.app.display_name}.app', manifest


def verify_module_build(game_id, dist_dir):
    app, manifest = expected_app_path(game_id, dist_dir)
    if app.is_symlink() or not app.is_dir():
        raise ValueError(f'Expected built app is missing or not a real app directory: {app}')
    contents = app / 'Contents'
    resources = contents / 'Resources'
    info_path = contents / 'Info.plist'
    game_marker = resources / 'ACTIVE_GAME_ID'
    games_dir = resources / 'Backend/games'
    manifest_path = games_dir / game_id / 'module.json'
    if not info_path.is_file() or not game_marker.is_file() or not manifest_path.is_file():
        raise ValueError(f'Expected app is missing selected module/build metadata: {app}')
    with info_path.open('rb') as stream:
        info = plistlib.load(stream)
    if info.get('CFBundleIdentifier') != manifest.app.bundle_identifier:
        raise ValueError(f'Bundle identifier mismatch in {info_path}')
    if info.get('CFBundleName') != manifest.app.display_name:
        raise ValueError(f'Bundle name mismatch in {info_path}')
    if game_marker.read_text(encoding='utf-8').strip() != game_id:
        raise ValueError(f'Selected module marker mismatch in {game_marker}')
    with manifest_path.open(encoding='utf-8') as stream:
        packaged_module = json.load(stream)
    if packaged_module.get('id') != game_id:
        raise ValueError(f'Packaged module identity mismatch in {manifest_path}')
    module_manifests = list(games_dir.rglob('module.json'))
    if module_manifests != [manifest_path]:
        raise ValueError(f'Expected exactly the selected module manifest in {app}; found {module_manifests}')
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
