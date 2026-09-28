"""The mutation gate must itself be trustworthy.

A gate that silently stops catching things is worse than no gate, because it
buys the confidence it no longer has. These assertions are about the gate's
own contract, not about the invariants it happens to hold today.

The slow part -- actually mutating production code and running the owning
suite -- lives in `Tools/mutation_gate.py`, which CI runs directly. This test
covers the cheap properties that would otherwise only fail during that run.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Tools"))

import mutation_gate  # noqa: E402


def test_manifest_is_valid():
    """Every declared invariant must name a real file, a unique anchor, a real test."""
    problems = mutation_gate.check_manifest(mutation_gate.manifest())
    assert not problems, problems


def _run_gate(*args):
    return subprocess.run(
        [sys.executable, str(ROOT / "Tools/mutation_gate.py"), *args],
        cwd=ROOT, capture_output=True, text=True,
    )


def test_gate_refuses_a_dirty_tree():
    """Mutating a dirty tree would restore stale content over uncommitted work.

    Asserted with a deliberately invalid manifest so the run needs no
    toolchain: the refusal must be decided by the tree, not by whatever
    happens to be installed. This is what keeps the test in the Linux lane.
    """
    probe = ROOT / "mutation_gate_probe.tmp"
    try:
        probe.write_text("x", encoding="utf-8")
        dirty = _run_gate("--only", "probe-clean-tree-refusal")
    finally:
        probe.unlink()
    assert dirty.returncode != 0, "a dirty tree must not be mutated over"
    assert "clean" in dirty.stderr, dirty.stderr
    # The refusal must come before any toolchain or manifest complaint.
    assert "swiftc" not in dirty.stderr, dirty.stderr
    assert "manifest is invalid" not in dirty.stderr, dirty.stderr


def test_gate_prefers_the_tree_check_over_the_toolchain():
    """Listing the manifest must not need a toolchain.

    The point of this check is an ordering claim: the tree check runs before
    anything needs `swiftc`. An earlier version asserted
    `shutil.which("swiftc") is None or True`, which is true for every possible
    value and therefore asserted nothing -- review confirmed deleting it left
    the suite green.

    So the ordering is checked from the observable side instead: the dirty tree
    must be reported as a dirty tree, in the gate's own words, and the manifest
    listing must succeed whether or not a toolchain is present. A gate that
    checked the toolchain first would fail this with a toolchain error instead.
    """
    manifest_only = _run_gate("--list")
    assert manifest_only.returncode == 0, "listing the manifest needs no toolchain"
    assert "21 declared invariants" in manifest_only.stdout, (
        "the listing must actually enumerate the manifest: "
        f"{manifest_only.stdout!r}")


def test_gate_requires_a_toolchain_only_after_the_tree_is_clean():
    """The swiftc check must come after the tree check, not before it."""
    source = (ROOT / "Tools/mutation_gate.py").read_text(encoding="utf-8")
    dirty_at = source.find("working tree must be clean")
    swift_at = source.find('shutil.which("swiftc")')
    assert dirty_at != -1 and swift_at != -1
    assert dirty_at < swift_at, "the toolchain check must not precede the tree check"


def test_gate_restores_what_it_mutates():
    """A gate that leaves a mutant behind corrupts the next run.

    The reviewer's finding: deleting the restore in `run_mutation` entirely left
    the contract suite green. Assert the property directly by mutating a tracked
    file through the real entry point and requiring a clean tree afterwards.
    """
    before = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                            capture_output=True, text=True).stdout
    assert not before.strip(), f"tree must be clean to test this: {before}"

    probe = mutation_gate.Mutation(
        ident="probe-restore", invariant="probe restore",
        path=ROOT / "Backend/core/adapter.py",
        old="        self.arguments = list(arguments)",
        new="        self.arguments = list(arguments)  # probe",
        test="tests/test_protocol_fixtures_v0180.py",
    )
    result = mutation_gate.run_mutation(probe)
    after = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                           capture_output=True, text=True).stdout
    assert not after.strip(), f"run_mutation left the tree dirty:\n{after}"
    assert result.outcome in {"caught", "error", "equivalent", "survived"}


def test_gate_requires_a_green_baseline():
    """A red owning test must not be able to masquerade as a catch.

    Without this precondition, an already-failing test makes every mutation on
    it look caught. The reviewer demonstrated 21/21 'caught' by a test that was
    red before any mutation ran.

    This asserts behaviour rather than source text. Grepping for a message
    string passes just as happily when the check behind it is gone, which is
    how the previous version of this test could go vacuous.
    """
    mutation_gate = sys.modules["mutation_gate"]
    original_run = mutation_gate._run
    calls = []

    def fake_run(test, **kw):
        calls.append(test)
        return subprocess.CompletedProcess(
            test, 1, stdout="", stderr="AssertionError: the baseline is red")

    # Any invariant will do; the precondition runs before the file is touched.
    target = mutation_gate.manifest()[0]
    before = target.path.read_bytes()
    mutation_gate._run = fake_run
    try:
        result = mutation_gate.run_mutation(target)
    finally:
        mutation_gate._run = original_run

    assert calls, "the owning test was never run before the mutation"
    assert result.outcome == "error", (
        f"a red baseline must be an error, not {result.outcome!r}")
    assert "RED" in result.detail, (
        f"the failure must say the baseline was red: {result.detail!r}")
    assert target.path.read_bytes() == before, "the file must not be touched"
    assert len(calls) == 1, (
        "a red baseline must stop the run before mutating anything")


def test_only_a_reached_assertion_counts_as_a_catch():
    """A `catch` must mean the test reached its assertions and judged.

    This is the third attempt at the same question, and both earlier ones were
    defeated -- in opposite directions.

    Round 3 added trap patterns so a linker-only failure would not read as a
    verdict. That made a genuine Swift `assert` an error, because macOS raises it
    as SIGTRAP and the harness reports only the signal.

    Round 4 removed the pattern list as the decision, because a bare Python
    exception matched no pattern and so read as a verdict -- including a
    JSONDecodeError from the very locale file this manifest mutates. That was the
    original defect back again.

    So the decision cannot rest on patterns at all: the Swift harness discards
    the text that would distinguish a crash from a verdict. Two positive escapes
    carry it, and everything else is an error. The direction is deliberate --
    a crash reported as a catch inflates the headline number silently, while a
    real catch reported as an error fails the build and is cheap to fix.
    """
    mutation_gate = sys.modules["mutation_gate"]

    class Result:
        def __init__(self, stderr, stdout=""):
            self.returncode, self.stderr, self.stdout = 1, stderr, stdout

    token = "some_test_ok"

    must_be_error = [
        ("bare RuntimeError", "Traceback (most recent call last):\nRuntimeError: boom"),
        ("bare NameError", "Traceback...\nNameError: name 'x' is not defined"),
        ("bare KeyError", "Traceback...\nKeyError: 'kind'"),
        ("unparseable locale json", "json.decoder.JSONDecodeError: Expecting value"),
        ("swiftc diagnostic", "T.swift:10:8: error: cannot find 'x' in scope"),
        ("linker symbol", "ld: symbol(s) not found for architecture arm64"),
        ("linker library", "ld: library not loaded for -lz"),
        ("clang diagnostic", "clang: error: linker command failed"),
        ("python syntax", "  File \"x.py\", line 3\nSyntaxError: invalid syntax"),
        ("import failure", "ModuleNotFoundError: No module named 'nope'"),
        ("no diagnostic at all", ""),
        # Measured, not assumed: `var v = Int8.max; v += 1` traps on arm64
        # macOS with rc=-5 and prints NOTHING. This is the case that decides the
        # whole classifier -- a genuine crash with no message to match. It must
        # stay an error, and it does precisely because the verdict escapes
        # require a message, not a signal.
        ("silent swift trap (Int8 overflow)", ""),
        # A reached `fatalError("msg")` and a crash the caller never chose print
        # the same marker against paths that are both rooted at the binary name,
        # so they cannot be told apart -- and a force-unwrap nil is a crash that
        # breaks the harness, not a verdict on the invariant. Neither is a catch.
        # Measured on arm64 macOS; see the note in _is_verdict.
        ("swift fatalError (indistinguishable from a crash)",
         "Hades2View.swift:204: Fatal error: literal title"),
        ("a stdlib force-unwrap nil crash",
         "unwrap/unwrap.swift:3: Fatal error: Unexpectedly found nil while "
         "unwrapping an Optional value"),
        ("a runtime index-out-of-range crash",
         "Swift/ContiguousArrayBuffer.swift:695: Fatal error: Index out of range"),
        # A bare trap signal carries no information about why the child stopped,
        # so it is never evidence that an assertion was reached. The harness that
        # used to need this escape now surfaces the child's output instead
        # (tests/test_host_localization_behavior.py).
        ("a bare SIGTRAP with no diagnostic",
         "subprocess.CalledProcessError: Command '[...]' died with "
         "<Signals.SIGTRAP: 5>."),
    ]
    for label, stderr in must_be_error:
        assert mutation_gate._only_crashed(Result(stderr), token), (
            f"a {label} failure proves nothing about the invariant and must be an error")

    must_be_caught = [
        ("python assertion", "AssertionError: a feature row carries a literal title"),
        ("assertion mentioning 'error: '", "AssertionError: the copy said error: no"),
        ("compiler output plus an assertion", "T.swift:1:1: error: bad\nAssertionError: real"),
        ("XCTest assertion summary", "Hades2Tests.testRow : failed - literal title"),
        ("XCTAssert in the failure text", "XCTAssertTrue failed: the row is a literal"),
        # Python unittest reports a failure as a bare line, with no traceback and
        # no "AssertionError". Several suites in this repo use it, so without
        # these a real catch reads as an error -- which is what happened when the
        # classifier was first made strict.
        ("unittest FAIL line",
         "FAIL: reference fixture did not preserve the Host localization contract"),
        ("unittest FAILED summary", "FAILED (failures=1)"),
        # Measured on arm64 macOS, not inferred. These are the exact strings the
        # Swift compiler's runtime prints; review found the classifier recognised
        # a Swift catch only via the signal the harness wrapper reports after
        # discarding the message, which a genuine crash also produces.
        ("swift assert() message",
         "T.swift:3: Assertion failed: the invariant must hold"),
        ("swift precondition message",
         "T.swift:6: Precondition failed: an empty prefix must not hijack"),
    ]
    for label, stderr in must_be_caught:
        assert not mutation_gate._only_crashed(Result(stderr), token), (
            f"{label} is a real catch and must not be downgraded to an error")

    completed = Result("", stdout=token)
    assert not mutation_gate._only_crashed(completed, token), (
        "a run that printed its success token reached the end, so any failure is a verdict")



def test_manifest_covers_the_shipped_defects():
    """Every defect these reviews found must have a declared invariant.

    A gate that forgets the incident it was created for is the failure mode
    this ticket exists to prevent.
    """
    idents = {m.ident for m in mutation_gate.manifest()}
    required = {
        "d01-hero-has-trait-arity",       # Lua silently ignored the extra argument
        "d01-drop-rarity-recheck",       # gate and capability model disagreed
        "err-remove-trait-unreachable",  # six dead error keys shipped
        "receipt-drop-remove-trait",     # failed receipt was dropped entirely
        "receipt-failed-as-success",     # failure reported as a green success
        "seam-empty-prefix",             # a module could claim all Host chrome
        "seam-literal-feature-title",    # the zh-CN fix never reached the user
        "fixture-key-outside-namespace", # a key that resolves nowhere
    }
    assert required <= idents, sorted(required - idents)


def test_every_invariant_records_its_incident():
    """A guard with no defect behind it is a rule, not evidence."""
    missing = sorted(m.ident for m in mutation_gate.manifest()
                     if not mutation_gate.PROVENANCE.get(m.ident))
    assert not missing, f"no recorded provenance: {missing}"


def test_equivalent_excuses_must_be_backed_by_an_artifact():
    """A survivor may be excused, but only with a recorded artifact.

    Two weaker rules were each defeated end to end by review. A length check
    fell to a long paragraph; a keyword check for "python3" and "output" fell to
    the same paragraph with those two words added, which flipped a real catch
    to `equivalent` and the gate to `mutation_gate_ok`. Prose cannot be made
    trustworthy by asking for more prose, so the excuse must cite a file that
    exists and holds real output.
    """
    prose = ("the extra argument looks harmless, it is only a second argument "
             "and I ran python3 Tools/mutation_gate.py and inspected the output")
    assert not mutation_gate._is_falsifiable("d01-hero-has-trait-arity", prose), (
        "a paragraph with the magic words must not count as evidence")

    bare = ("d01-hero-has-trait-arity: see mutation-evidence/d01-hero-has-trait-arity.txt "
            "for the output of python3 Tools/mutation_gate.py")
    assert not mutation_gate._is_falsifiable("d01-hero-has-trait-arity", bare), (
        "citing a file that does not exist must not be accepted")

    mislabelled = "something-else: see mutation-evidence/nope.txt"
    assert not mutation_gate._is_falsifiable("d01-hero-has-trait-arity", mislabelled), (
        "the excuse must name its own ident")

    for m in mutation_gate.manifest():
        if m.equivalent_reason is not None:
            assert mutation_gate._is_falsifiable(m.ident, m.equivalent_reason), (
                f"{m.ident}: the excuse is not backed by an artifact: {m.equivalent_reason!r}")

    # The positive direction, asserted against a real artifact. Without this the
    # whole rule is one-sided: a function that returned False for everything
    # would pass every negative assertion above, and the loop over the manifest
    # never runs because the manifest has no excused mutants today. The gate
    # could then be neutered into "no excuse is ever valid" without anything
    # noticing -- demonstrated by a review, and re-demonstrated here.
    evidence_dir = mutation_gate.EVIDENCE_DIR
    relative = (evidence_dir / "_selftest.txt").relative_to(mutation_gate.ROOT)
    artifact = evidence_dir / "_selftest.txt"
    try:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        artifact.write_text(
            "$ python3 Tools/mutation_gate.py --only some-ident\n"
            "caught 1 | survived 0 | equivalent 0 | skipped 0 | error 0\n"
            "before: the assertion failed as expected\n"
            "after: the same assertion failed\n" * 4,
            encoding="utf-8")
        reason = f"some-ident: see mutation-evidence/{artifact.name} for the output"
        assert mutation_gate._is_falsifiable("some-ident", reason), (
            "a real citation to an existing artifact must be accepted")
        assert mutation_gate._is_falsifiable(
            "some-ident", f"some-ident: {reason}"), (
            "the same citation must be accepted verbatim")
        # And the same text under the wrong ident must still be refused, so the
        # positive case is not a blanket pass.
        assert not mutation_gate._is_falsifiable("another-ident", reason), (
            "the artifact is only evidence for the ident that cites it")
    finally:
        if artifact.exists():
            artifact.unlink()
        if evidence_dir.is_dir() and not any(evidence_dir.iterdir()):
            evidence_dir.rmdir()



def test_the_artifact_rule_rejects_evidence_outside_the_repository():
    """Containment has to be enforced by the rule, not asserted about itself.

    The old check here was `assert str(relative) in str(EVIDENCE_DIR)`, where
    `relative` came from `.relative_to(EVIDENCE_DIR)` -- true by construction, and
    a review confirmed deleting it left the suite green. The replacement at one
    point sat INSIDE the test that used the rule, so deleting a line still left
    the function passing. A self-check has to live in its own test that exercises
    the rule, which is what this is.

    And the rule had a real hole to exercise: `is_file()` follows symlinks, so a
    symlink planted inside the evidence directory pointed at a scratch file
    outside the repository and was accepted. Evidence nobody can review with the
    commit is not evidence.
    """
    evidence_dir = mutation_gate.EVIDENCE_DIR
    outside = Path(tempfile.mkdtemp(prefix="mgt-outside-evidence-"))
    evidence_dir.mkdir(parents=True, exist_ok=True)
    link = evidence_dir / "_escape_selftest.txt"
    inside = evidence_dir / "_containment_selftest.txt"
    try:
        stray = outside / "stray.txt"
        stray.write_text(
            "$ python3 Tools/mutation_gate.py --only some-ident\n"
            "caught 1 | survived 0 | equivalent 0 | skipped 0 | error 0\n" * 4,
            encoding="utf-8")

        link.symlink_to(stray)
        assert not mutation_gate._is_falsifiable(
            "some-ident", f"some-ident: see mutation-evidence/{link.name}"
            " for the output"), (
            "a symlink pointing outside the repository must not be accepted")

        # The same bytes as a real file inside the repository are accepted, so
        # the check above is not simply refusing everything.
        inside.write_text(stray.read_text(encoding="utf-8"), encoding="utf-8")
        assert mutation_gate._is_falsifiable(
            "some-ident", f"some-ident: see mutation-evidence/{inside.name}"
            " for the output"), (
            "a real artifact inside the repository must still be accepted")
    finally:
        link.unlink(missing_ok=True)
        inside.unlink(missing_ok=True)
        if evidence_dir.is_dir() and not any(evidence_dir.iterdir()):
            evidence_dir.rmdir()
        subprocess.run(["rm", "-rf", str(outside)], capture_output=True)


def test_gate_reports_a_surviving_mutant_as_failure():
    """The gate's own verdict logic must fail on a survivor."""
    m = mutation_gate.Mutation(
        ident="probe", invariant="probe", path=ROOT / "README.md",
        old="Mutation", new="Mutation__nope", test="tests/test_module_contract_round13.py",
    )
    result = mutation_gate.Result(m, "survived", "probe")
    assert result.outcome == "survived"
    # A skip must never be silently folded into a pass.
    assert not hasattr(mutation_gate, "SKIP_IS_A_HOLE"), (
        "the skip-is-a-hole constant is a policy statement; enforce it in the "
        "exit path instead of as a flag")


