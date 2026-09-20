#!/usr/bin/env python3
from pathlib import Path
import argparse
import sys

from module_support import HOST_PROTOCOL_VERSION, ManifestError, load_manifest, swift_string


def generate(manifest, output: Path):
    output.parent.mkdir(parents=True, exist_ok=True)
    module_type = manifest.frontend.module_type
    output.write_text(
        '// Generated from module.json. Do not edit.\n'
        f'extension {module_type} {{\n'
        '    static let descriptor = GameModuleDescriptor(\n'
        f'        id: {swift_string(manifest.id)},\n'
        f'        displayName: {swift_string(manifest.display_name)},\n'
        f'        backendGameID: {swift_string(manifest.id)},\n'
        f'        targetProcessName: {swift_string(manifest.runtime.process_name)},\n'
        f'        targetBundleIdentifier: {swift_string(manifest.runtime.bundle_identifier)},\n'
        f'        expectedHostProtocolVersion: {HOST_PROTOCOL_VERSION},\n'
        f'        expectedModuleProtocolVersion: {manifest.module_protocol_version},\n'
        f'        supportsSaveManagement: {str(manifest.runtime.save_management is not None).lower()}\n'
        '    )\n'
        '}\n'
        f'typealias ActiveGameModule = {module_type}\n',
        encoding='utf-8',
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description='Generate Swift binding for one game module.')
    parser.add_argument('game_id')
    parser.add_argument('output')
    args = parser.parse_args(argv)
    try:
        generate(load_manifest(args.game_id), Path(args.output))
    except (ManifestError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
