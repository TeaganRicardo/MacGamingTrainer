import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.command_contract import Hades2CommandContract, command_metadata
from games.hades2.preferences import (
    DESIRED_STATE_SCHEMA_VERSION,
    Hades2PreferenceStore,
    normalize_persisted_desired,
)


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


probe = AdapterProbe()
contract = Hades2CommandContract(probe)

contract.dispatch(
    "apply_world_occurrence",
    {"target": "npc:Nemesis"},
    "occurrence-request",
)
assert probe.calls == [(
    "apply_world_occurrence",
    {"target": "npc:Nemesis", "requestId": "occurrence-request"},
)]

probe.calls.clear()
contract.dispatch(
    "cancel_world_occurrence",
    {"leaseToken": "occurrence-request"},
    "occurrence-clear",
)
assert probe.calls == [(
    "cancel_world_occurrence",
    {"leaseToken": "occurrence-request", "requestId": "occurrence-clear"},
)]

names = {row["name"] for row in command_metadata()}
assert {"apply_world_occurrence", "cancel_world_occurrence"} <= names
assert "set_next_occurrence_once" not in names
assert "set_next_occurrence_desired" not in names

assert DESIRED_STATE_SCHEMA_VERSION == 12
for raw in (
    {
        "nextOccurrenceTarget": "npc:Nemesis",
        "nextOccurrenceToken": "occurrence-token",
    },
    {
        "nextOccurrenceTarget": None,
        "nextOccurrenceToken": "stale-token",
    },
):
    normalized = Hades2PreferenceStore.normalize(raw)
    assert "nextOccurrenceTarget" not in normalized
    assert "nextOccurrenceToken" not in normalized

for version in (8, 9, 11, 12):
    normalized = normalize_persisted_desired(
        {
            "schemaVersion": version,
            "nextOccurrenceTarget": "npc:Nemesis",
            "nextOccurrenceToken": "legacy-token",
        },
        version,
    )
    assert "nextOccurrenceTarget" not in normalized, version
    assert "nextOccurrenceToken" not in normalized, version

print("hades2_occurrence_world_action_contract_ok")
