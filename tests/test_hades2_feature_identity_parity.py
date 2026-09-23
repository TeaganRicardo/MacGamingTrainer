from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


swift_types = read("Sources/Hades2/Hades2Types.swift")
backend_schema = read("Backend/games/hades2/schema.py")
lua = read("Backend/games/hades2/runtime/hades.lua")
adapter = read("Backend/games/hades2/adapter.py")


def swift_enum_cases(source):
    block = source.split("enum Hades2FeatureKey", 1)[1].split("}", 1)[0]
    return set(re.findall(r"case ([A-Za-z0-9_]+)", block))


def python_tuple(source, name):
    block = source.split(f"{name} = (", 1)[1].split(")", 1)[0]
    return set(re.findall(r"'([A-Za-z0-9_]+)'", block))


def lua_desired_keys(source):
    block = source.split("desiredFeatures = {", 1)[1].split("},", 1)[0]
    return set(re.findall(r"([A-Za-z0-9_]+) = false", block))


swift_features = swift_enum_cases(swift_types)
python_features = python_tuple(backend_schema, "TOGGLES")
lua_features = lua_desired_keys(lua)

assert swift_features == python_features == lua_features

python_multiplier_block = backend_schema.split("MULTIPLIER_RULES = {", 1)[1].split("}", 1)[0]
python_multipliers = set(re.findall(r"'([A-Za-z0-9_]+)':", python_multiplier_block))

lua_multiplier_branch = lua.split('if feature == "damageMultiplier"', 1)[1].split("then", 1)[0]
lua_multipliers = {"damageMultiplier", "moneyMultiplier", "resourceMultiplier"}
assert lua_multipliers <= python_multipliers
assert all(key in lua for key in lua_multipliers)

assert 'if key==\'gameSpeed\':continue' in adapter or "if key == 'gameSpeed':continue" in adapter
assert 'feature == "gameSpeed"' in adapter

print("hades2_feature_identity_parity_ok")
