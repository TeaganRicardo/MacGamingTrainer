"""#704 Direction B is one World Actions contract in both game modules."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades.schema import WORLD_COMMANDS
from games.hades.world import mutation_params
from runtime_revision_support import runtime_revision

manifest = json.loads((ROOT / "Backend/games/hades/module.json").read_text(encoding="utf-8"))
runtime = (ROOT / "Backend/games/hades/runtime.lua").read_text(encoding="utf-8")
types = (ROOT / "Sources/Hades/HadesTypes.swift").read_text(encoding="utf-8")
model = (ROOT / "Sources/Hades/HadesModule.swift").read_text(encoding="utf-8")
view = (ROOT / "Sources/Hades/HadesRoomsPanel.swift").read_text(encoding="utf-8")
core = (ROOT / "Sources/Core/UI/Components/TrainerListControls.swift").read_text(encoding="utf-8")

assert manifest["protocolVersion"] >= 3
assert runtime_revision(runtime) >= 12

required = {
    "apply_world_exit", "cancel_world_exit",
    "apply_world_occurrence", "cancel_world_occurrence",
}
assert required <= WORLD_COMMANDS
for retired in ("set_door_reward", "set_door_route", "restore_door"):
    assert retired not in WORLD_COMMANDS
    assert f"function runtime.{retired}" not in runtime

assert mutation_params("apply_world_exit", {
    "roomId": "room:1",
    "doorToken": "exit:1",
    "kind": "reward",
    "target": "AthenaUpgrade",
}) == {
    "roomId": "room:1",
    "doorToken": "exit:1",
    "kind": "reward",
    "target": "AthenaUpgrade",
}
assert mutation_params("cancel_world_exit", {
    "roomId": "room:1",
    "doorToken": "exit:1",
    "leaseToken": "lease:1",
}) == {
    "roomId": "room:1",
    "doorToken": "exit:1",
    "leaseToken": "lease:1",
}
assert mutation_params("apply_world_occurrence", {"target": "thanatos"}) == {
    "target": "thanatos",
}
assert mutation_params("cancel_world_occurrence", {"leaseToken": "occurrence:1"}) == {
    "leaseToken": "occurrence:1",
}

assert "struct HadesWorldActionTarget" in types
assert "let targets: [HadesWorldActionTarget]" in types
assert "let activeLease: HadesWorldActionLease?" in types
assert "let occurrenceTargets: [String]" in types
assert "let occurrence: HadesWorldOccurrenceLease?" in types
assert "toggleWorldExit" in model
assert "toggleWorldOccurrence" in model

rooms = view[view.index("struct HadesRoomsPanel"):view.index("}", view.index("struct HadesRoomsPanel")) + 1]
# Search the whole source for the load-bearing names because Swift nested braces
# make a syntactic region parser unnecessary for this contract.
assert "worldExitRow" in view
assert "worldOccurrenceRow" in view
assert "latched: door?.activeLease != nil" in view
assert "latched: model.world?.occurrence != nil" in view
for retired in (
    '"set_door_reward"', '"set_door_route"', '"restore_door"',
    "hades.thanatosPending", "hades.restoreDoor",
):
    assert retired not in view, retired

assert "let latched: Bool" in core
assert ".accessibilityAddTraits(latched ? .isSelected : [])" in core

print("hades_world_actions_direction_b_ok")
