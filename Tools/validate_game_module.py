#!/usr/bin/env python3
import argparse
import json
import sys

from module_inventory import ModuleInventoryError, discover_module_ids
from module_support import ManifestError, load_manifest, normalized_manifest


def _validate(game_ids):
    manifests = []
    for game_id in game_ids:
        manifests.append(load_manifest(game_id))
    return manifests


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
