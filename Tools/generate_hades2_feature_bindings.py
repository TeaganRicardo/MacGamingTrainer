#!/usr/bin/env python3
"""Generate durable Hades feature projections from the authoritative schema."""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.schema import MULTIPLIER_RULES, TOGGLES

LUA_STATE_BEGIN = "    -- BEGIN GENERATED DURABLE FEATURE STATE"
LUA_STATE_END = "    -- END GENERATED DURABLE FEATURE STATE"
LUA_DESIRED_BEGIN = "    -- BEGIN GENERATED DURABLE DESIRED FEATURES"
LUA_DESIRED_END = "    -- END GENERATED DURABLE DESIRED FEATURES"
LUA_PROJECTION_BEGIN = "      -- BEGIN GENERATED DURABLE FEATURE PROJECTION"
LUA_PROJECTION_END = "      -- END GENERATED DURABLE FEATURE PROJECTION"
LUA_MULTIPLIER_BEGIN = "      -- BEGIN GENERATED DURABLE MULTIPLIER DISPATCH"
LUA_MULTIPLIER_END = "      -- END GENERATED DURABLE MULTIPLIER DISPATCH"


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


def _resident_multiplier_rows():
    return [
        row for row in _validated_multipliers()
        if row[4] == "resident"
    ]


def render_lua_state():
    lines = [LUA_STATE_BEGIN]
    for key in TOGGLES:
        lines.append(f"    {key} = false,")
    for key, default, _, _, _ in _resident_multiplier_rows():
        lines.append(f"    {key} = {_lua_number(default)},")
    lines.append(LUA_STATE_END)
    return "\n".join(lines)


def render_lua_desired_defaults():
    lines = [
        LUA_DESIRED_BEGIN,
        "    desiredFeatures = {",
    ]
    for key in TOGGLES:
        lines.append(f"      {key} = false,")
    lines.extend([
        "    },",
        LUA_DESIRED_END,
    ])
    return "\n".join(lines)


def render_lua_state_projection():
    lines = [
        LUA_PROJECTION_BEGIN,
        "      desiredFeatures = {",
    ]
    for key in TOGGLES:
        lines.append(f"        {key} = M.desiredFeatures.{key},")
    lines.extend([
        "      },",
        LUA_PROJECTION_END,
    ])
    return "\n".join(lines)


def render_lua_multiplier_dispatch():
    lines = [LUA_MULTIPLIER_BEGIN]
    for key, _, minimum, maximum, _ in _resident_multiplier_rows():
        lo = _lua_number(minimum)
        hi = _lua_number(maximum)
        lines.extend([
            f'      if feature == "{key}" then',
            f'        if not finite(value) or value < {lo} or value > {hi} then error("Multiplier must be {lo}..{hi}") end',
        ])
        if key == "damageMultiplier":
            lines.extend([
                "        runtimeState.previousDamageMultiplier = M.damageMultiplier",
                "        M.damageMultiplier = value",
                '        feature = "damageEnabled"',
                "        value = value ~= 1",
            ])
        else:
            lines.extend([
                f"        M.{key} = value",
                "        return state(params.includeCatalogs)",
            ])
        lines.append("      end")
    lines.append(LUA_MULTIPLIER_END)
    return "\n".join(lines)


def lua_projection_blocks():
    return [
        (LUA_STATE_BEGIN, LUA_STATE_END, render_lua_state()),
        (LUA_DESIRED_BEGIN, LUA_DESIRED_END, render_lua_desired_defaults()),
        (LUA_PROJECTION_BEGIN, LUA_PROJECTION_END, render_lua_state_projection()),
        (LUA_MULTIPLIER_BEGIN, LUA_MULTIPLIER_END, render_lua_multiplier_dispatch()),
    ]


def _replace_block(source, begin, end, replacement):
    start = source.index(begin)
    finish = source.index(end, start) + len(end)
    return source[:start] + replacement + source[finish:]


def replace_lua_projections(source):
    for begin, end, replacement in lua_projection_blocks():
        source = _replace_block(source, begin, end, replacement)
    return source


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
        path.write_text(
            replace_lua_projections(path.read_text(encoding="utf-8")),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
