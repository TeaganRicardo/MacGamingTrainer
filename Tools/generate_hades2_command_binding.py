#!/usr/bin/env python3
"""Generate Hades Host-command Swift metadata from the authoritative contract."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.command_contract import command_metadata


def swift_case(name):
    parts = name.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def render():
    rows = command_metadata()
    lines = [
        "// Generated from Backend/games/hades2/command_contract.py. Do not edit.",
        "import Foundation",
        "",
        "enum Hades2Command: String {",
    ]
    for row in rows:
        lines.append(f'    case {swift_case(row["name"])} = "{row["name"]}"')
    lines.extend([
        "",
        "    var timeout: TimeInterval {",
        "        switch self {",
    ])
    for row in rows:
        timeout = float(row["timeoutSeconds"])
        if abs(timeout - 6.0) <= 1e-9:
            continue
        lines.append(f"        case .{swift_case(row['name'])}: return {timeout:.1f}")
    lines.extend([
        "        default: return 6.0",
        "        }",
        "    }",
        "}",
        "",
    ])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    args = parser.parse_args(argv)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
