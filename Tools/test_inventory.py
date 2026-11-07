"""Check the native platform boundary before discovering portable tests."""
from __future__ import annotations

import ast
from pathlib import Path


def requires_macos(path: Path, seen: set[Path] | None = None) -> bool:
    seen = set() if seen is None else seen
    if path in seen:
        return False
    seen.add(path)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        condition = ast.unparse(node.test)
        if "sys.platform" in condition and "darwin" in condition and "!=" in condition:
            if any(isinstance(statement, ast.Raise) for statement in node.body):
                return True
    for node in tree.body:
        modules = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                   else [node.module] if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module
                   else [])
        for module in modules:
            helper = path.parent / (module.split(".")[0] + ".py")
            if helper.is_file() and requires_macos(helper, seen):
                return True
    return False


def validate_native_inventory(root: Path, inventory: set[str]) -> None:
    missing = [path.name for path in sorted((root / "tests").rglob("test_*.py"))
               if path.name not in inventory and requires_macos(path)]
    if missing:
        raise ValueError("native tests missing from Tools/macos_only_tests.txt: " + ", ".join(missing))
