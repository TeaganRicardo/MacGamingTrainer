from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

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
    "set_desired", {"feature": "godMode", "value": True}
) == {"feature": "godMode", "value": True}
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

assert validate_command_params(
    "spawn_reward", {"reward": "EmptyMaxHealthDrop"}
) == {"reward": "EmptyMaxHealthDrop"}
assert validate_command_params(
    "open_sell_traits", {}
) == {}
assert validate_command_params(
    "open_special_choice", {"source": "Zeus"}
) == {"source": "Zeus"}
expect_error(
    "open_special_choice", {}, "请选择支持原生三选一的特殊祝福来源。"
)
expect_error(
    "open_special_choice", {"source": ""}, "请选择支持原生三选一的特殊祝福来源。"
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

print("hades2_command_validation_ok")
