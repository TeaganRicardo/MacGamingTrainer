"""Executable identity/routing contract for durable Hades desired features.

Backend/games/hades2/schema.py is the canonical identity source. This contract
checks real consumers and dispatch boundaries without adding another schema.
"""
import ast
import importlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
from games.hades2.schema import MULTIPLIER_RULES, TOGGLES

ECONOMY_TOGGLES = {key for key in TOGGLES if key.endswith("MultiplierEnabled")}
LUA_MULTIPLIERS = set(MULTIPLIER_RULES) - {"gameSpeed"}


def source(root, path):
    return (root / path).read_text(encoding="utf-8")


def balanced_text_block(text, marker):
    start = text.index(marker) + len(marker)
    opening = text.index("{", start)
    depth = 0
    quote = None
    escaped = False
    line_comment = False
    block_comment = False
    for index in range(opening, len(text)):
        char = text[index]
        following = text[index + 1] if index + 1 < len(text) else ""
        if line_comment:
            if char == "\n":
                line_comment = False
            continue
        if block_comment:
            if char == "*" and following == "/":
                block_comment = False
            continue
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char == "/" and following == "/":
            line_comment = True
        elif char == "/" and following == "*":
            block_comment = True
        elif char in ("'", '"'):
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[opening + 1:index]
    raise AssertionError("unclosed source block: " + marker)


def swift_tokens(text):
    """Small Swift lexer for identity-bearing calls and switch rows."""
    result = []
    index = 0
    while index < len(text):
        if text[index].isspace():
            index += 1
        elif text.startswith("//", index):
            end = text.find("\n", index)
            index = len(text) if end < 0 else end + 1
        elif text.startswith("/*", index):
            depth, index = 1, index + 2
            while index < len(text) and depth:
                if text.startswith("/*", index):
                    depth += 1
                    index += 2
                elif text.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
        elif text[index] == '"':
            index += 1
            value = []
            while index < len(text):
                char = text[index]
                if char == "\\" and index + 1 < len(text):
                    value.append(text[index + 1])
                    index += 2
                elif char == '"':
                    index += 1
                    break
                else:
                    value.append(char)
                    index += 1
            result.append(("string", "".join(value)))
        elif text[index].isalpha() or text[index] == "_":
            end = index + 1
            while end < len(text) and (text[end].isalnum() or text[end] == "_"):
                end += 1
            result.append(("id", text[index:end]))
            index = end
        elif text[index] == "$":
            end = index + 1
            while end < len(text) and text[end].isdigit():
                end += 1
            result.append(("closure", text[index:end]))
            index = end
        elif text.startswith("==", index):
            result.append(("operator", "=="))
            index += 2
        elif text[index] in ".(),:{}[]=!":
            result.append((text[index], text[index]))
            index += 1
        else:
            index += 1
    return [value for _, value in result]


def swift_mapping(root, toggles):
    types = source(root, "Sources/Hades2/Hades2Types.swift")
    enum = balanced_text_block(types, "enum Hades2FeatureKey")
    cases = []
    for line in enum.splitlines():
        line = line.split("//", 1)[0].strip()
        if line.startswith("case "):
            cases.extend(item.strip() for item in line[5:].split(","))
    assert cases == list(toggles), (
        "Swift Hades2FeatureKey cases differ from canonical TOGGLES: "
        f"missing={sorted(set(toggles)-set(cases))}, extra={sorted(set(cases)-set(toggles))}"
    )

    model = source(root, "Sources/Hades2/Hades2Model.swift")
    marker = "private extension Hades2FeatureKey"
    mapping = balanced_text_block(model, marker)
    tokens = swift_tokens(mapping)
    pairs = []
    for index in range(len(tokens) - 7):
        if tokens[index:index + 4] == ["case", ".", tokens[index + 2], ":"]:
            if tokens[index + 2] in toggles and tokens[index + 4:index + 6] == ["return", "."]:
                pairs.append((tokens[index + 2], tokens[index + 6]))
    assert len(pairs) == len(toggles) and dict(pairs) == {key: key for key in toggles}, (
        "Swift modelKeyPath must map every durable key to its same-named model property"
    )

    swift_compiled_mapping(root, toggles)


