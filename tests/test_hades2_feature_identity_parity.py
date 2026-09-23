from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


swift_types = read("Sources/Hades2/Hades2Types.swift")
backend_schema = read("Backend/games/hades2/schema.py")
lua = read("Backend/games/hades2/runtime/hades.lua")


def swift_enum_cases(source):
    block = source.split("enum Hades2FeatureKey", 1)[1].split("}", 1)[0]
    return set(re.findall(r"case ([A-Za-z0-9_]+)", block))


def python_toggle_keys(source):
    block = source.split("TOGGLES = (", 1)[1].split(")", 1)[0]
    return set(re.findall(r"'([A-Za-z0-9_]+)'", block))


def lua_toggle_keys(source):
    block = source.split("desiredFeatures = {", 1)[1].split("},", 1)[0]
    return set(re.findall(r"([A-Za-z0-9_]+) = false", block))


swift_features = swift_enum_cases(swift_types)
python_features = python_toggle_keys(backend_schema)
lua_features = lua_toggle_keys(lua)

assert python_features <= swift_features
assert python_features <= lua_features
assert lua_features <= python_features

multiplier_block = backend_schema.split("MULTIPLIER_RULES = {", 1)[1].split("}", 1)[0]
python_multipliers = set(re.findall(r"'([A-Za-z0-9_]+)':", multiplier_block))

for key in ("damageMultiplier", "moneyMultiplier", "resourceMultiplier"):
    assert key in python_multipliers
    assert key in lua

assert "gameSpeed" in backend_schema

print("hades2_feature_identity_parity_ok")
