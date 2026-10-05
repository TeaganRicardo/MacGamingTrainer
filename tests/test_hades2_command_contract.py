import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

import games.hades2.command_contract as command_contract_module
from games.hades2.command_contract import Hades2CommandContract, command_metadata
from games.hades2.error_presentation import Hades2PresentationError


class TransportProbe:
    def __init__(self):
        self.live = False

    def alive(self):
        return self.live


class ProbeAdapter:
    def __init__(self):
        self.calls = []
        self.runtime = TransportProbe()

    def _record(self, name, *args):
        self.calls.append((name, *copy.deepcopy(args)))
        return {"route": name, "args": copy.deepcopy(args)}

    def scan(self):
        return self._record("scan")

    def connect(self, probe_runtime=True):
        return self._record("connect", probe_runtime)

    def disconnect(self):
        return self._record("disconnect")

    def runtime_reset(self):
        return self._record("runtime_reset")

    def reset_desired(self):
        return self._record("reset_desired")

    def execute(self, command, params):
        return self._record("execute", command, dict(params))

    def set_desired(self, feature, value):
        return self._record("set_desired", feature, value)

    def set_boon_rarity_desired(self, config):
        return self._record("set_boon_rarity_desired", dict(config))

    def set_next_room_reward_desired(self, reward):
        return self._record("set_next_room_reward_desired", reward)

    def set_gathering_desired(self, family, probability):
        return self._record("set_gathering_desired", family, probability)

    def set_chaos_gate_desired(self, probability):
        return self._record("set_chaos_gate_desired", probability)

    def list_profiles(self):
        self.calls.append(("list_profiles",))
        return [{"name": "A"}]

    def save_profile(self, name, shortcuts):
        return self._record("save_profile", name, shortcuts)

    def load_profile(self, name):
        return self._record("load_profile", name)

    def delete_profile(self, name):
        return self._record("delete_profile", name)


probe = ProbeAdapter()
contract = Hades2CommandContract(probe)


def last_execute():
    kind, command, params = probe.calls[-1]
    assert kind == "execute"
    return command, params


def dispatch_runtime(command, params, request_id="request"):
    probe.calls.clear()
    result = contract.dispatch(command, params, request_id)
    routed, validated = last_execute()
    assert routed == command
    return result, validated


def expect_error(command, params, message):
    probe.calls.clear()
    try:
        contract.dispatch(command, params, "invalid-request")
    except Exception as error:
        diagnostic = getattr(error, "diagnostic", None)
        assert (diagnostic or str(error)) == message, (
            command,
            diagnostic,
            str(error),
        )
    else:
        raise AssertionError(f"invalid command accepted: {command} {params!r}")
    assert probe.calls == []


# The build-facing metadata is one complete authoritative Host command list and
# one Host watchdog policy. Swift generation consumes this directly.
metadata = command_metadata()
names = [row["name"] for row in metadata]
assert names == [
    "scan", "status", "connect", "disconnect", "launch",
    "disable_all", "runtime_reset", "reset_desired", "set_desired",
    "set_vital", "set_counter", "lock_vital",
    "set_resource", "lock_resource", "set_rerolls", "lock_rerolls",
    "reroll_choice", "set_gathering_desired", "set_chaos_gate_desired",
    "generate_gathering", "set_stat", "set_element", "lock_element",
    "set_boon_rarity_desired", "set_next_room_reward_desired",
    "spawn_reward", "acquire_chaos_pair", "open_sell_traits",
    "set_trait_level", "set_trait_rarity", "set_trait_remaining_uses",
    "expire_trait", "remove_trait", "advance_trait_lifecycle",
    "open_special_choice", "list_profiles", "save_profile", "load_profile",
    "delete_profile", "diagnostics", "export_diagnostics", "prepare", "restore",
]
timeouts = {row["name"]: row["timeoutSeconds"] for row in metadata}
assert {name: value for name, value in timeouts.items() if value != 6.0} == {
    "scan": 15.0,
    "status": 15.0,
    "connect": 90.0,
    "disconnect": 12.0,
    "launch": 10.0,
    "diagnostics": 70.0,
    "export_diagnostics": 85.0,
    "prepare": 560.0,
    "restore": 240.0,
}


