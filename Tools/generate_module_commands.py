#!/usr/bin/env python3
"""Generate Swift Host-command metadata from module.json commandContract declarations."""

from __future__ import annotations

import argparse
from importlib import import_module
import math
from pathlib import Path
import sys

TOOLS_DIR = Path(__file__).resolve().parent
ROOT = TOOLS_DIR.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
if str(ROOT / "Backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "Backend"))

from module_inventory import discover_module_ids  # noqa: E402
from module_support import ManifestError, load_manifest  # noqa: E402


def swift_case(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def load_command_rows(metadata_ref: str) -> list[dict]:
    module_name, attr_name = metadata_ref.split(":", 1)
    module = import_module(module_name)
    provider = getattr(module, attr_name)
    rows = list(provider())
    if not rows:
        raise ManifestError(f"{metadata_ref} returned no commands.")
    seen: set[str] = set()
    validated: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ManifestError(f"{metadata_ref} entry must be an object.")
        name = row.get("name")
        if not isinstance(name, str) or not name or name in seen:
            raise ManifestError(f"{metadata_ref} has invalid or duplicate command name: {name!r}")
        seen.add(name)
        timeout = row.get("timeoutSeconds")
        if type(timeout) not in (int, float) or isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
            raise ManifestError(f"{metadata_ref}.{name} has invalid timeoutSeconds: {timeout!r}")
        trusted = row.get("requiresTrustedTarget")
        offline = row.get("supportsOfflineIntent")
        if type(trusted) is not bool or type(offline) is not bool:
            raise ManifestError(
                f"{metadata_ref}.{name} requires boolean requiresTrustedTarget and supportsOfflineIntent."
            )
        if offline and not trusted:
            raise ManifestError(
                f"{metadata_ref}.{name} cannot declare supportsOfflineIntent when requiresTrustedTarget is false."
            )
        validated.append(row)
    return validated


def render_commands(game_id: str) -> str:
    manifest = load_manifest(game_id)
    if manifest.command_contract is None:
        raise ManifestError(f"Game module {game_id!r} does not declare commandContract.")
    spec = manifest.command_contract
    module_ref = spec.metadata.split(":", 1)[0]
    rows = load_command_rows(spec.metadata)
    default_timeout = float(spec.default_timeout_seconds)

    lines = [
        f"// Generated from {module_ref}. Do not edit.",
        "import Foundation",
        "",
        f"enum {spec.enum_name}: String {{",
    ]
    for row in rows:
        lines.append(f'    case {swift_case(row["name"])} = "{row["name"]}"')

    lines.extend(
        [
            "",
            "    var timeout: TimeInterval {",
            "        switch self {",
        ]
    )
    for row in rows:
        timeout = float(row["timeoutSeconds"])
        if timeout == default_timeout:
            continue
        lines.append(f"        case .{swift_case(row['name'])}: return {timeout!r}")
    lines.extend(
        [
            f"        default: return {default_timeout!r}",
            "        }",
            "    }",
            "",
            "    var supportsOfflineIntent: Bool {",
            "        switch self {",
        ]
    )
    offline_cases = [f".{swift_case(row['name'])}" for row in rows if row["supportsOfflineIntent"]]
    if offline_cases:
        lines.append(f"        case {', '.join(offline_cases)}: return true")
    lines.extend(
        [
            "        default: return false",
            "        }",
            "    }",
            "",
            "    private var baseRequiresTrustedTarget: Bool {",
            "        switch self {",
        ]
    )
    untrusted_cases = [f".{swift_case(row['name'])}" for row in rows if not row["requiresTrustedTarget"]]
    if untrusted_cases:
        lines.append(f"        case {', '.join(untrusted_cases)}: return false")
    lines.extend(
        [
            "        default: return true",
            "        }",
            "    }",
            "",
            "    func offlineIntent(connected: Bool) -> Bool {",
            "        !connected && supportsOfflineIntent",
            "    }",
            "",
            "    func requiresTrustedTarget(connected: Bool) -> Bool {",
            "        baseRequiresTrustedTarget && !offlineIntent(connected: connected)",
            "    }",
            "}",
            "",
        ]
    )
    return "\n".join(lines)


def default_output_path(game_id: str) -> Path:
    manifest = load_manifest(game_id)
    if manifest.command_contract is None:
        raise ManifestError(f"Game module {game_id!r} does not declare commandContract.")
    return (
        ROOT
        / manifest.frontend.source_directory
        / "Generated"
        / f"{manifest.command_contract.enum_name}.generated.swift"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("game_id", nargs="?", help="Game module ID, or pass --all.")
    parser.add_argument("output", nargs="?", help="Output Swift file path when generating one module.")
    parser.add_argument(
        "--all", action="store_true", help="Write checked-in command bindings for all declaring modules."
    )
    parser.add_argument("--check", action="store_true", help="Verify checked-in files match rendered output.")
    args = parser.parse_args(argv)

    try:
        if args.all or args.check:
            if args.game_id or args.output:
                parser.error("--all/--check cannot be combined with positional arguments.")
            targets = [gid for gid in discover_module_ids(ROOT) if load_manifest(gid).command_contract is not None]
            if not targets:
                raise ManifestError("No game modules declare commandContract.")
            for gid in targets:
                rendered = render_commands(gid)
                target = default_output_path(gid)
                if args.check:
                    if not target.is_file() or target.read_text(encoding="utf-8") != rendered:
                        raise ManifestError(f"{target.relative_to(ROOT)} is missing or out of date.")
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(rendered, encoding="utf-8")
            return 0

        if not args.game_id:
            parser.error("Provide <game_id> [output] or --all.")
        rendered = render_commands(args.game_id)
        target = Path(args.output) if args.output else default_output_path(args.game_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
    except (ManifestError, OSError, ImportError, AttributeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
