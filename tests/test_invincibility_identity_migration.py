import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.command_contract import Hades2CommandContract
from games.hades2.preferences import (
    DESIRED_STATE_SCHEMA_VERSION,
    Hades2PreferenceStore,
    normalize_persisted_desired,
)
from games.hades2.profile_service import PROFILE_SCHEMA_VERSION, Hades2ProfileService

assert DESIRED_STATE_SCHEMA_VERSION == 8
assert PROFILE_SCHEMA_VERSION == 6

legacy_desired = {"godMode": True, "gardenQoL": True}
migrated = normalize_persisted_desired(legacy_desired, 4)
assert migrated["invincibility"] is True
assert migrated["gardenQoL"] is True
assert "godMode" not in migrated

current = normalize_persisted_desired(
    {"godMode": True, "invincibility": False}, DESIRED_STATE_SCHEMA_VERSION
)
assert current["invincibility"] is False
assert "godMode" not in current

class DesiredProbe:
    def __init__(self):
        self.calls = []

    def set_desired(self, feature, value):
        self.calls.append((feature, value))
        return {"feature": feature, "value": value}


probe = DesiredProbe()
contract = Hades2CommandContract(probe)
assert contract.dispatch(
    "set_desired", {"feature": "invincibility", "value": True}, "current"
) == {"feature": "invincibility", "value": True}
assert probe.calls == [("invincibility", True)]
try:
    contract.dispatch(
        "set_desired", {"feature": "godMode", "value": True}, "legacy"
    )
except Exception as error:
    assert (getattr(error, "diagnostic", None) or str(error)) == "未知功能。"
else:
    raise AssertionError("legacy godMode remained a live current-protocol alias")

base = Path(tempfile.mkdtemp(prefix="mgt-invincibility-migration-"))
service = Hades2ProfileService(base / "profiles")
legacy_profile_path = service.path("legacy-v5")
legacy_chord = {"keyCode": 7, "modifiers": 768, "keyLabel": "X"}
legacy_profile_path.write_text(json.dumps({
    "schemaVersion": 5,
    "desiredSchemaVersion": 4,
    "name": "legacy-v5",
    "updatedAt": "2026-09-30T00:00:00+0000",
    "desired": {"godMode": True, "gardenQoL": True},
    "shortcuts": {
        "godMode": legacy_chord,
        "disableAll": {"keyCode": 38, "modifiers": 6144, "keyLabel": "J"},
    },
}, ensure_ascii=False), encoding="utf-8")

loaded = service.load("legacy-v5")
assert loaded["desired"]["invincibility"] is True
assert "godMode" not in loaded["desired"]
assert loaded["shortcuts"]["invincibility"] == legacy_chord
assert "godMode" not in loaded["shortcuts"]
assert loaded["shortcuts"]["disableAll"]["keyLabel"] == "J"

service.save("current-v6", {"invincibility": True}, {"invincibility": legacy_chord})
current_path = service.path("current-v6")
document = json.loads(current_path.read_text(encoding="utf-8"))
assert document["schemaVersion"] == PROFILE_SCHEMA_VERSION
assert document["desiredSchemaVersion"] == DESIRED_STATE_SCHEMA_VERSION
assert document["desired"]["invincibility"] is True
assert "godMode" not in document["desired"]
assert document["shortcuts"]["invincibility"] == legacy_chord
assert "godMode" not in document["shortcuts"]

print("invincibility_identity_migration_ok")