# Direct routing is contract-owned.
probe.calls.clear()
assert contract.dispatch("scan", {}, "scan-request")["route"] == "scan"
assert probe.calls == [("scan",)]
probe.calls.clear()
contract.dispatch("connect", {}, "connect-default")
assert probe.calls == [("connect", True)]
probe.calls.clear()
contract.dispatch("connect", {"probeRuntime": False}, "connect-false")
assert probe.calls == [("connect", False)]
probe.calls.clear()
contract.dispatch("disconnect", {"ignored": "kept-compatible"}, "disconnect")
assert probe.calls == [("disconnect",)]
probe.calls.clear()
contract.dispatch("runtime_reset", {}, "runtime-reset")
assert probe.calls == [("runtime_reset",)]
probe.calls.clear()
contract.dispatch("reset_desired", {}, "reset-desired")
assert probe.calls == [("reset_desired",)]


# Validation and normalization are observable through the same dispatch seam.
_, params = dispatch_runtime(
    "set_vital", {"vital": "health", "field": "current", "value": 120}
)
assert params == {"vital": "health", "field": "current", "value": 120}
expect_error(
    "set_vital",
    {"vital": "armor", "field": "max", "value": 10},
    "护甲仅提供当前值，不存在可编辑上限。",
)
expect_error(
    "set_vital",
    {"vital": "health", "field": "current", "value": 0},
    "生命值必须至少为 1。",
)

_, params = dispatch_runtime("set_counter", {"counter": "spellCharge", "value": 3})
assert params == {"counter": "spellCharge", "value": 3}
expect_error(
    "set_counter",
    {"counter": "unknown", "value": 3},
    "未知局内计数器。",
)

_, params = dispatch_runtime("lock_vital", {"vital": "mana", "locked": True})
assert params == {"vital": "mana", "locked": True}
expect_error(
    "lock_vital",
    {"vital": "mana", "locked": 1},
    "锁定值必须为布尔值。",
)

_, params = dispatch_runtime(
    "set_stat", {"stat": "enemyHealth", "locked": True, "value": 175}
)
assert params == {"stat": "enemyHealth", "locked": True, "value": 175}
expect_error(
    "set_stat",
    {"stat": "enemyHealth", "locked": True, "value": 9},
    "敌人生命倍率必须为 10–1000%。",
)

_, params = dispatch_runtime("set_element", {"element": "Fire", "amount": 4})
assert params == {"element": "Fire", "amount": 4}
expect_error("set_element", {"element": "Void", "amount": 4}, "未知元素。")
expect_error(
    "set_element",
    {"element": "Fire", "amount": 1000000},
    "元素数量必须为 0–999999 的整数。",
)

_, params = dispatch_runtime("set_resource", {"resource": "Money", "amount": 10}, "resource-id")
assert params == {"resource": "Money", "amount": 10, "requestId": "resource-id"}
_, params = dispatch_runtime("lock_resource", {"resource": "Money", "locked": False}, "lock-resource-id")
assert params == {"resource": "Money", "locked": False, "requestId": "lock-resource-id"}
_, params = dispatch_runtime("set_rerolls", {"amount": 7}, "rerolls-id")
assert params == {"amount": 7, "requestId": "rerolls-id"}
_, params = dispatch_runtime("lock_rerolls", {"locked": True}, "lock-rerolls-id")
assert params == {"locked": True, "requestId": "lock-rerolls-id"}

_, params = dispatch_runtime(
    "reroll_choice",
    {"menuToken": "observed-menu", "expectedCost": 2},
    "reroll-id",
)
assert params == {
    "menuToken": "observed-menu",
    "expectedCost": 2,
    "requestId": "reroll-id",
}
for invalid in (
    {},
    {"menuToken": "", "expectedCost": 1},
    {"menuToken": "x", "expectedCost": -1},
    {"menuToken": "x", "expectedCost": True},
    {"menuToken": "x", "expectedCost": 1.5},
):
    expect_error("reroll_choice", invalid, "请刷新后重新随机当前选项。")

_, params = dispatch_runtime(
    "spawn_reward", {"reward": "EmptyMaxHealthDrop"}, "spawn-id"
)
assert params == {"reward": "EmptyMaxHealthDrop", "requestId": "spawn-id"}
_, params = dispatch_runtime(
    "acquire_chaos_pair",
    {"blessing": "ChaosHealthBlessing", "curse": "ChaosDamageCurse"},
    "chaos-id",
)
assert params == {
    "blessing": "ChaosHealthBlessing",
    "curse": "ChaosDamageCurse",
    "requestId": "chaos-id",
}
expect_error(
    "acquire_chaos_pair",
    {"blessing": "ChaosHealthBlessing"},
    "请选择掉落物或祝福。",
)

