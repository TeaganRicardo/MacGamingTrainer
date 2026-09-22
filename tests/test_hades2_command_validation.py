from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.command_validation import validate_command_params


def expect_error(command, params, message):
    try:
        validate_command_params(command, params, "req-bad")
    except ValueError as error:
        assert str(error) == message
    else:
        raise AssertionError(f"invalid command accepted: {command} {params!r}")


assert validate_command_params("connect", {}, "req") == {"probeRuntime": True}
assert validate_command_params("connect", {"probeRuntime": False}, "req") == {"probeRuntime": False}
expect_error("connect", {"probeRuntime": 1}, "probeRuntime 必须为布尔值。")

assert validate_command_params(
    "set_desired", {"feature": "godMode", "value": True}, "req"
) == {"feature": "godMode", "value": True}
assert validate_command_params(
    "set_desired", {"feature": "gameSpeed", "value": 2}, "req"
) == {"feature": "gameSpeed", "value": 2.0}
expect_error(
    "set_desired",
    {"feature": "resourceMultiplier", "value": 0},
    "倍率范围为 1–100。",
)

assert validate_command_params(
    "set_vital", {"vital": "health", "field": "current", "value": 120}, "req"
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
    "set_counter", {"counter": "spellCharge", "value": 3}, "req"
) == {"counter": "spellCharge", "value": 3}
expect_error(
    "set_counter", {"counter": "unknown", "value": 3}, "未知局内计数器。"
)

assert validate_command_params(
    "lock_vital", {"vital": "mana", "locked": True}, "req"
) == {"vital": "mana", "locked": True}
expect_error(
    "lock_vital", {"vital": "mana", "locked": 1}, "锁定值必须为布尔值。"
)

assert validate_command_params(
    "set_stat", {"stat": "enemyHealth", "locked": True, "value": 175}, "req"
) == {"stat": "enemyHealth", "locked": True, "value": 175}
expect_error(
    "set_stat",
    {"stat": "enemyHealth", "locked": True, "value": 9},
    "敌人生命倍率必须为 10–1000%。",
)

assert validate_command_params(
    "set_element", {"element": "Fire", "amount": 4}, "req"
) == {"element": "Fire", "amount": 4}
expect_error(
    "set_element", {"element": "Void", "amount": 4}, "未知元素。"
)
expect_error(
    "set_element", {"element": "Fire", "amount": 1000000},
    "元素数量必须为 0–999999 的整数。",
)

assert validate_command_params(
    "set_resource", {"resource": "Money", "amount": 10}, "resource-id"
) == {"resource": "Money", "amount": 10, "requestId": "resource-id"}
assert validate_command_params(
    "lock_resource", {"resource": "Money", "locked": False}, "lock-resource-id"
) == {"resource": "Money", "locked": False, "requestId": "lock-resource-id"}
assert validate_command_params(
    "set_rerolls", {"amount": 7}, "reroll-id"
) == {"amount": 7, "requestId": "reroll-id"}
assert validate_command_params(
    "lock_rerolls", {"locked": True}, "lock-reroll-id"
) == {"locked": True, "requestId": "lock-reroll-id"}

assert validate_command_params(
    "spawn_reward", {"reward": "EmptyMaxHealthDrop"}, "spawn-id"
) == {"reward": "EmptyMaxHealthDrop", "requestId": "spawn-id"}
assert validate_command_params(
    "open_sell_traits", {}, "sell-id"
) == {"requestId": "sell-id"}
assert validate_command_params(
    "open_special_choice", {"source": "Zeus"}, "choice-id"
) == {"source": "Zeus", "requestId": "choice-id"}

assert validate_command_params(
    "set_boon_rarity_desired",
    {
        "target": "Epic",
        "multiplier": 250,
        "forceLegendary": True,
        "forceDuo": False,
    },
    "rarity-id",
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
    "set_next_room_reward_desired", {"reward": "WeaponUpgrade"}, "next-room-id"
) == {"reward": "WeaponUpgrade"}
assert validate_command_params(
    "set_next_room_reward_desired", {"reward": None}, "next-room-id"
) == {"reward": None}
expect_error(
    "set_next_room_reward_desired",
    {"reward": "x" * 129},
    "下一房奖励无效。",
)

# Commands with no pure parameter contract pass through a defensive copy.
original = {"ignored": "value"}
validated = validate_command_params("status", original, "status-id")
assert validated == original and validated is not original

print("hades2_command_validation_ok")
