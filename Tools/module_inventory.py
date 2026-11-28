#!/usr/bin/env python3
"""Discover game modules from the manifests in Backend/games."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES_RELATIVE = Path("Backend/games")


class ModuleInventoryError(RuntimeError):
    pass


def _module_id(manifest_path: Path, data) -> str:
    if manifest_path.parent.parent != MODULES_RELATIVE:
        raise ModuleInventoryError(
            f"{manifest_path}: buildable module manifests must live directly under Backend/games/<id>/"
        )
    if not isinstance(data, dict):
        raise ModuleInventoryError(f"{manifest_path}: module manifest must be a JSON object")
    game_id = data.get("id")
    if not isinstance(game_id, str) or not game_id:
        raise ModuleInventoryError(f"{manifest_path}: module id must be a non-empty string")
    if manifest_path.parent.name != game_id:
        raise ModuleInventoryError(
            f"{manifest_path}: module id {game_id!r} must match directory {manifest_path.parent.name!r}"
        )
    return game_id


def discover_module_ids(root: Path = ROOT) -> tuple[str, ...]:
    modules = root / MODULES_RELATIVE
    if not modules.is_dir():
        raise ModuleInventoryError(f"module directory is missing: {modules}")
    ids = []
    # Discover nested manifests so invalid build layouts get reported.
    for manifest in sorted(modules.rglob("module.json")):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ModuleInventoryError(f"{manifest}: cannot read module manifest: {error}") from error
        ids.append(_module_id(manifest.relative_to(root), data))
    if not ids:
        raise ModuleInventoryError("no game module manifests found")
    if len(ids) != len(set(ids)):
        raise ModuleInventoryError("duplicate game module id discovered")
    return tuple(ids)


def main(argv=None) -> int:
    import argparse

    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    for game_id in discover_module_ids():
        print(game_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
