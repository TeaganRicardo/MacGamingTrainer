#!/usr/bin/env python3
"""Discover test entrypoints and their platform declarations without importing them."""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREREQUISITES_DIR = Path("Tools/ci_prerequisites")
_PREREQUISITE_RE = re.compile(r"^[a-z0-9_][a-z0-9_-]*$")


def prerequisite_path(name: str) -> str:
    return f"{PREREQUISITES_DIR.as_posix()}/{name}.sh"


def validate_prerequisite(name: object, source: str, *, root: Path | None = None) -> str:
    if not isinstance(name, str) or not _PREREQUISITE_RE.fullmatch(name):
        raise ValueError(f"{source}: invalid CI prerequisite name: {name!r}")
    if root is not None and not (root / PREREQUISITES_DIR / f"{name}.sh").is_file():
        raise ValueError(f"{source}: unknown CI prerequisite {name!r} (missing {prerequisite_path(name)})")
    return name


def declared_prerequisites(tree: ast.Module, source: str, *, root: Path | None = None) -> tuple[str, ...]:
    values = declarations(tree, "MGT_PREREQUISITES")
    if not values:
        return ()
    message = f"{source}: MGT_PREREQUISITES must be a literal list of unique prerequisite names"
    if len(values) != 1 or not isinstance(values[0], (ast.List, ast.Tuple)):
        raise ValueError(message)
    prereqs: list[str] = []
    seen: set[str] = set()
    for element in values[0].elts:
        if not isinstance(element, ast.Constant) or not isinstance(element.value, str):
            raise ValueError(message)
        name = validate_prerequisite(element.value, source, root=root)
        if name in seen:
            raise ValueError(message)
        seen.add(name)
        prereqs.append(name)
    return tuple(prereqs)


def discover_module_test_prerequisites(root: Path = ROOT) -> dict[str, tuple[str, ...]]:
    games_root = root / "Backend" / "games"
    if not games_root.is_dir():
        return {}
    discovered: dict[str, tuple[str, ...]] = {}
    for manifest_path in sorted(games_root.glob("*/module.json")):
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        req = raw.get("buildRequirements", {}) if isinstance(raw, dict) else {}
        if not isinstance(req, dict):
            raise ValueError(f"{manifest_path}: buildRequirements must be an object")
        raw_prereqs = req.get("testPrerequisites", [])
        if not isinstance(raw_prereqs, list) or len(set(raw_prereqs)) != len(raw_prereqs):
            raise ValueError(f"{manifest_path}: buildRequirements.testPrerequisites must be a list of unique names")
        if raw_prereqs:
            discovered[manifest_path.parent.name] = tuple(
                validate_prerequisite(item, manifest_path.relative_to(root).as_posix(), root=root)
                for item in raw_prereqs
            )
    return discovered


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
