"""Select the product's modules without coupling Host architecture to its targets."""
import json
import platform
import re
from dataclasses import dataclass
from pathlib import Path

from generate_game_binding import generate_module_sources
from module_support import (
    ROOT, AppBuildSpec, ManifestError, load_manifest, load_product_declaration,
    normalized_manifest, product_app_spec,
)
from swift_module_layout import SWIFT_APP_MODULE, SWIFT_CORE_MODULE, SWIFT_PACKAGE_NAME

CORE_SWIFT_SOURCES = 'Sources/Core'
APP_SWIFT_SOURCE = 'Sources/App.swift'


@dataclass(frozen=True)
class BuildSelection:
    modules: tuple
    app: AppBuildSpec
    architectures: tuple
    minimum_macos: str
    product: bool

    @property
    def ids(self):
        return tuple(module.id for module in self.modules)

    @property
    def selection_id(self):
        """Packaged selection identity: all for the product, else its module ID."""
        return 'all' if self.product else self.ids[0]

    def normalized(self):
        modules = [normalized_manifest(module) for module in self.modules]
        resources = []
        for module in self.modules:
            for resource in module.app_resources:
                resources.append({
                    'source': resource.source,
                    'destination': f'Modules/{module.id}/{resource.destination}',
                })
        return {
            'id': self.selection_id,
            'moduleIDs': list(self.ids),
            'modules': modules,
            'app': {
                'bundleIdentifier': self.app.bundle_identifier,
                'displayName': self.app.display_name,
                'executable': self.app.executable,
            },
            'frontend': {
                'architectures': list(self.architectures),
                'minimumMacOS': self.minimum_macos,
                'swift': swift_layout(self.modules),
            },
            'buildRequirements': {
                'lldbPython': any(module.requirements.lldb_python for module in self.modules),
                'processTimeWarp': any(module.requirements.process_time_warp for module in self.modules),
                'debuggerEntitlement': any(module.requirements.debugger_entitlement for module in self.modules),
                'entitlements': list(dict.fromkeys(
                    module.requirements.entitlements for module in self.modules
                    if module.requirements.entitlements
                )),
            },
            'appResources': resources,
        }


def swift_layout(modules):
    """Swift modules in build order, each seeing only its declared dependencies.

    Core imports nothing of the product, each game imports only Core, and the
    App imports Core and every selected game.
    """
    games = [module.frontend.swift_module for module in modules]
    layout = {
        'packageName': SWIFT_PACKAGE_NAME,
        'modules': [
            {'name': SWIFT_CORE_MODULE, 'role': 'core', 'sources': [CORE_SWIFT_SOURCES],
             'dependencies': []},
            *({'name': module.frontend.swift_module, 'role': 'game', 'gameID': module.id,
               'sources': [module.frontend.source_directory], 'dependencies': [SWIFT_CORE_MODULE]}
              for module in modules),
            {'name': SWIFT_APP_MODULE, 'role': 'app', 'sources': [APP_SWIFT_SOURCE],
             'dependencies': [SWIFT_CORE_MODULE, *games]},
        ],
    }
    _validate_swift_ownership(layout['modules'], ROOT)
    return layout


def _validate_swift_ownership(modules, root):
    names = set()
    roots = []
    for module in modules:
        name = module['name']
        if name in names:
            raise ManifestError(f'Duplicate Swift module name: {name}.')
        names.add(name)
        for relative in module['sources']:
            path = (Path(root) / relative).resolve()
            for owner, owned in roots:
                if owner != name and (path == owned or path in owned.parents or owned in path.parents):
                    raise ManifestError(f'Overlapping Swift source ownership: {owner} and {name}: {relative}.')
            roots.append((name, path))


