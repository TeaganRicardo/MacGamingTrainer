"""The mutation gate must itself be trustworthy.

A gate that silently stops catching things is worse than no gate, because it
buys the confidence it no longer has. These assertions are about the gate's
own contract, not about the invariants it happens to hold today.

The slow part -- actually mutating production code and running the owning
suite -- lives in `Tools/mutation_gate.py`, which the Build 2 macOS
convergence lane runs directly. That run also validates the manifest's anchors
and owning tests before it mutates anything. Anchors are exact production
text, so this pull-request lane deliberately does not validate them: it covers
the gate's own validator, runner and classifier against temporary fixtures,
never against production anchors, and it does not need a clean checkout.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Tools"))

import mutation_gate  # noqa: E402


def _probe(tmp, *, checks_target):
    """A temporary production file and an owning test that may or may not read it."""
    target = Path(tmp) / "target.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    test = Path(tmp) / "test_probe.py"
    assertion = (f"assert open({str(target)!r}).read() == 'VALUE = 1\\n', 'VALUE changed'\n"
                 if checks_target else "")
    test.write_text(f"{assertion}print('probe_ok')\n", encoding="utf-8")
    mutation = mutation_gate.Mutation(
        ident="probe", invariant="VALUE is preserved", path=target,
        old="VALUE = 1", new="VALUE = 2", test=str(test),
    )
    return target, mutation


def test_success_token_is_discovered_from_the_owning_test():
    """The owning test declares one *_ok marker; the harness never mirrors it."""
    with tempfile.TemporaryDirectory(prefix="mgt-mg-token-") as tmp:
        single = Path(tmp) / "test_single.py"
        single.write_text("print('single_ok')\n", encoding="utf-8")
        assert mutation_gate.success_token_for(str(single)) == "single_ok"

        embedded = Path(tmp) / "test_embedded.py"
        embedded.write_text("HARNESS = 'print(\"embedded_ok\")'\n", encoding="utf-8")
        assert mutation_gate.success_token_for(str(embedded)) == "embedded_ok"

        ambiguous = Path(tmp) / "test_ambiguous.py"
        ambiguous.write_text("print('one_ok')\nprint('two_ok')\n", encoding="utf-8")
        try:
            mutation_gate.success_token_for(str(ambiguous))
        except ValueError as error:
            assert "multiple" in str(error), error
        else:
            raise AssertionError("two completion markers must not resolve to either one")


def test_manifest_validation_reports_each_invalid_entry():
    """The gate's first stage refuses each kind of stale or invalid entry.

    Production anchors are validated only when the gate runs. The validator
    itself is checked here on fixtures, so a defect in it fails the pull
    request rather than the next convergence run.
    """
    owning_test = "tests/test_mutation_gate_contract.py"
    idents = ("fixture-valid",)
    with tempfile.TemporaryDirectory(prefix="mgt-mg-manifest-") as tmp:
        target = Path(tmp) / "target.py"
        target.write_text("VALUE = 1\nREPEATED = 1\nREPEATED = 1\n", encoding="utf-8")

        def entry(ident="fixture-valid", path=target, old="VALUE = 1", test=owning_test):
            return mutation_gate.Mutation(ident=ident, invariant="fixture", path=path,
                                          old=old, new="VALUE = 2", test=test)

        for ident in idents:
            mutation_gate.PROVENANCE[ident] = "contract-test fixture"
        try:
            assert mutation_gate.check_manifest([entry()]) == []
            cases = (
                ("missing anchor", [entry(old="ABSENT = 1")], "anchor not found"),
                ("non-unique anchor", [entry(old="REPEATED = 1")], "anchor appears 2x"),
                ("duplicate ident", [entry(), entry()], "duplicate ident"),
                ("test outside tests/", [entry(test="Tools/mutation_gate.py")], "must be a tests/ path"),
                ("missing test", [entry(test="tests/test_does_not_exist.py")], "test does not exist"),
                ("no provenance", [entry(ident="fixture-unrecorded")], "no provenance recorded"),
                ("missing production file", [entry(path=Path(tmp) / "absent.py")], "production file missing"),
            )
            for label, mutations, expected in cases:
                problems = mutation_gate.check_manifest(mutations)
                assert len(problems) == 1 and expected in problems[0], (label, problems)
        finally:
            for ident in idents:
                mutation_gate.PROVENANCE.pop(ident, None)


def _run_gate(*args):
    return subprocess.run(
        [sys.executable, str(ROOT / "Tools/mutation_gate.py"), *args],
        cwd=ROOT, capture_output=True, text=True,
    )


def test_gate_refuses_a_dirty_tree():
    """Mutating a dirty tree would restore stale content over uncommitted work.

    A real invariant selection must reach the dirty-tree refusal before the
    gate checks its manifest or toolchain.
    """
    probe = ROOT / "mutation_gate_probe.tmp"
    try:
        probe.write_text("x", encoding="utf-8")
        dirty = _run_gate("--only", "protocol-error-arguments")
    finally:
        probe.unlink()
    assert dirty.returncode != 0, "a dirty tree must not be mutated over"
    assert "working tree must be clean before running the gate:" in dirty.stderr, dirty.stderr
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
    expected = f"{len(mutation_gate.manifest())} declared invariants"
    assert expected in manifest_only.stdout, (
        "the listing must actually enumerate the manifest: "
        f"{manifest_only.stdout!r}")


def test_git_status_failure_is_not_a_clean_tree():
    """A failed git inspection must fail closed with actionable diagnostics."""
    original_run = mutation_gate.subprocess.run

    def failing_git(*args, **kwargs):
        return subprocess.CompletedProcess(
            args[0], 128, stdout="", stderr="fatal: not a git repository"
        )

    mutation_gate.subprocess.run = failing_git
    try:
        failure = mutation_gate.verify_clean_tree()
    finally:
        mutation_gate.subprocess.run = original_run

    assert failure, "failed git status was interpreted as a clean worktree"
    assert "128" in failure, failure
    assert "fatal: not a git repository" in failure, failure


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
    the contract suite green. Assert the property directly through the real
    runner, with a real owning test that catches the mutation.
    """
    with tempfile.TemporaryDirectory(prefix="mgt-mg-restore-") as tmp:
        target, probe = _probe(tmp, checks_target=True)
        before = target.read_bytes()
        result = mutation_gate.run_mutation(probe)
        assert target.read_bytes() == before, "run_mutation left the target mutated"
        assert result.outcome == "caught", result


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

    with tempfile.TemporaryDirectory(prefix="mgt-mg-red-") as tmp:
        _, target = _probe(tmp, checks_target=True)
        before = target.path.read_bytes()
        mutation_gate._run = fake_run
        try:
            result = mutation_gate.run_mutation(target)
        finally:
            mutation_gate._run = original_run
        after = target.path.read_bytes()

    assert calls, "the owning test was never run before the mutation"
    assert result.outcome == "error", (
        f"a red baseline must be an error, not {result.outcome!r}")
    assert "RED" in result.detail, (
        f"the failure must say the baseline was red: {result.detail!r}")
    assert after == before, "the file must not be touched"
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
        ("unittest errors summary", "FAILED (errors=1)"),
        ("unittest zero failures with errors", "FAILED (failures=0, errors=1)"),
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

    for failure in ("ModuleNotFoundError('missing fixture')", "TypeError('invalid fixture')"):
        program = ("import unittest\nclass BrokenHarness(unittest.TestCase):\n"
                   "    def test_fixture(self): raise " + failure + "\nunittest.main()\n")
        crashed = subprocess.run([sys.executable, '-c', program], capture_output=True, text=True)
        assert crashed.returncode != 0 and 'FAILED (errors=1)' in crashed.stderr, crashed.stderr
        assert mutation_gate._only_crashed(crashed, token), 'unittest harness errors were counted as mutation catches'

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
        ("unittest mixed failure summary", "FAILED (failures=1, errors=1)"),
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
        # #227 replaced the old D01 SellTraits-only mutation model with the
        # live target/capability/replay contract. Do not require retired
        # mutation anchors to survive after the owning behavior seam changes.
        "receipt-drop-remove-trait",     # failed receipt was dropped entirely
        "receipt-failed-as-success",     # failure reported as a green success
        "seam-empty-prefix",             # a module could claim all Host chrome
        "seam-literal-feature-title",    # the zh-CN fix never reached the user
        "fixture-key-outside-namespace", # a key that resolves nowhere
    }
    assert required <= idents, sorted(required - idents)


