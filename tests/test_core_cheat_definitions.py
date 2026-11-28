"""Core declarative cheat catalog, migration, and Hades parity checks."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
sys.path.insert(0, str(ROOT / "tests"))

from core.adapter import AdapterError, GameAdapterContext  # noqa: E402
from core.cheats import (  # noqa: E402
    CheatBackendAction,
    CheatCatalog,
    CheatDefinition,
    CheatLabel,
)
from games.hades.adapter import HadesAdapter  # noqa: E402
from games.hades.cheats import HADES_CHEAT_CATALOG  # noqa: E402
from games.hades.command_contract import COMMAND_SPECS  # noqa: E402
from games.hades.preferences import HadesPreferenceStore  # noqa: E402
from games.hades.profiles import HadesProfileStore  # noqa: E402
from games.hades.schema import DEFAULT_FEATURES, DEFAULT_PREFERENCES, PREFERENCE_SCHEMA_VERSION  # noqa: E402
from games.hades2.cheats import HADES2_CHEAT_CATALOG  # noqa: E402
from games.hades2.command_contract import COMMAND_SPECS as HADES2_COMMAND_SPECS  # noqa: E402
from games.hades2.profile_service import (  # noqa: E402
    PROFILE_SCHEMA_VERSION as HADES2_PROFILE_SCHEMA_VERSION,
    Hades2ProfileService,
)
from games.hades2.schema import MULTIPLIER_RULES as HADES2_MULTIPLIER_RULES  # noqa: E402
from games.hades2.schema import STAT_RULES as HADES2_STAT_RULES  # noqa: E402
from games.hades2.schema import TOGGLES as HADES2_TOGGLES  # noqa: E402
from games.hades2.persistence import UnsupportedSchemaVersionError  # noqa: E402
from swift_test_compiler import SWIFT_CORE_MODULE, SwiftModule, compile_swift_test  # noqa: E402


def _assert_raises_value_error(fn, message: str) -> None:
    try:
        fn()
    except ValueError:
        return
    raise AssertionError(message)


# 1. Core Python CheatCatalog validation and migration helpers.
valid_catalog = CheatCatalog(
    (
        CheatDefinition(
            id="infiniteHealth",
            kind="toggle",
            label=CheatLabel(zh_cn="无限生命", en="Infinite Life"),
            action=CheatBackendAction("set_feature", {"feature": "infiniteHealth"}, "value"),
            shortcut_id="infiniteHealth",
            aliases=("fullHealth",),
            default_value=False,
        ),
        CheatDefinition(
            id="gameSpeed",
            kind="value",
            label=CheatLabel(zh_cn="游戏速度", en="Game Speed"),
            action=CheatBackendAction("set_feature", {"feature": "gameSpeed"}, "value"),
            default_value=1.0,
        ),
        CheatDefinition(
            id="healthLock",
            kind="lock",
            label=CheatLabel(zh_cn="锁定生命值", en="Lock Life"),
            action=CheatBackendAction("lock_vital", {"vital": "health"}, "locked"),
        ),
        CheatDefinition(
            id="disableAll",
            kind="one_shot",
            label=CheatLabel(zh_cn="禁用全部", en="Disable All"),
            action=CheatBackendAction("disable_all"),
            shortcut_id="disableAll",
        ),
    ),
    retired_ids=("retiredToggle",),
)
assert valid_catalog.ids() == ("infiniteHealth", "gameSpeed", "healthLock", "disableAll")
assert valid_catalog.ids_for_kind("toggle") == ("infiniteHealth",)
assert valid_catalog.resolve_id("fullHealth") == "infiniteHealth"
assert valid_catalog.resolve_id("retiredToggle") is None
assert valid_catalog.definition("fullHealth").id == "infiniteHealth"
assert valid_catalog.resolve_shortcut_id("fullHealth") == "infiniteHealth"
valid_catalog.validate_commands({"set_feature", "lock_vital", "disable_all"})

migrated_map = valid_catalog.migrate_identity_map(
    {"fullHealth": True, "retiredToggle": True, "unknownKey": 5},
    defaults={"infiniteHealth": False, "gameSpeed": 1.0},
)
assert migrated_map == {"infiniteHealth": True, "gameSpeed": 1.0}

# Canonical key takes precedence when both canonical and legacy aliases exist.
canonical_wins = valid_catalog.migrate_identity_map(
    {"fullHealth": True, "infiniteHealth": False},
    defaults={"infiniteHealth": True, "gameSpeed": 1.0},
)
assert canonical_wins == {"infiniteHealth": False, "gameSpeed": 1.0}

migrated_shortcuts = valid_catalog.migrate_shortcut_payload(
    {
        "_layoutVersion": 1,
        "fullHealth": {"keyCode": 19, "modifiers": 6144, "keyLabel": "2"},
        "retiredToggle": {"keyCode": 20, "modifiers": 6144, "keyLabel": "3"},
    }
)
assert migrated_shortcuts == {
    "_layoutVersion": 1,
    "infiniteHealth": {"keyCode": 19, "modifiers": 6144, "keyLabel": "2"},
}

_assert_raises_value_error(
    lambda: valid_catalog.validate_commands({"set_feature"}),
    "missing command did not raise ValueError",
)
_assert_raises_value_error(
    lambda: CheatLabel(zh_cn="   ", en="Valid"),
    "blank zh_cn label accepted",
)
_assert_raises_value_error(
    lambda: CheatBackendAction(" "),
    "blank command accepted",
)
_assert_raises_value_error(
    lambda: CheatCatalog(
        (
            CheatDefinition(
                id="dup",
                kind="toggle",
                label=CheatLabel("a", "a"),
                action=CheatBackendAction("set_feature"),
            ),
            CheatDefinition(
                id="dup",
                kind="toggle",
                label=CheatLabel("b", "b"),
                action=CheatBackendAction("set_feature"),
            ),
        )
    ),
    "duplicate cheat id accepted",
)
_assert_raises_value_error(
    lambda: CheatCatalog(
        (
            CheatDefinition(
                id="badKind",
                kind="invalid",  # type: ignore[arg-type]
                label=CheatLabel("a", "a"),
                action=CheatBackendAction("set_feature"),
            ),
        )
    ),
    "invalid cheat kind accepted",
)
_assert_raises_value_error(
    lambda: CheatCatalog(
        (
            CheatDefinition(
                id="a",
                kind="toggle",
                label=CheatLabel("a", "a"),
                action=CheatBackendAction("set_feature"),
                shortcut_id="same",
            ),
            CheatDefinition(
                id="b",
                kind="toggle",
                label=CheatLabel("b", "b"),
                action=CheatBackendAction("set_feature"),
                shortcut_id="same",
            ),
        )
    ),
    "duplicate shortcut_id accepted",
)
_assert_raises_value_error(
    lambda: CheatCatalog(
        (
            CheatDefinition(
                id="a",
                kind="toggle",
                label=CheatLabel("a", "a"),
                action=CheatBackendAction("set_feature"),
                aliases=("b",),
            ),
            CheatDefinition(
                id="b",
                kind="toggle",
                label=CheatLabel("b", "b"),
                action=CheatBackendAction("set_feature"),
            ),
        )
    ),
    "alias colliding with canonical id accepted",
)
_assert_raises_value_error(
    lambda: CheatCatalog(
        (
            CheatDefinition(
                id="a",
                kind="toggle",
                label=CheatLabel("a", "a"),
                action=CheatBackendAction("set_feature"),
                aliases=("shared",),
            ),
            CheatDefinition(
                id="b",
                kind="toggle",
                label=CheatLabel("b", "b"),
                action=CheatBackendAction("set_feature"),
                aliases=("shared",),
            ),
        )
    ),
    "duplicate alias across definitions accepted",
)
_assert_raises_value_error(
    lambda: CheatCatalog(
        (
            CheatDefinition(
                id="a",
                kind="toggle",
                label=CheatLabel("a", "a"),
                action=CheatBackendAction("set_feature"),
                aliases=("retired",),
            ),
        ),
        retired_ids=("retired",),
    ),
    "retired alias collision accepted",
)


# 2. Hades I catalog validation, schema migrations, and runtime translation.
HADES_CHEAT_CATALOG.validate_commands(COMMAND_SPECS)
assert PREFERENCE_SCHEMA_VERSION == 6

to_legacy = HADES_CHEAT_CATALOG.alias_map()
canonical_to_legacy = {canonical: alias for alias, canonical in to_legacy.items()}


class FakeRuntime:
    def __init__(self) -> None:
        self.connected = False
        self.events: list[tuple[str, object]] = []
        self.speed = 1.0
        self.state: dict[str, object] = {
            "connected": False,
            "heroReady": True,
            "invincible": False,
            "health": 80,
            "maxHealth": 100,
            "money": 250,
            "rerolls": 3,
            "godGauge": 0,
            "boonRarityTarget": "Heroic",
            "healthLocked": False,
            "moneyLocked": False,
            "rerollsLocked": False,
            "features": {},
            "activeFeatures": {},
            "dormantFeatures": {},
            "resources": {},
            "traits": [],
            "world": None,
            "pid": 77,
            "target": {"heroId": "run:hero:1"},
        }

    def status(self):
        return {**self.state, "connected": self.connected}

    def connect(self, _pid, _exe, features=None):
        self.events.append(("connect", dict(features or {})))
        self.connected = True
        self.state["connected"] = True
        self.state["features"] = dict(features or {})
        self.state["activeFeatures"] = {"fullHealth": bool((features or {}).get("fullHealth"))}
        self.state["dormantFeatures"] = {"forceRerolls": bool((features or {}).get("forceRerolls"))}
        return self.status()

    def set_game_speed(self, value: float):
        self.events.append(("set_game_speed", value))
        self.speed = value
        return value

    def current_game_speed(self) -> float:
        return self.speed

    def command(self, name: str, params: dict[str, object]):
        self.events.append((name, dict(params)))
        if name == "set_feature":
            features = dict(self.state["features"])  # type: ignore[arg-type]
            features[params["feature"]] = params["value"]  # type: ignore[index]
            self.state["features"] = features
            if params["feature"] == "moneyNoDecrease" and params["value"]:
                self.state["moneyLocked"] = False
                self.state["moneyLock"] = None
            if params["feature"] == "rerollsNoDecrease" and params["value"]:
                self.state["rerollsLocked"] = False
                self.state["rerollsLock"] = None
            self.state["activeFeatures"] = {"fullHealth": bool(features.get("fullHealth"))}
        elif name == "configure":
            features = dict(params["features"])  # type: ignore[arg-type]
            self.state["features"] = features
            self.state["activeFeatures"] = {"fullHealth": bool(features.get("fullHealth"))}
        elif name == "configure_locks":
            self.state["moneyLock"] = params.get("money")
            self.state["moneyLocked"] = params.get("money") is not None
        elif name == "lock_resource":
            locked = bool(params["locked"])
            self.state["moneyLocked"] = locked
            self.state["moneyLock"] = self.state["money"] if locked else None
        elif name == "disable_all":
            self.state["features"] = {canonical_to_legacy.get(k, k): v for k, v in DEFAULT_FEATURES.items()}
            self.state["activeFeatures"] = {}
            self.state["dormantFeatures"] = {}
        return self.status()

    def disconnect(self):
        self.connected = False
        self.state["connected"] = False
        return self.status()

    def close(self) -> None:
        pass


module_protocol = json.loads((ROOT / "Backend/games/hades/module.json").read_text(encoding="utf-8"))["protocolVersion"]
assert module_protocol == 9

with tempfile.TemporaryDirectory(prefix="mgt-cheat-defs-") as td:
    root = Path(td)
    pref_store = HadesPreferenceStore(root / "preferences.json")

    # V2 legacy preference keys migrate onto canonical v6 keys while refusing v7 files read-only.
    v5_features = {
        k: v
        for k, v in DEFAULT_PREFERENCES.items()
        if k not in {
            "moneyMultiplierEnabled",
            "resourceMultiplierEnabled",
            "moneyMultiplier",
            "resourceMultiplier",
            "resourceLocks",
        }
    }
    v4_features = {
        k: v
        for k, v in v5_features.items()
        if k not in {"fishingChance", "chaosGateChance"}
    }
    v3_features = {
        k: v
        for k, v in v4_features.items()
        if k not in {"boonForceLegendary", "boonForceDuo"}
    }
    v2_features = {canonical_to_legacy.get(k, k): v for k, v in v3_features.items()}
    v2_features["fullHealth"] = True
    v2_features["moneyNoDecrease"] = True
    v2_features["forceRerolls"] = True
    # Historical schema-1 files carrying full v2 keys migrate, whereas unshipped canonical keys under schema 1 are rejected.
    pref_store.path.write_text(json.dumps({"schemaVersion": 1, "features": v2_features}), encoding="utf-8")
    assert pref_store.load()["infiniteHealth"] is True
    pref_store.path.write_text(json.dumps({"schemaVersion": 1, "features": DEFAULT_PREFERENCES}), encoding="utf-8")
    try:
        pref_store.load()
    except AdapterError as error:
        assert error.code == "preferences_failed"
    else:
        raise AssertionError("schema 1 accepted unshipped v6 canonical keys")

    pref_store.path.write_text(json.dumps({"schemaVersion": 2, "features": v2_features}), encoding="utf-8")
    migrated_prefs = pref_store.load()
    assert migrated_prefs["infiniteHealth"] is True
    assert migrated_prefs["infiniteMoney"] is True
    assert migrated_prefs["forceEnableRerolls"] is True
    assert migrated_prefs["boonForceLegendary"] is False
    assert migrated_prefs["boonForceDuo"] is False
    assert migrated_prefs["fishingChance"] is None
    assert migrated_prefs["chaosGateChance"] is None
    assert migrated_prefs["moneyMultiplier"] == 2
    assert migrated_prefs["resourceLocks"] == {}
    assert "fullHealth" not in migrated_prefs

    pref_store.path.write_text(json.dumps({"schemaVersion": 3, "features": v3_features}), encoding="utf-8")
    migrated_v3 = pref_store.load()
    assert migrated_v3["boonForceLegendary"] is False and migrated_v3["boonForceDuo"] is False
    assert migrated_v3["fishingChance"] is None and migrated_v3["chaosGateChance"] is None

    pref_store.path.write_text(json.dumps({"schemaVersion": 4, "features": v4_features}), encoding="utf-8")
    migrated_v4 = pref_store.load()
    assert migrated_v4["fishingChance"] is None and migrated_v4["chaosGateChance"] is None

    pref_store.path.write_text(json.dumps({"schemaVersion": 5, "features": v5_features}), encoding="utf-8")
    migrated_v5 = pref_store.load()
    assert migrated_v5["moneyMultiplierEnabled"] is False
    assert migrated_v5["resourceLocks"] == {}

    pref_store.path.write_text(json.dumps({"schemaVersion": 6, "features": v5_features}), encoding="utf-8")
    try:
        pref_store.load()
    except AdapterError as error:
        assert error.code == "preferences_failed"
    else:
        raise AssertionError("schema 6 accepted v5 keys missing economy modifiers")

    future_pref_payload = json.dumps({"schemaVersion": 7, "features": {"futureToggle": True}})
    pref_store.path.write_text(future_pref_payload, encoding="utf-8")
    try:
        pref_store.load()
    except AdapterError as error:
        assert error.code == "preferences_unsupported_schema"
    else:
        raise AssertionError("future v7 preferences were loaded")
    try:
        pref_store.save(migrated_prefs)
    except AdapterError as error:
        assert error.code == "preferences_unsupported_schema"
    else:
        raise AssertionError("future v7 preferences were overwritten by save")
    assert pref_store.path.read_text(encoding="utf-8") == future_pref_payload
    pref_store.path.unlink()

    # Save valid migrated prefs for adapter test.
    pref_store.save(migrated_prefs)
    context = GameAdapterContext("hades", "Hades", module_protocol, ROOT / "Backend/games/hades", {})
    runtime = FakeRuntime()
    adapter = HadesAdapter(
        context,
        runtime=runtime,
        locate_process=lambda: (77, "/tmp/Hades/Game.macOS"),
        preferences=pref_store,
    )

    state = adapter.dispatch("connect", {}, "connect")
    connect_sent = next(payload for cmd, payload in runtime.events if cmd == "connect")
    assert connect_sent["fullHealth"] is True  # type: ignore[index]
    assert connect_sent["moneyNoDecrease"] is True  # type: ignore[index]
    assert connect_sent["forceRerolls"] is True  # type: ignore[index]
    assert "infiniteHealth" not in connect_sent  # type: ignore[operator]
    assert state["features"]["infiniteHealth"] is True
    assert state["activeFeatures"] == {"infiniteHealth": True}
    assert state["dormantFeatures"] == {"forceEnableRerolls": True}

    toggled = adapter.dispatch("set_feature", {"feature": "infiniteHealth", "value": False}, "toggle-off")
    assert runtime.events[-1] == ("set_feature", {"feature": "fullHealth", "value": False})
    assert toggled["features"]["infiniteHealth"] is False

    # Turn off infiniteMoney so moneyLock can engage, then re-enabling infiniteMoney clears moneyLock.
    adapter.dispatch("set_feature", {"feature": "infiniteMoney", "value": False}, "gold-off")
    adapter.dispatch("lock_resource", {"resource": "Money", "locked": True, "target": {"heroId": "run:hero:1"}}, "lock-gold")
    assert pref_store.load()["moneyLock"] == 250
    unlocked = adapter.dispatch("set_feature", {"feature": "infiniteMoney", "value": True}, "gold-inf")
    assert runtime.events[-1] == ("set_feature", {"feature": "moneyNoDecrease", "value": True})
    assert unlocked["moneyLocked"] is False and pref_store.load()["moneyLock"] is None

    # Profile store v2 -> v3 migration preserves canonical features and migrates shortcuts.
    profiles = HadesProfileStore(root / "profiles")
    profiles.root.mkdir(parents=True, exist_ok=True)
    v2_profile = {
        "schemaVersion": 2,
        "gameID": "hades",
        "name": "Legacy",
        "updatedAt": "2026-11-24T00:00:00+00:00",
        "features": v2_features,
        "shortcuts": {
            "_layoutVersion": 1,
            "fullHealth": {"keyCode": 19, "modifiers": 6144, "keyLabel": "2"},
            "rerollsNoDecrease": {"keyCode": 21, "modifiers": 6144, "keyLabel": "4"},
        },
    }
    profiles.path("Legacy").write_text(json.dumps(v2_profile), encoding="utf-8")
    loaded = adapter.dispatch("load_profile", {"name": "Legacy"}, "load-legacy")
    assert loaded["features"]["infiniteHealth"] is True
    assert loaded["shortcuts"]["infiniteHealth"] == {"keyCode": 19, "modifiers": 6144, "keyLabel": "2"}
    assert loaded["shortcuts"]["infiniteRerolls"] == {"keyCode": 21, "modifiers": 6144, "keyLabel": "4"}
    assert "fullHealth" not in loaded["shortcuts"]
    configure_sent = [payload for cmd, payload in runtime.events if cmd == "configure"][-1]
    assert configure_sent["features"]["fullHealth"] is True  # type: ignore[index]

    future_profile = json.dumps({**v2_profile, "schemaVersion": 7, "name": "Future", "features": {"future": True}})
    profiles.path("Future").write_text(future_profile, encoding="utf-8")
    try:
        profiles.load_record("Future")
    except AdapterError as error:
        assert error.code == "profile_unsupported_schema"
    else:
        raise AssertionError("future v7 profile was loaded")
    assert profiles.path("Future").read_text(encoding="utf-8") == future_profile

from games.hades.lldb_worker import _runtime_feature_document  # noqa: E402

ambiguous_features = {**DEFAULT_FEATURES, "fullHealth": False}
try:
    _runtime_feature_document(ambiguous_features)
except AdapterError as error:
    assert error.code == "invalid_value"
else:
    raise AssertionError("ambiguous canonical+alias feature document was accepted")


# 3. Hades II catalog validation, profile migration, and bilingual label resolution.
HADES2_CHEAT_CATALOG.validate_commands(HADES2_COMMAND_SPECS)
hades2_protocol = json.loads((ROOT / "Backend/games/hades2/module.json").read_text(encoding="utf-8"))["protocolVersion"]
assert hades2_protocol == 24
assert HADES2_PROFILE_SCHEMA_VERSION == 7

for hades2_def in HADES2_CHEAT_CATALOG.definitions:
    assert hades2_def.label.zh_cn and "{term:" not in hades2_def.label.zh_cn, hades2_def.id
    assert hades2_def.label.en and "{term:" not in hades2_def.label.en, hades2_def.id
    if hades2_def.help_label is not None:
        assert hades2_def.help_label.zh_cn and "{term:" not in hades2_def.help_label.zh_cn, hades2_def.id
        assert hades2_def.help_label.en and "{term:" not in hades2_def.help_label.en, hades2_def.id

assert {
    d.id for d in HADES2_CHEAT_CATALOG.definitions if d.kind == "toggle" and d.action.command == "set_desired"
} == set(HADES2_TOGGLES)
assert (
    set(HADES2_MULTIPLIER_RULES)
    | set(HADES2_STAT_RULES)
    | {"gameSpeed", "health", "mana", "armor", "runGold", "rerolls", "spellCharge", "biomeTime"}
) == set(HADES2_CHEAT_CATALOG.ids_for_kind("value"))
assert HADES2_CHEAT_CATALOG.resolve_id("godMode") == "invincibility"
assert HADES2_CHEAT_CATALOG.resolve_id("applyNextRoomReward") == "applyWorldExit"
assert HADES2_CHEAT_CATALOG.resolve_shortcut_id("applyNextRoomReward") == "applyWorldExit"
assert HADES2_CHEAT_CATALOG.resolve_id("gardenQoL") is None
assert HADES2_CHEAT_CATALOG.resolve_id("damageEnabled") is None
assert HADES2_CHEAT_CATALOG.migrate_shortcut_payload(
    {
        "_layoutVersion": 1,
        "applyNextRoomReward": {"keyCode": 13, "modifiers": 6144, "keyLabel": "W"},
        "applyWorldExit": {"keyCode": 14, "modifiers": 6144, "keyLabel": "E"},
    }
) == {
    "_layoutVersion": 1,
    "applyWorldExit": {"keyCode": 14, "modifiers": 6144, "keyLabel": "E"},
}

with tempfile.TemporaryDirectory(prefix="mgt-hades2-cheat-defs-") as td2:
    hades2_service = Hades2ProfileService(Path(td2))
    v6_profile_path = hades2_service.path("LegacyWorldExit")
    v6_profile_path.write_text(
        json.dumps(
            {
                "schemaVersion": 6,
                "desiredSchemaVersion": 13,
                "name": "LegacyWorldExit",
                "updatedAt": "2026-11-24T12:00:00+0000",
                "desired": {"invincibility": True},
                "shortcuts": {
                    "_layoutVersion": 1,
                    "applyNextRoomReward": {"keyCode": 13, "modifiers": 6144, "keyLabel": "W"},
                    "damageEnabled": {"keyCode": 19, "modifiers": 6144, "keyLabel": "2"},
                },
            }
        ),
        encoding="utf-8",
    )
    migrated_hades2 = hades2_service.load("LegacyWorldExit")
    assert migrated_hades2["shortcuts"] == {
        "_layoutVersion": 1,
        "applyWorldExit": {"keyCode": 13, "modifiers": 6144, "keyLabel": "W"},
    }
    future_v8_path = hades2_service.path("FutureV8")
    future_v8_payload = json.dumps(
        {
            "schemaVersion": HADES2_PROFILE_SCHEMA_VERSION + 1,
            "desiredSchemaVersion": 13,
            "name": "FutureV8",
            "updatedAt": "2026-11-24T12:00:00+0000",
            "desired": {"invincibility": False},
        },
        sort_keys=True,
    ).encode("utf-8")
    future_v8_path.write_bytes(future_v8_payload)
    try:
        hades2_service.load("FutureV8")
    except UnsupportedSchemaVersionError as error:
        assert error.kind == "Profile"
    else:
        raise AssertionError("future Hades II v8 profile was loaded")
    assert future_v8_path.read_bytes() == future_v8_payload


# 4. Portable Foundation-only Swift cheat definitions and Python parity check (Hades I + Hades II).
with tempfile.TemporaryDirectory(prefix="mgt-cheat-swift-") as td:
    root = Path(td)
    catalog_json = root / "python_catalog.json"
    catalog_json.write_text(json.dumps(HADES_CHEAT_CATALOG.to_list()), encoding="utf-8")
    hades2_catalog_json = root / "hades2_python_catalog.json"
    hades2_catalog_json.write_text(json.dumps(HADES2_CHEAT_CATALOG.to_list()), encoding="utf-8")

    harness = """
