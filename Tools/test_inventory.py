#!/usr/bin/env python3
"""Discover test entrypoints and their platform declarations without importing them."""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def declarations(tree: ast.Module, name: str) -> list[ast.expr | None]:
    """Read assignments to a top-level test declaration without executing it."""
    values = []
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            values.append(node.value)
        elif isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            values.append(node.value)
    return values


def discover_test_inventory(root: Path) -> dict[str, str | None]:
    """Return platform by test path relative to tests/."""
    tests_root = root / "tests"
    if not tests_root.is_dir():
        raise FileNotFoundError(f"test tree is missing: {tests_root}")
    inventory = {}
    for path in sorted(tests_root.rglob("test_*.py")):
        name = path.relative_to(tests_root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        platforms = declarations(tree, "MGT_PLATFORM")
        if platforms and (
            len(platforms) != 1
            or not isinstance(platforms[0], ast.Constant)
            or platforms[0].value != "macos"
        ):
            raise ValueError(f"{path}: expected one literal MGT_PLATFORM = 'macos' declaration")
        inventory[name] = "macos" if platforms else None
    return inventory


def load_macos_only_tests(root: Path = ROOT) -> set[str]:
    return {
        name for name, platform in discover_test_inventory(root).items()
        if platform == "macos"
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="List macOS test entrypoints relative to tests/")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        tests = load_macos_only_tests(args.root)
        if not tests:
            raise ValueError("no macOS tests discovered")
    except (OSError, SyntaxError, ValueError) as error:
        print(f"macOS test discovery: {error}", file=sys.stderr)
        return 2
    print("\n".join(sorted(tests)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