def test_manifest_covers_final_hardening_seams():
    """The final #203 gate must protect the completed hardening seams."""
    idents = {m.ident for m in mutation_gate.manifest()}
    required = {
        "core-time-warp-presentation",
        "host-registry-forbidden-term",
        "diagnostics-toggle-source",
        "diagnostics-host-protocol-symbol",
        "error-registry-producer",
        "package-product-version-owner",
        "package-module-identity",
    }
    assert required <= idents, sorted(required - idents)


def test_manifest_covers_c05_drift_classes():
    """C05 drift enforcement stays represented by executable mutations."""
    idents = {m.ident for m in mutation_gate.manifest()}
    required = {
        "terminology-metadata-provenance",
        "hades-internal-term-leak",
        "hades-compatibility-alias-leak",
        "runtime-error-code-identity",
        "core-registry-vocabulary-leak",
    }
    assert required <= idents, sorted(required - idents)


def test_every_invariant_records_its_incident():
    """A guard with no defect behind it is a rule, not evidence."""
    missing = sorted(m.ident for m in mutation_gate.manifest()
                     if not mutation_gate.PROVENANCE.get(m.ident))
    assert not missing, f"no recorded provenance: {missing}"


def test_gate_reports_a_real_surviving_mutant_as_failure():
    """An uncaught production mutation must fail the gate.

    This drives the real mutation runner rather than constructing a Result by
    hand. The owning test never reads the mutated file, so the mutation must
    survive it; the gate must then turn the survivor into a failing exit status
    and restore the file. No survivor can be excused.
    """
    with tempfile.TemporaryDirectory(prefix="mgt-mg-survivor-") as tmp:
        target, m = _probe(tmp, checks_target=False)
        before = target.read_bytes()
        result = mutation_gate.run_mutation(m)
        assert result.outcome == "survived", result
        assert mutation_gate.exit_code_for([result]) != 0, (
            "a real surviving mutant must fail the gate")
        assert target.read_bytes() == before, (
            "the real survivor probe left the target mutated")


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


