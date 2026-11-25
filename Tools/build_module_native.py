#!/usr/bin/env python3
"""Build and sign the selected module's declared C libraries in app staging."""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

PROCESS_TIME_WARP_LIBRARY = {
    'source': 'ProcessTimeWarp.c',
    'extraSources': ['vendor/fishhook/fishhook.c'],
    'includeDirectories': ['vendor/fishhook'],
    'frameworks': ['QuartzCore'],
    'filename': 'libMGTTimeWarp.dylib',
    'license': {
        'source': 'vendor/fishhook/LICENSE',
        'destination': 'LICENSE.fishhook',
    },
}


def build_libraries(
    manifest,
    module,
    staging,
    *,
    clang,
    sdk,
    architectures,
    minimum_macos,
    output_dir=None,
    clean_signing_metadata=None,
    app=None,
    staging_root=None,
):
    module, staging = Path(module), Path(staging)
    target_dir = Path(output_dir) if output_dir is not None else (module / 'native')
    for library in manifest.get('nativeLibraries', []):
        sources = [module / library['source'], *(module / item for item in library.get('extraSources', ()))]
        for src in sources:
            if not src.is_file():
                raise FileNotFoundError(f'Missing native source: {src}')
        license_spec = library.get('license')
        if license_spec is not None and not (module / license_spec['source']).is_file():
            raise FileNotFoundError(f"Missing native license: {module / license_spec['source']}")
        include_args = [f'-I{module / item}' for item in library.get('includeDirectories', ())]
        framework_args = [arg for fw in library.get('frameworks', ()) for arg in ('-framework', fw)]
        destination = target_dir / library['filename']
        destination.parent.mkdir(parents=True, exist_ok=True)
        binaries = []
        for architecture in library.get('architectures') or architectures:
            binary = staging / f"{module.name}-{library['filename']}.{architecture}"
            subprocess.run([
                clang, '-dynamiclib', '-isysroot', sdk, '-arch', architecture,
                f'-mmacosx-version-min={minimum_macos}', '-std=c11', '-Wall', '-Wextra',
                '-Os', '-fvisibility=hidden', *include_args, *map(str, sources),
                *framework_args, '-o', str(binary),
            ], check=True)
            binaries.append(binary)
        if len(binaries) == 1:
            shutil.copy2(binaries[0], destination)
        else:
            subprocess.run(['xcrun', 'lipo', '-create', *map(str, binaries), '-output', str(destination)], check=True)
        if license_spec is not None:
            shutil.copy2(module / license_spec['source'], target_dir / license_spec['destination'])
        if clean_signing_metadata and app and staging_root:
            subprocess.run(
                [sys.executable, str(clean_signing_metadata), str(app), '--staging-root', str(staging_root)],
                check=True,
            )
        subprocess.run(['codesign', '--force', '--sign', '-', '--timestamp=none', str(destination)], check=True)
        subprocess.run(['codesign', '--verify', '--strict', str(destination)], check=True)


def process_time_warp_architectures(manifest):
    architectures = []
    for module in manifest.get('modules', [manifest]):
        if not module.get('buildRequirements', {}).get('processTimeWarp', False):
            continue
        architecture = module.get('supportedBuild', {}).get('architecture')
        if architecture not in ('arm64', 'x86_64'):
            raise ValueError('Process Time Warp requires a supported target architecture.')
        if architecture not in architectures:
            architectures.append(architecture)
    return architectures


def build_process_time_warp(
    manifest,
    time_warp_root,
    staging,
    *,
    output_dir,
    clang,
    sdk,
    minimum_macos,
    clean_signing_metadata=None,
    app=None,
    staging_root=None,
):
    if not manifest.get('buildRequirements', {}).get('processTimeWarp', False):
        return False
    architectures = process_time_warp_architectures(manifest)
    if not architectures:
        raise ValueError('Process Time Warp has no selected target architecture.')
    build_libraries(
        {'nativeLibraries': [PROCESS_TIME_WARP_LIBRARY]},
        time_warp_root,
        staging,
        clang=clang,
        sdk=sdk,
        architectures=architectures,
        minimum_macos=minimum_macos,
        output_dir=output_dir,
        clean_signing_metadata=clean_signing_metadata,
        app=app,
        staging_root=staging_root,
    )
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('module', type=Path)
    parser.add_argument('staging', type=Path)
    parser.add_argument('--process-time-warp', action='store_true')
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--clean-signing-metadata', type=Path)
    parser.add_argument('--app', type=Path)
    parser.add_argument('--staging-root', type=Path)
    parser.add_argument('--clang', required=True)
    parser.add_argument('--sdk', required=True)
    parser.add_argument('--minimum-macos', required=True)
    parser.add_argument('--architectures', nargs='+', required=True)
    args = parser.parse_args()
    manifest_data = json.loads(args.manifest.read_text(encoding='utf-8'))
    if args.process_time_warp:
        if args.output_dir is None:
            parser.error('--process-time-warp requires --output-dir')
        build_process_time_warp(
            manifest_data,
            args.module,
            args.staging,
            output_dir=args.output_dir,
            clang=args.clang,
            sdk=args.sdk,
            minimum_macos=args.minimum_macos,
            clean_signing_metadata=args.clean_signing_metadata,
            app=args.app,
            staging_root=args.staging_root,
        )
        return
    build_libraries(
        manifest_data,
        args.module,
        args.staging,
        clang=args.clang,
        sdk=args.sdk,
        architectures=args.architectures,
        minimum_macos=args.minimum_macos,
        output_dir=args.output_dir,
        clean_signing_metadata=args.clean_signing_metadata,
        app=args.app,
        staging_root=args.staging_root,
    )


if __name__ == '__main__':
    main()