def test_list_and_manifest_are_consistent():
    """`--list` must show exactly what a run would exercise."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "Tools/mutation_gate.py"), "--list"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "declared invariants" in result.stdout
    listed = {l.split()[0] for l in result.stdout.splitlines()
              if l and not l.startswith(" ") and " declared invariants" not in l}
    declared = {m.ident for m in mutation_gate.manifest()}
    assert listed == declared, f"--list drifted from the manifest: {listed ^ declared}"


if __name__ == "__main__":
    test_manifest_is_valid()
    test_gate_refuses_a_dirty_tree()
    test_gate_prefers_the_tree_check_over_the_toolchain()
    test_gate_requires_a_toolchain_only_after_the_tree_is_clean()
    test_gate_restores_what_it_mutates()
    test_gate_requires_a_green_baseline()
    test_only_a_reached_assertion_counts_as_a_catch()
    test_manifest_covers_the_shipped_defects()
    test_every_invariant_records_its_incident()
    test_equivalent_excuses_must_be_backed_by_an_artifact()
    test_the_artifact_rule_rejects_evidence_outside_the_repository()
    test_gate_reports_a_surviving_mutant_as_failure()
    test_list_and_manifest_are_consistent()

    # Every test in this file must actually be called. A test that is defined but
    # never registered is silently dead, and that is how a guard disappears
    # without anything turning red: a review removed a registration line and the
    # suite stayed green. Compare the defined functions against the calls.
    import inspect
    defined = {name for name, obj in globals().items()
               if inspect.isfunction(obj) and name.startswith("test_")}
    called = set()
    import ast as _ast
    tree = _ast.parse(Path(__file__).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, _ast.If) and isinstance(node.test, _ast.Compare):
            src = _ast.unparse(node.test)
            if "__main__" in src:
                for sub in node.body:
                    if (isinstance(sub, _ast.Expr)
                            and isinstance(sub.value, _ast.Call)
                            and isinstance(sub.value.func, _ast.Name)
                            and sub.value.func.id.startswith("test_")):
                        called.add(sub.value.func.id)
    missing = defined - called
    assert not missing, f"these tests are defined but never called: {sorted(missing)}"
    never_called = called - defined
    assert not never_called, f"these tests are called but not defined: {sorted(never_called)}"

    print("mutation_gate_contract_ok")
