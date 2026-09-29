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


def _module_id(manifest_path: Path, data, *, require_build_layout: bool) -> str:
    if manifest_path.name != "module.json" or tuple(manifest_path.parts[:2]) != ("Backend", "games"):
        raise ModuleInventoryError(
            f"{manifest_path}: module manifest must live under Backend/games/"
        )
    if not isinstance(data, dict):
        raise ModuleInventoryError(f"{manifest_path}: module manifest must be a JSON object")
    game_id = data.get("id")
    if not isinstance(game_id, str) or not game_id:
        raise ModuleInventoryError(f"{manifest_path}: module id must be a non-empty string")
    if require_build_layout:
        if manifest_path.parent.parent != MODULES_RELATIVE:
            raise ModuleInventoryError(
                f"{manifest_path}: buildable module manifests must live directly under Backend/games/<id>/"
            )
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
    # Scan recursively, then reject layouts outside Backend/games/<id>/ below.
    # A one-level glob would silently ignore a stray nested module manifest
    # while ref-based discovery (git ls-tree -r) sees it, giving local and CI
    # consumers different module sets.
    for manifest in sorted(modules.rglob("module.json")):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ModuleInventoryError(f"{manifest}: cannot read module manifest: {error}") from error
        ids.append(_module_id(manifest.relative_to(root), data, require_build_layout=True))
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


def module_manifests_at_ref(ref: str, root: Path = ROOT) -> tuple[tuple[str, dict], ...]:
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
    records = []
    for line in listing.splitlines():
        if not line.endswith("/module.json"):
            continue
        try:
            data = json.loads(_git(root, "show", f"{ref}:{line}"))
        except ValueError as error:
            raise ModuleInventoryError(f"{line} at {ref}: invalid JSON: {error}") from error
        game_id = _module_id(Path(line), data, require_build_layout=False)
        records.append((game_id, data))
    ids = [game_id for game_id, _ in records]
    if len(ids) != len(set(ids)):
        raise ModuleInventoryError(f"duplicate game module id discovered at {ref}")
    return tuple(sorted(records, key=lambda item: item[0]))


def module_ids_at_ref(ref: str, root: Path = ROOT) -> tuple[str, ...]:
    return tuple(game_id for game_id, _ in module_manifests_at_ref(ref, root))


def _app_resource_sources(records) -> tuple[str, ...]:
    sources = set()
    for game_id, data in records:
        resources = data.get("appResources", [])
        if not isinstance(resources, list):
            raise ModuleInventoryError(
                f"module {game_id}: appResources must be a list for CI routing"
            )
        for index, row in enumerate(resources):
            if not isinstance(row, dict):
                raise ModuleInventoryError(
                    f"module {game_id}: appResources[{index}] must be an object"
                )
            source = row.get("source")
            if not isinstance(source, str) or not source.strip():
                raise ModuleInventoryError(
                    f"module {game_id}: appResources[{index}].source must be a non-empty string"
                )
            sources.add(source.strip())
    return tuple(sorted(sources))


def current_app_resource_sources(root: Path = ROOT) -> tuple[str, ...]:
    records = []
    for game_id in discover_module_ids(root):
        manifest = root / MODULES_RELATIVE / game_id / "module.json"
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ModuleInventoryError(f"{manifest}: cannot read module manifest: {error}") from error
        records.append((game_id, data))
    return _app_resource_sources(records)


def app_resource_sources_for_diff(
    base_ref: str,
    head_ref: str,
    root: Path = ROOT,
) -> tuple[str, ...]:
    merge_base = _git(root, "merge-base", base_ref, head_ref).strip()
    if not merge_base:
        raise ModuleInventoryError("unable to resolve merge-base for module resources")
    return tuple(sorted(set(
        _app_resource_sources(module_manifests_at_ref(merge_base, root))
    ) | set(
        _app_resource_sources(module_manifests_at_ref(head_ref, root))
    )))


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
