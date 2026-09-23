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

lua_multipliers = {"damageMultiplier", "moneyMultiplier", "resourceMultiplier"}
assert lua_multipliers <= python_multipliers
assert all(key in lua for key in lua_multipliers)

# gameSpeed is intentionally routed through the time-warp adapter rather than
# the regular Lua feature toggle path. Keep the contract test focused on that
# routing boundary instead of formatting details in implementation text.
assert "gameSpeed" in backend_schema
assert "_time_warp_speed" in adapter

print("hades2_feature_identity_parity_ok")
