#!/usr/bin/env python3
import argparse
import json
import sys
import unicodedata

from module_inventory import ModuleInventoryError, discover_module_ids
from module_support import ManifestError, load_manifest, normalized_manifest


def _validate(game_ids):
    # Check every declared destination even for a selected-module build: two
    # modules must never be allowed to publish to the same app directory.
    manifests = {game_id: load_manifest(game_id) for game_id in discover_module_ids()}
    destinations = {}
    for manifest in manifests.values():
        destination = unicodedata.normalize('NFC', manifest.app.display_name).casefold()
        previous = destinations.get(destination)
        if previous is not None:
            raise ManifestError(
                f'Duplicate app output {manifest.app.display_name!r}: modules {previous} and {manifest.id}.')
        destinations[destination] = manifest.id
    return [manifests[game_id] if game_id in manifests else load_manifest(game_id)
            for game_id in game_ids]


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
