import ast
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "tests/contract_evidence.json"
TEST_EVIDENCE_TYPES = {"behavior", "compiled-behavior", "diff-gate", "source-boundary"}
WORKFLOW_CONFIG_TYPE = "workflow-config"
CONFIG_ONLY_CLAIM = (
    "configuration-only; does not attest a workflow run/check result or source SHA"
)
REQUIRED_INVARIANTS = {
    "host.connection-lifetime",
    "host.single-backend-session",
    "backend.recovery-no-request-replay",
    "module.cross-game-isolation",
    "swift.production-graph-build-configured",
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


class EvidenceMapError(AssertionError):
    pass


def _require(condition, message):
    if not condition:
        raise EvidenceMapError(message)


def _has_test_failure_path(source):
    tree = ast.parse(source)
    return any(
        isinstance(node, (ast.Assert, ast.Raise))
        or (
            isinstance(node, ast.Call)
            and (
                (isinstance(node.func, ast.Name) and node.func.id in {"fail", "fatalError"})
                or (isinstance(node.func, ast.Attribute) and node.func.attr == "assert")
            )
        )
        for node in ast.walk(tree)
    )


def validate_evidence_item(item, root, macos_only=(), execute=True):
    """Validate schema v2: behavioral tests execute a declared marker; workflow-config only proves wiring."""
    _require(isinstance(item, dict), "evidence item must be an object")
    evidence_type = item.get("type")
    if evidence_type == WORKFLOW_CONFIG_TYPE:
        expected_keys = {"type", "sourcePath", "marker", "command", "claim"}
    elif evidence_type in TEST_EVIDENCE_TYPES:
        expected_keys = {"type", "sourcePath", "marker", "command"}
        if evidence_type == "source-boundary":
            expected_keys.add("reason")
        if "declaredInvariants" in item:
            # The behavioural invariants a gate declares. Recorded here so the
            # evidence map and the gate cannot drift apart.
            expected_keys.add("declaredInvariants")
    else:
        raise EvidenceMapError("unsupported evidence type {!r}".format(evidence_type))
    _require(set(item) == expected_keys, "evidence fields must be exactly {}".format(sorted(expected_keys)))

    source_path = item["sourcePath"]
    _require(
        isinstance(source_path, str)
        and source_path
        and not Path(source_path).is_absolute()
        and ".." not in Path(source_path).parts,
        "sourcePath must be a repository-relative path",
    )
    source_file = root / source_path
    _require(source_file.is_file(), "referenced evidence does not exist: {}".format(source_path))
    source = source_file.read_text(encoding="utf-8")
    marker = item["marker"]
    command = item["command"]
    _require(isinstance(marker, str) and marker.strip(), "marker is required")
    _require(isinstance(command, str) and command.strip(), "command is required")

    if evidence_type == WORKFLOW_CONFIG_TYPE:
        _require(item["claim"] == CONFIG_ONLY_CLAIM, "workflow config must not claim a verified run/check/SHA")
        _require(marker in source, "workflow configuration marker not found: {}".format(marker))
        _require(command in source, "workflow configured command not found: {}".format(command))
        return "configuration-only"

    if "declaredInvariants" in item:
        groups = item["declaredInvariants"]
        _require(isinstance(groups, dict) and groups, "declaredInvariants must be a non-empty object")
        declared = set()
        for group_name, group in groups.items():
            _require(isinstance(group, dict), "declaredInvariants group must be an object")
            _require(set(group) == {"claim", "idents"},
                     "declaredInvariants group fields must be exactly claim and idents")
            _require(isinstance(group["claim"], str) and group["claim"].strip(),
                     "each group needs a claim")
            _require(isinstance(group["idents"], list) and group["idents"],
                     "each group needs idents")
            for ident in group["idents"]:
                _require(isinstance(ident, str) and ident.strip(), "ident must be a non-empty string")
                _require(ident not in declared, "ident declared twice: {}".format(ident))
                declared.add(ident)

    if evidence_type == "source-boundary":
        _require(isinstance(item["reason"], str) and item["reason"].strip(), "source-boundary requires a reason")
    _require(command == "python3 {}".format(source_path), "test command must run its declared sourcePath directly")
    _require(marker in source, "success marker is not identifiable in source: {}".format(marker))
    _require(_has_test_failure_path(source), "test evidence must contain an assertion or explicit failure path")
    _require(marker.endswith("_ok"), "test success marker must use the explicit _ok suffix")

    if not execute:
        return "declared"
    if evidence_type == "compiled-behavior" and sys.platform != "darwin":
        return "unavailable: compiled Swift behavior requires macOS"
    if sys.platform != "darwin" and source_path in macos_only:
        return "unavailable: macOS-only test on {}".format(sys.platform)

    result = subprocess.run(
        ["python3", source_path],
        cwd=str(root),
        text=True,
        capture_output=True,
        timeout=180,
    )
    _require(
        result.returncode == 0,
        "evidence command failed ({}):\n{}{}".format(
            command, result.stdout, result.stderr
        ),
    )
    _require(
        marker in result.stdout.splitlines(),
        "evidence command did not emit success marker {!r}: {}".format(marker, command),
    )
    return "executed"


def validate_contract_evidence(data, root=ROOT, execute=True):
    _require(isinstance(data, dict), "contract evidence map must be an object")
    _require(set(data) == {"schemaVersion", "invariants"}, "contract evidence map has unexpected top-level fields")
    _require(data.get("schemaVersion") == 2, "contract evidence map schemaVersion must be 2")
    invariants = data.get("invariants")
    _require(isinstance(invariants, dict) and invariants, "contract evidence map must define invariants")
    missing = sorted(REQUIRED_INVARIANTS - set(invariants))
    _require(not missing, "contract evidence map missing stable invariants: {}".format(missing))

    macos_only_file = root / "Tools/macos_only_tests.txt"
    _require(macos_only_file.is_file(), "macOS-only test list is missing")
    macos_only = {
        line.strip()
        for line in macos_only_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }

    results = []
    for invariant_id, entry in sorted(invariants.items()):
        _require(isinstance(entry, dict), "{}: entry must be an object".format(invariant_id))
        _require(set(entry) == {"evidence"}, "{}: entry must contain only evidence".format(invariant_id))
        evidence = entry["evidence"]
        _require(isinstance(evidence, list) and evidence, "{}: evidence must be non-empty".format(invariant_id))
        for index, item in enumerate(evidence):
            prefix = "{}.evidence[{}]".format(invariant_id, index)
            try:
                result = validate_evidence_item(item, root, macos_only=macos_only, execute=execute)
            except EvidenceMapError as error:
                raise EvidenceMapError("{}: {}".format(prefix, error))
            results.append(result)
    return results


def test_noop_placeholder_is_not_evidence():
    with tempfile.TemporaryDirectory(prefix="mgt-evidence-noop-") as directory:
        root = Path(directory)
        test_dir = root / "tests"
        test_dir.mkdir()
        (test_dir / "noop_placeholder.py").write_text(
            "print('noop_placeholder_ok')\n", encoding="utf-8"
        )
        placeholder = {
            "type": "behavior",
            "sourcePath": "tests/noop_placeholder.py",
            "marker": "noop_placeholder_ok",
            "command": "python3 tests/noop_placeholder.py",
        }
        bad_marker = dict(placeholder, marker="file_exists_only")
        try:
            validate_evidence_item(bad_marker, root, execute=False)
        except EvidenceMapError as error:
            _require("not identifiable" in str(error), "placeholder marker rejected for unexpected reason")
        else:
            raise AssertionError("file-exists-only marker was accepted")
        try:
            validate_evidence_item(placeholder, root, execute=False)
        except EvidenceMapError as error:
            _require("assertion or explicit failure path" in str(error), "noop rejected for unexpected reason")
        else:
            raise AssertionError("no-op placeholder was accepted as behavior evidence")


def test_shortcut_compiled_behavior_fails_closed_without_swiftc():
    with tempfile.TemporaryDirectory(prefix="mgt-no-swiftc-") as directory:
        result = subprocess.run(
            [sys.executable, str(ROOT / "tests/test_shortcut_chord_semantics.py")],
            cwd=str(ROOT),
            env=dict(os.environ, PATH=directory),
            text=True,
            capture_output=True,
            timeout=10,
        )
    _require(result.returncode != 0, "shortcut compiled-behavior test silently passed without swiftc")
    _require("swiftc required" in result.stderr, "missing swiftc did not produce an explicit failure")


def _declared_mutation_idents(data):
    """Every ident the evidence map claims the mutation gate declares."""
    entry = (data.get("invariants") or {}).get(
        "mutation.declared-invariants-fail-under-mutation")
    if not entry:
        return set()
    found = set()
    for item in entry.get("evidence", []):
        for group in (item.get("declaredInvariants") or {}).values():
            found.update(group.get("idents", []))
    return found


def test_evidence_map_and_mutation_gate_cannot_drift():
    """The gate and the evidence map must declare the same invariants.

    The review's MAJOR: the manifest is hand-maintained, so a behavioural guard
    could be added without appearing in the evidence map. Binding them here
    makes a declared invariant reviewable evidence rather than a private note
    inside a tool, and makes an undeclared guard a build failure.
    """
    sys.path.insert(0, str(ROOT / "Tools"))
    import mutation_gate  # noqa: E402

    data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    by_gate = {m.ident for m in mutation_gate.manifest()}
    by_map = _declared_mutation_idents(data)
    _require(
        by_gate == by_map,
        "the mutation gate and the evidence map declare different invariants; "
        "gate-only: {}; map-only: {}".format(sorted(by_gate - by_map), sorted(by_map - by_gate)),
    )

    missing = sorted(i for i in by_gate if not mutation_gate.PROVENANCE.get(i))
    _require(not missing, "these invariants have no recorded provenance: {}".format(missing))


def test_a_map_that_disagrees_with_the_gate_is_rejected():
    """The drift rule must reject a real disagreement, not merely exist.

    A review deleted the `by_gate == by_map` assertion, dropped an ident from the
    evidence map, and the suite still passed. The rule was correct and simply
    unverified -- the same defect shape as the round-1 CRITICAL. So the rule is
    now exercised here against a map that is genuinely wrong, in this file,
    without depending on another suite noticing.
    """
    sys.path.insert(0, str(ROOT / "Tools"))
    import mutation_gate  # noqa: E402

    data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    by_gate = {m.ident for m in mutation_gate.manifest()}
    by_map = _declared_mutation_idents(data)
    _require(by_map == by_gate,
             "the committed map must agree with the gate for this test to mean anything")

    # Drop one declared invariant and require the comparison to notice, naming it.
    groups = data["invariants"][
        "mutation.declared-invariants-fail-under-mutation"]["evidence"][0]["declaredInvariants"]
    victim = next((name for name, group in groups.items() if group["idents"]), None)
    _require(victim is not None, "the map declares no invariants to remove")
    dropped = groups[victim]["idents"].pop()
    try:
        reduced = _declared_mutation_idents(data)
        _require(by_gate != reduced, "removing {} from the map must break the comparison".format(dropped))
        _require(by_gate - reduced == {dropped},
                 "the difference must name exactly the dropped invariant, got {}".format(
                     sorted(by_gate - reduced)))
    finally:
        groups[victim]["idents"].append(dropped)


def test_equivalent_excuses_must_be_falsifiable():
    """A survivor may be excused, but only with a re-runnable observation."""
    sys.path.insert(0, str(ROOT / "Tools"))
    import mutation_gate  # noqa: E402

    _require(
        not mutation_gate._is_falsifiable(
            "d01-hero-has-trait-arity",
            "the extra argument looks harmless, it is only a second argument"),
        "a paragraph asserting harmlessness must not count as evidence",
    )
    for m in mutation_gate.manifest():
        if m.equivalent_reason is None:
            continue
        _require(
            mutation_gate._is_falsifiable(m.ident, m.equivalent_reason),
            "{}: the excuse is prose, not evidence: {!r}".format(m.ident, m.equivalent_reason),
        )


def main():
    test_noop_placeholder_is_not_evidence()
    test_shortcut_compiled_behavior_fails_closed_without_swiftc()
    test_evidence_map_and_mutation_gate_cannot_drift()
    test_a_map_that_disagrees_with_the_gate_is_rejected()
    test_equivalent_excuses_must_be_falsifiable()
    _require(MAP_PATH.is_file(), "contract evidence map is missing")
    data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    results = validate_contract_evidence(data)
    executed = results.count("executed")
    unavailable = len(results) - executed - results.count("configuration-only")
    print(
        "contract_evidence_map_ok ({} test markers executed, {} platform-unavailable, {} workflow configs only)".format(
            executed, unavailable, results.count("configuration-only")
        )
    )


if __name__ == "__main__":
    main()
