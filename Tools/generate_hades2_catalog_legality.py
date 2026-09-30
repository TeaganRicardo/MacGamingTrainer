#!/usr/bin/env python3
"""Generate the frozen Hades II catalog legality ledger from curated policy.

The policy owns research conclusions. Official Chinese presentation names come
from the frozen generated snapshot/terminology registry, and target version
metadata comes from the frozen manifest.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import io
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "docs/reference/hades2/1.139672-24556151"
POLICY_PATH = SNAPSHOT / "catalog_legality_policy.json"
OUTPUT_PATH = SNAPSHOT / "catalog_legality.csv"

FIELDNAMES = (
    "id",
    "kind",
    "sources",
    "official_name_zh_cn",
    "classification",
    "reason",
    "game_version",
    "steam_build",
)

_DIRECT_DATASETS = {
    "trait": ("generated/traits.csv", "TraitData"),
    "loot": ("generated/loot.csv", "LootData"),
    "consumable": ("generated/consumables.csv", "ConsumableData"),
    "alias": ("generated/aliases.csv", None),
}

_GENERATED_OVERRIDE_DATASETS = {
    "resources": ("generated/resources.csv", "ResourceData"),
}

_MARKUP_RE = re.compile(r"\{[^{}]*\}")
_WHITESPACE_RE = re.compile(r"\s+")


def _clean_name(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", _MARKUP_RE.sub("", value or "")).strip()


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _index_names(relative_path: str, preferred_table: str | None) -> dict[str, str]:
    rows = _read_rows(SNAPSHOT / relative_path)
    names: dict[str, str] = {}
    for row in rows:
        identifier = row.get("id", "")
        if not identifier:
            continue
        if identifier not in names or (
            preferred_table is not None and row.get("table") == preferred_table
        ):
            names[identifier] = _clean_name(row.get("display_name_zh_cn", ""))
    return names


def _resolve_terminology(terminology: dict, path: list[str]) -> str:
    value = terminology
    for key in path:
        if not isinstance(value, dict) or key not in value:
            raise ValueError(f"Unknown terminology path: {path!r}")
        value = value[key]
    if not isinstance(value, dict) or not isinstance(value.get("value"), str):
        raise ValueError(f"Terminology path has no string value: {path!r}")
    return _clean_name(value["value"])


def _official_name(
    row: dict,
    direct_names: dict[str, dict[str, str]],
    override_names: dict[str, dict[str, str]],
    terminology: dict,
) -> str:
    directive = row.get("officialName")
    if directive is None:
        return direct_names[row["kind"]].get(row["id"], "")
    if not isinstance(directive, dict):
        raise ValueError(f"{row['id']}: officialName must be an object")

    mode = directive.get("mode")
    if mode == "none":
        return ""
    if mode == "generated":
        dataset = directive.get("dataset")
        identifier = directive.get("id")
        if dataset not in override_names or not isinstance(identifier, str):
            raise ValueError(f"{row['id']}: invalid generated officialName reference")
        return override_names[dataset].get(identifier, "")
    if mode == "terminology":
        path = directive.get("path")
        if not isinstance(path, list) or not all(isinstance(item, str) for item in path):
            raise ValueError(f"{row['id']}: invalid terminology officialName path")
        return _resolve_terminology(terminology, path)
    raise ValueError(f"{row['id']}: unsupported officialName mode {mode!r}")


def _load_policy() -> list[dict]:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != 1 or not isinstance(payload.get("rows"), list):
        raise ValueError("Unsupported catalog legality policy schema")

    seen: set[str] = set()
    result: list[dict] = []
    allowed = {"id", "kind", "sources", "classification", "reason", "officialName"}
    for item in payload["rows"]:
        if not isinstance(item, dict) or set(item) - allowed:
            raise ValueError(f"Invalid catalog legality policy row: {item!r}")
        identifier = item.get("id")
        kind = item.get("kind")
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            raise ValueError(f"Invalid/duplicate catalog legality id: {identifier!r}")
        if kind not in _DIRECT_DATASETS:
            raise ValueError(f"{identifier}: unsupported kind {kind!r}")
        for field in ("sources", "classification"):
            if not isinstance(item.get(field), str):
                raise ValueError(f"{identifier}: {field} must be a string")
        if "reason" in item and not isinstance(item["reason"], str):
            raise ValueError(f"{identifier}: reason must be a string")
        seen.add(identifier)
        result.append(item)
    return result


def render() -> str:
    policy_rows = _load_policy()
    manifest = json.loads((SNAPSHOT / "manifest.json").read_text(encoding="utf-8"))
    terminology = json.loads((SNAPSHOT / "ui_terminology.json").read_text(encoding="utf-8"))

    game_version = manifest.get("game_version")
    steam_build = manifest.get("steam_build")
    if not isinstance(game_version, str) or not isinstance(steam_build, str):
        raise ValueError("Frozen manifest is missing target version/build")

    direct_names = {
        kind: _index_names(path, table)
        for kind, (path, table) in _DIRECT_DATASETS.items()
    }
    override_names = {
        name: _index_names(path, table)
        for name, (path, table) in _GENERATED_OVERRIDE_DATASETS.items()
    }

    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDNAMES, lineterminator="\n")
    writer.writeheader()
    for item in policy_rows:
        writer.writerow(
            {
                "id": item["id"],
                "kind": item["kind"],
                "sources": item["sources"],
                "official_name_zh_cn": _official_name(
                    item, direct_names, override_names, terminology
                ),
                "classification": item["classification"],
                "reason": item.get("reason", ""),
                "game_version": game_version,
                "steam_build": steam_build,
            }
        )
    return output.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    expected = render()
    if args.write:
        OUTPUT_PATH.write_text(expected, encoding="utf-8", newline="")
        return 0

    try:
        actual = OUTPUT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        actual = ""
    if actual == expected:
        return 0

    diff = difflib.unified_diff(
        actual.splitlines(keepends=True),
        expected.splitlines(keepends=True),
        fromfile=str(OUTPUT_PATH),
        tofile="generated catalog_legality.csv",
    )
    sys.stderr.writelines(diff)
    print(
        "catalog_legality.csv is stale; run "
        "python3 Tools/generate_hades2_catalog_legality.py --write",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