def swift_compiled_mapping(root, toggles):
    """Execute the extracted production key paths against distinct model slots."""
    model = source(root, "Sources/Hades2/Hades2Model.swift")
    marker = "private extension Hades2FeatureKey"
    mapping = balanced_text_block(model, marker)
    swiftc = shutil.which("swiftc")
    if swiftc:
        properties = """final class Hades2TrainerModel {
%s
}
""" % "\n".join("    var " + key + " = false" for key in toggles)
        harness = """import Foundation
%s
%s
var model = Hades2TrainerModel()
for key in Hades2FeatureKey.allCases {
    model[keyPath: key.modelKeyPath] = true
    for other in Hades2FeatureKey.allCases {
        precondition(model[keyPath: other.modelKeyPath] == (key == other), "modelKeyPath misroute: \\(key.rawValue)")
    }
    for other in Hades2FeatureKey.allCases { model[keyPath: other.modelKeyPath] = false }
}
print("swift_feature_consumers_ok")
""" % (properties, marker + " {" + mapping + "}")
        with tempfile.TemporaryDirectory(prefix="mgt-feature-keypath-") as temp:
            main = Path(temp) / "main.swift"
            binary = Path(temp) / "feature-keypath-test"
            main.write_text(harness, encoding="utf-8")
            subprocess.run([
                swiftc, str(root / "Sources/Hades2/Hades2Types.swift"),
                str(main), "-o", str(binary),
            ], check=True, capture_output=True, text=True)
            result = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
            assert "swift_feature_consumers_ok" in result.stdout


def swift_call_feature_ids(text, method):
    tokens = swift_tokens(text)
    found = []
    for index in range(len(tokens) - 5):
        if tokens[index:index + 3] != ["model", ".", method] or tokens[index + 3] != "(":
            continue
        if tokens[index + 4] == "." and tokens[index + 5] != "self":
            found.append(tokens[index + 5])
    return found


def swift_multiplier_controls(text):
    tokens = swift_tokens(text)
    result = {}
    for index in range(len(tokens) - 2):
        if tokens[index:index + 2] != ["multiplierRow", "("]:
            continue
        # The method declaration starts with `_ title`; call sites start with a title string.
        if tokens[index + 2] == "_":
            continue
        depth = 1
        end = index + 2
        while end < len(tokens) and depth:
            if tokens[end] == "(":
                depth += 1
            elif tokens[end] == ")":
                depth -= 1
            end += 1
        args = tokens[index + 2:end - 1]
        feature = None
        toggle = None
        for cursor in range(len(args) - 2):
            if args[cursor] == "feature" and args[cursor + 1] == ":":
                feature = args[cursor + 2]
            if args[cursor:cursor + 3] == ["toggle", ":", "."]:
                toggle = args[cursor + 3]
        assert feature and toggle, "Swift multiplier row needs explicit feature/toggle identities"
        assert contains_tokens(args, ["enabled", ":", "model", ".", toggle]), (
            "Swift multiplier row enabled state misroutes " + feature
        )
        assert contains_tokens(args, ["actual", ":", "model", ".", feature]), (
            "Swift multiplier row displayed value misroutes " + feature
        )
        assert contains_tokens(args, ["shortcut", ":", ".", toggle]), (
            "Swift multiplier shortcut misroutes " + feature
        )
        assert feature not in result, "duplicate Swift multiplier control: " + feature
        result[feature] = toggle
    return result


def swift_view_toggle_routes(view, toggles):
    # SwiftUI cannot be built in Linux CI; bind each visible control to its
    # exact displayed/edited property, not merely the union of token names.
    row = re.compile(
        r'featureRow\("[^"]+", key: \.(\w+), .*?enabled: model\.(\w+), '
        r'.*?shortcut: \.(\w+)\) \{ model\.feature\(\.(\w+), value: !model\.(\w+)\) \}'
    )
    rows = row.findall(view)
    assert len(rows) == view.count('featureRow("'), "Swift toggle view row no longer has a verified dispatch"
    for key, enabled, shortcut, action, inverted in rows:
        assert key == enabled == shortcut == action == inverted, "Swift view toggle misroutes: " + key
    identities = [key for key, *_ in rows]

    combat = swift_tokens(balanced_text_block(view, "private var combatSection"))
    damage = "damageMultiplier"
    assert any(combat[i:i + 2] == ["featureMultiplierRow", "("]
               and combat[i + 3:i + 8] == [",", "key", ":", ".", "damageEnabled"]
               for i in range(len(combat) - 7)), "Swift damage multiplier control missing"
    for expected in (
        ["enabled", ":", "model", ".", "damageEnabled"],
        ["model", ".", "setMultiplier", "(", damage, ",", "text", ":", "$0"],
        ["model", ".", "feature", "(", ".", "damageEnabled", ",", "value", ":", "!", "model", ".", "damageEnabled"],
    ):
        assert contains_tokens(combat, expected), "Swift damage multiplier view misroutes " + str(expected)
    identities.append("damageEnabled")

    rarity = swift_tokens(balanced_text_block(view, "private var boonRarityPanel"))
    for expected in (
        ["isOn", ":", "model", ".", "boonRarityEnabled"],
        ["model", ".", "feature", "(", ".", "boonRarityEnabled", ",", "value", ":", "$0"],
    ):
        assert contains_tokens(rarity, expected), "Swift boon rarity toggle misroutes"
    identities.append("boonRarityEnabled")
    assert len(identities) == len(set(identities)), "Duplicate Swift feature control identity"
    assert set(identities) == set(toggles) - ECONOMY_TOGGLES, (
        "Swift toggle controls differ from canonical toggles: "
        f"missing={sorted(set(toggles)-ECONOMY_TOGGLES-set(identities))}, "
        f"extra={sorted(set(identities)-set(toggles))}"
    )


