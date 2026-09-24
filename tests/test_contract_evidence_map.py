import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "tests/contract_evidence.json"

assert MAP_PATH.is_file(), "contract evidence map is missing"
data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
assert data.get("schemaVersion") == 1, "contract evidence map schemaVersion must be 1"

invariants = data.get("invariants")
assert isinstance(invariants, dict) and invariants, "contract evidence map must define invariants"

allowed_types = {
    "behavior",
    "compiled-behavior",
    "build",
    "diff-gate",
    "source-boundary",
}
required_invariants = {
    "host.connection-lifetime",
    "host.single-backend-session",
    "backend.recovery-no-request-replay",
    "module.cross-game-isolation",
    "hades.same-pid-runtime-generation",
    "hades.resident-runtime-static-wiring",
    "hades.retired-protocol-surface",
    "mutation.outcome-unknown-taints-transport",
    "save.transaction-recovery",
    "shortcut.collision-reflow",
    "runtime.revision-diff-discipline",
    "profile.version-compatibility",
    "ci.portable-test-discovery",
}

missing = sorted(required_invariants - set(invariants))
assert not missing, f"contract evidence map missing stable invariants: {missing}"

for invariant_id, entry in sorted(invariants.items()):
    assert isinstance(entry, dict), f"{invariant_id}: entry must be an object"
    evidence = entry.get("evidence")
    assert isinstance(evidence, list) and evidence, f"{invariant_id}: evidence must be a non-empty list"

    for index, item in enumerate(evidence):
        prefix = f"{invariant_id}.evidence[{index}]"
        assert isinstance(item, dict), f"{prefix}: evidence item must be an object"
        evidence_type = item.get("type")
        path = item.get("path")
        assert evidence_type in allowed_types, f"{prefix}: unsupported evidence type {evidence_type!r}"
        assert isinstance(path, str) and path, f"{prefix}: path is required"
        assert (ROOT / path).is_file(), f"{prefix}: referenced evidence does not exist: {path}"
        if evidence_type == "source-boundary":
            reason = item.get("reason")
            assert isinstance(reason, str) and reason.strip(), (
                f"{prefix}: source-boundary evidence requires a reason why behavior/build evidence is impractical"
            )

assert (ROOT / "tests/test_host_module_session_ownership.py").is_file(), (
    "single backend-session ownership must have a focused boundary contract"
)

print("contract_evidence_map_ok")
