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


class RuntimeProbe:
    def alive(self):
        return True


class AdapterProbe:
    def __init__(self):
        self.runtime = RuntimeProbe()
        self.calls = []

    def set_next_occurrence_once(self, target, request_id):
        self.calls.append(("set_next_occurrence_once", target, request_id))
        return {"nextOccurrenceTarget": target}


probe = AdapterProbe()
contract = Hades2CommandContract(probe)

result = contract.dispatch(
    "set_next_occurrence_once",
    {"target": "npc:Nemesis"},
    "occurrence-request",
)
assert result["nextOccurrenceTarget"] == "npc:Nemesis"
assert probe.calls == [
    ("set_next_occurrence_once", "npc:Nemesis", "occurrence-request")
]

probe.calls.clear()
result = contract.dispatch(
    "set_next_occurrence_once",
    {"target": None},
    "occurrence-clear",
)
assert result["nextOccurrenceTarget"] is None
assert probe.calls == [
    ("set_next_occurrence_once", None, "occurrence-clear")
]

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

print("hades2_occurrence_live_action_contract_ok")