def validate_swift_consumers(root, toggles):
    swift_mapping(root, toggles)
    view = source(root, "Sources/Hades2/Hades2View.swift")
    swift_view_toggle_routes(view, toggles)
    actual = set(swift_call_feature_ids(view, "feature"))
    view_tokens = swift_tokens(view)
    actual.update(
        view_tokens[index + 3]
        for index in range(len(view_tokens) - 4)
        if view_tokens[index:index + 3] == ["toggle", ":", "."]
    )
    assert actual == set(toggles), (
        "Swift feature controls must dispatch every durable toggle exactly by identity: "
        f"missing={sorted(set(toggles)-actual)}, extra={sorted(actual-set(toggles))}"
    )
    controls = swift_multiplier_controls(view)
    lua_multipliers = set(MULTIPLIER_RULES) - {"gameSpeed"}
    expected_controls = {
        key: key + "Enabled" for key in lua_multipliers
        if key + "Enabled" in toggles
    }
    assert set(expected_controls) == lua_multipliers - {"damageMultiplier"}, (
        "Every economy multiplier needs a same-named Enabled toggle"
    )
    assert "damageEnabled" in toggles, "Damage multiplier needs its separate damageEnabled toggle"
    assert controls == expected_controls, "Swift multiplier controls must map exact multiplier-to-toggle identities"
    model = source(root, "Sources/Hades2/Hades2Model.swift")
    feature_tokens = swift_tokens(model[model.index("    func feature(_ key:"):model.index("    func setGameSpeed(")])
    assert contains_tokens(feature_tokens, ["self", "[", "keyPath", ":", "key", ".", "modelKeyPath", "]", "=", "value"]), (
        "Swift feature mutation must update the key's own modelKeyPath"
    )
    assert contains_tokens(feature_tokens, ["setDesired", "(", "feature", ":", "key", ".", "rawValue", ",", "value", ":", "value"]), (
        "Swift feature mutation must transmit the same raw identity"
    )
    method_tokens = swift_tokens(model[model.index("    func setMultiplier("):model.index("    func setCounter(")])
    for key in sorted(LUA_MULTIPLIERS):
        expected_current = ["case", key, ":", "current", "=", key]
        expected_store = ["case", key, ":", key, "=", "value"]
        assert any(method_tokens[i:i + len(expected_current)] == expected_current for i in range(len(method_tokens))), (
            "Swift multiplier current-value route mismatch: " + key
        )
        assert any(method_tokens[i:i + len(expected_store)] == expected_store for i in range(len(method_tokens))), (
            "Swift multiplier model-value route mismatch: " + key
        )
    assert ["setDesired", "(", "feature", ":", "key", ",", "value", ":", "value"] in [
        method_tokens[i:i + 9] for i in range(len(method_tokens) - 8)
    ], "Swift multiplier setter must dispatch the original identity"
    multiplier_row_start = next(i for i in range(len(view_tokens) - 3)
                                if view_tokens[i:i + 4] == ["private", "func", "multiplierRow", "("])
    multiplier_row = view_tokens[multiplier_row_start:]
    row_contracts = (
        ["featurePresentation", "(", "toggle", ",", "enabled", ":", "enabled"],
        ["configIntentBinding", "(", "text", ",", "key", ":", "feature"],
        ["model", ".", "setMultiplier", "(", "feature", ",", "text", ":", "$0"],
        ["model", ".", "feature", "(", "toggle", ",", "value", ":", "!", "enabled"],
    )
    for expected in row_contracts:
        assert expected in [multiplier_row[i:i + len(expected)] for i in range(len(multiplier_row) - len(expected) + 1)], (
            "Swift multiplier row must route feature value and toggle through their matching consumer"
        )
    speed_start = model.index("    private func setGameSpeedValue(")
    speed_end = model.index("    private func amountValue(", speed_start)
    speed_tokens = swift_tokens(model[speed_start:speed_end])
    assert contains_tokens(speed_tokens, ["setDesired", "(", "feature", ":", "gameSpeed", ",", "value", ":", "value"]), (
        "Swift gameSpeed control must keep its separate desired-state route"
    )
    for marker, dispatched in (("private var gameSpeedInputBinding", "$0"),
                                ("private var gameSpeedSliderValue", "gameSpeedInput")):
        control = swift_tokens(balanced_text_block(view, marker))
        assert contains_tokens(control, ["model", ".", "setGameSpeed", "(", dispatched, ")"]), (
            "Swift gameSpeed UI control must dispatch to setGameSpeed: " + marker
        )
    panel = swift_tokens(balanced_text_block(view, "private var gameSpeedPanel"))
    for expected in (["model", ".", "featureSupport", "[", "gameSpeed", "]", "==", "true"],
                     ["text", ":", "gameSpeedInputBinding"], ["value", ":", "gameSpeedSliderValue"]):
        assert contains_tokens(panel, expected), "Swift gameSpeed panel misroutes its Core-owned input"


