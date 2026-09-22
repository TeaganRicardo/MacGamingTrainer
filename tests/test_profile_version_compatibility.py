from pathlib import Path
import json
import logging
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.persistence import UnsupportedSchemaVersionError
from games.hades2.preferences import DESIRED_STATE_SCHEMA_VERSION, Hades2PreferenceStore
from games.hades2.profile_service import (
    PROFILE_COMPATIBILITY_FLOOR,
    PROFILE_SCHEMA_VERSION,
    Hades2ProfileService,
)


FIXTURES = ROOT / "tests/fixtures/hades2/profiles"
assert PROFILE_SCHEMA_VERSION == 5
assert PROFILE_COMPATIBILITY_FLOOR == 3
assert DESIRED_STATE_SCHEMA_VERSION == 4

fixture_paths = sorted(FIXTURES.glob("profile-v*.json"))
fixture_versions = {
    json.loads(path.read_text(encoding="utf-8"))["schemaVersion"]
    for path in fixture_paths
}
assert set(range(PROFILE_COMPATIBILITY_FLOOR, PROFILE_SCHEMA_VERSION)) <= fixture_versions, (
    "every historical Profile version must retain a compatibility fixture before the schema can advance"
)


def canonical_desired(raw, schema_version, root):
    path = root / f"desired-v{schema_version}.json"
    document = dict(raw)
    document["schemaVersion"] = schema_version
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    loaded, initialized = Hades2PreferenceStore(path).load()
    assert initialized is True
    return loaded


base = Path(tempfile.mkdtemp(prefix="mgt-profile-version-compat-"))
service = Hades2ProfileService(base / "profiles")

loaded_by_name = {}
for fixture_path in fixture_paths:
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    path = service.path(payload["name"])
    original_bytes = fixture_path.read_bytes()
    path.write_bytes(original_bytes)

    loaded = service.load(payload["name"])
    loaded_by_name[payload["name"]] = loaded
    assert path.read_bytes() == original_bytes, "historical Profile load must be non-destructive"

    if payload["schemaVersion"] == 3:
        source_desired_schema = 3
    elif payload["schemaVersion"] == 4:
        source_desired_schema = 4 if "nextRoomRewardToken" in payload["desired"] else 3
    else:
        raise AssertionError(f"unexpected historical fixture version: {payload['schemaVersion']}")

    expected = canonical_desired(payload["desired"], source_desired_schema, base)
    assert loaded["desired"] == expected, (
        f"{fixture_path.name}: Profile desired migration diverged from desired-state migration"
    )

rows = {row["name"]: row for row in service.list()}
assert {"release-0.1-v3", "profile-v4-desired-v3", "profile-v4-desired-v4"} <= set(rows)

v3_shortcuts = loaded_by_name["release-0.1-v3"]["shortcuts"]
assert v3_shortcuts["godMode"] == {"keyCode": 18, "modifiers": 6144, "keyLabel": "1"}
assert v3_shortcuts["infiniteHealth"] == {"keyCode": 19, "modifiers": 6144, "keyLabel": "2"}
assert v3_shortcuts["disableAll"] == {"keyCode": 29, "modifiers": 6144, "keyLabel": "0"}

assert loaded_by_name["profile-v4-desired-v3"]["desired"]["nextRoomRewardToken"].startswith("legacy-")
assert (
    loaded_by_name["profile-v4-desired-v4"]["desired"]["nextRoomRewardToken"]
    == "profile-existing-v4-token"
)

service.save("current-v5", {"godMode": True}, {})
current_path = service.path("current-v5")
current_doc = json.loads(current_path.read_text(encoding="utf-8"))
assert current_doc["schemaVersion"] == PROFILE_SCHEMA_VERSION
assert current_doc["desiredSchemaVersion"] == DESIRED_STATE_SCHEMA_VERSION
assert set(current_doc) == {
    "schemaVersion", "desiredSchemaVersion", "name", "updatedAt", "desired", "shortcuts"
}
assert service.load("current-v5")["desired"] == canonical_desired(
    current_doc["desired"], DESIRED_STATE_SCHEMA_VERSION, base
)

