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


def publish_app(source, dist, name):
    source = Path(source).absolute()
    dist = Path(dist).absolute()
    if not name or name in ('.', '..') or Path(name).name != name or '\0' in name:
        raise ValueError('Invalid app name for publication.')
    if source.is_symlink() or not source.is_dir():
        raise ValueError(f'Signed staging app is missing or unsafe: {source}')
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
            require_same_directory()
            destination = Path(f'{name}.app')
            if destination.is_symlink():
                destination.unlink()
            elif destination.exists():
                if not destination.is_dir():
                    raise ValueError(f'Build output app is not a directory: {destination}')
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