def python_router_source(root):
    tree = ast.parse(source(root, "Backend/games/hades2/command_router.py"))
    dispatch = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "_dispatch")
    for node in ast.walk(dispatch):
        test = getattr(node, "test", None)
        if not isinstance(test, ast.Compare) or not isinstance(test.left, ast.Name) or test.left.id != "command":
            continue
        if not any(isinstance(op, ast.Eq) for op in test.ops):
            continue
        if not any(isinstance(value, ast.Constant) and value.value == "set_desired" for value in test.comparators):
            continue
        calls = [child for child in ast.walk(node) if isinstance(child, ast.Call)
                 and isinstance(child.func, ast.Attribute) and child.func.attr == "set_desired"]
        assert len(calls) == 1, "Python set_desired router must have one adapter consumer"
        expected = [ast.Subscript(value=ast.Name(id="params", ctx=ast.Load()), slice=ast.Constant(value=name), ctx=ast.Load())
                    for name in ("feature", "value")]
        assert [ast.dump(arg, include_attributes=False) for arg in calls[0].args] == [
            ast.dump(arg, include_attributes=False) for arg in expected
        ], "Python router must preserve params.feature and params.value"
        return
    raise AssertionError("Python router has no set_desired dispatch branch")


def load_python_consumer(root, filename, name):
    path = root / "Backend/games/hades2" / filename
    spec = importlib.util.spec_from_file_location("games.hades2._feature_identity_" + name, path)
    assert spec and spec.loader, "Python consumer loader missing: " + filename
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def exercise_python_router(root, toggles, multipliers):
    router_type = load_python_consumer(root, "command_router.py", "router").Hades2CommandRouter

    class Probe:
        def __init__(self):
            self.received = []

        def set_desired(self, feature, value):
            self.received.append((feature, value))
            return {"feature": feature, "value": value}

    probe = Probe()
    router = router_type(probe)
    cases = [(key, True) for key in toggles] + [
        (key, rule["default"]) for key, rule in multipliers.items()
    ]
    for index, (key, value) in enumerate(cases):
        result = router.dispatch("set_desired", {"feature": key, "value": value}, str(index))
        assert result == {"feature": key, "value": value}, "Python router misrouted " + key
    assert probe.received == cases, "Python router changed a durable feature identity"


