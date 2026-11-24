import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.persistence import UnsupportedSchemaVersionError
from games.hades2.preferences import (
    DESIRED_STATE_SCHEMA_VERSION,
    Hades2PreferenceStore,
    normalize_persisted_desired,
)
from games.hades2.schema import (
    MULTIPLIERS,
    TOGGLES,
    desired_feature_defaults,
    is_known_element,
    normalize_desired_feature_value,
    validate_desired_feature_value,
)

assert DESIRED_STATE_SCHEMA_VERSION == 13

EXPECTED_DEFAULTS = {
    "invincibility": False,
    "infiniteHealth": False,
    "infiniteMana": False,
    "infiniteMoney": False,
    "infiniteRerolls": False,
    "instantCastCooldown": False,
    "hexAlwaysReady": False,
    "infiniteAmmo": False,
    "autoMiniGames": False,
    "boonRarityEnabled": False,
    "forceEnableRerolls": False,
    "moneyMultiplierEnabled": False,
    "resourceMultiplierEnabled": False,
    "damageMultiplier": 1.0,
    "moneyMultiplier": 2.0,
    "resourceMultiplier": 2.0,
    "gameSpeed": 1.0,
}

defaults = desired_feature_defaults()
assert defaults == EXPECTED_DEFAULTS
assert set(defaults) == set(TOGGLES) | set(MULTIPLIERS)

# Toggle values are exact booleans. Numeric truthy values must not silently
# become durable feature intent.
assert normalize_desired_feature_value("invincibility", True) is True
assert normalize_desired_feature_value("invincibility", False) is False
assert normalize_desired_feature_value("damageEnabled", True) is None
for value in (1, 0, "true", None):
    assert normalize_desired_feature_value("invincibility", value) is None

# Canonical schema predicates are total over arbitrary JSON-compatible keys.
for malformed_feature in ([], {}):
    assert normalize_desired_feature_value(malformed_feature, True) is None
    try:
        validate_desired_feature_value(malformed_feature, True)
    except ValueError as error:
        assert str(error) == "未知功能。"
    else:
        raise AssertionError(f"malformed feature accepted: {malformed_feature!r}")
for malformed_element in ([], {}):
    assert is_known_element(malformed_element) is False

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

assert validate_desired_feature_value("invincibility", True) is True
validated_damage = validate_desired_feature_value("damageMultiplier", 3)
assert validated_damage == 3 and type(validated_damage) is int
assert validate_desired_feature_value("gameSpeed", 1.5) == 1.5

cases = (
    ("unknown", True, "未知功能。"),
    ("damageEnabled", True, "未知功能。"),
    ("invincibility", 1, "开关值必须为布尔值。"),
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

# Force Enable Rerolls did not exist before desired schema 8. Older documents
# must not reinterpret unrelated historical bytes as opt-in intent.
assert normalize_persisted_desired({"forceEnableRerolls": True}, 7)["forceEnableRerolls"] is False
assert normalize_persisted_desired({"forceEnableRerolls": True}, 8)["forceEnableRerolls"] is True

normalized = Hades2PreferenceStore.normalize({
    "invincibility": True,
    "damageMultiplier": 4,
    "gameSpeed": 2,
})
assert normalized["invincibility"] is True
assert normalized["damageMultiplier"] == 4.0
assert normalized["gameSpeed"] == 2.0

print("hades2_desired_feature_schema_ok")

# Damage multiplier is the only durable source of truth; historical schema < 13
# migrates old damageEnabled / gardenQoL documents once and drops those keys.
for legacy_version in (10, 12):
    legacy_disabled = normalize_persisted_desired(
        {"damageEnabled": False, "damageMultiplier": 3.0, "gardenQoL": True},
        legacy_version,
    )
    assert legacy_disabled["damageMultiplier"] == 1.0
    assert "damageEnabled" not in legacy_disabled
    assert "gardenQoL" not in legacy_disabled

    legacy_enabled = normalize_persisted_desired(
        {"damageEnabled": True, "damageMultiplier": 3.0},
        legacy_version,
    )
    assert legacy_enabled["damageMultiplier"] == 3.0
    assert "damageEnabled" not in legacy_enabled

    legacy_default = normalize_persisted_desired(
        {"damageEnabled": True},
        legacy_version,
    )
    assert legacy_default["damageMultiplier"] == 2.0
    assert "damageEnabled" not in legacy_default

    # An explicit 1x is normal damage even when an old profile left the toggle on:
    # migration must not silently upgrade it to the historical 2x default.
    legacy_explicit_one = normalize_persisted_desired(
        {"damageEnabled": True, "damageMultiplier": 1.0},
        legacy_version,
    )
    assert legacy_explicit_one["damageMultiplier"] == 1.0
    assert "damageEnabled" not in legacy_explicit_one

# Current-schema normalization treats damageEnabled as a retired unknown key:
# it neither vetoes an explicit multiplier nor resurrects a 2x default.
current_veto_ignored = Hades2PreferenceStore.normalize({"damageEnabled": False, "damageMultiplier": 3.0})
assert current_veto_ignored["damageMultiplier"] == 3.0
assert "damageEnabled" not in current_veto_ignored
current_enable_ignored = Hades2PreferenceStore.normalize({"damageEnabled": True})
assert current_enable_ignored["damageMultiplier"] == 1.0
assert "damageEnabled" not in current_enable_ignored
current_v13 = normalize_persisted_desired(
    {"schemaVersion": DESIRED_STATE_SCHEMA_VERSION, "damageEnabled": False, "damageMultiplier": 4.0},
    DESIRED_STATE_SCHEMA_VERSION,
)
assert current_v13["damageMultiplier"] == 4.0
assert "damageEnabled" not in current_v13

# Future desired schema versions must be refused rather than coerced.
try:
    normalize_persisted_desired(
        {"schemaVersion": DESIRED_STATE_SCHEMA_VERSION + 1, "damageMultiplier": 5.0},
        DESIRED_STATE_SCHEMA_VERSION + 1,
    )
except UnsupportedSchemaVersionError as error:
    assert error.found == DESIRED_STATE_SCHEMA_VERSION + 1
else:
    raise AssertionError("future desired schema version was accepted")
