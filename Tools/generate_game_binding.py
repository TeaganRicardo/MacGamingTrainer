#!/usr/bin/env python3
"""Generate the Swift seam between game frontend modules and the App.

Each game's Swift module receives one generated file: the manifest-derived
descriptor and a `package` binding enum, which is the only declaration the App
module sees from that game. The App module receives the catalog that composes
those bindings. No game sees another game's binding.
"""
import argparse
import sys
from pathlib import Path

from module_support import (
    HOST_PROTOCOL_VERSION,
    ManifestError,
    load_manifest,
    swift_string,
)
from swift_module_layout import SWIFT_APP_MODULE, SWIFT_CORE_MODULE

HEADER = '// Generated from module manifests. Do not edit.\n'
BINDING_FILENAME = 'GameBinding.generated.swift'
CATALOG_FILENAME = 'TrainerGameCatalog.generated.swift'


def binding_name(manifest):
    return f'{manifest.frontend.module_type}Binding'


def descriptor_source(manifest):
    module_type = manifest.frontend.module_type
    return (
        f'extension {module_type} {{\n'
        '    static let descriptor = GameModuleDescriptor(\n'
        f'        id: {swift_string(manifest.id)},\n'
        f'        displayName: {swift_string(manifest.display_name)},\n'
        f'        targetProcessName: {swift_string(manifest.runtime.process_name)},\n'
        f'        targetBundleIdentifier: {swift_string(manifest.runtime.bundle_identifier)},\n'
        f'        targetExecutablePathSuffix: {swift_string(manifest.runtime.executable_path_suffix)},\n'
        f'        expectedHostProtocolVersion: {HOST_PROTOCOL_VERSION},\n'
        f'        expectedModuleProtocolVersion: {manifest.module_protocol_version},\n'
        f'        supportsSaveManagement: {str(manifest.runtime.save_management is not None).lower()}\n'
        '    )\n'
        '}\n'
    )


def binding_declaration(manifest):
    module = manifest.frontend.module_type
    return (
        descriptor_source(manifest)
        + '/// The App composes this game only through this binding; every other\n'
        + "/// declaration of the game's Swift module stays internal to it.\n"
        + f'package enum {binding_name(manifest)} {{\n'
        + f'    package static var descriptor: GameModuleDescriptor {{ {module}.descriptor }}\n'
        + '\n'
        + '    @MainActor\n'
        + '    package static func makeContext() -> AnyTrainerGameContext {\n'
        + f'        AnyTrainerGameContext(TrainerGameContext<{module}>())\n'
        + '    }\n'
        + '\n'
        + '    @MainActor @CommandsBuilder\n'
        + '    package static func makeManagementCommands(\n'
        + '        application: TrainerApplicationCoordinator,\n'
        + '        localization: TrainerLocalizationStore\n'
        + '    ) -> some Commands {\n'
        + f'        if !application.terminationRequested && application.selectedGameID == {module}.descriptor.id,\n'
        + f'           let context = application.context(id: {module}.descriptor.id)?.typed(as: {module}.self) {{\n'
        + f'            {module}.makeManagementCommands(model: context.model, localization: localization)\n'
        + '        }\n'
        + '    }\n'
        + '}\n'
    )


def catalog_declaration(manifests):
    bindings = [binding_name(item) for item in manifests]
    descriptors = ', '.join(f'{binding}.descriptor' for binding in bindings)
    contexts = ',\n'.join(f'            {binding}.makeContext()' for binding in bindings)
    commands = ''.join(
        f'        {binding}.makeManagementCommands(application: application, localization: localization)\n'
        for binding in bindings
    )
    return (
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
        f'{commands}'
        '    }\n'
        '}\n'
    )


def _imports(*modules):
    return ''.join(f'import {module}\n' for module in modules)


def binding_source(manifest):
    """The generated file compiled into one game's Swift module."""
    return HEADER + _imports('SwiftUI', SWIFT_CORE_MODULE) + binding_declaration(manifest)


def catalog_source(manifests):
    """The generated file compiled into the App module."""
    games = [item.frontend.swift_module for item in manifests]
    return HEADER + _imports('SwiftUI', SWIFT_CORE_MODULE, *games) + catalog_declaration(manifests)


def generate_module_sources(manifests, directory: Path):
    """Write each Swift module's generated sources under ``directory/<module>``.

    build.sh compiles ``directory/<module>/*.swift`` together with that
    module's own sources.
    """
    manifests = list(manifests)
    written = []
    for manifest in manifests:
        path = directory / manifest.frontend.swift_module / BINDING_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(binding_source(manifest), encoding='utf-8')
        written.append(path)
    catalog = directory / SWIFT_APP_MODULE / CATALOG_FILENAME
    catalog.parent.mkdir(parents=True, exist_ok=True)
    catalog.write_text(catalog_source(manifests), encoding='utf-8')
    written.append(catalog)
    return written


def generate(manifest, output: Path, *, catalog=False):
    """Write one file for a harness that compiles Core and games as one module.

    Only Swift test harnesses still compile that single-module shape; the
    product compiles the per-module sources of ``generate_module_sources``.
    """
    manifests = list(manifest) if isinstance(manifest, (list, tuple)) else [manifest]
    output.parent.mkdir(parents=True, exist_ok=True)
    text = HEADER + _imports('SwiftUI') + ''.join(binding_declaration(item) for item in manifests)
    if catalog or len(manifests) > 1:
        text += catalog_declaration(manifests)
    output.write_text(text, encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('game_ids', help='Comma-separated game module IDs.')
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--module-sources', metavar='DIRECTORY',
                        help='Write per-Swift-module generated sources for the product build.')
    target.add_argument('output', nargs='?',
                        help='Write one single-module file for a Swift test harness.')
    parser.add_argument('--catalog', action='store_true',
                        help='Include the App catalog in single-module output.')
    args = parser.parse_args(argv)
    if args.module_sources and args.catalog:
        parser.error('--catalog applies only to single-module output; --module-sources always writes the catalog.')
    try:
        manifests = [load_manifest(game_id) for game_id in args.game_ids.split(',')]
        if args.module_sources:
            generate_module_sources(manifests, Path(args.module_sources))
        else:
            generate(manifests, Path(args.output), catalog=args.catalog)
    except (ManifestError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
