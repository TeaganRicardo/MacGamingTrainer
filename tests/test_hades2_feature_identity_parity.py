import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


swift_types = read("Sources/Hades2/Hades2Types.swift")
backend_schema = read("Backend/games/hades2/schema.py")
lua = read("Backend/games/hades2/runtime/hades.lua")


def balanced_block(source, marker, open_char, close_char):
    start = source.index(marker) + len(marker)
    start = source.index(open_char, start)
    depth = 0
    for index in range(start, len(source)):
        char = source[index]
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return source[start + 1:index]
    raise AssertionError(marker)


def swift_enum_cases(source):
    block = balanced_block(source, "enum Hades2FeatureKey", "{", "}")
    return {
        item.strip()
        for line in re.findall(r"\bcase\s+([^\n]+)", block)
        for item in line.split(",")
        if re.fullmatch(r"[A-Za-z0-9_]+", item.strip())
    }


def python_toggle_keys(source):
    block = balanced_block(source, "TOGGLES =", "(", ")")
    return set(re.findall(r"'([A-Za-z0-9_]+)'", block))


def lua_toggle_keys(source):
    block = balanced_block(source, "desiredFeatures =", "{", "}")
    return set(re.findall(r"([A-Za-z0-9_]+)\s*=\s*false", block))


swift_features = swift_enum_cases(swift_types)
python_features = python_toggle_keys(backend_schema)
lua_features = lua_toggle_keys(lua)

assert python_features <= swift_features
assert python_features == lua_features

multiplier_block = balanced_block(backend_schema, "MULTIPLIER_RULES =", "{", "}")
python_multipliers = set(re.findall(r"'([A-Za-z0-9_]+)'\s*:", multiplier_block))

for key in ("damageMultiplier", "moneyMultiplier", "resourceMultiplier"):
    assert key in python_multipliers
    assert re.search(rf"\b{key}\b", lua)

assert "gameSpeed" in multiplier_block

print("hades2_feature_identity_parity_ok")