embedded_old = service.path("embedded-old")
embedded_old.write_text(json.dumps({
    "schemaVersion": PROFILE_SCHEMA_VERSION,
    "desiredSchemaVersion": 3,
    "name": "embedded-old",
    "updatedAt": "2026-09-23T00:00:00+0000",
    "desired": {"godMode": True, "nextRoomReward": "RoomMoneyDrop"},
}), encoding="utf-8")
assert service.load("embedded-old")["desired"] == canonical_desired(
    {"godMode": True, "nextRoomReward": "RoomMoneyDrop"}, 3, base
)

future_desired_path = service.path("future-desired")
future_desired_doc = {
    "schemaVersion": PROFILE_SCHEMA_VERSION,
    "desiredSchemaVersion": DESIRED_STATE_SCHEMA_VERSION + 1,
    "name": "future-desired",
    "updatedAt": "2026-09-23T00:00:00+0000",
    "desired": {"future": True},
}
future_desired_bytes = json.dumps(future_desired_doc, sort_keys=True).encode("utf-8")
future_desired_path.write_bytes(future_desired_bytes)
try:
    service.load("future-desired")
except UnsupportedSchemaVersionError as error:
    assert error.kind == "Profile desired-state"
else:
    raise AssertionError("future embedded desired schema was accepted")
assert future_desired_path.read_bytes() == future_desired_bytes
assert not list((base / "profiles").glob(future_desired_path.name + ".corrupt-*"))

future_path = service.path("future-profile")
future_doc = {
    "schemaVersion": PROFILE_SCHEMA_VERSION + 1,
    "name": "future-profile",
    "updatedAt": "2026-09-23T00:00:00+0000",
    "desired": {"future": True},
}
future_bytes = json.dumps(future_doc, sort_keys=True).encode("utf-8")
future_path.write_bytes(future_bytes)
for operation in (
    lambda: service.load("future-profile"),
    lambda: service.save("future-profile", {"godMode": False}, {}),
):
    try:
        operation()
    except UnsupportedSchemaVersionError as error:
        assert error.kind == "Profile"
    else:
        raise AssertionError("future Profile schema was accepted or overwritten")
    assert future_path.read_bytes() == future_bytes
assert not list((base / "profiles").glob(future_path.name + ".corrupt-*"))

unsupported_path = service.path("unsupported-old")
unsupported_bytes = json.dumps({
    "schemaVersion": PROFILE_COMPATIBILITY_FLOOR - 1,
    "name": "unsupported-old",
    "updatedAt": "2026-09-23T00:00:00+0000",
    "desired": {},
}, sort_keys=True).encode("utf-8")
unsupported_path.write_bytes(unsupported_bytes)
try:
    service.load("unsupported-old")
except UnsupportedSchemaVersionError:
    pass
else:
    raise AssertionError("unsupported old numeric Profile schema was accepted")
assert unsupported_path.read_bytes() == unsupported_bytes

logging.disable(logging.CRITICAL)
try:
    corrupt_path = service.path("corrupt-schema")
    corrupt_path.write_text(json.dumps({
        "schemaVersion": "five",
        "name": "corrupt-schema",
        "updatedAt": "2026-09-23T00:00:00+0000",
        "desired": {},
    }), encoding="utf-8")
    try:
        service.load("corrupt-schema")
    except ValueError:
        pass
    else:
        raise AssertionError("malformed Profile schema identity was not treated as corrupt")
    assert not corrupt_path.exists()
    assert len(list((base / "profiles").glob(corrupt_path.name + ".corrupt-*"))) == 1
finally:
    logging.disable(logging.NOTSET)

print("profile_version_compatibility_ok")
