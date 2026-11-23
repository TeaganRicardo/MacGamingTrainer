"""Contract and behavior tests for Core VersionedDocumentStore, ProfileStore, and Hades I D4 shortcuts."""

import json
import logging
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.adapter import AdapterError, GameAdapterContext
from core.persistence import ProfileStore, VersionedDocumentStore, normalize_shortcut_map
from games.hades.adapter import HadesAdapter
from games.hades.preferences import HadesPreferenceStore
from games.hades.schema import DEFAULT_FEATURES, DEFAULT_PREFERENCES


class _FakeHadesRuntime:
    def __init__(self):
        self.connected = False
        self.calls = []
        self.speed = 1.0
        self.features = dict(DEFAULT_FEATURES)

    def status(self):
        return {
            "connected": self.connected,
            "pid": 42 if self.connected else None,
            "heroReady": self.connected,
            "target": {"heroId": "run:hero:1"} if self.connected else None,
            "features": dict(self.features),
            "health": 50,
            "money": 25,
        }

    def command(self, command, params):
        self.calls.append((command, params))
        self.features = dict(params["features"])
        return self.status()

    def current_game_speed(self):
        return self.speed

    def set_game_speed(self, value):
        self.speed = value
        return value


def _chord(code: int, label: str, modifiers: int = 6144) -> dict:
    return {"keyCode": code, "modifiers": modifiers, "keyLabel": label}