def test_baseline_cache_reuses_green_clean_run_and_isolates_failures():
    """Sharing an owning test runs its green baseline once, never reusing red runs."""
    with tempfile.TemporaryDirectory(prefix="mgt-mg-cache-") as tmp:
        target = Path(tmp) / "target.py"
        original = "X = 1\nY = 1\n"
        target.write_text(original, encoding="utf-8")
        m1 = mutation_gate.Mutation(
            ident="m1", invariant="X preserved", path=target,
            old="X = 1", new="X = 2", test="tests/test_shared_ok.py",
        )
        m2 = mutation_gate.Mutation(
            ident="m2", invariant="Y preserved", path=target,
            old="Y = 1", new="Y = 2", test="tests/test_shared_ok.py",
        )
        calls: list[str] = []
        original_run = mutation_gate._run
        original_token = mutation_gate.success_token_for

        def fake_run_green(test: str, **kw):
            calls.append(test)
            if target.read_text(encoding="utf-8") == original:
                return subprocess.CompletedProcess([test], 0, stdout="shared_ok\n", stderr="")
            return subprocess.CompletedProcess([test], 1, stdout="", stderr="AssertionError: broken")

        mutation_gate.success_token_for = lambda test: "shared_ok"
        mutation_gate._run = fake_run_green
        try:
            results = mutation_gate.run_mutations([m1, m2])
        finally:
            mutation_gate._run = original_run
            mutation_gate.success_token_for = original_token

        assert [r.outcome for r in results] == ["caught", "caught"], results
        assert len(calls) == 3, ("expected 1 clean + 2 mutated runs, got", len(calls))
        assert target.read_text(encoding="utf-8") == original

        # Failing clean baselines must not be cached across mutations.
        calls.clear()

        def fake_run_red(test: str, **kw):
            calls.append(test)
            return subprocess.CompletedProcess([test], 1, stdout="", stderr="AssertionError: baseline red")

        mutation_gate.success_token_for = lambda test: "shared_ok"
        mutation_gate._run = fake_run_red
        try:
            red_results = mutation_gate.run_mutations([m1, m2])
        finally:
            mutation_gate._run = original_run
            mutation_gate.success_token_for = original_token

        assert all(r.outcome == "error" and "RED" in r.detail for r in red_results), red_results
        assert len(calls) == 2, calls
        assert target.read_text(encoding="utf-8") == original


