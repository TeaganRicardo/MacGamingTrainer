#!/usr/bin/env python3
"""List portable Linux test entrypoints under the repository's tests tree."""

import argparse
import sys
from pathlib import Path

from test_inputs import load_portable_test_prerequisites
from test_inventory import discover_test_inventory


def discover_tests(root: Path) -> list[str]:
    tests = [
        f"tests/{name}" for name, platform in discover_test_inventory(root).items()
        if platform is None
    ]
    if not tests:
        raise RuntimeError("no portable tests discovered")
    return tests


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--prerequisites",
        action="store_true",
        help="List CI prerequisite names declared by portable tests and module manifests.",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.prerequisites:
            for name in load_portable_test_prerequisites(root):
                print(name)
            return 0
        for test_file in discover_tests(root):
            print(test_file)
    except (OSError, SyntaxError, ValueError, RuntimeError) as error:
        print(f"Linux test discovery: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