def exercise_adapter_routes(root, toggles, multipliers):
    """Drive the real router/adapter with isolated preferences, no game or save tree."""
    preparation = importlib.import_module("games.hades2.preparation")

    class Transport:
        pid = 4242
        last_duration = 0.001

        def __init__(self):
            self.sources = []

        def alive(self):
            return True

        def execute(self, lua_source):
            self.sources.append(lua_source)
            return json.dumps({
                "status": "ready", "scene": "run", "capabilities": {"setFeature": True},
                "featureSupport": {}, "desiredFeatures": {}, "activeFeatures": {},
                "dormantFeatures": {}, "featureErrors": {}, "stats": {},
                "resources": [], "elements": [], "boons": [], "rewards": [],
                "nextRoomReward": None,
            })

    class TimeWarp:
        def __init__(self):
            self.calls = []

        def set_speed(self, speed):
            self.calls.append(("set_speed", speed))
            return speed

        def reset(self):
            self.calls.append(("reset", 1.0))
            return 1.0

    previous_data = preparation.DATA
    try:
        with tempfile.TemporaryDirectory(prefix="mgt-feature-preferences-") as temporary:
            setattr(preparation, "DATA", Path(temporary))
            adapter_module = load_python_consumer(root, "adapter.py", "adapter")
            adapter_type = adapter_module.Hades2Adapter
            transport = Transport()
            adapter = adapter_type(transport=transport)
            time_warp = TimeWarp()
            adapter.time_warp = time_warp
            adapter._runtime_bootstrapped = True
            adapter.preference_initialized = True
            adapter.state.update(connected=True, status="waiting", capabilities={"setFeature": True})
            lua_value = adapter_module.lua_value
            for index, key in enumerate((*toggles, *(key for key in multipliers if key != "gameSpeed"))):
                value = True if key in toggles else multipliers[key]["default"]
                before = len(transport.sources)
                adapter.dispatch("set_desired", {"feature": key, "value": value}, str(index))
                assert len(transport.sources) == before + 1, "Lua-bound feature missed Lua: " + key
                expected = 'dispatch("set_feature",' + lua_value({"feature": key, "value": value})[:-1] + ","
                assert expected in transport.sources[-1], "Lua-bound feature misrouted: " + key
                assert not time_warp.calls, "Lua-bound feature crossed Core Time Warp: " + key
            before = len(transport.sources)
            speed = multipliers["gameSpeed"]["default"] + 1.0
            result = adapter.dispatch("set_desired", {"feature": "gameSpeed", "value": speed}, "core-speed")
            assert len(transport.sources) == before, "Core-owned gameSpeed crossed Lua"
            assert time_warp.calls == [("set_speed", speed)], "Core-owned gameSpeed missed Time Warp"
            assert result["gameSpeed"] == speed, "Core-owned gameSpeed state misrouted"
    finally:
        setattr(preparation, "DATA", previous_data)


def lua_tokens(text):
    """Tokenize identity-bearing Lua fragments, ignoring comments and strings safely."""
    result = []
    index = 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
        elif text.startswith("--[[", index):
            end = text.find("]]", index + 4)
            index = len(text) if end < 0 else end + 2
        elif text.startswith("--", index):
            end = text.find("\n", index)
            index = len(text) if end < 0 else end + 1
        elif char in "'\"":
            quote = char
            index += 1
            value = []
            while index < len(text):
                if text[index] == "\\" and index + 1 < len(text):
                    value.append(text[index + 1])
                    index += 2
                elif text[index] == quote:
                    index += 1
                    break
                else:
                    value.append(text[index])
                    index += 1
            result.append(("string", "".join(value)))
        elif char.isalpha() or char == "_":
            end = index + 1
            while end < len(text) and (text[end].isalnum() or text[end] == "_"):
                end += 1
            result.append(("id", text[index:end]))
            index = end
        elif text.startswith("==", index):
            result.append(("symbol", "=="))
            index += 2
        else:
            result.append(("symbol", char))
            index += 1
    return [value for _, value in result]


def lua_table_items(tokens, marker, occurrence=0):
    pattern = marker.split()
    starts = [index for index in range(len(tokens) - len(pattern) + 1)
              if tokens[index:index + len(pattern)] == pattern]
    assert len(starts) > occurrence, "Lua table declaration missing: " + marker
    opening = starts[occurrence] + len(pattern) - 1
    assert tokens[opening] == "{", "Lua table declaration malformed: " + marker
    depth = 1
    items, item_start = [], opening + 1
    for index in range(opening + 1, len(tokens)):
        token = tokens[index]
        if token in ("{", "(", "["):
            depth += 1
        elif token in ("}", ")", "]"):
            depth -= 1
            if depth == 0:
                if index > item_start:
                    items.append(tokens[item_start:index])
                return items
        elif token == "," and depth == 1:
            if index > item_start:
                items.append(tokens[item_start:index])
            item_start = index + 1
    raise AssertionError("unclosed Lua table: " + marker)


def lua_key_values(items, label):
    pairs = []
    for item in items:
        assert len(item) >= 3 and item[0].isidentifier() and item[1] == "=", "Malformed Lua " + label
        pairs.append((item[0], item[2:]))
    keys = [key for key, _ in pairs]
    assert len(keys) == len(set(keys)), "Duplicate Lua identities in " + label
    return dict(pairs), keys


