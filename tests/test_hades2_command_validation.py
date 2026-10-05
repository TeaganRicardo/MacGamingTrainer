import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.command_router import Hades2CommandRouter
from games.hades2.command_validation import validate_command_params


def expect_error(command, params, message):
    try:
        validate_command_params(command, params)
    except ValueError as error:
        assert str(error) == message
    else:
        raise AssertionError(f"invalid command accepted: {command} {params!r}")


assert validate_command_params("connect", {}) == {"probeRuntime": True}
assert validate_command_params("connect", {"probeRuntime": False}) == {"probeRuntime": False}
expect_error("connect", {"probeRuntime": 1}, "probeRuntime 必须为布尔值。")

assert validate_command_params(
    "set_desired", {"feature": "invincibility", "value": True}
) == {"feature": "invincibility", "value": True}
assert validate_command_params(
    "set_desired", {"feature": "gameSpeed", "value": 2}
) == {"feature": "gameSpeed", "value": 2.0}
expect_error(
    "set_desired",
    {"feature": "resourceMultiplier", "value": 0},
    "倍率范围为 1–100。",
)

assert validate_command_params(
    "set_vital", {"vital": "health", "field": "current", "value": 120}
) == {"vital": "health", "field": "current", "value": 120}
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

assert validate_command_params(
    "set_counter", {"counter": "spellCharge", "value": 3}
) == {"counter": "spellCharge", "value": 3}
expect_error(
    "set_counter", {"counter": "unknown", "value": 3}, "未知局内计数器。"
)

assert validate_command_params(
    "lock_vital", {"vital": "mana", "locked": True}
) == {"vital": "mana", "locked": True}
expect_error(
    "lock_vital", {"vital": "mana", "locked": 1}, "锁定值必须为布尔值。"
)

assert validate_command_params(
    "set_stat", {"stat": "enemyHealth", "locked": True, "value": 175}
) == {"stat": "enemyHealth", "locked": True, "value": 175}
expect_error(
    "set_stat",
    {"stat": "enemyHealth", "locked": True, "value": 9},
    "敌人生命倍率必须为 10–1000%。",
)

assert validate_command_params(
    "set_element", {"element": "Fire", "amount": 4}
) == {"element": "Fire", "amount": 4}
expect_error(
    "set_element", {"element": "Void", "amount": 4}, "未知元素。"
)
expect_error(
    "set_element", {"element": "Fire", "amount": 1000000},
    "元素数量必须为 0–999999 的整数。",
)

assert validate_command_params(
    "set_resource", {"resource": "Money", "amount": 10}
) == {"resource": "Money", "amount": 10}
assert validate_command_params(
    "lock_resource", {"resource": "Money", "locked": False}
) == {"resource": "Money", "locked": False}
assert validate_command_params(
    "set_rerolls", {"amount": 7}
) == {"amount": 7}
assert validate_command_params(
    "lock_rerolls", {"locked": True}
) == {"locked": True}
assert validate_command_params("reroll_choice", {"menuToken": "observed-menu", "expectedCost": 2}) == {"menuToken": "observed-menu", "expectedCost": 2}
for invalid in ({}, {"menuToken": "", "expectedCost": 1}, {"menuToken": "x", "expectedCost": -1},
                {"menuToken": "x", "expectedCost": True}, {"menuToken": "x", "expectedCost": 1.5}):
    expect_error("reroll_choice", invalid, "请刷新后重新随机当前选项。")

