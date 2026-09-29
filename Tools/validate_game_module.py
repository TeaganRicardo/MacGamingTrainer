#!/usr/bin/env python3
import argparse
import json
import sys
import unicodedata

from module_inventory import ModuleInventoryError, discover_module_ids
from module_support import ManifestError, load_manifest, normalized_manifest


def _validate(game_ids):
    all_manifests = [load_manifest(game_id) for game_id in discover_module_ids()]
    for field in ('display_name', 'bundle_identifier'):
        owners = {}
        for manifest in all_manifests:
            value = getattr(manifest.app, field)
            identity = unicodedata.normalize('NFC', value).casefold()
            if identity in owners:
                spelling = 'displayName' if field == 'display_name' else 'bundleIdentifier'
                raise ManifestError(
                    f'app.{spelling} {value!r} is claimed by both {owners[identity]} and {manifest.id}; '
                    'selected module app output identities must be unique.'
                )
            owners[identity] = manifest.id
    selected = set(game_ids)
    if selected - {manifest.id for manifest in all_manifests}:
        raise ManifestError(f'Unknown game module: {sorted(selected - {manifest.id for manifest in all_manifests})}')
    return [manifest for manifest in all_manifests if manifest.id in selected]


def main(argv=None):
    parser = argparse.ArgumentParser(description='Validate Mac Gaming Trainer game modules.')
    parser.add_argument('game_id', nargs='?')
    parser.add_argument('--all', action='store_true', dest='all_modules',
                        help='validate every discovered game module')
    parser.add_argument('--json', action='store_true', help='print normalized manifest JSON')
    args = parser.parse_args(argv)

    if args.all_modules == bool(args.game_id):
        parser.error('provide exactly one game_id or --all')

    try:
        game_ids = discover_module_ids() if args.all_modules else (args.game_id,)
        manifests = _validate(game_ids)
    except (ManifestError, ModuleInventoryError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2

    if args.json:
        payload = [normalized_manifest(manifest) for manifest in manifests]
        print(json.dumps(payload if args.all_modules else payload[0],
                         ensure_ascii=False, sort_keys=True))
    else:
        for manifest in manifests:
            print(f'{manifest.id}: ok')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