def lua_function_tokens(text, name):
    """Read the resident's top-level function, not a coincidental name elsewhere."""
    start = re.search(r"(?m)^  local function " + re.escape(name) + r"\(", text)
    assert start, "Lua consumer function missing: " + name
    end = re.search(r"(?m)^  (?:local function |featureOrder = |featureRegistry = |statOrder = )",
                    text[start.end():])
    assert end, "Lua consumer function boundary missing: " + name
    return lua_tokens(text[start.start():start.end() + end.start()])


def contains_tokens(tokens, expected):
    return any(tokens[i:i + len(expected)] == expected
               for i in range(len(tokens) - len(expected) + 1))


def lua_dispatch_source(root, toggles, multipliers):
    text = source(root, "Backend/games/hades2/runtime/hades.lua")
    tokens = lua_tokens(text)
    resident, _ = lua_key_values(lua_table_items(tokens, "local M = {"), "resident module")
    for key in toggles:
        assert resident.get(key) == ["false"], "Lua resident toggle missing or misrouted: " + key
    for key in multipliers:
        if key == "gameSpeed":
            assert key not in resident, "Core-owned gameSpeed must not enter resident state"
        else:
            assert resident.get(key) == [format(multipliers[key]["default"], "g")], (
                "Lua resident multiplier default missing or misrouted: " + key
            )
    default_table, default_keys = lua_key_values(lua_table_items(tokens, "desiredFeatures = {", 0), "desiredFeatures defaults")
    assert default_keys == list(toggles), (
        "Lua desiredFeatures defaults differ from canonical TOGGLES: "
        f"missing={sorted(set(toggles)-set(default_keys))}, extra={sorted(set(default_keys)-set(toggles))}"
    )
    assert all(value == ["false"] for value in default_table.values()), "Lua desired feature defaults must be false"

    state_table, state_keys = lua_key_values(lua_table_items(tokens, "desiredFeatures = {", 1), "state desiredFeatures")
    assert state_keys == list(toggles), "Lua state projection must return every durable toggle exactly"
    assert all(value == ["M", ".", "desiredFeatures", ".", key] for key, value in state_table.items()), (
        "Lua state projection must read each matching desiredFeatures key"
    )

    order_items = lua_table_items(tokens, "featureOrder = {")
    order = order_items and [item[0] for item in order_items if len(item) == 1]
    expected_order = [key for key in toggles if key not in ECONOMY_TOGGLES]
    assert order == expected_order, "Lua feature reconciliation order differs from canonical toggles"
    registry, registry_keys = lua_key_values(lua_table_items(tokens, "featureRegistry = {"), "featureRegistry")
    assert registry_keys == expected_order, "Lua feature registry has missing/extra/misrouted toggle identities"
    for key in expected_order:
        entry = registry[key]
        for label, state in (("install", "true"), ("release", "false")):
            marker = [label, "="]
            indexes = [i for i in range(len(entry) - 2) if entry[i:i + 2] == marker]
            assert len(indexes) == 1, "Lua registry callback missing/duplicate: " + key + "." + label
            callback = entry[indexes[0] + 2]
            assert contains_tokens(lua_function_tokens(text, callback), ["M", ".", key, "=", state]), (
                "Lua registry callback does not update its own feature: " + key + "." + label
            )
        active = entry.index("active")
        assert contains_tokens(entry[active:], ["M", ".", key]), (
            "Lua registry active state reads another feature: " + key
        )

    economy = lua_function_tokens(text, "reconcileEconomy")
    for key in ECONOMY_TOGGLES:
        assert contains_tokens(economy, ["M", ".", key, "=", "M", ".", "desiredFeatures", ".", key]), (
            "Lua economy toggle does not apply its own desired identity: " + key
        )

    dispatch_start = next(i for i in range(len(tokens) - 4)
                          if tokens[i:i + 5] == ["function", "M", ".", "dispatch", "("])
    set_feature_index = next(i for i in range(dispatch_start + 5, len(tokens) - 4)
                             if tokens[i:i + 5] == ["if", "command", "==", "set_feature", "then"])
    rarity_index = next(i for i in range(dispatch_start + 5, len(tokens) - 4)
                        if tokens[i:i + 5] == ["if", "command", "==", "set_boon_rarity", "then"])
    set_feature = tokens[set_feature_index:]
    next_branch = next((i for i in range(5, len(set_feature) - 4)
                        if set_feature[i:i + 5] == ["if", "command", "==", "set_resource", "then"]), None)
    assert next_branch is not None and rarity_index < set_feature_index, "Lua set_feature dispatch boundary missing"
    set_feature = set_feature[:next_branch]

    exact_guard = ["if", "M", ".", "desiredFeatures", "[", "feature", "]", "==", "nil",
                   "then", "error", "(", "Unknown feature", ")", "end"]
    assert any(set_feature[i:i + len(exact_guard)] == exact_guard for i in range(len(set_feature))), (
        "Lua set_feature must accept exactly desiredFeatures keys, without forced missing-feature rejects"
    )
    multiplier_routes = []
    for i in range(len(set_feature) - 2):
        if set_feature[i:i + 2] == ["feature", "=="] and i + 2 < len(set_feature):
            # Lua string tokens carry their contents as ordinary token values.
            if set_feature[i + 2] in multipliers:
                multiplier_routes.append(set_feature[i + 2])
    assert multiplier_routes == [key for key in multipliers if key != "gameSpeed"], (
        "Lua set_feature multiplier dispatch differs from canonical Lua-owned multipliers"
    )
    assert contains_tokens(set_feature, ["M", "[", "feature", "]", "=", "value"]), (
        "Lua multiplier dispatch must set M[feature] to the passed value"
    )
    assert "gameSpeed" not in multiplier_routes, "gameSpeed must remain Core-owned"

    damage = lua_function_tokens(text, "installDamage")
    assert contains_tokens(damage, ["if", "M", ".", "damageEnabled", "and", "attacker", "==",
                                    "CurrentRun", ".", "Hero", "then", "return", "result", "*",
                                    "M", ".", "damageMultiplier"]), (
        "Lua damage consumer must gate and apply its matching multiplier"
    )
    economy = lua_function_tokens(text, "installEconomy")
    assert contains_tokens(economy, ["if", "id", "==", "Money", "and", "M", ".", "moneyMultiplierEnabled",
                                     "then", "amount", "=", "amount", "*", "M", ".", "moneyMultiplier"]), (
        "Lua money consumer misroutes moneyMultiplier"
    )
    assert contains_tokens(economy, ["elseif", "id", "~", "=", "Money", "and", "M", ".",
                                     "resourceMultiplierEnabled", "then"]), (
        "Lua material consumer misroutes resourceMultiplierEnabled"
    )
    assert contains_tokens(economy, ["if", "allowed", "[", "id", "]", "then", "amount", "=", "amount",
                                     "*", "M", ".", "resourceMultiplier"]), (
        "Lua material consumer misroutes resourceMultiplier"
    )


