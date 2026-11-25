#!/usr/bin/env python3
"""Select tracked test entrypoints by their top-level platform declaration."""
import argparse
import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def platform_for_test(path):
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    declarations = []
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == 'MGT_PLATFORM':
                declarations.append(node.value)
        elif isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == 'MGT_PLATFORM' for target in node.targets
        ):
            declarations.append(node.value)
    if declarations and (
        len(declarations) != 1
        or not isinstance(declarations[0], ast.Constant)
        or declarations[0].value != 'macos'
    ):
        raise ValueError(f"{path}: expected one literal MGT_PLATFORM = 'macos' declaration")
    return 'macos' if declarations else 'linux'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('platform', choices=('linux', 'macos'))
    args = parser.parse_args()
    try:
        tracked = subprocess.check_output(
            ['git', 'ls-files', '-z', 'tests/test_*.py'], cwd=ROOT, text=True,
        ).split('\0')
        selected = [path for path in tracked if path and platform_for_test(ROOT / path) == args.platform]
    except (OSError, SyntaxError, ValueError, subprocess.CalledProcessError) as error:
        print(f'Test discovery failed: {error}', file=sys.stderr)
        return 2
    if selected:
        print('\n'.join(selected))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
