#!/usr/bin/env python3
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


CLEANUP_XATTRS = frozenset({'com.apple.FinderInfo', 'com.apple.ResourceFork'})
XATTR = shutil.which('xattr')


def _tree_paths(root):
    yield root
    if root.is_symlink() or not root.is_dir():
        return
    for directory, names, files in os.walk(root, followlinks=False):
        base = Path(directory)
        yield from (base / name for name in names)
        yield from (base / name for name in files)


def _attributes(path):
    if not XATTR:
        raise OSError('xattr tool is required to verify a clean signing target')
    result = subprocess.run(
        [XATTR, '-s', str(path)], capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise OSError(result.stderr.strip() or f'xattr failed for {path}')
    return frozenset(line for line in result.stdout.splitlines() if line)


def clean_signing_metadata(path, staging_root):
    root = Path(os.path.abspath(path))
    staging = Path(os.path.abspath(staging_root))
    if (not staging.is_dir() or staging.is_symlink() or root.parent != staging
            or root.suffix != '.app' or not root.is_dir() or root.is_symlink()
            or root.resolve().parent != staging.resolve()):
        raise ValueError(f'Cleanup target must be a real .app directly inside staging: {root}')
    for item in _tree_paths(root):
        for name in CLEANUP_XATTRS.intersection(_attributes(item)):
            if XATTR is None:
                raise OSError('xattr tool is required to remove signing metadata')
            subprocess.run([XATTR, '-d', '-s', name, str(item)], check=True)
        remaining = CLEANUP_XATTRS.intersection(_attributes(item))
        if remaining:
            raise OSError(f'Unable to remove signing metadata from {item}: {sorted(remaining)}')


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Remove FinderInfo and ResourceFork from a staged signing target.'
    )
    parser.add_argument('path', type=Path)
    parser.add_argument('--staging-root', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        clean_signing_metadata(args.path, args.staging_root)
    except (OSError, ValueError) as error:
        print(f'Cannot prepare clean signing target: {error}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
