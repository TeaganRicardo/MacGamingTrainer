#!/usr/bin/env python3
"""List portable Linux test entrypoints under the repository's tests tree."""

import argparse
from pathlib import Path


def discover_tests(root: Path) -> list[str]:
    tests_root = root / "tests"
    macos_only_file = root / "Tools" / "macos_only_tests.txt"
    macos_only = {
        line.strip()
        for line in macos_only_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    return sorted(
        path.relative_to(root).as_posix()
        for path in tests_root.rglob("test_*.py")
        if path.name not in macos_only
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    for test_file in discover_tests(args.root.resolve()):
        print(test_file)


if __name__ == "__main__":
    main()
