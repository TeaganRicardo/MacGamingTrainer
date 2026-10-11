#!/usr/bin/env python3
"""Build and sign the selected module's declared C libraries in app staging."""
import argparse
import json
import shutil
import subprocess
from pathlib import Path


def build_libraries(manifest, module, staging, *, clang, sdk, architectures, minimum_macos):
    module, staging = Path(module).resolve(), Path(staging).resolve()
    for library in manifest.get('nativeLibraries', []):
        source = module / library['source']
        destination = module / 'native' / library['filename']
        destination.parent.mkdir(parents=True, exist_ok=True)
        binaries = []
        for architecture in architectures:
            binary = staging / f"{library['filename']}.{architecture}"
            subprocess.run([
                clang, '-dynamiclib', '-isysroot', sdk, '-arch', architecture,
                f'-mmacosx-version-min={minimum_macos}', '-std=c11', '-Wall', '-Wextra',
                '-Os', '-fvisibility=hidden', str(source), '-o', str(binary),
            ], check=True)
            binaries.append(binary)
        if len(binaries) == 1:
            shutil.copy2(binaries[0], destination)
        else:
            subprocess.run(['xcrun', 'lipo', '-create', *map(str, binaries), '-output', str(destination)], check=True)
        subprocess.run(['codesign', '--force', '--sign', '-', '--timestamp=none', str(destination)], check=True)
        subprocess.run(['codesign', '--verify', '--strict', str(destination)], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('module', type=Path)
    parser.add_argument('staging', type=Path)
    parser.add_argument('--clang', required=True)
    parser.add_argument('--sdk', required=True)
    parser.add_argument('--minimum-macos', required=True)
    parser.add_argument('--architectures', nargs='+', required=True)
    args = parser.parse_args()
    build_libraries(json.loads(args.manifest.read_text()), args.module, args.staging,
        clang=args.clang, sdk=args.sdk, architectures=args.architectures, minimum_macos=args.minimum_macos)


if __name__ == '__main__':
    main()
