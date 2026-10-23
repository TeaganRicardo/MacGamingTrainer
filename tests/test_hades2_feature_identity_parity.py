"""Durable Hades feature schema projection and routing contract.

Backend/games/hades2/schema.py is the only authored identity/default/range source.
Generated Swift/Lua projections are checked byte-for-byte, while semantic tests
exercise the Host command and Adapter runtime-owner routes.
"""
import importlib
import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
sys.path.insert(0, str(ROOT / "tests"))

from games.hades2.schema import MULTIPLIER_RULES, TOGGLES
from hades2_resident_session_fakes import FakeResidentSession

GENERATOR_PATH = ROOT / "Tools/generate_hades2_feature_bindings.py"
GENERATED_SWIFT = ROOT / "Sources/Hades2/Generated/Hades2Feature.generated.swift"
LUA_SOURCE = ROOT / "Backend/games/hades2/runtime/hades.lua"


def load_generator():
    spec = importlib.util.spec_from_file_location("hades2_feature_bindings", GENERATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = load_generator()
lua = LUA_SOURCE.read_text(encoding="utf-8")

assert GENERATED_SWIFT.read_text(encoding="utf-8") == generator.render_swift(), (
    "checked-in Swift durable-feature binding drifted from schema.py"
)
for begin, end, expected in generator.lua_projection_blocks():
    start = lua.index(begin)
    finish = lua.index(end, start) + len(end)
    assert lua[start:finish] == expected, (
        f"resident generated projection drifted from schema.py: {begin}"
    )
assert "durableFeatureSchema" not in lua, (
    "schema projection must stay build-time-only, not become a resident config object"
)

resident_multipliers = {
    key for key, rule in MULTIPLIER_RULES.items() if rule["runtime"] == "resident"
}
core_multipliers = {
    key for key, rule in MULTIPLIER_RULES.items() if rule["runtime"] == "core"
}
assert core_multipliers == {"gameSpeed"}, "gameSpeed must remain the sole Core-owned multiplier"
assert '"gameSpeed"' not in generator.render_lua_multiplier_dispatch(), (
    "Core-owned gameSpeed must not enter resident multiplier dispatch"
)

# Runtime behavior ownership remains authored next to the actual callbacks.
# Validate that owner-specific featureOrder/featureRegistry projections still
# cover the schema identities without turning them into another generated config.
registry_start = lua.index("  featureRegistry = {")
registry_end = lua.index("  featureOrder = {", registry_start)
registry_block = lua[registry_start:registry_end]
registry_keys = set(re.findall(r"(?m)^    ([A-Za-z_][A-Za-z0-9_]*) = \{$", registry_block))
economy_toggles = {
    f"{key}Enabled"
    for key in resident_multipliers
    if f"{key}Enabled" in TOGGLES
}
# These currencies share their existing economy/reroll-lock owner rather
# than installing competing hooks from the independent-feature registry.
shared_currency_toggles = {"infiniteMoney", "infiniteRerolls"}
expected_registry_order = [key for key in TOGGLES if key not in economy_toggles | shared_currency_toggles]
assert registry_keys == set(expected_registry_order), (
    f"resident feature registry lost a durable behavior route: "
    f"missing={sorted(set(expected_registry_order) - registry_keys)}, "
    f"extra={sorted(registry_keys - set(expected_registry_order))}"
)
order_start = lua.index("  featureOrder = {", registry_end)
order_end = lua.index("  statOrder = {", order_start)
feature_order = re.findall(r'"([A-Za-z_][A-Za-z0-9_]*)"', lua[order_start:order_end])
assert feature_order == expected_registry_order, (
    "resident feature reconciliation order drifted from schema identity order"
)

# Compile the generated Swift facts and compare them to values assembled from
# the Python schema at test time. This is not another maintained identity list.
swiftc = shutil.which("swiftc")
if not swiftc:
    raise SystemExit("swiftc required for Hades II feature projection test")
feature_cases = ", ".join(f'\"{key}\"' for key in TOGGLES)
multiplier_checks = []
for key, rule in MULTIPLIER_RULES.items():
    multiplier_checks.extend([
        f'precondition(Hades2MultiplierKey.{key}.rawValue == \"{key}\")',
        f'precondition(Hades2MultiplierKey.{key}.defaultValue == {float(rule["default"])!r})',
        f'precondition(Hades2MultiplierKey.{key}.range.lowerBound == {float(rule["min"])!r})',
        f'precondition(Hades2MultiplierKey.{key}.range.upperBound == {float(rule["max"])!r})',
        f'precondition(Hades2MultiplierKey.{key}.runtimeOwner == .{rule["runtime"]})',
    ])
harness = f"""
import Foundation
let expectedFeatures = Set([{feature_cases}])
precondition(Set(Hades2FeatureKey.allCases.map(\\.rawValue)) == expectedFeatures)
{chr(10).join(multiplier_checks)}
print("hades2_generated_feature_binding_ok")
"""
with tempfile.TemporaryDirectory(prefix="mgt-feature-binding-") as temporary:
    main = Path(temporary) / "main.swift"
    binary = Path(temporary) / "feature-binding-test"
    main.write_text(harness, encoding="utf-8")
    subprocess.run(
        [swiftc, str(GENERATED_SWIFT), str(main), "-o", str(binary)],
        check=True,
    )
    subprocess.run([str(binary)], check=True)


# Host command validation must preserve every schema identity and value.
contract_type = importlib.import_module(
    "games.hades2.command_contract"
).Hades2CommandContract


class Probe:
    def __init__(self):
        self.received = []

    def set_desired(self, feature, value):
        self.received.append((feature, value))
        return {"feature": feature, "value": value}


probe = Probe()
contract = contract_type(probe)
cases = [(key, True) for key in TOGGLES] + [
    (key, rule["default"]) for key, rule in MULTIPLIER_RULES.items()
]
for index, (key, value) in enumerate(cases):
    result = contract.dispatch(
        "set_desired",
        {"feature": key, "value": value},
        str(index),
    )
    assert result == {"feature": key, "value": value}
assert probe.received == cases


# The real Adapter must send resident-owned desired state through set_feature
# and keep Core-owned gameSpeed on Process Time Warp.
preparation = importlib.import_module("games.hades2.preparation")


class TimeWarp:
    def __init__(self):
        self.calls = []

    def current_speed(self):
        return 1.0

    def set_speed(self, speed):
        self.calls.append(("set_speed", float(speed)))
        return float(speed)

    def reset(self):
        self.calls.append(("reset", 1.0))
        return 1.0


previous_data = preparation.DATA
try:
    with tempfile.TemporaryDirectory(prefix="mgt-feature-preferences-") as temporary:
        preparation.DATA = Path(temporary)
        adapter_type = importlib.import_module("games.hades2.adapter").Hades2Adapter
        session = FakeResidentSession({
            "status": "ready",
            "scene": "run",
            "capabilities": {"setFeature": True},
            "featureSupport": {},
            "desiredFeatures": {},
            "activeFeatures": {},
            "dormantFeatures": {},
            "featureErrors": {},
            "stats": {},
            "resources": [],
            "elements": [],
            "boons": [],
            "rewards": [],
            "nextRoomReward": None,
            "boonRarity": {},
            "gatheringProbabilities": {},
            "chaosGateProbability": None,
        }, pid=4242)
        time_warp = TimeWarp()
        adapter = adapter_type(
            resident_session=session,
            time_warp_controller=time_warp,
        )
        adapter.preference_initialized = True
        adapter.state.update(
            connected=True,
            status="waiting",
            capabilities={"setFeature": True},
        )

        # `damageEnabled` is a derived projection of `damageMultiplier`, so the
        # adapter translates a write to it instead of forwarding the retired
        # name; the translation is asserted on its own below.
        derived_toggles = {"damageEnabled"}
        resident_cases = [(key, True) for key in TOGGLES if key not in derived_toggles]
        resident_cases.extend(
            (key, MULTIPLIER_RULES[key]["default"])
            for key in MULTIPLIER_RULES
            if key in resident_multipliers
        )
        for index, (key, value) in enumerate(resident_cases):
            before = len(session.calls)
            adapter.dispatch(
                "set_desired",
                {"feature": key, "value": value},
                f"resident-{index}",
            )
            assert len(session.calls) == before + 1
            call = session.calls[-1]
            assert call["kind"] == "mutate"
            assert call["command"] == "set_feature"
            assert call["params"] == {"feature": key, "value": value}
            assert not time_warp.calls

        before = len(session.calls)
        adapter.dispatch(
            "set_desired",
            {"feature": "damageEnabled", "value": True},
            "resident-damage-toggle",
        )
        assert len(session.calls) == before + 1
        assert session.calls[-1]["params"] == {"feature": "damageMultiplier", "value": 2.0}

        before = len(session.calls)
        speed = MULTIPLIER_RULES["gameSpeed"]["default"] + 1.0
        result = adapter.dispatch(
            "set_desired",
            {"feature": "gameSpeed", "value": speed},
            "core-speed",
        )
        assert len(session.calls) == before
        assert time_warp.calls == [("set_speed", speed)]
        assert result["gameSpeed"] == speed
finally:
    preparation.DATA = previous_data

print("hades2_feature_identity_contract_ok")
