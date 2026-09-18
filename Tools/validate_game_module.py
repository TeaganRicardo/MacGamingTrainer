#!/usr/bin/env python3
import argparse
import json
import sys

from module_support import ManifestError, load_manifest, normalized_manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description='Validate a Mac Gaming Trainer game module.')
    parser.add_argument('game_id')
    parser.add_argument('--json', action='store_true', help='print normalized manifest JSON')
    args = parser.parse_args(argv)
    try:
        manifest = load_manifest(args.game_id)
    except (ManifestError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(normalized_manifest(manifest), ensure_ascii=False, sort_keys=True))
    else:
        print(f'{manifest.id}: ok')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
