"""Hades World Actions and other world one-shots share one validated boundary."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.adapter import AdapterError
from games.hades.adapter import HadesAdapter
from games.hades.schema import DEFAULT_PREFERENCES, ONE_SHOT_COMMANDS
from games.hades.world import WORLD_COMMANDS, mutation_params, reward_catalog, runtime_definitions

assert WORLD_COMMANDS <= ONE_SHOT_COMMANDS
assert WORLD_COMMANDS.isdisjoint(DEFAULT_PREFERENCES)
assert {"apply_world_exit", "cancel_world_exit", "apply_world_occurrence", "cancel_world_occurrence"} <= WORLD_COMMANDS
assert {"set_door_reward", "set_door_route", "restore_door"}.isdisjoint(WORLD_COMMANDS)

for row in reward_catalog():
    assert row["names"]["zh-CN"] and row["names"]["en"]
    assert runtime_definitions()[row["id"]]["kind"] in ("loot", "consumable")

exit_apply = {
    "roomId": "runtime:run:room",
    "doorToken": "exit:run:room:door:target",
    "kind": "reward",
    "actionTarget": "AthenaUpgrade",
}
assert HadesAdapter._mutation_params("apply_world_exit", exit_apply) == exit_apply
assert mutation_params("cancel_world_exit", {
    "roomId": "runtime:run:room",
    "doorToken": "exit:run:room:door:target",
    "leaseToken": "lease:exit:1",
}) == {
    "roomId": "runtime:run:room",
    "doorToken": "exit:run:room:door:target",
    "leaseToken": "lease:exit:1",
}
assert mutation_params("apply_world_occurrence", {"actionTarget": "thanatos"}) == {
    "actionTarget": "thanatos",
}
assert mutation_params("cancel_world_occurrence", {"leaseToken": "lease:occurrence:1"}) == {
    "leaseToken": "lease:occurrence:1",
}
assert mutation_params("gain_resource", {"resource": "Gems", "amount": 20}) == {
    "resource": "Gems", "amount": 20,
}

for command, payload, expected in (
    ("apply_world_exit", {**exit_apply, "roomId": ""}, "stale_room"),
    ("apply_world_exit", {**exit_apply, "doorToken": ""}, "stale_door"),
    ("apply_world_exit", {**exit_apply, "actionTarget": "TrialUpgrade"}, "invalid_value"),
    ("apply_world_exit", {**exit_apply, "kind": "roomCategory", "actionTarget": "arbitraryMap"}, "invalid_value"),
    ("cancel_world_exit", {**exit_apply, "leaseToken": ""}, "stale_door"),
    ("apply_world_occurrence", {"actionTarget": "arbitraryNPC"}, "invalid_value"),
    ("cancel_world_occurrence", {"leaseToken": ""}, "stale_door"),
    ("spawn_reward", {**exit_apply, "reward": "ArbitraryLua"}, "invalid_value"),
    ("generate_chamber_object", {**exit_apply, "object": "arbitraryObject"}, "invalid_value"),
    ("gain_resource", {"resource": "Gems", "amount": True}, "invalid_value"),
    ("gain_resource", {"resource": "Gems", "amount": 1.5}, "invalid_value"),
    ("gain_resource", {"resource": "Gems", "amount": -1}, "invalid_value"),
):
    try:
        HadesAdapter._mutation_params(command, payload)
    except AdapterError as error:
        assert error.code == expected, (command, error.code)
    else:
        raise AssertionError((command, payload))

print("hades_world_commands_ok")