def test_baseline_cache_fails_closed_on_clean_hash_drift():
    """Tracked clean-hash drift blocks cached baseline reuse and further mutation."""
    with tempfile.TemporaryDirectory(prefix="mgt-mg-drift-") as tmp:
        target = Path(tmp) / "target.py"
        original = "A = 1\n"
        target.write_text(original, encoding="utf-8")
        m = mutation_gate.Mutation(
            ident="m-drift", invariant="A preserved", path=target,
            old="A = 1", new="A = 2", test="tests/test_drift_ok.py",
        )
        expected_hashes = mutation_gate._clean_baseline_hashes([m])
        cache = {
            m.test: (
                subprocess.CompletedProcess([m.test], 0, stdout="drift_ok\n", stderr=""),
                "drift_ok",
            )
        }
        # External drift between mutations must fail closed without calling _run.
        target.write_text("A = 1\n# drifted\n", encoding="utf-8")

        calls: list[str] = []
        original_run = mutation_gate._run
        original_token = mutation_gate.success_token_for
        mutation_gate.success_token_for = lambda test: "drift_ok"
        mutation_gate._run = lambda test, **kw: calls.append(test)
        try:
            res = mutation_gate.run_mutation(
                m, baseline_cache=cache, expected_clean_hashes=expected_hashes,
            )
        finally:
            mutation_gate._run = original_run
            mutation_gate.success_token_for = original_token

        assert res.outcome == "error", res
        assert "drifted" in res.detail and "SHA-256" in res.detail, res.detail
        assert not calls, ("_run must not execute after clean-hash drift", calls)


if __name__ == "__main__":
    test_success_token_is_discovered_from_the_owning_test()
    test_manifest_validation_reports_each_invalid_entry()
    test_gate_refuses_a_dirty_tree()
    test_gate_prefers_the_tree_check_over_the_toolchain()
    test_git_status_failure_is_not_a_clean_tree()
    test_gate_requires_a_toolchain_only_after_the_tree_is_clean()
    test_gate_restores_what_it_mutates()
    test_gate_requires_a_green_baseline()
    test_only_a_reached_assertion_counts_as_a_catch()
    test_manifest_covers_the_shipped_defects()
    test_manifest_covers_final_hardening_seams()
    test_manifest_covers_c05_drift_classes()
    test_every_invariant_records_its_incident()
    test_gate_reports_a_real_surviving_mutant_as_failure()
    test_list_and_manifest_are_consistent()
    test_baseline_cache_reuses_green_clean_run_and_isolates_failures()
    test_baseline_cache_fails_closed_on_clean_hash_drift()

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
