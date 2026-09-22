from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.schema import (
    MULTIPLIERS,
    TOGGLES,
    desired_feature_defaults,
    normalize_desired_feature_value,
    validate_desired_feature_value,
)
from games.hades2.preferences import Hades2PreferenceStore

EXPECTED_DEFAULTS = {
    "godMode": False,
    "infiniteHealth": False,
    "infiniteMana": False,
    "damageEnabled": False,
    "instantCastCooldown": False,
    "hexAlwaysReady": False,
    "infiniteAmmo": False,
    "autoMiniGames": False,
    "gardenQoL": False,
    "boonRarityEnabled": False,
    "moneyMultiplierEnabled": False,
    "resourceMultiplierEnabled": False,
    "damageMultiplier": 2.0,
    "moneyMultiplier": 2.0,
    "resourceMultiplier": 2.0,
    "gameSpeed": 1.0,
}

defaults = desired_feature_defaults()
assert defaults == EXPECTED_DEFAULTS
assert set(defaults) == set(TOGGLES) | set(MULTIPLIERS)

# Toggle values are exact booleans. Numeric truthy values must not silently
# become durable feature intent.
assert normalize_desired_feature_value("godMode", True) is True
assert normalize_desired_feature_value("godMode", False) is False
for value in (1, 0, "true", None):
    assert normalize_desired_feature_value("godMode", value) is None

# Multipliers share one normalization contract between Host commands and
# persisted desired state.
assert normalize_desired_feature_value("damageMultiplier", 1) == 1.0
assert normalize_desired_feature_value("damageMultiplier", 100) == 100.0
assert normalize_desired_feature_value("gameSpeed", 0) == 0.0
assert normalize_desired_feature_value("gameSpeed", 10) == 10.0
for feature, value in (
    ("damageMultiplier", 0.999),
    ("damageMultiplier", 100.001),
    ("gameSpeed", -0.001),
    ("gameSpeed", 10.001),
    ("gameSpeed", float("nan")),
    ("moneyMultiplier", float("inf")),
    ("unknown", 1),
):
    assert normalize_desired_feature_value(feature, value) is None

assert validate_desired_feature_value("godMode", True) is True
validated_damage = validate_desired_feature_value("damageMultiplier", 3)
assert validated_damage == 3 and type(validated_damage) is int
assert validate_desired_feature_value("gameSpeed", 1.5) == 1.5

cases = (
    ("unknown", True, "未知功能。"),
    ("godMode", 1, "开关值必须为布尔值。"),
    ("damageMultiplier", float("nan"), "倍率必须为有限数值。"),
    ("gameSpeed", 11, "游戏速度范围为 0–10。"),
    ("resourceMultiplier", 0, "倍率范围为 1–100。"),
)
for feature, value, message in cases:
    try:
        validate_desired_feature_value(feature, value)
    except ValueError as error:
        assert str(error) == message
    else:
        raise AssertionError(f"invalid desired feature accepted: {feature}={value!r}")

# Preference defaults must expose the same canonical values instead of
# maintaining a parallel set of feature defaults.
stored_defaults = Hades2PreferenceStore.defaults()
assert {key: stored_defaults[key] for key in EXPECTED_DEFAULTS} == EXPECTED_DEFAULTS

normalized = Hades2PreferenceStore.normalize({
    "godMode": True,
    "damageMultiplier": 4,
    "gameSpeed": 2,
})
assert normalized["godMode"] is True
assert normalized["damageMultiplier"] == 4.0
assert normalized["gameSpeed"] == 2.0

print("hades2_desired_feature_schema_ok")
