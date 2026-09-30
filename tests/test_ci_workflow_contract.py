import re
from pathlib import Path

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
    # Both consumers must read the same BASE_SHA/HEAD_SHA pair, so a PR that is
    # behind main cannot have unrelated main-side changes pollute its routing.
    assert 'env:' in text, f'{workflow.name}: missing workflow-level env block'
    assert 'BASE_SHA:' in text, f'{workflow.name}: missing workflow-level BASE_SHA'
    assert 'HEAD_SHA:' in text, f'{workflow.name}: missing workflow-level HEAD_SHA'
    assert 'github.event.pull_request.head.sha || github.sha' in text, (
        f'{workflow.name}: HEAD_SHA must resolve to the PR head, not the merge ref'
    )
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

    # Cancellation: PR runs cancel stale superseded runs of the same PR; main
    # pushes never cancel each other.
    assert 'concurrency:' in text, f'{workflow.name}: missing concurrency control'
    assert 'group: ${{ github.workflow }}-' in text, f'{workflow.name}: concurrency group must include workflow name'
    assert re.search(r'cancel-in-progress:.*', text), (
        f'{workflow.name}: cancel-in-progress must be declared'
    )

    # The executable checkout must be the same HEAD_SHA used for diff scope.
    # A scope-only HEAD_SHA with default PR merge checkout gives false
    # exact-head provenance even when both trees happen to match.
    checkouts = re.findall(r'^([ ]*)- uses: actions/checkout@v4\n((?:[ ]+[^\n]*\n)*)', text, re.M)
    assert checkouts, f'{workflow.name}: no executable checkout found'
    for _, block in checkouts:
        assert re.search(r'^\s+ref: \$\{\{ env\.HEAD_SHA \}\}$', block, re.M), (
            f'{workflow.name}: executable checkout must pin the intended HEAD_SHA'
        )

linux = (ROOT / '.github/workflows/linux-contracts.yml').read_text()
assert 'python3 Tools/ci_docs_only.py "$BASE_SHA" "$HEAD_SHA"' in linux
assert "steps.scope.outputs.needs_linux == 'true'" in linux
assert "steps.scope.outputs.needs_linux != 'true' && steps.scope.outputs.needs_linux != 'false'" in linux
assert "steps.scope.outputs.needs_linux == 'false'" in linux
runtime_line = [line for line in linux.splitlines() if 'check_runtime_revision.py' in line][0]
assert '"$BASE_SHA"' in runtime_line and '"$HEAD_SHA"' in runtime_line
runner = (ROOT / 'Tools/run_linux_checks.sh').read_text()
assert 'python3 Tools/validate_game_module.py --all' in runner
assert 'validate_game_module.py hades2' not in runner

for shared_tool in (
    ROOT / 'Tools/ci_docs_only.py',
    ROOT / 'Tools/module_inventory.py',
    ROOT / 'Tools/run_linux_checks.sh',
):
    assert 'hades2' not in shared_tool.read_text(), (
        f'{shared_tool.name}: shared module discovery/routing must not name a game id'
    )

build2 = (ROOT / '.github/workflows/build2-macos.yml').read_text()
assert 'scope:\n    runs-on: ubuntu-latest' in build2
assert 'needs_macos: ${{ steps.scope.outputs.needs_macos }}' in build2
assert 'needs: scope' in build2
assert "needs.scope.outputs.needs_macos == 'true' && 'macos-latest' || 'ubuntu-latest'" in build2
assert "steps.scope.outputs.needs_macos != 'true' && steps.scope.outputs.needs_macos != 'false'" in build2
assert "needs.scope.outputs.needs_macos == 'false'" in build2
assert 'bash Tools/run_macos_checks.sh' in build2
assert './build.sh hades2' in build2

module_matrix = (ROOT / '.github/workflows/module-build-matrix.yml').read_text()
assert 'scope:\n    runs-on: ubuntu-latest' in module_matrix
assert 'needs_module: ${{ steps.scope.outputs.needs_module }}' in module_matrix
assert 'needs: scope' in module_matrix
assert "needs.scope.outputs.needs_module == 'true' && 'macos-latest' || 'ubuntu-latest'" in module_matrix
assert "steps.scope.outputs.needs_module != 'true' && steps.scope.outputs.needs_module != 'false'" in module_matrix
assert "needs.scope.outputs.needs_module == 'false'" in module_matrix
assert '- reference_fixture' in module_matrix
assert '- hades2' not in module_matrix, 'Hades II build is already owned by Build 2 macOS'
assert './build.sh "${{ matrix.game }}"' in module_matrix


# Recurring verification is PR-owned; expensive convergence work is explicit.
for name, path in {
    "linux": ROOT / ".github/workflows/linux-contracts.yml",
    "macos": ROOT / ".github/workflows/build2-macos.yml",
    "module": ROOT / ".github/workflows/module-build-matrix.yml",
}.items():
    workflow_text = path.read_text(encoding="utf-8")
    trigger = workflow_text.split("\npermissions:", 1)[0]
    assert "pull_request:" in trigger, f"{name}: PR task verification trigger missing"
    assert "workflow_dispatch:" in trigger, f"{name}: explicit convergence trigger missing"
    assert not re.search(r"^  push:\s*$", trigger, re.M), (
        f"{name}: merged main must not automatically rerun task verification"
    )

revision_pos = linux.index("Enforce diff-based invariants")
revision_window = linux[revision_pos:revision_pos + 500]
assert "github.event_name == 'pull_request'" in revision_window, (
    "diff-based runtime revision enforcement must stay a PR task gate"
)

for step in (
    "Verify declared invariants fail under mutation",
    "Package release candidate",
    "Verify release provenance and checksum",
    "actions/upload-artifact@v4",
):
    pos = build2.index(step)
    window = build2[pos:pos + 700]
    assert "github.event_name == 'workflow_dispatch'" in window, (
        f"Build 2 heavy convergence step is not dispatch-only: {step}"
    )
assert "Run macOS-only contract suite" in build2
assert "Build Hades II trainer" in build2
assert "Verify package" in build2

for step in (
    "Retain reference module artifact and source provenance",
    "Verify reference artifact checksum and declared inputs",
    "actions/upload-artifact@v4",
):
    pos = module_matrix.index(step)
    window = module_matrix[pos:pos + 700]
    assert "github.event_name == 'workflow_dispatch'" in window, (
        f"reference convergence artifact step is not dispatch-only: {step}"
    )
assert "Build selected module" in module_matrix
assert "Verify packaged module isolation" in module_matrix

print("ci_workflow_contract_ok")
