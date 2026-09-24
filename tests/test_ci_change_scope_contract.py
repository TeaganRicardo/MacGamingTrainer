from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = [
    ROOT / '.github/workflows/linux-contracts.yml',
    ROOT / '.github/workflows/build2-macos.yml',
    ROOT / '.github/workflows/module-build-matrix.yml',
]
for workflow in WORKFLOWS:
    assert workflow.is_file(), workflow
    text = workflow.read_text()

    # Every lane resolves the change scope exactly once, at workflow level.
    # Both consumers (docs-only detection and the runtime revision gate) must
    # read the same BASE_SHA/HEAD_SHA pair, so a PR that is behind main cannot
    # have main-side runtime changes pollute the revision-gate diff.
    assert 'env:' in text, f'{workflow.name}: missing workflow-level env block'
    assert 'BASE_SHA:' in text, f'{workflow.name}: missing workflow-level BASE_SHA'
    assert 'HEAD_SHA:' in text, f'{workflow.name}: missing workflow-level HEAD_SHA'
    # The single canonical scope expression must resolve to the PR head on
    # pull_request events and github.sha elsewhere (push: the pushed commit).
    assert 'github.event.pull_request.head.sha || github.sha' in text, (
        f'{workflow.name}: HEAD_SHA must resolve to the PR head, not the merge ref'
    )
    # No lane may keep a second, divergent inline scope expression. Workflow-
    # level env uses 2-space indent; any deeper-indented re-declaration is a
    # step-level inline copy and is forbidden.
    inline = re.findall(
        r"^(?P<indent>[ ]{4,})BASE_SHA: \$\{\{ github\.event_name == 'pull_request'[^}]*\}\}",
        text,
        re.M,
    )
    step_inline = re.findall(
        r"^(?P<indent>[ ]{4,})HEAD_SHA: \$\{\{ github\.event_name == 'pull_request'[^}]*\}\}",
        text,
        re.M,
    )
    assert not inline and not step_inline, (
        f'{workflow.name}: change scope must not be re-declared inline per step'
    )

    # The runtime revision gate must consume the workflow-level scope pair.
    if 'check_runtime_revision.py' in text:
        gate_call = text.split('check_runtime_revision.py', 1)[1]
        gate_call = gate_call.split('\n', 1)[1] if '\n' in gate_call else gate_call
        m = re.search(r'run:.*?python3 Tools/check_runtime_revision\.py[^\n]*', text, re.S)
        assert m, f'{workflow.name}: runtime revision gate call not found'
        call_line = [l for l in text.splitlines() if 'check_runtime_revision.py' in l][0]
        assert '"$BASE_SHA"' in call_line and '"$HEAD_SHA"' in call_line, (
            f'{workflow.name}: revision gate must use the workflow-level scope env'
        )

    # Cancellation: PR runs cancel stale superseded runs of the same PR; main
    # pushes never cancel each other.
    assert 'concurrency:' in text, f'{workflow.name}: missing concurrency control'
    assert 'group: ${{ github.workflow }}-' in text, f'{workflow.name}: concurrency group must include workflow name'
    pr_cancel = re.search(r'cancel-in-progress:.*', text)
    assert pr_cancel, f'{workflow.name}: cancel-in-progress must be declared'

print('change_scope_contract_ok')
