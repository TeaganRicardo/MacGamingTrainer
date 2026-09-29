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

print('change_scope_contract_ok')
