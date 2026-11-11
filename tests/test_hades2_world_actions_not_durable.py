"""World one-shot actions are live resident state, never durable desired intent."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.command_contract import Hades2CommandContract
from games.hades2.preferences import (
    DESIRED_STATE_SCHEMA_VERSION,
    Hades2PreferenceStore,
    normalize_persisted_desired,
)

assert DESIRED_STATE_SCHEMA_VERSION >= 12

for version in (3, 8, 9, 11, DESIRED_STATE_SCHEMA_VERSION):
    normalized = normalize_persisted_desired(
        {
            "schemaVersion": version,
            "nextRoomReward": "WeaponUpgrade",
            "nextRoomRewardToken": "reward-token",
            "nextOccurrenceTarget": "npc:Nemesis",
            "nextOccurrenceToken": "occurrence-token",
        },
        version,
    )
    for key in (
        "nextRoomReward", "nextRoomRewardToken",
        "nextOccurrenceTarget", "nextOccurrenceToken",
    ):
        assert key not in normalized, (version, key, normalized)

defaults = Hades2PreferenceStore.defaults()
for key in (
    "nextRoomReward", "nextRoomRewardToken",
    "nextOccurrenceTarget", "nextOccurrenceToken",
):
    assert key not in defaults, key

class RuntimeProbe:
    def alive(self):
        return True

class AdapterProbe:
    def __init__(self):
        self.runtime = RuntimeProbe()
        self.calls = []

    def execute(self, command, params):
        self.calls.append((command, dict(params)))
        return {"worldActions": {"exits": []}}

    def set_next_occurrence_once(self, target, request_id):
        self.calls.append(("set_next_occurrence_once", target, request_id))
        return {"nextOccurrenceTarget": target}

probe = AdapterProbe()
contract = Hades2CommandContract(probe)

contract.dispatch(
    "apply_world_exit",
    {"doorToken": "exit:1:2:3:4:5", "kind": "reward", "target": "WeaponUpgrade"},
    "world-exit-apply",
)
contract.dispatch(
    "cancel_world_exit",
    {"doorToken": "exit:1:2:3:4:5", "leaseToken": "lease-1"},
    "world-exit-cancel",
)
contract.dispatch(
    "set_next_occurrence_once",
    {"target": "npc:Nemesis"},
    "world-occurrence-request",
)
assert probe.calls == [
    ("apply_world_exit", {
        "doorToken": "exit:1:2:3:4:5", "kind": "reward",
        "target": "WeaponUpgrade", "requestId": "world-exit-apply",
    }),
    ("cancel_world_exit", {
        "doorToken": "exit:1:2:3:4:5", "leaseToken": "lease-1",
        "requestId": "world-exit-cancel",
    }),
    ("set_next_occurrence_once", "npc:Nemesis", "world-occurrence-request"),
]

for retired in (
    "set_next_room_reward_desired", "set_next_room_reward_once",
    "set_next_occurrence_desired",
):
    try:
        contract.dispatch(retired, {}, "retired-request")
    except Exception:
        pass
    else:
        raise AssertionError(retired + " remained a public Host command")

runtime = (ROOT / "Backend/games/hades2/runtime/hades.lua").read_text(encoding="utf-8")
replay = runtime[runtime.index("runtimeConfig.preferenceReplayCommands = {"):runtime.index(
    "function M.dispatchBatch", runtime.index("runtimeConfig.preferenceReplayCommands = {")
)]
assert "set_next_room_reward" not in runtime
assert "set_next_occurrence" not in replay
assert "Next occurrence cannot be preference-replayed" in runtime

print("hades2_world_actions_not_durable_ok")