import Foundation
import TrainerCore
import HadesCheatsFixture
import Hades2CheatsFixture

struct PythonCheatSpec: Decodable {
    struct ActionSpec: Decodable {
        let command: String
        let valueParam: String?
    }
    let id: String
    let kind: String
    let action: ActionSpec
    let shortcutId: String?
    let aliases: [String]?
}

enum TestAction: String, CaseIterable, Hashable {
    case infiniteHealth, infiniteMoney, disableAll
}

func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() {
        fputs("Assertion failed: \\(message)\\n", stderr)
        exit(1)
    }
}

@main
struct CheatDefinitionHarness {
    static func main() throws {
        // Validate error cases in Core Swift catalog validator.
        check(HadesCheatCatalog.catalog.validationErrors().isEmpty, "Hades catalog reported validation errors")
        check(Hades2CheatCatalog.catalog.validationErrors().isEmpty, "Hades2 catalog reported validation errors")
        check(Hades2CheatCatalog.catalog.resolveID("godMode") == "invincibility", "Hades2 godMode alias did not resolve")
        check(Hades2CheatCatalog.catalog.resolveID("applyNextRoomReward") == "applyWorldExit", "Hades2 applyNextRoomReward alias did not resolve")
        check(Hades2CheatCatalog.catalog.resolveShortcutID("applyNextRoomReward") == "applyWorldExit", "Hades2 applyNextRoomReward shortcut alias did not resolve")
        check(Hades2CheatCatalog.catalog.resolveID("gardenQoL") == nil, "Hades2 retired gardenQoL resolved")
        check(Hades2CheatCatalog.catalog.resolveID("damageEnabled") == nil, "Hades2 retired damageEnabled resolved")
        let valid = try TrainerCheatCatalog.validated(definitions: [
            TrainerCheatDefinition(
                id: "alpha",
                kind: .toggle,
                label: .bilingual(TrainerCheatText(zhCN: "甲", en: "Alpha")),
                icon: "bolt.fill",
                action: TrainerCheatActionSpec(command: "set_feature", valueParam: "value"),
                shortcutID: "alpha",
                aliases: ["oldAlpha"]
            ),
        ], retiredIDs: ["oldRetired"])
        check(valid.resolveID("oldAlpha") == "alpha", "alias did not resolve")
        check(valid.resolveShortcutID("oldAlpha") == "alpha", "shortcut alias did not resolve")

        let invalidDefs = [
            TrainerCheatDefinition(
                id: "",
                kind: .toggle,
                label: .bilingual(TrainerCheatText(zhCN: "", en: "NoZh")),
                icon: "bolt.fill",
                action: TrainerCheatActionSpec(command: " "),
                shortcutID: "",
                aliases: ["dupAlias", "dupAlias", "collision", "oldRetired"]
            ),
            TrainerCheatDefinition(
                id: "collision",
                kind: .value,
                label: .key("host.value"),
                icon: "bolt.fill",
                action: TrainerCheatActionSpec(command: "set_value"),
                shortcutID: "sameShortcut",
                aliases: ["sharedAlias"]
            ),
            TrainerCheatDefinition(
                id: "collision",
                kind: .lock,
                label: .key(" "),
                icon: "bolt.fill",
                action: TrainerCheatActionSpec(command: "lock_vital"),
                shortcutID: "sameShortcut",
                aliases: ["sharedAlias"]
            ),
        ]
        let issues = TrainerCheatCatalog.validationErrors(definitions: invalidDefs, retiredIDs: ["oldRetired"])
        check(issues.contains(.emptyID), "missing emptyID issue")
        check(issues.contains(.duplicateID("collision")), "missing duplicateID issue")
        check(issues.contains(.duplicateShortcutID("sameShortcut")), "missing duplicateShortcutID issue")
        check(issues.contains(.aliasCollidesWithCanonicalID("collision")), "missing canonical alias collision")
        check(issues.contains(.retiredIDCollision("oldRetired")), "missing retired collision")
        check(issues.contains(.duplicateAlias("sharedAlias")), "missing duplicate alias issue")

        // Verify 1:1 parity between Python and Swift catalogs (Hades I + Hades II).
        let data = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
        let pythonDefs = try JSONDecoder().decode([PythonCheatSpec].self, from: data)
        check(pythonDefs.count == HadesCheatCatalog.catalog.definitions.count, "cheat definition count drifted")
        for (py, sw) in zip(pythonDefs, HadesCheatCatalog.catalog.definitions) {
            check(py.id == sw.id, "id drifted: \\(py.id) vs \\(sw.id)")
            check(py.kind == sw.kind.rawValue, "kind drifted for \\(py.id)")
            check(py.action.command == sw.action.command, "command drifted for \\(py.id)")
            check(py.action.valueParam == sw.action.valueParam, "valueParam drifted for \\(py.id)")
            check(py.shortcutId == sw.shortcutID, "shortcutID drifted for \\(py.id)")
            check((py.aliases ?? []) == sw.aliases, "aliases drifted for \\(py.id)")
        }

        let data2 = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[2]))
        let pythonDefs2 = try JSONDecoder().decode([PythonCheatSpec].self, from: data2)
        check(pythonDefs2.count == Hades2CheatCatalog.catalog.definitions.count, "hades2 cheat definition count drifted")
        for (py, sw) in zip(pythonDefs2, Hades2CheatCatalog.catalog.definitions) {
            check(py.id == sw.id, "hades2 id drifted: \\(py.id) vs \\(sw.id)")
            check(py.kind == sw.kind.rawValue, "hades2 kind drifted for \\(py.id)")
            check(py.action.command == sw.action.command, "hades2 command drifted for \\(py.id)")
            check(py.action.valueParam == sw.action.valueParam, "hades2 valueParam drifted for \\(py.id)")
            check(py.shortcutId == sw.shortcutID, "hades2 shortcutID drifted for \\(py.id)")
            check((py.aliases ?? []) == sw.aliases, "hades2 aliases drifted for \\(py.id)")
        }

        // Verify Core TrainerShortcutStore legacy alias profile import + locked chord preservation.
        let defaults = InMemoryDefaults()
        let defaultLayout: [TestAction: HotkeyChord] = [
            .infiniteHealth: HotkeyChord(keyCode: 18, modifiers: HotkeyChord.controlModifier | HotkeyChord.optionModifier, keyLabel: "1"),
            .infiniteMoney: HotkeyChord(keyCode: 19, modifiers: HotkeyChord.controlModifier | HotkeyChord.optionModifier, keyLabel: "2"),
            .disableAll: TrainerHotkeyLayout.disableAllChord,
        ]
        var store = TrainerShortcutStore(
            orderedActions: [.infiniteHealth, .infiniteMoney, .disableAll],
            defaultLayout: defaultLayout,
            lockedActions: [.disableAll: TrainerHotkeyLayout.disableAllChord],
            storage: TrainerShortcutStorage(moduleID: "testmod", defaults: defaults)
        )
        let custom1 = HotkeyChord(keyCode: 99, modifiers: HotkeyChord.controlModifier | HotkeyChord.optionModifier, keyLabel: "F3")
        let custom2 = HotkeyChord(keyCode: 98, modifiers: HotkeyChord.controlModifier | HotkeyChord.optionModifier, keyLabel: "F5")
        let result = store.applyProfile(
            [
                "_layoutVersion": 1,
                "fullHealth": custom1.payload,
                "moneyNoDecrease": custom2.payload,
            ],
            legacyActionAliases: ["fullHealth": .infiniteHealth, "moneyNoDecrease": .infiniteMoney]
        )
        check(result == .applied, "valid legacy alias profile failed to apply")
        check(store.chord(.infiniteHealth) == custom1, "legacy shortcut alias did not apply")
        check(store.chord(.infiniteMoney) == custom2, "second legacy shortcut alias did not apply")
        // Canonical key takes priority over legacy alias in a non-conflicting profile import.
        let custom3 = HotkeyChord(keyCode: 97, modifiers: HotkeyChord.controlModifier | HotkeyChord.optionModifier, keyLabel: "F6")
        _ = store.applyProfile(
            [
                "_layoutVersion": 1,
                "moneyNoDecrease": custom2.payload,
                "infiniteMoney": custom3.payload,
            ],
            legacyActionAliases: ["fullHealth": .infiniteHealth, "moneyNoDecrease": .infiniteMoney]
        )
        check(store.chord(.infiniteMoney) == custom3, "canonical key did not beat legacy alias on profile import")
        check(
            store.applyProfile(["_layoutVersion": 99]) == .unsupportedLayoutVersion(99),
            "unsupported layout version was not refused"
        )
        print("core_cheat_definitions_ok")
    }
}
"""
    main_swift = root / "main.swift"
    main_swift.write_text(harness, encoding="utf-8")
    binary = root / "test-cheats"
    compile_swift_test(
        modules=[
            SwiftModule(
                SWIFT_CORE_MODULE,
                [
                    ROOT / "Sources/Core/UI/TrainerSemanticIcon.swift",
                    ROOT / "Sources/Core/Cheats/TrainerCheatDefinition.swift",
                    ROOT / "Sources/Core/Input/HotkeyChord.swift",
                    ROOT / "Sources/Core/Input/TrainerShortcutStore.swift",
                ],
            ),
            SwiftModule(
                "HadesCheatsFixture",
                [ROOT / "Sources/Hades/HadesCheats.swift"],
                (SWIFT_CORE_MODULE,),
            ),
            SwiftModule(
                "Hades2CheatsFixture",
                [ROOT / "Sources/Hades2/Hades2Cheats.swift"],
                (SWIFT_CORE_MODULE,),
            ),
        ],
        harness_sources=[ROOT / "tests/fixtures/swift/InMemoryDefaults.swift", main_swift],
        output=binary,
        cwd=ROOT,
    )
    proc = subprocess.run([str(binary), str(catalog_json), str(hades2_catalog_json)], cwd=ROOT, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    assert "core_cheat_definitions_ok" in proc.stdout, proc.stdout
    print(proc.stdout.strip())

print("test_core_cheat_definitions_ok")
