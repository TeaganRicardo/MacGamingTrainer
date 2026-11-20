#!/usr/bin/env python3
"""List portable Linux test entrypoints under the repository's tests tree."""

import argparse
from pathlib import Path

from test_inventory import discover_test_inventory


def discover_tests(root: Path) -> list[str]:
    tests = [
        f"tests/{name}" for name, platform in discover_test_inventory(root).items()
        if platform is None
    ]
    if not tests:
        raise RuntimeError("no portable tests discovered")
    return tests


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    for test_file in discover_tests(args.root.resolve()):
        print(test_file)


if __name__ == "__main__":
    main()