def swift_module_sources(modules, root, generated):
    """Each of ``modules`` (``swift_layout`` order) with the Swift files it compiles.

    A module compiles its declared sources under ``root`` (a directory
    contributes every ``*.swift`` file below it) plus the binding generator's
    files for it under ``generated/<module>``. The product build and the Swift
    test harnesses both take their source lists from here.
    """
    _validate_swift_ownership(modules, root)
    built = set()
    source_owners = {}
    result = []
    for module in modules:
        name = module['name']
        if any(dependency not in built for dependency in module['dependencies']):
            raise ManifestError(f'Swift module {name} depends on a module not built before it.')
        sources = []
        for relative in module['sources']:
            path = Path(root) / relative
            if path.is_dir():
                sources += sorted(path.rglob('*.swift'))
            elif path.is_file() and path.suffix == '.swift':
                sources.append(path)
            else:
                raise ManifestError(f'Missing Swift source for {name}: {relative}')
        sources += sorted((Path(generated) / name).glob('*.swift'))
        if not sources:
            raise ManifestError(f'No Swift sources for module {name}.')
        for source in sources:
            canonical = source.resolve()
            owner = source_owners.get(canonical)
            if owner is not None and owner != name:
                raise ManifestError(f'Swift source belongs to both {owner} and {name}: {source}.')
            source_owners[canonical] = name
        result.append((module, sources))
        built.add(name)
    return result


def swift_library_modules(game_ids, generated):
    """TrainerCore and each game's Swift module for ``game_ids``, with their files.

    Writes each module's generated sources under ``generated`` first. A Swift
    test harness compiles these modules and takes the App module's place.
    """
    manifests = [load_manifest(game_id) for game_id in game_ids]
    modules = [module for module in swift_layout(manifests)['modules'] if module['role'] != 'app']
    generate_module_sources(manifests, Path(generated))
    return swift_module_sources(modules, ROOT, generated)


def swift_harness_resources(game_ids):
    """Declared `appResources` for ``game_ids`` as `(moduleID, source, destination)` dicts."""
    resources = []
    for game_id in game_ids:
        manifest = load_manifest(game_id)
        for resource in manifest.app_resources:
            resources.append({
                'moduleID': manifest.id,
                'source': str(ROOT / resource.source),
                'destination': resource.destination,
            })
    return resources


def load_selection(selection='all'):
    product = selection in ('all', '--all') or ',' in selection
    if not product:
        module = load_manifest(selection)
        return BuildSelection(
            (module,), module.app,
            module.frontend.architectures or (platform.machine(),),
            module.frontend.minimum_macos, False,
        )
    raw = load_product_declaration()
    ids = selection.split(',') if ',' in selection else raw.get('modules')
    if (not isinstance(ids, list) or not ids or any(not isinstance(item, str) for item in ids)
            or len(set(ids)) != len(ids)):
        raise ManifestError('app.json modules must be a non-empty array of unique game IDs.')
    modules = tuple(load_manifest(game_id) for game_id in ids)
    arches = raw.get('architectures')
    if (not isinstance(arches, list) or not arches or len(set(arches)) != len(arches)
            or any(arch not in ('arm64', 'x86_64') for arch in arches)):
        raise ManifestError('app.json architectures must contain unique arm64/x86_64 values.')
    minimum = raw.get('minimumMacOS')
    if not isinstance(minimum, str) or not re.fullmatch(r'[0-9]{1,2}(?:\.[0-9]{1,2}){1,2}', minimum):
        raise ManifestError('app.json minimumMacOS must be a macOS version.')
    minimum = max((minimum, *(module.frontend.minimum_macos for module in modules)),
                  key=lambda value: tuple(map(int, value.split('.'))))
    app = product_app_spec(raw, modules[0].app.executable)
    types = [module.frontend.module_type for module in modules]
    directories = [module.frontend.source_directory for module in modules]
    swift_modules = [module.frontend.swift_module for module in modules]
    if (len(set(types)) != len(types) or len(set(directories)) != len(directories)
            or len(set(swift_modules)) != len(swift_modules)):
        raise ManifestError('Product modules must have distinct frontend types, directories and Swift modules.')
    result = BuildSelection(modules, app, tuple(arches), minimum, True)
    result.normalized()  # Validate collisions before compilation or copying any output.
    return result


def main():
    import argparse
    import sys
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('selection', nargs='?', default='all')
    args = parser.parse_args()
    try:
        print(json.dumps(load_selection(args.selection).normalized(), ensure_ascii=False))
    except (ManifestError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
