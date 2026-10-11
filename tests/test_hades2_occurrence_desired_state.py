import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.command_contract import Hades2CommandContract
from games.hades2.preferences import DESIRED_STATE_SCHEMA_VERSION, Hades2PreferenceStore


class RuntimeProbe:
    def alive(self):
        return False


class AdapterProbe:
    def __init__(self):
        self.runtime = RuntimeProbe()
        self.calls = []

    def set_next_occurrence_desired(self, target):
        self.calls.append(("set_next_occurrence_desired", target))
        return {"nextOccurrenceTarget": target}


probe = AdapterProbe()
contract = Hades2CommandContract(probe)

# The Host command owns only one opaque audited target identity. Native room /
# encounter eligibility remains runtime-owned.
result = contract.dispatch(
    "set_next_occurrence_desired",
    {"target": "npc:Nemesis"},
    "occurrence-request",
)
assert result["nextOccurrenceTarget"] == "npc:Nemesis"
assert probe.calls == [("set_next_occurrence_desired", "npc:Nemesis")]

probe.calls.clear()
result = contract.dispatch(
    "set_next_occurrence_desired",
    {"target": None},
    "occurrence-clear",
)
assert result["nextOccurrenceTarget"] is None
assert probe.calls == [("set_next_occurrence_desired", None)]

# Durable desired state keeps the one-shot identity across backend restarts.
assert DESIRED_STATE_SCHEMA_VERSION == 9
normalized = Hades2PreferenceStore.normalize(
    {
        "nextOccurrenceTarget": "npc:Nemesis",
        "nextOccurrenceToken": "occurrence-token",
    }
)
assert normalized["nextOccurrenceTarget"] == "npc:Nemesis"
assert normalized["nextOccurrenceToken"] == "occurrence-token"

# A token without an armed target is meaningless and must not survive
# normalization.
cleared = Hades2PreferenceStore.normalize(
    {
        "nextOccurrenceTarget": None,
        "nextOccurrenceToken": "stale-token",
    }
)
assert cleared["nextOccurrenceTarget"] is None
assert cleared["nextOccurrenceToken"] is None

print("hades2_occurrence_desired_state_contract_ok")
