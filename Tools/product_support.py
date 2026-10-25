"""Select the product's modules without coupling Host architecture to its targets."""
import json
import platform
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from module_support import (
    ROOT, AppBuildSpec, ManifestError, app_spec_from_manifest, load_manifest,
    normalized_manifest,
)


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
            'id': 'all' if self.product else self.ids[0],
            'moduleIDs': list(self.ids),
            'modules': modules,
            'app': {
                'bundleIdentifier': self.app.bundle_identifier,
                'displayName': self.app.display_name,
                'executable': self.app.executable,
            },
            'frontend': {
                'sourceDirectories': [module.frontend.source_directory for module in self.modules],
                'architectures': list(self.architectures),
                'minimumMacOS': self.minimum_macos,
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


def load_selection(selection='all'):
    product = selection in ('all', '--all') or ',' in selection
    if not product:
        module = load_manifest(selection)
        return BuildSelection(
            (module,), module.app,
            module.frontend.architectures or (platform.machine(),),
            module.frontend.minimum_macos, False,
        )
    raw = json.loads((ROOT / 'app.json').read_text(encoding='utf-8'))
    if not isinstance(raw, dict) or raw.get('schemaVersion') != 1:
        raise ManifestError('app.json schemaVersion must be 1.')
    ids = selection.split(',') if ',' in selection else raw.get('modules')
    if (not isinstance(ids, list) or not ids or any(not isinstance(item, str) for item in ids)
            or len(set(ids)) != len(ids)):
        raise ManifestError('app.json modules must be a non-empty array of unique game IDs.')
    modules = tuple(load_manifest(game_id) for game_id in ids)
    arches = raw.get('architectures')
    if (not isinstance(arches, list) or not arches or len(set(arches)) != len(arches)
            or any(arch not in ('arm64', 'x86_64') for arch in arches)):
        raise ManifestError('app.json architectures must contain unique arm64/x86_64 values.')
    minimum = raw.get('minimumMacOS', '14.0')
    if not isinstance(minimum, str) or not re.fullmatch(r'[0-9]{1,2}(?:\.[0-9]{1,2}){1,2}', minimum):
        raise ManifestError('app.json minimumMacOS must be a macOS version.')
    minimum = max((minimum, *(module.frontend.minimum_macos for module in modules)),
                  key=lambda value: tuple(map(int, value.split('.'))))
    app = app_spec_from_manifest(raw, 'product', 'Product', modules[0].app.executable)
    types = [module.frontend.module_type for module in modules]
    directories = [module.frontend.source_directory for module in modules]
    if len(set(types)) != len(types) or len(set(directories)) != len(directories):
        raise ManifestError('Product modules must have distinct frontend types and directories.')
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
