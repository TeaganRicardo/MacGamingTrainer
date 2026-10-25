#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

from module_support import (
    HOST_PROTOCOL_VERSION,
    ManifestError,
    load_manifest,
    swift_string,
)


def descriptor_source(manifest):
    module_type = manifest.frontend.module_type
    return (
        f'extension {module_type} {{\n'
        '    static let descriptor = GameModuleDescriptor(\n'
        f'        id: {swift_string(manifest.id)},\n'
        f'        displayName: {swift_string(manifest.display_name)},\n'
        f'        backendGameID: {swift_string(manifest.id)},\n'
        f'        targetProcessName: {swift_string(manifest.runtime.process_name)},\n'
        f'        targetBundleIdentifier: {swift_string(manifest.runtime.bundle_identifier)},\n'
        f'        targetExecutablePathSuffix: {swift_string(manifest.runtime.executable_path_suffix)},\n'
        f'        expectedHostProtocolVersion: {HOST_PROTOCOL_VERSION},\n'
        f'        expectedModuleProtocolVersion: {manifest.module_protocol_version},\n'
        f'        supportsSaveManagement: {str(manifest.runtime.save_management is not None).lower()}\n'
        '    )\n'
        '}\n'
    )


def generate(manifest, output: Path, *, catalog=False):
    manifests = list(manifest) if isinstance(manifest, (list, tuple)) else [manifest]
    output.parent.mkdir(parents=True, exist_ok=True)
    text = '// Generated from module manifests. Do not edit.\n'
    text += ''.join(descriptor_source(item) for item in manifests)
    if len(manifests) == 1:
        text += f'typealias ActiveGameModule = {manifests[0].frontend.module_type}\n'
    if catalog or len(manifests) > 1:
        text = 'import SwiftUI\n' + text
        descriptors = ', '.join(f'{item.frontend.module_type}.descriptor' for item in manifests)
        contexts = ',\n'.join(
            f'            AnyTrainerGameContext(TrainerGameContext<{item.frontend.module_type}>())'
            for item in manifests
        )
        text += (
            '@MainActor\nenum TrainerGameCatalog {\n'
            f'    static let descriptors: [GameModuleDescriptor] = [{descriptors}]\n'
            '    static func makeContexts() -> [AnyTrainerGameContext] {\n'
            f'        [\n{contexts}\n        ]\n'
            '    }\n'
            '}\n'
            'struct TrainerGameCatalogCommands: Commands {\n'
            '    @ObservedObject var application: TrainerApplicationCoordinator\n'
            '    let localization: TrainerLocalizationStore\n'
            '    var body: some Commands {\n'
        )
        for item in manifests:
            module = item.frontend.module_type
            text += (
                f'        if !application.terminationRequested && application.selectedGameID == {module}.descriptor.id,\n'
                f'           let context = application.context(id: {module}.descriptor.id)?.typed(as: {module}.self) {{\n'
                f'            {module}.makeManagementCommands(model: context.model, localization: localization)\n'
                '        }\n'
            )
        text += '    }\n}\n'
    output.write_text(text, encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Generate Swift binding for one game module.')
    parser.add_argument('game_id')
    parser.add_argument('output')
    parser.add_argument('--catalog', action='store_true')
    args = parser.parse_args(argv)
    try:
        manifests = [load_manifest(game_id) for game_id in args.game_id.split(',')]
        generate(manifests, Path(args.output), catalog=args.catalog)
    except (ManifestError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
