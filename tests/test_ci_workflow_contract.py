"""Workflow-level contracts that cannot execute outside GitHub Actions.

The scripts the workflows call own their behavior tests (scope classification,
PR smoke selection, runners, build). This file keeps only the workflow
configuration that AGENTS.md states: PR/dispatch triggers, the stable required
check contexts with their Ubuntu fast path, fail-closed scope decisions, the
PR/convergence split, exact-SHA checkout, immutable actions and the pinned
Python runtime. Rules read a parsed step model, never incidental line text.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / '.github/workflows'
TASK_WORKFLOWS = ('linux-contracts.yml', 'build2-macos.yml', 'module-build-matrix.yml')
RELEASE_WORKFLOW = 'direct-release.yml'
PULL_REQUEST = "github.event_name == 'pull_request'"
DISPATCH = "github.event_name == 'workflow_dispatch'"


def _scalar(value):
    value = value.split(' #', 1)[0].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in '\'"':
        return value[1:-1]
    return value


def _parse_block(lines, index, indent):
    if lines[index][1].startswith('- '):
        sequence = []
        while index < len(lines) and lines[index][0] == indent and lines[index][1].startswith('- '):
            item = lines[index][1][2:].strip()
            if re.match(r'[\w.-]+:(\s|$)', item):
                lines[index] = (indent + 2, item)
                node, index = _parse_block(lines, index, indent + 2)
            else:
                node, index = _scalar(item), index + 1
            sequence.append(node)
        return sequence, index
    mapping = {}
    while index < len(lines) and lines[index][0] == indent and not lines[index][1].startswith('- '):
        key, separator, value = lines[index][1].partition(':')
        assert separator, f'unsupported workflow line: {lines[index][1]}'
        value = value.strip()
        index += 1
        if value in ('|', '>'):
            block = []
            while index < len(lines) and lines[index][0] > indent:
                block.append(lines[index][1])
                index += 1
            mapping[key] = '\n'.join(block)
        elif value:
            mapping[key] = _scalar(value)
        elif index < len(lines) and (lines[index][0] > indent or lines[index][1].startswith('- ')):
            mapping[key], index = _parse_block(lines, index, lines[index][0])
        else:
            mapping[key] = None
    return mapping, index


def parse_workflow(path):
    """Parse the block-style YAML subset the workflows use (no PyYAML in CI)."""
    lines = []
    for raw in path.read_text(encoding='utf-8').splitlines():
        content = raw.strip()
        if content and not content.startswith('#'):
            lines.append((len(raw) - len(raw.lstrip(' ')), content))
    workflow, index = _parse_block(lines, 0, 0)
    assert index == len(lines), f'{path.name}: unparsed line {lines[index][1]!r}'
    return workflow


def steps(job):
    return job.get('steps') or []


def conjuncts(condition):
    """Top-level `&&` terms of a workflow condition."""
    text = str(condition or '').strip()
    if text.startswith('${{') and text.endswith('}}'):
        text = text[3:-2]
    terms, depth, start = [], 0, 0
    for index, character in enumerate(text):
        depth += {'(': 1, ')': -1}.get(character, 0)
        if depth == 0 and text.startswith('&&', index):
            terms.append(text[start:index].strip())
            start = index + 2
    terms.append(text[start:].strip())
    return terms


workflows = {name: parse_workflow(WORKFLOW_DIR / name) for name in (*TASK_WORKFLOWS, RELEASE_WORKFLOW)}
all_steps = {
    name: [(job_id, step) for job_id, job in workflow['jobs'].items() for step in steps(job)]
    for name, workflow in workflows.items()
}

# Merged main does not repeat task verification; only the release workflow has
# its own trigger, and it never runs for pull requests.
for name in TASK_WORKFLOWS:
    assert set(workflows[name]['on']) == {'pull_request', 'workflow_dispatch'}, (name, workflows[name]['on'])
assert 'pull_request' not in workflows[RELEASE_WORKFLOW]['on']

# The stable required contexts `backend-contracts`, `build` and
# `build (reference_fixture)` always report: the job is never skipped, falls
# back to an Ubuntu fast path when platform work is unnecessary, and fails
# closed when its scope dependency failed.
REQUIRED_JOBS = {
    'linux-contracts.yml': 'backend-contracts',
    'build2-macos.yml': 'build',
    'module-build-matrix.yml': 'build',
}
for name, job_id in REQUIRED_JOBS.items():
    job = workflows[name]['jobs'][job_id]
    assert job.get('if') in (None, '${{ always() }}'), (name, job_id, job.get('if'))
    runs_on = job['runs-on']
    assert runs_on == 'ubuntu-latest' or re.search(r"\|\|\s*'ubuntu-latest'\s*\}\}$", runs_on), (name, runs_on)
    declared = job.get('needs') or []
    declared = {declared} if isinstance(declared, str) else set(declared)
    referenced = set(re.findall(r'needs\.([\w-]+)\.', json.dumps(job)))
    assert referenced <= declared, (name, job_id, referenced - declared)
    for dependency in declared:
        assert any(
            f"needs.{dependency}.result != 'success'" in str(step.get('if')) and 'exit 1' in str(step.get('run'))
            for step in steps(job)
        ), f'{name}: {job_id} must fail closed when {dependency} fails'
games = workflows['module-build-matrix.yml']['jobs']['build']['strategy']['matrix']['game']
assert 'reference_fixture' in games, games
assert 'hades' in games, 'isolated Hades diagnostics run on explicit convergence'

# An unclassified change (no true|false decision) fails closed instead of
# silently taking the fast path.
DECISIONS = {
    'linux-contracts.yml': ('needs_linux',),
    'build2-macos.yml': ('needs_macos', 'needs_full_build'),
    'module-build-matrix.yml': ('needs_module',),
}
for name, outputs in DECISIONS.items():
    for output in outputs:
        reference = f'steps.scope.outputs.{output}'
        assert any(
            f"{reference} != 'true'" in str(step.get('if'))
            and f"{reference} != 'false'" in str(step.get('if'))
            and 'exit 1' in str(step.get('run'))
            for _, step in all_steps[name]
        ), f'{name}: unclassified {output} must fail closed'

# Recurring verification is PR-owned and diff-based gates need a PR base; full
# macOS contracts, mutation audits, packaging/provenance and retained artifacts
# belong to exact-SHA convergence dispatch.
LANES = (
    ('diff gate', PULL_REQUEST, lambda run, step: 'Tools/check_runtime_revision.py' in run),
    ('macOS PR smoke', PULL_REQUEST,
     lambda run, step: 'Tools/run_macos_checks.sh --pr' in run or 'Tools/select_macos_pr_tests.py' in run),
    ('full macOS contracts', DISPATCH, lambda run, step: re.search(r'Tools/run_macos_checks\.sh\s*$', run, re.M)),
    ('mutation audit', DISPATCH, lambda run, step: 'Tools/mutation_gate.py' in run),
    ('package/provenance', DISPATCH, lambda run, step: '_build_provenance.py' in run or 'ditto -c' in run),
    ('retained artifact', DISPATCH, lambda run, step: str(step.get('uses', '')).startswith('actions/upload-artifact@')
     and 'artifacts/' in str((step.get('with') or {}).get('path'))),
)
EXPECTED_LANES = {
    'linux-contracts.yml': {'diff gate'},
    'build2-macos.yml': {'macOS PR smoke', 'full macOS contracts', 'mutation audit',
                         'package/provenance', 'retained artifact'},
    'module-build-matrix.yml': {'package/provenance', 'retained artifact'},
}
for name, expected in EXPECTED_LANES.items():
    found = set()
    for job_id, step in all_steps[name]:
        for lane, event, matches in LANES:
            if matches(str(step.get('run') or ''), step):
                found.add(lane)
                assert event in conjuncts(step.get('if')), (
                    f"{name}: {step.get('name') or step.get('uses')} ({lane}) must require {event}"
                )
    assert found == expected, (name, found)

# Evidence belongs to the exact PR head: one workflow-level BASE/HEAD pair feeds
# both the scope classifier and every executable checkout.
for name in TASK_WORKFLOWS:
    workflow = workflows[name]
    assert 'github.event.pull_request.head.sha' in workflow['env']['HEAD_SHA'], name
    for job_id, job in workflow['jobs'].items():
        scopes = [job.get('env') or {}, *((step.get('env') or {}) for step in steps(job))]
        assert not any({'BASE_SHA', 'HEAD_SHA'} & set(scope) for scope in scopes), (name, job_id)
    checkouts = [step for _, step in all_steps[name] if str(step.get('uses', '')).startswith('actions/checkout@')]
    assert checkouts and all(step['with']['ref'] == '${{ env.HEAD_SHA }}' for step in checkouts), name

# Supply-chain inputs are immutable commits. The runner context is unavailable
# at job level: using it there makes GitHub reject the whole workflow file.
for name, workflow in workflows.items():
    for job_id, step in all_steps[name]:
        if 'uses' in step:
            assert re.fullmatch(r'[\w.-]+/[\w./-]+@[0-9a-f]{40}', step['uses']), (name, step['uses'])
    for job_id, job in workflow['jobs'].items():
        assert not any('runner.' in str(value) for value in (job.get('env') or {}).values()), (name, job_id)

# Project Python always runs on the interpreter pinned by Tools/python_runtime.json.
RUNTIME_VERSION = json.loads((ROOT / 'Tools/python_runtime.json').read_text())['version']
match = re.fullmatch(r'(\d+\.\d+\.\d+)(?:(a|b|rc)(\d+))?', RUNTIME_VERSION)
assert match, f'unsupported pinned Python version format: {RUNTIME_VERSION}'
CI_PYTHON_VERSION = f'{match.group(1)}-{match.group(2)}.{match.group(3)}' if match.group(2) else match.group(1)
for name, workflow in workflows.items():
    for job_id, job in workflow['jobs'].items():
        job_steps = steps(job)
        setups = [index for index, step in enumerate(job_steps)
                  if str(step.get('uses', '')).startswith('actions/setup-python@')]
        for index in setups:
            assert job_steps[index]['with']['python-version'] == CI_PYTHON_VERSION, (name, job_id)
        python_runs = [index for index, step in enumerate(job_steps)
                       if re.search(r'\bpython3?\b', str(step.get('run') or ''))]
        if python_runs:
            assert setups and setups[0] < python_runs[0], f'{name}: {job_id} runs Python before setup-python'


# A push-triggered release waits for the dispatched convergence lanes on the
# same SHA. The wait must outlast the slowest producer's dispatch budget plus
# runner queueing, and the release job must outlast its wait.
def dispatch_minutes(job):
    value = str(job.get('timeout-minutes'))
    conditional = re.search(r"workflow_dispatch'\s*&&\s*(\d+)", value)
    return int(conditional.group(1) if conditional else value)


producer_minutes = max(dispatch_minutes(job) for name in TASK_WORKFLOWS for job in workflows[name]['jobs'].values())
release_job = workflows[RELEASE_WORKFLOW]['jobs']['release']
waits = [int(step['env']['CONVERGENCE_WAIT_MINUTES']) for step in steps(release_job)
         if 'CONVERGENCE_WAIT_MINUTES' in (step.get('env') or {})]
assert len(waits) == 1, waits
assert waits[0] >= producer_minutes + 30, (waits[0], producer_minutes)
assert dispatch_minutes(release_job) >= waits[0] + 10, (dispatch_minutes(release_job), waits[0])

print('ci_workflow_contract_ok')
