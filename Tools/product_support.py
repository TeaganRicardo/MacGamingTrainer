"""Select the product's modules without coupling Host architecture to its targets."""
import json
import platform
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

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
        destinations = {}
        for module in self.modules:
            for resource in module.app_resources:
                key = unicodedata.normalize('NFC', resource.destination).casefold()
                if key in destinations:
                    raise ManifestError(
                        f'App resource destination {resource.destination!r} is shared by '
                        f'{destinations[key]} and {module.id}.'
                    )
                destinations[key] = module.id
                resources.append({'source': resource.source, 'destination': resource.destination})
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
    return {
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
