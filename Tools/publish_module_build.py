#!/usr/bin/env python3
"""Publish a signed app without following a replaced dist directory."""
import argparse
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


def _verify_signature(app):
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)


def _copy_app(source, destination):
    subprocess.run(['/bin/cp', '-R', str(source), str(destination)], check=True)


def _module_id(app):
    marker = app / 'Contents/Resources/ACTIVE_GAME_ID'
    if marker.is_symlink() or not marker.is_file():
        raise ValueError(f'App has no safe selected-module marker: {app}')
    game_id = marker.read_text(encoding='utf-8').strip()
    if not game_id or '/' in game_id or '\\' in game_id:
        raise ValueError(f'App has invalid selected-module marker: {marker}')
    return game_id


def publish_app(source, dist, name):
    source = Path(source).absolute()
    dist = Path(dist).absolute()
    if not name or name in ('.', '..') or Path(name).name != name or '\0' in name:
        raise ValueError('Invalid app name for publication.')
    if source.is_symlink() or not source.is_dir():
        raise ValueError(f'Signed staging app is missing or unsafe: {source}')
    selected_game = _module_id(source)
    dist.mkdir(parents=True, exist_ok=True)
    directory_fd = os.open(dist, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    previous_fd = os.open('.', os.O_RDONLY | os.O_DIRECTORY)
    try:
        identity = os.fstat(directory_fd)

        def require_same_directory():
            current = os.stat(dist, follow_symlinks=False)
            if not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino):
                raise ValueError(f'Build output directory changed during publication: {dist}')

        os.fchdir(directory_fd)
        with tempfile.TemporaryDirectory(prefix='.mgt-publish-', dir='.') as temporary:
            candidate = Path(temporary) / f'{name}.app'
            _copy_app(source, candidate)
            _verify_signature(candidate)
            if _module_id(candidate) != selected_game:
                raise ValueError('Copied app selected-module identity changed during publication.')
            require_same_directory()
            destination = Path(f'{name}.app')
            if destination.is_symlink():
                raise ValueError(f'Build output app must not be a symlink: {destination}')
            elif destination.exists():
                if not destination.is_dir():
                    raise ValueError(f'Build output app is not a directory: {destination}')
                previous_game = _module_id(destination)
                if previous_game != selected_game:
                    raise ValueError(
                        f'Build output app {destination} belongs to {previous_game}; '
                        f'cannot replace it with {selected_game}.'
                    )
                shutil.rmtree(destination)
            os.rename(candidate, destination)
            _verify_signature(destination)
            require_same_directory()
    finally:
        os.fchdir(previous_fd)
        os.close(previous_fd)
        os.close(directory_fd)
    return dist / f'{name}.app'


def main(argv=None):
    parser = argparse.ArgumentParser(description='Publish a verified selected module app.')
    parser.add_argument('source', type=Path)
    parser.add_argument('dist', type=Path)
    parser.add_argument('name')
    args = parser.parse_args(argv)
    try:
        publish_app(args.source, args.dist, args.name)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f'Unable to publish signed app: {error}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