def validate_python_consumers(root):
    python_router_source(root)
    exercise_python_router(root, tuple(TOGGLES), dict(MULTIPLIER_RULES))


def exercise_python_router_mutation(root):
    exercise_python_router(root, tuple(TOGGLES), dict(MULTIPLIER_RULES))


def validate_core_speed(root):
    exercise_adapter_routes(root, tuple(TOGGLES), dict(MULTIPLIER_RULES))


def validate(root=ROOT):
    toggles = tuple(TOGGLES)
    multipliers = dict(MULTIPLIER_RULES)
    validate_swift_consumers(root, toggles)
    validate_python_consumers(root)
    validate_core_speed(root)
    lua_dispatch_source(root, toggles, multipliers)


def mutation_regressions():
    swift = ("Sources/Hades2/Hades2Types.swift", "Sources/Hades2/Hades2Model.swift", "Sources/Hades2/Hades2View.swift")
    router = ("Backend/games/hades2/command_router.py",)
    adapter = ("Backend/games/hades2/adapter.py", "Backend/games/hades2/runtime/hades.lua")
    lua = ("Backend/games/hades2/runtime/hades.lua",)
    mutations = (
        ("swift-model-keypath", swift[1], "case .godMode: return \\.godMode",
         "case .godMode: return \\.infiniteHealth", validate_swift_consumers, swift),
        *((("swift-keypath-execution", swift[1], "case .godMode: return \\.godMode",
            "case .godMode: return \\.infiniteHealth", swift_compiled_mapping, swift),) if shutil.which("swiftc") else ()),
        ("swift-view-action", swift[2], "model.feature(.infiniteHealth, value: !model.infiniteHealth)",
         "model.feature(.godMode, value: !model.infiniteHealth)", validate_swift_consumers, swift),
        ("swift-multiplier-display", swift[2], "actual: model.resourceMultiplier,",
         "actual: model.moneyMultiplier,", validate_swift_consumers, swift),
        ("swift-feature-dispatch", swift[1], "feature: key.rawValue, value: value",
         'feature: "godMode", value: value', validate_swift_consumers, swift),
        ("swift-speed-dispatch", swift[1], 'feature: "gameSpeed", value: value',
         'feature: "damageMultiplier", value: value', validate_swift_consumers, swift),
        ("swift-speed-input", swift[2], "model.setGameSpeed(gameSpeedInput)",
         'model.setMultiplier("damageMultiplier", text: gameSpeedInput)', validate_swift_consumers, swift),
        ("swift-extra-case", swift[0], "case moneyMultiplierEnabled, resourceMultiplierEnabled",
         "case moneyMultiplierEnabled, resourceMultiplierEnabled, phantomFeature", validate_swift_consumers, swift),
        ("python-router-key", router[0], "result=adapter.set_desired(params['feature'],params['value'])",
         "result=adapter.set_desired('godMode',params['value'])", exercise_python_router_mutation, router),
        ("python-router-value", router[0], "result=adapter.set_desired(params['feature'],params['value'])",
         "result=adapter.set_desired(params['feature'],True)", exercise_python_router_mutation, router),
        ("core-speed-to-lua", adapter[0], "if feature=='gameSpeed':",
         "if feature=='moneyMultiplier':", validate_core_speed, adapter),
        ("core-speed-value", adapter[0], "self.time_warp.set_speed(float(value))",
         "self.time_warp.set_speed(1.0)", validate_core_speed, adapter),
        ("lua-missing-toggle", lua[0], "    resourceMultiplier = 2, resourceMultiplierEnabled = false,",
         "    resourceMultiplier = 2,", lua_dispatch_source, lua),
        ("lua-state-projection", lua[0], "infiniteHealth = M.desiredFeatures.infiniteHealth,",
         "infiniteHealth = M.desiredFeatures.godMode,", lua_dispatch_source, lua),
        ("lua-registry-install", lua[0], "infiniteHealth = {\n      install = installHealth,",
         "infiniteHealth = {\n      install = installMana,", lua_dispatch_source, lua),
        ("lua-economy-toggle", lua[0], "M.moneyMultiplierEnabled = M.desiredFeatures.moneyMultiplierEnabled",
         "M.moneyMultiplierEnabled = M.desiredFeatures.resourceMultiplierEnabled", lua_dispatch_source, lua),
        ("lua-damage-gate", lua[0], "if M.damageEnabled and attacker == CurrentRun.Hero then",
         "if M.infiniteHealth and attacker == CurrentRun.Hero then", lua_dispatch_source, lua),
        ("lua-multiplier-consumer", lua[0], "return result * M.damageMultiplier",
         "return result * M.moneyMultiplier", lua_dispatch_source, lua),
        ("lua-money-consumer", lua[0], "amount = amount * M.moneyMultiplier",
         "amount = amount * M.resourceMultiplier", lua_dispatch_source, lua),
        ("lua-multiplier-dispatch", lua[0], "M[feature] = value",
         "M.moneyMultiplier = value", lua_dispatch_source, lua),
        ("lua-speed-ownership", lua[0], 'or feature == "resourceMultiplier" then',
         'or feature == "resourceMultiplier" or feature == "gameSpeed" then', lua_dispatch_source, lua),
        ("lua-forced-missing-feature", lua[0],
         'if M.desiredFeatures[feature] == nil then error("Unknown feature") end',
         'if feature == "godMode" or M.desiredFeatures[feature] == nil then error("Unknown feature") end', lua_dispatch_source, lua),
    )
    for label, path, before, after, check, required_files in mutations:
        with tempfile.TemporaryDirectory(prefix="mgt-feature-mutation-") as temp:
            copy = Path(temp)
            for required in required_files:
                destination = copy / required
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / required, destination)
            target = copy / path
            original = target.read_text(encoding="utf-8")
            assert before in original, "mutation anchor missing: " + label
            target.write_text(original.replace(before, after, 1), encoding="utf-8")
            try:
                if check in (validate_swift_consumers, swift_compiled_mapping):
                    check(copy, tuple(TOGGLES))
                elif check is lua_dispatch_source:
                    check(copy, tuple(TOGGLES), dict(MULTIPLIER_RULES))
                else:
                    check(copy)
            except AssertionError as error:
                print("identity_mutation_rejected:", label, str(error))
                continue
            except subprocess.CalledProcessError as error:
                assert check is swift_compiled_mapping and Path(error.cmd[0]).name == "feature-keypath-test", (
                    "Swift mutation failed to compile rather than misrouting the live key path: " + label
                )
                print("identity_mutation_rejected:", label, "compiled key path trapped")
                continue
            raise AssertionError("identity contract missed negative mutation: " + label)


validate()
mutation_regressions()
print("hades2_feature_identity_contract_ok")