_, params = dispatch_runtime("open_sell_traits", {}, "sell-id")
assert params == {"requestId": "sell-id"}
_, params = dispatch_runtime("open_special_choice", {"source": "Zeus"}, "choice-id")
assert params == {"source": "Zeus", "requestId": "choice-id"}
expect_error("open_special_choice", {}, "请选择支持原生奖励选择界面的角色。")

_, params = dispatch_runtime(
    "generate_gathering",
    {"family": "mining", "scopeToken": "observed-room"},
    "gather-id",
)
assert params == {
    "family": "mining",
    "scopeToken": "observed-room",
    "requestId": "gather-id",
}
expect_error(
    "generate_gathering",
    {"family": "mining", "scopeToken": ""},
    "请刷新当前房间后再生成采集点。",
)


trait_target = {
    "generationId": "generation-55",
    "runId": "run-1",
    "instanceId": "trait-42",
    "trait": "ZeusWeaponBoon",
    "family": "olympianHermes",
    "expectedLevel": 1,
    "expectedRarity": "Rare",
    "expectedSameNameCount": 1,
}
_, params = dispatch_runtime(
    "set_trait_level",
    dict(trait_target, targetLevel=4),
    "trait-level-id",
)
assert params == dict(trait_target, targetLevel=4, requestId="trait-level-id")
_, params = dispatch_runtime(
    "set_trait_rarity",
    dict(trait_target, rarity="Epic"),
    "trait-rarity-id",
)
assert params == dict(trait_target, rarity="Epic", requestId="trait-rarity-id")
_, params = dispatch_runtime("remove_trait", trait_target, "trait-remove-id")
assert params == dict(trait_target, requestId="trait-remove-id")
_, params = dispatch_runtime(
    "advance_trait_lifecycle", trait_target, "trait-advance-id"
)
assert params == dict(trait_target, requestId="trait-advance-id")

temporary_target = dict(trait_target, family="temporary", expectedRemainingUses=5)
_, params = dispatch_runtime(
    "set_trait_remaining_uses",
    dict(temporary_target, targetRemainingUses=8),
    "trait-uses-id",
)
assert params == dict(
    temporary_target,
    targetRemainingUses=8,
    requestId="trait-uses-id",
)
_, params = dispatch_runtime("expire_trait", temporary_target, "trait-expire-id")
assert params == dict(temporary_target, requestId="trait-expire-id")
expect_error(
    "set_trait_remaining_uses",
    dict(temporary_target, targetRemainingUses=0),
    "剩余次数必须为 1–999999 的整数。",
)
expect_error(
    "set_trait_level",
    dict({key: value for key, value in trait_target.items() if key != "instanceId"}, targetLevel=4),
    "请选择当前局祝福。",
)
expect_error(
    "set_trait_level",
    dict(trait_target, targetLevel=1),
    "目标等级必须高于当前等级。",
)
expect_error(
    "set_trait_rarity",
    dict(trait_target, rarity="Mythic"),
    "最低稀有度无效。",
)


# Desired commands retain their direct Adapter semantics and normalization.
probe.calls.clear()
contract.dispatch(
    "set_desired",
    {"feature": "gameSpeed", "value": 2},
    "desired-id",
)
assert probe.calls == [("set_desired", "gameSpeed", 2.0)]
expect_error(
    "set_desired",
    {"feature": "resourceMultiplier", "value": 0},
    "倍率范围为 1–100。",
)

probe.calls.clear()
contract.dispatch(
    "set_boon_rarity_desired",
    {
        "target": "Epic",
        "multiplier": 250,
        "forceLegendary": True,
        "forceDuo": False,
    },
    "rarity-id",
)
assert probe.calls == [(
    "set_boon_rarity_desired",
    {
        "target": "Epic",
        "multiplier": 250,
        "forceLegendary": True,
        "forceDuo": False,
    },
)]
expect_error(
    "set_boon_rarity_desired",
    {
        "target": "Mythic",
        "multiplier": 100,
        "forceLegendary": False,
        "forceDuo": False,
    },
    "最低稀有度无效。",
)