assert validate_command_params(
    "spawn_reward", {"reward": "EmptyMaxHealthDrop"}
) == {"reward": "EmptyMaxHealthDrop"}
assert validate_command_params(
    "acquire_chaos_pair",
    {"blessing": "ChaosHealthBlessing", "curse": "ChaosDamageCurse"},
) == {"blessing": "ChaosHealthBlessing", "curse": "ChaosDamageCurse"}
expect_error(
    "acquire_chaos_pair",
    {"blessing": "ChaosHealthBlessing"},
    "请选择掉落物或祝福。",
)
expect_error(
    "acquire_chaos_pair",
    {"blessing": "", "curse": "ChaosDamageCurse"},
    "请选择掉落物或祝福。",
)
assert validate_command_params(
    "open_sell_traits", {}
) == {}
assert validate_command_params(
    "open_special_choice", {"source": "Zeus"}
) == {"source": "Zeus"}
expect_error(
    "open_special_choice", {}, "请选择支持原生奖励选择界面的角色。"
)
expect_error(
    "open_special_choice", {"source": ""}, "请选择支持原生奖励选择界面的角色。"
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
assert validate_command_params(
    "set_trait_level", dict(trait_target, targetLevel=4)
) == dict(trait_target, targetLevel=4)
assert validate_command_params(
    "set_trait_rarity", dict(trait_target, rarity="Epic")
) == dict(trait_target, rarity="Epic")
assert validate_command_params("remove_trait", trait_target) == trait_target
assert validate_command_params("advance_trait_lifecycle", trait_target) == trait_target

temporary_target = dict(trait_target, family="temporary", expectedRemainingUses=5)
assert validate_command_params(
    "set_trait_remaining_uses", dict(temporary_target, targetRemainingUses=8)
) == dict(temporary_target, targetRemainingUses=8)
assert validate_command_params("expire_trait", temporary_target) == temporary_target
expired_uses_target = dict(trait_target, family="temporary", expectedRemainingUses=0)
assert validate_command_params("remove_trait", expired_uses_target) == expired_uses_target
assert validate_command_params(
    "set_trait_remaining_uses", dict(expired_uses_target, targetRemainingUses=2)
) == dict(expired_uses_target, targetRemainingUses=2)
expect_error(
    "set_trait_remaining_uses",
    dict(temporary_target, targetRemainingUses=0),
    "剩余次数必须为 1–999999 的整数。",
)
expect_error(
    "set_trait_remaining_uses",
    dict({key: value for key, value in temporary_target.items() if key != "expectedRemainingUses"},
         targetRemainingUses=8),
    "请选择当前局效果。",
)
expect_error(
    "expire_trait",
    {key: value for key, value in temporary_target.items() if key != "expectedRemainingUses"},
    "请选择当前局效果。",
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
    "remove_trait",
    dict(trait_target, expectedSameNameCount=0),
    "请选择当前局祝福。",
)
expect_error(
    "set_trait_rarity",
    dict(trait_target, rarity="Mythic"),
    "最低稀有度无效。",
)

assert validate_command_params(
    "set_boon_rarity_desired",
    {
        "target": "Epic",
        "multiplier": 250,
        "forceLegendary": True,
        "forceDuo": False,
    },
) == {
    "target": "Epic",
    "multiplier": 250,
    "forceLegendary": True,
    "forceDuo": False,
}
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

assert validate_command_params(
    "set_next_room_reward_desired", {"reward": "WeaponUpgrade"}
) == {"reward": "WeaponUpgrade"}
assert validate_command_params(
    "set_next_room_reward_desired", {"reward": None}
) == {"reward": None}
expect_error(
    "set_next_room_reward_desired",
    {"reward": "x" * 129},
    "下一房奖励无效。",
)

# Request identity is router-owned; validation only returns JSON-compatible command params.
# Commands with no pure parameter contract pass through a defensive copy.
original = {"ignored": "value"}
validated = validate_command_params("status", original)
assert validated == original and validated is not original

class RuntimeProbe:
    def __init__(self):
        self.calls = []

    def execute(self, command, params):
        self.calls.append((command, params))
        return {"ok": True}

probe = RuntimeProbe()
router = Hades2CommandRouter(probe)
result = router.dispatch(
    "acquire_chaos_pair",
    {"blessing": "ChaosHealthBlessing", "curse": "ChaosDamageCurse"},
    "chaos-pair-router-request",
)
assert result == {"ok": True}
assert probe.calls == [(
    "acquire_chaos_pair",
    {
        "blessing": "ChaosHealthBlessing",
        "curse": "ChaosDamageCurse",
        "requestId": "chaos-pair-router-request",
    },
)]
router.dispatch("reroll_choice", {"menuToken": "observed-menu", "expectedCost": 2}, "reroll-router-request")
assert probe.calls[-1] == ("reroll_choice", {"menuToken": "observed-menu", "expectedCost": 2, "requestId": "reroll-router-request"})

print("hades2_command_validation_ok")