with tempfile.TemporaryDirectory(prefix="mgt-core-stores-") as temporary:
    root = Path(temporary)

    # 1. Core VersionedDocumentStore: fallback mode quarantines corrupt JSON,
    # refuses newer schema without overwriting, and uses caller error keys.
    doc_path = root / "doc.json"

    class CustomSchemaError(RuntimeError):
        def __init__(self, found, supported):
            super().__init__(f"custom.error.schema.{found}.{supported}")
            self.found = found
            self.supported = supported

    store = VersionedDocumentStore(
        doc_path,
        schema_version=2,
        compatibility_floor=1,
        defaults=lambda: {"flag": False},
        normalize=lambda raw, version: {"flag": bool(raw.get("flag", False))},
        quarantine_corrupt=True,
        fallback_on_error=True,
        newer_schema_error=CustomSchemaError,
    )
    doc_path.write_text("{broken", encoding="utf-8")
    logging.disable(logging.CRITICAL)
    try:
        loaded, initialized = store.load()
    finally:
        logging.disable(logging.NOTSET)
    assert loaded == {"flag": False} and initialized is False
    assert not doc_path.exists()
    assert len(list(root.glob("doc.json.corrupt-*"))) == 1

    future_bytes = json.dumps({"schemaVersion": 3, "flag": True}).encode("utf-8")
    doc_path.write_bytes(future_bytes)
    safe, initialized = store.load()
    assert safe == {"flag": False} and initialized is False
    assert store.unsupported_schema_version == 3
    try:
        store.save({"flag": True})
    except CustomSchemaError as error:
        assert (error.found, error.supported) == (3, 2)
    else:
        raise AssertionError("VersionedDocumentStore overwrote newer schema")
    assert doc_path.read_bytes() == future_bytes

    # Strict mode raises caller-supplied read errors on missing schema version (< floor).
    strict_path = root / "strict.json"
    strict_path.write_text(json.dumps({"flag": True}), encoding="utf-8")
    strict_store = VersionedDocumentStore(
        strict_path,
        schema_version=2,
        compatibility_floor=1,
        defaults=lambda: {"flag": False},
        normalize=lambda raw, version: {"flag": bool(raw["flag"])},
        quarantine_corrupt=False,
        fallback_on_error=False,
        newer_schema_error=CustomSchemaError,
        older_schema_error=lambda found, supported: KeyError(f"old:{found}"),
    )
    try:
        strict_store.load()
    except KeyError as error:
        assert "old:0" in str(error)
    else:
        raise AssertionError("missing schemaVersion below floor succeeded in strict mode")

    # 2. Core ProfileStore: name sanitization, envelope guards, shortcuts normalization.
    profiles = ProfileStore(
        root / "profiles",
        schema_version=2,
        compatibility_floor=1,
        payload_key="settings",
        normalize_payload=lambda payload, version: {"x": int(payload["x"])},
        prepare_save_payload=lambda payload: {"x": int(payload["x"])},
        game_id="samplegame",
        slug_length=16,
        retired_shortcut_actions=("retiredAction",),
        invalid_name_error=lambda reason: ValueError(f"name.{reason}"),
        not_found_error=lambda name: FileNotFoundError(name),
        newer_schema_error=CustomSchemaError,
    )
    for bad_name, expected in ((123, "name.non_string"), ("../bad", "name.separator"), ("", "name.length")):
        try:
            profiles.sanitize_name(bad_name)
        except ValueError as error:
            assert str(error) == expected
        else:
            raise AssertionError((bad_name, expected))

    rows = profiles.save(
        "  Run Build  ",
        {"x": 42},
        {"_layoutVersion": 1, "invincibility": _chord(18, "1"), "retiredAction": _chord(19, "2")},
    )
    assert [row["name"] for row in rows] == ["Run Build"]
    loaded_profile = profiles.load("Run Build")
    assert loaded_profile["settings"] == {"x": 42}
    assert loaded_profile["shortcuts"] == {"_layoutVersion": 1, "invincibility": _chord(18, "1")}

    # Wrong gameID fails validation and quarantines corrupt envelope.
    wrong_game = profiles.path("wrong-game")
    wrong_game.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "gameID": "othergame",
                "name": "wrong-game",
                "updatedAt": "2026-11-23T00:00:00+00:00",
                "settings": {"x": 1},
            }
        ),
        encoding="utf-8",
    )
    logging.disable(logging.CRITICAL)
    try:
        try:
            profiles.load("wrong-game")
        except ValueError:
            pass
        else:
            raise AssertionError("ProfileStore loaded mismatched gameID")
    finally:
        logging.disable(logging.NOTSET)
    assert not wrong_game.exists()
    assert len(list((root / "profiles").glob(wrong_game.name + ".corrupt-*"))) == 1

    # 3. D4 parity in Hades I adapter: profiles store and replay optional shortcuts,
    # while legacy Hades I profiles without shortcuts return an empty map.
    hades_data = root / "hades-data"
    hades_context = GameAdapterContext("hades", "Hades", 2, ROOT / "Backend/games/hades", {})
    hades_runtime = _FakeHadesRuntime()
    hades_adapter = HadesAdapter(
        hades_context,
        runtime=hades_runtime,
        preferences=HadesPreferenceStore(hades_data / "preferences.json"),
        locate_process=lambda: (42, "/tmp/Hades/Game.macOS"),
    )
    shortcut_patch = {
        "_layoutVersion": 1,
        "invincibility": _chord(99, "F3", modifiers=1 << 8 | 1 << 12),
    }
    hades_adapter.dispatch("set_feature", {"feature": "invincibility", "value": True}, "feat-on")
    saved_profiles = hades_adapter.dispatch(
        "save_profile", {"name": "With Shortcuts", "shortcuts": shortcut_patch}, "save-shortcuts"
    )["profiles"]
    assert [row["name"] for row in saved_profiles] == ["With Shortcuts"]
    loaded_hades = hades_adapter.dispatch("load_profile", {"name": "With Shortcuts"}, "load-shortcuts")
    assert loaded_hades["shortcuts"] == shortcut_patch

    # Non-dict shortcuts input is rejected instead of being ignored.
    try:
        hades_adapter.dispatch("save_profile", {"name": "Bad Shortcuts", "shortcuts": ["not-a-dict"]}, "bad-shortcuts")
    except AdapterError as error:
        assert error.code == "invalid_value"
    else:
        raise AssertionError("invalid Hades I shortcuts payload was accepted")

    # Legacy Hades I profile without shortcuts key returns empty shortcuts (D4).
    legacy_path = hades_adapter.profiles.path("Legacy No Shortcuts")
    legacy_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "gameID": "hades",
                "name": "Legacy No Shortcuts",
                "updatedAt": "2026-11-22T00:00:00+00:00",
                "features": dict(DEFAULT_PREFERENCES),
            }
        ),
        encoding="utf-8",
    )
    loaded_legacy = hades_adapter.dispatch("load_profile", {"name": "Legacy No Shortcuts"}, "load-legacy")
    assert loaded_legacy["shortcuts"] == {}
    assert normalize_shortcut_map({"bad key": _chord(18, "1")}) == {}

print("core_persistence_stores_ok")