probe.calls.clear()
contract.dispatch(
    "set_gathering_desired",
    {"family": "flora", "probability": 25},
    "gather-desired",
)
assert probe.calls == [("set_gathering_desired", "flora", 25.0)]
probe.calls.clear()
contract.dispatch(
    "set_chaos_gate_desired",
    {"probability": 50},
    "chaos-desired",
)
assert probe.calls == [("set_chaos_gate_desired", 50.0)]
probe.calls.clear()
contract.dispatch(
    "set_next_room_reward_desired",
    {"reward": "WeaponUpgrade"},
    "reward-desired",
)
assert probe.calls == [("set_next_room_reward_desired", "WeaponUpgrade")]


# Non-request-id runtime commands must not inherit the Host request identity.
for command, params in (
    ("status", {"includeCatalogs": True}),
    ("disable_all", {}),
    ("set_vital", {"vital": "mana", "field": "current", "value": 50}),
    ("set_stat", {"stat": "enemyHealth", "locked": False}),
    ("set_element", {"element": "Fire", "amount": 2}),
    ("lock_element", {"element": "Fire", "locked": False}),
):
    _, routed = dispatch_runtime(command, params, "must-not-inject")
    assert "requestId" not in routed, command


# Profile routing remains part of the same Host command contract.
probe.calls.clear()
contract.dispatch("list_profiles", {}, "profiles-list")
assert probe.calls == [("list_profiles",)]
probe.calls.clear()
contract.dispatch(
    "save_profile",
    {"name": "Build", "shortcuts": {"invincibility": {"x": 1}}},
    "profiles-save",
)
assert probe.calls == [(
    "save_profile",
    "Build",
    {"invincibility": {"x": 1}},
)]
probe.calls.clear()
contract.dispatch("load_profile", {"name": "Build"}, "profiles-load")
assert probe.calls == [("load_profile", "Build")]
probe.calls.clear()
contract.dispatch("delete_profile", {"name": "Build"}, "profiles-delete")
assert probe.calls == [("delete_profile", "Build")]


# System-effect routes are still behind dispatch. Tests substitute those effects
# locally instead of exposing them through the external command interface.
system_events = []
old_build_diagnostics = command_contract_module.build_diagnostics
old_export_diagnostics = command_contract_module.export_diagnostics
old_subprocess_run = command_contract_module.subprocess.run
old_prepare = command_contract_module.preparation.prepare
old_restore = command_contract_module.preparation.restore
try:
    command_contract_module.build_diagnostics = lambda adapter: {"diagnostics": True}
    command_contract_module.export_diagnostics = lambda adapter: {
        "diagnosticBundle": "/tmp/fake-diagnostics.zip"
    }
    command_contract_module.subprocess.run = (
        lambda argv, **kwargs: system_events.append((list(argv), dict(kwargs)))
    )
    command_contract_module.preparation.prepare = lambda: {"prepared": True}
    command_contract_module.preparation.restore = lambda: {"restored": True}

    assert contract.dispatch("diagnostics", {}, "diag") == {"diagnostics": True}
    assert contract.dispatch("export_diagnostics", {}, "export") == {
        "diagnosticBundle": "/tmp/fake-diagnostics.zip"
    }
    assert system_events[-1][0] == [
        "/usr/bin/open",
        "-R",
        "/tmp/fake-diagnostics.zip",
    ]

    probe.calls.clear()
    contract.dispatch("launch", {}, "launch")
    assert system_events[-1][0] == ["/usr/bin/open", command_contract_module.STEAM_SPEC.launch_url]
    assert probe.calls == [("scan",)]

    probe.runtime.live = False
    probe.calls.clear()
    prepared = contract.dispatch("prepare", {}, "prepare")
    assert prepared == {"route": "scan", "args": (), "operation": {"prepared": True}}
    probe.calls.clear()
    restored = contract.dispatch("restore", {}, "restore")
    assert restored == {"route": "scan", "args": (), "operation": {"restored": True}}
    probe.runtime.live = True
    expect_error("prepare", {}, "请断开连接并退出游戏后操作。")
finally:
    command_contract_module.build_diagnostics = old_build_diagnostics
    command_contract_module.export_diagnostics = old_export_diagnostics
    command_contract_module.subprocess.run = old_subprocess_run
    command_contract_module.preparation.prepare = old_prepare
    command_contract_module.preparation.restore = old_restore


# One final presentation-key funnel owns Hades player-facing error identity.
try:
    contract.dispatch("not_a_command", {}, "unknown-request")
except Hades2PresentationError as error:
    assert error.presentation == "hades2.error.invalidCommand"
    assert error.diagnostic == "未知命令。"
else:
    raise AssertionError("unknown Host command was accepted")

print("hades2_command_contract_ok")
