#!/usr/bin/env python3
"""Discover game modules for shared build/CI tooling.

The module set is owned by Backend/games/*/module.json. Shared tools consume
this inventory instead of carrying their own game-id lists. Working-tree
consumers use discover_module_ids(); diff consumers use module_ids_for_diff()
so a module removed by the proposed change remains visible on the base side.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES_RELATIVE = Path("Backend/games")


class ModuleInventoryError(RuntimeError):
    pass


def _module_id(manifest_path: Path, data) -> str:
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
    for manifest in sorted(modules.glob("*/module.json")):
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


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        errors="replace",
    )
    if result.returncode != 0:
        raise ModuleInventoryError(
            result.stderr.strip() or result.stdout.strip() or "git command failed"
        )
    return result.stdout


def module_ids_at_ref(ref: str, root: Path = ROOT) -> tuple[str, ...]:
    listing = _git(
        root,
        "-c",
        "core.quotePath=false",
        "ls-tree",
        "-r",
        "--name-only",
        ref,
        "--",
        MODULES_RELATIVE.as_posix(),
    )
    ids = []
    for line in listing.splitlines():
        if not line.endswith("/module.json"):
            continue
        try:
            data = json.loads(_git(root, "show", f"{ref}:{line}"))
        except ValueError as error:
            raise ModuleInventoryError(f"{line} at {ref}: invalid JSON: {error}") from error
        ids.append(_module_id(Path(line), data))
    if len(ids) != len(set(ids)):
        raise ModuleInventoryError(f"duplicate game module id discovered at {ref}")
    return tuple(sorted(ids))


def module_ids_for_diff(base_ref: str, head_ref: str, root: Path = ROOT) -> tuple[str, ...]:
    merge_base = _git(root, "merge-base", base_ref, head_ref).strip()
    if not merge_base:
        raise ModuleInventoryError("unable to resolve merge-base for module inventory")
    # Union is deliberate: deleting a module may also delete/move its executable
    # reference data. Looking only at HEAD would classify that data as docs-only
    # in the exact commit that removed its owner.
    return tuple(sorted(set(module_ids_at_ref(merge_base, root)) | set(module_ids_at_ref(head_ref, root))))


def executable_reference_prefixes(game_ids) -> tuple[str, ...]:
    return tuple(f"docs/reference/{game_id}/" for game_id in sorted(set(game_ids)))


def main() -> int:
    for game_id in discover_module_ids():
        print(game_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
