#!/usr/bin/env python3
"""Generate durable Hades feature projections from the authoritative schema."""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.schema import MULTIPLIER_RULES, TOGGLES

LUA_BEGIN = "    -- BEGIN GENERATED DURABLE FEATURE SCHEMA"
LUA_END = "    -- END GENERATED DURABLE FEATURE SCHEMA"


def _swift_identifier(name):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError(f"unsupported Swift identifier: {name!r}")
    return name


def _number(value):
    number = float(value)
    if number.is_integer():
        return f"{number:.1f}"
    return repr(number)


def _lua_number(value):
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return repr(number)


def _validated_multipliers():
    rows = []
    for key, rule in MULTIPLIER_RULES.items():
        owner = rule.get("runtime")
        if owner not in ("resident", "core"):
            raise ValueError(f"{key} has invalid runtime owner {owner!r}")
        minimum = float(rule["min"])
        maximum = float(rule["max"])
        default = float(rule["default"])
        if minimum > maximum or not minimum <= default <= maximum:
            raise ValueError(f"{key} has invalid default/range")
        rows.append((key, default, minimum, maximum, owner))
    if dict((key, owner) for key, _, _, _, owner in rows).get("gameSpeed") != "core":
        raise ValueError("gameSpeed must remain Core-owned")
    return rows


def render_swift():
    rows = _validated_multipliers()
    lines = [
        "// Generated from Backend/games/hades2/schema.py. Do not edit.",
        "import Foundation",
        "",
        "enum Hades2FeatureKey: String, CaseIterable, Hashable {",
    ]
    for key in TOGGLES:
        lines.append(f"    case {_swift_identifier(key)}")
    lines.extend([
        "}",
        "",
        "enum Hades2MultiplierRuntimeOwner: Equatable {",
        "    case resident",
        "    case core",
        "}",
        "",
        "enum Hades2MultiplierKey: String, CaseIterable {",
    ])
    for key, *_ in rows:
        lines.append(f"    case {_swift_identifier(key)}")
    lines.extend([
        "",
        "    var defaultValue: Double {",
        "        switch self {",
    ])
    for key, default, *_ in rows:
        lines.append(f"        case .{_swift_identifier(key)}: return {_number(default)}")
    lines.extend([
        "        }",
        "    }",
        "",
        "    var range: ClosedRange<Double> {",
        "        switch self {",
    ])
    for key, _, minimum, maximum, _ in rows:
        lines.append(
            f"        case .{_swift_identifier(key)}: return {_number(minimum)}...{_number(maximum)}"
        )
    lines.extend([
        "        }",
        "    }",
        "",
        "    var runtimeOwner: Hades2MultiplierRuntimeOwner {",
        "        switch self {",
    ])
    for key, *_, owner in rows:
        lines.append(f"        case .{_swift_identifier(key)}: return .{owner}")
    lines.extend([
        "        }",
        "    }",
        "}",
        "",
    ])
    return "\n".join(lines)


def render_lua_schema():
    rows = _validated_multipliers()
    lines = [
        LUA_BEGIN,
        "    durableFeatureSchema = {",
        "      toggles = {",
    ]
    for key in TOGGLES:
        lines.append(f'        "{key}",')
    lines.extend([
        "      },",
        "      multipliers = {",
    ])
    for key, default, minimum, maximum, owner in rows:
        lines.append(
            f'        {key} = {{ default = {_lua_number(default)}, min = {_lua_number(minimum)}, '
            f'max = {_lua_number(maximum)}, runtime = "{owner}" }},'
        )
    lines.extend([
        "      },",
        "    },",
        LUA_END,
    ])
    return "\n".join(lines)

def replace_lua_schema(source):
    start = source.index(LUA_BEGIN)
    end = source.index(LUA_END, start) + len(LUA_END)
    return source[:start] + render_lua_schema() + source[end:]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--swift-output")
    parser.add_argument("--lua-source")
    args = parser.parse_args(argv)
    if not args.swift_output and not args.lua_source:
        parser.error("at least one output is required")
    if args.swift_output:
        path = Path(args.swift_output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_swift(), encoding="utf-8")
    if args.lua_source:
        path = Path(args.lua_source)
        path.write_text(replace_lua_schema(path.read_text(encoding="utf-8")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
