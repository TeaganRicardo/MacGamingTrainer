"""Workflow-level contracts that cannot execute outside GitHub Actions.

The scripts the workflows call own their behavior tests (scope classification,
PR smoke selection, runners, build). This file keeps only the workflow
configuration that AGENTS.md states: PR/dispatch triggers and the nightly
Build 2 macOS schedule, the stable required check contexts with their Ubuntu
fast path, fail-closed scope decisions, the PR/convergence split, exact-SHA
checkout, immutable actions and the pinned Python runtime, plus the
toolchain, provenance and release wiring that only a dispatch would otherwise
exercise. Rules read a parsed step model, never incidental line text; a step
whose script is pure logic is executed instead.
"""
import json
import os
import plistlib
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / '.github/workflows'
TASK_WORKFLOWS = ('linux-contracts.yml', 'build2-macos.yml', 'module-build-matrix.yml')
RELEASE_WORKFLOW = 'direct-release.yml'
PULL_REQUEST = "github.event_name == 'pull_request'"
# Every event without a PR diff (dispatch and the nightly schedule) converges.
CONVERGENCE = "github.event_name != 'pull_request'"
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

# Merged main does not repeat PR verification. Build 2 macOS alone adds a
# nightly convergence schedule for earlier signal; the release workflow has its
# own trigger and never runs for pull requests.
SCHEDULED = {'build2-macos.yml'}
for name in TASK_WORKFLOWS:
    expected_events = {'pull_request', 'workflow_dispatch'} | ({'schedule'} if name in SCHEDULED else set())
    assert set(workflows[name]['on']) == expected_events, (name, workflows[name]['on'])
    # Only pull-request runs cancel superseded runs: a repeated dispatch must
    # not cancel the exact-SHA convergence build a release is waiting on.
    assert workflows[name]['concurrency']['cancel-in-progress'] == "${{ github.event_name == 'pull_request' }}", name
for name in SCHEDULED:
    workflow = workflows[name]
    schedule = workflow['on']['schedule']
    assert schedule and all(len(str(entry.get('cron', '')).split()) == 5 for entry in schedule), (name, schedule)
    # A running nightly must not queue a release's convergence dispatch on the
    # same ref behind it, so the event separates the concurrency groups.
    assert '${{ github.event_name }}' in workflow['concurrency']['group'], name
    # A scheduled run has no diff base. The scope classifier must receive none,
    # which it treats as unknown scope and routes to every lane
    # (tests/test_ci_docs_only.py owns that behavior).
    base = workflow['env']['BASE_SHA']
    assert base.startswith('${{') and base.endswith('}}'), base
    pr_base, separator, fallback = base[3:-2].rpartition('||')
    assert separator and fallback.strip() == "''", base
    assert pr_base.strip() == f'{PULL_REQUEST} && github.event.pull_request.base.sha', base
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

# Scoped static tooling belongs to the existing Linux contract, including
# workflow dispatch. Formatting is checked against the exact checkout.
static_commands = set()
for _, step in all_steps['linux-contracts.yml']:
    for line in str(step.get('run') or '').splitlines():
        if line.startswith(('python3 -m ruff ', 'python3 -m mypy')):
            assert conjuncts(step.get('if')) == ["steps.scope.outputs.needs_linux == 'true'"], step
            static_commands.add(tuple(shlex.split(line)[2:]))
assert {('ruff', 'check'), ('ruff', 'format', '--check'), ('mypy',)} <= static_commands, static_commands

# Recurring verification is PR-owned and diff-based gates need a PR base. Full
# macOS contracts and the mutation audit run on every convergence event
# (dispatch and the nightly schedule); release-candidate packaging/provenance
# and retained artifacts belong to explicit exact-SHA dispatch only, because the
# release coordinator consumes nothing else.
LANES = (
    ('diff gate', PULL_REQUEST, lambda run, step: 'Tools/check_runtime_revision.py' in run),
    ('macOS PR smoke', PULL_REQUEST,
     lambda run, step: 'Tools/run_macos_checks.sh --pr' in run or ('Tools/select_macos_pr_tests.py' in run and '--all-prerequisites' not in run)),
    ('macOS convergence prerequisites', CONVERGENCE,
     lambda run, step: 'Tools/select_macos_pr_tests.py --all-prerequisites' in run),
    ('full macOS contracts', CONVERGENCE, lambda run, step: re.search(r'Tools/run_macos_checks\.sh\s*$', run, re.M)),
    ('mutation audit', CONVERGENCE, lambda run, step: 'Tools/mutation_gate.py' in run),
    ('package/provenance', DISPATCH, lambda run, step: '_build_provenance.py' in run or 'ditto -c' in run),
    ('retained artifact', DISPATCH, lambda run, step: str(step.get('uses', '')).startswith('actions/upload-artifact@')
     and 'artifacts/' in str((step.get('with') or {}).get('path'))),
)
EXPECTED_LANES = {
    'linux-contracts.yml': {'diff gate'},
    'build2-macos.yml': {'macOS PR smoke', 'macOS convergence prerequisites', 'full macOS contracts',
                         'mutation audit', 'package/provenance', 'retained artifact'},
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

# Convergence also links, signs and verifies the unified app; a Swift-only pull
# request only typechecks it, so the nightly is where a link failure surfaces.
def requires_convergence(condition):
    return any(CONVERGENCE in (part.strip(' ()') for part in term.split('||'))
               for term in conjuncts(condition))


build2_app_steps = [step for _, step in all_steps['build2-macos.yml']
                    if str(step.get('run') or '').strip() == './build.sh --all'
                    or 'codesign --verify' in str(step.get('run') or '')]
assert len(build2_app_steps) == 2, [step.get('name') for step in build2_app_steps]
for step in build2_app_steps:
    assert requires_convergence(step.get('if')), (step.get('name'), step.get('if'))

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

# Project Python always runs on the interpreter pinned in .python-version and Tools/python_runtime.json.
RUNTIME_VERSION = json.loads((ROOT / 'Tools/python_runtime.json').read_text())['version']
match = re.fullmatch(r'(\d+\.\d+\.\d+)(?:(a|b|rc)(\d+))?', RUNTIME_VERSION)
assert match, f'unsupported pinned Python version format: {RUNTIME_VERSION}'
CI_PYTHON_VERSION = f'{match.group(1)}-{match.group(2)}.{match.group(3)}' if match.group(2) else match.group(1)
assert (ROOT / '.python-version').read_text(encoding='utf-8').strip() == CI_PYTHON_VERSION
for name, workflow in workflows.items():
    for job_id, job in workflow['jobs'].items():
        job_steps = steps(job)
        setups = [index for index, step in enumerate(job_steps)
                  if str(step.get('uses', '')).startswith('actions/setup-python@')]
        for index in setups:
            setup_with = job_steps[index]['with']
            assert setup_with.get('python-version-file') == '.python-version', (name, job_id, setup_with)
            assert 'python-version' not in setup_with, (name, job_id, setup_with)
        python_runs = [index for index, step in enumerate(job_steps)
                       if re.search(r'\bpython3?\b', str(step.get('run') or ''))]
        if python_runs:
            assert setups and setups[0] < python_runs[0], f'{name}: {job_id} runs Python before setup-python'


# A push-triggered release waits for the dispatched convergence lanes on the
# same SHA. The wait must outlast the slowest producer's dispatch budget plus
# runner queueing, and the release job must outlast its wait. A conditional
# budget is bounded by its largest branch.
def dispatch_minutes(job):
    return max(int(minutes) for minutes in re.findall(r'\b\d+\b', str(job['timeout-minutes'])))


producer_minutes = max(dispatch_minutes(job) for name in TASK_WORKFLOWS for job in workflows[name]['jobs'].values())
release_job = workflows[RELEASE_WORKFLOW]['jobs']['release']
waits = [int(step['env']['CONVERGENCE_WAIT_MINUTES']) for step in steps(release_job)
         if 'CONVERGENCE_WAIT_MINUTES' in (step.get('env') or {})]
assert len(waits) == 1, waits
assert waits[0] >= producer_minutes + 30, (waits[0], producer_minutes)
assert dispatch_minutes(release_job) >= waits[0] + 10, (dispatch_minutes(release_job), waits[0])

# Direct release serializes concurrent main pushes and gates every post-precheck
# step on release_needed so non-version Info.plist edits exit cleanly without
# dispatching convergence lanes.
release_workflow = workflows[RELEASE_WORKFLOW]
# Release triggers must queue rather than replacing an earlier pending version bump
# with a later metadata-only push whose precheck correctly skips publication.
assert release_workflow.get('concurrency') == {
    'group': 'direct-release',
    'cancel-in-progress': 'false',
    'queue': 'max',
}, release_workflow.get('concurrency')
release_steps = steps(release_job)
scope_index = next(i for i, step in enumerate(release_steps) if step.get('id') == 'release-scope')
# A push releases only when Tools/release_tag.py's precheck reports a release
# identity change since the previous push.
scope_run = str(release_steps[scope_index].get('run') or '')
assert re.search(r'^\s*needed=\$\(python3 Tools/release_tag\.py --push-precheck ', scope_run, re.M), scope_run
for step in release_steps[scope_index + 1:]:
    assert "steps.release-scope.outputs.release_needed == 'true'" in conjuncts(step.get('if')), step

# Workflows discover and execute declared CI prerequisites generically without
# hardcoding Lua packages or mirrors; Lua 5.2.4 mirrors & SHA-256 checks live in
# Tools/ci_prerequisites/lua52.sh.
linux_workflow_text = (WORKFLOW_DIR / 'linux-contracts.yml').read_text(encoding='utf-8')
build2_workflow_text = (WORKFLOW_DIR / 'build2-macos.yml').read_text(encoding='utf-8')
for marker in ('lua5.2', 'liblua5.2-dev', 'lua-5.2.4', 'lua52_native'):
    assert marker not in linux_workflow_text, ('linux-contracts.yml', marker)
    assert marker not in build2_workflow_text, ('build2-macos.yml', marker)

assert any(
    '--prerequisites' in str(step.get('run') or '') and 'Tools/ci_prerequisites/' in str(step.get('run') or '')
    for _, step in all_steps['linux-contracts.yml']
), 'linux-contracts.yml must install declared CI prerequisites generically'

build2_steps = steps(workflows['build2-macos.yml']['jobs']['build'])
assert any(
    str(step.get('uses', '')).startswith('actions/cache@')
    and 'ci-prerequisites' in str((step.get('with') or {}).get('path'))
    for step in build2_steps
), 'build2-macos.yml must cache ci-prerequisites'
assert any(
    'Tools/ci_prerequisites/${prereq}.sh' in str(step.get('run') or '')
    for step in build2_steps
), 'build2-macos.yml must install declared CI prerequisites generically'

lua52_script = ROOT / 'Tools/ci_prerequisites/lua52.sh'
assert lua52_script.is_file() and os.access(str(lua52_script), os.X_OK), lua52_script
lua52_text = lua52_script.read_text(encoding='utf-8')
for marker in (
    'https://www.lua.org/ftp/lua-5.2.4.tar.gz',
    'https://deb.debian.org/debian/pool/main/l/lua5.2/lua5.2_5.2.4.orig.tar.gz',
    'https://archive.ubuntu.com/ubuntu/pool/universe/l/lua5.2/lua5.2_5.2.4.orig.tar.gz',
    'shasum -a 256 -c -',
    'MGT_LUA52=',
    'lua5.2',
):
    assert marker in lua52_text, marker


def runs(step):
    return str(step.get('run') or '')


def job_of(name, step):
    return next(job_id for job_id, candidate in all_steps[name] if candidate is step)


# A step reads only outputs of steps that ran before it in the same job.
for name, workflow in workflows.items():
    for job_id, job in workflow['jobs'].items():
        earlier = set()
        for step in steps(job):
            referenced = set(re.findall(r'steps\.([\w-]+)\.outputs\.', json.dumps(step)))
            assert referenced <= earlier, (name, job_id, step.get('name'), referenced - earlier)
            if step.get('id'):
                earlier.add(step['id'])

# Every workflow uses one reviewed commit of each action.
action_commits = {}
for name in workflows:
    for _, step in all_steps[name]:
        if 'uses' in step:
            action, commit = step['uses'].split('@')
            action_commits.setdefault(action, set()).add(commit)
assert all(len(commits) == 1 for commits in action_commits.values()), action_commits

# macOS jobs resolve the runner profile and Xcode path from Tools/macos_toolchain_identity.py
# without hardcoding runner labels or Xcode paths in YAML, and verify that toolchain
# before building.
sys.path.insert(0, str(ROOT / 'Tools'))
from macos_toolchain_identity import (  # noqa: E402
    SUPPORTED_DEVELOPER_DIR,
    SUPPORTED_RUNNER_ARCH,
    SUPPORTED_RUNNER_LABEL,
    SUPPORTED_RUNNER_PROFILES,
)
from macos_fixture_policy import HOSTED_ARCH, HOSTED_PROFILE, PROFILE_VARIABLE  # noqa: E402

assert HOSTED_PROFILE == SUPPORTED_RUNNER_LABEL
assert HOSTED_ARCH == SUPPORTED_RUNNER_ARCH
assert HOSTED_PROFILE in SUPPORTED_RUNNER_PROFILES
toolchain_output = subprocess.check_output(
    [sys.executable, str(ROOT / 'Tools/macos_toolchain_identity.py'), '--print-github-output'],
    text=True,
)
assert dict(line.split('=', 1) for line in toolchain_output.splitlines()) == {
    'runner_label': SUPPORTED_RUNNER_LABEL,
    'developer_dir': SUPPORTED_DEVELOPER_DIR,
    'runner_arch': SUPPORTED_RUNNER_ARCH,
}, toolchain_output

macos_jobs = []
for name, workflow in workflows.items():
    raw_yaml = (WORKFLOW_DIR / name).read_text(encoding='utf-8')
    assert not re.search(r'\bmacos-\d+', raw_yaml), (name, 'hardcoded macOS runner label in workflow YAML')
    assert '/Applications/Xcode_' not in raw_yaml, (name, 'hardcoded DEVELOPER_DIR in workflow YAML')
    assert PROFILE_VARIABLE not in (workflow.get('env') or {}), name
    assert 'DEVELOPER_DIR' not in (workflow.get('env') or {}), name
    for job_id, job in workflow['jobs'].items():
        if 'needs.scope.outputs.runner_label' not in str(job['runs-on']):
            continue
        macos_jobs.append((name, job_id))
        scope_job = workflow['jobs']['scope']
        scope_outputs = scope_job.get('outputs') or {}
        assert 'steps.toolchain.outputs.runner_label' in str(scope_outputs.get('runner_label')), (name, scope_outputs)
        assert 'steps.toolchain.outputs.developer_dir' in str(scope_outputs.get('developer_dir')), (name, scope_outputs)
        assert any(
            step.get('id') == 'toolchain'
            and 'Tools/macos_toolchain_identity.py --print-github-output' in runs(step)
            for step in steps(scope_job)
        ), (name, 'scope job must emit toolchain outputs')
        job_env = job.get('env') or {}
        assert job_env.get(PROFILE_VARIABLE) == '${{ needs.scope.outputs.runner_label }}', (name, job_id, job_env)
        assert job_env.get('DEVELOPER_DIR') == '${{ needs.scope.outputs.developer_dir }}', (name, job_id, job_env)
        job_runs = [runs(step) for step in steps(job)]
        identity = next((index for index, run in enumerate(job_runs) if 'Tools/macos_toolchain_identity.py' in run), None)
        assert identity is not None, f'{name}: {job_id} never verifies its macOS toolchain'
        assert all(index > identity for index, run in enumerate(job_runs) if 'build.sh' in run), (name, job_id)
assert {name for name, _ in macos_jobs} == {'build2-macos.yml', 'module-build-matrix.yml'}, macos_jobs
# Hosted macOS steps run under /bin/bash 3.2, whose errexit ignores a failing
# `[[ ]]` or `(( ))`: such a check must branch or exit explicitly.
for name, job_id in macos_jobs:
    for step in steps(workflows[name]['jobs'][job_id]):
        for line in runs(step).splitlines():
            for segment in line.split(';'):
                check = re.sub(r'^(then|do|else|\{)\s+', '', segment.strip())
                if not check.startswith(('[[', '((')):
                    continue
                # Operators inside the test itself do not handle its failure.
                rest = re.sub(r'^\[\[.*?\]\]|^\(\(.*?\)\)', '', check).strip()
                action = rest[2:].strip() if rest.startswith('&&') else ''
                assert rest.startswith('||') or (
                    action and action not in (':', 'true') and not action.startswith(('[[', '(('))
                ), (name, step.get('name'), check)

# A pull request typechecks the unified App unless its diff needs the full
# linked/signed build, which convergence always runs.
typecheck_steps = [step for _, step in all_steps['build2-macos.yml'] if runs(step).strip() == './build.sh --typecheck --all']
assert len(typecheck_steps) == 1, typecheck_steps
assert {PULL_REQUEST, "needs.scope.outputs.needs_build == 'true'",
        "needs.scope.outputs.needs_full_build == 'false'"} <= set(conjuncts(typecheck_steps[0].get('if')))
for step in build2_app_steps:
    alternatives = {part.strip(' ()') for term in conjuncts(step.get('if')) for part in term.split('||')}
    assert "needs.scope.outputs.needs_full_build == 'true'" in alternatives, (step.get('name'), step.get('if'))

# Diff-based steps compare a pull request against its own base, with the full
# history of the exact head checkout.
for name in TASK_WORKFLOWS:
    base = workflows[name]['env']['BASE_SHA']
    assert base.startswith(f'${{{{ {PULL_REQUEST} && github.event.pull_request.base.sha ||'), (name, base)
for name in workflows:
    for job_id, job in workflows[name]['jobs'].items():
        if any('"$BASE_SHA"' in runs(step) for step in steps(job)):
            checkout = next(step for step in steps(job) if str(step.get('uses', '')).startswith('actions/checkout@'))
            assert checkout['with']['fetch-depth'] == '0', (name, job_id)

# Steps that act on a built App locate it through the selection-aware verifier,
# never by listing the output directory.
app_locators = [(name, located) for name in workflows for _, step in all_steps[name]
                for located in re.findall(r'^\s*app=(.*)$', runs(step), re.M)]
assert {name for name, _ in app_locators} == {'build2-macos.yml', 'module-build-matrix.yml'}, app_locators
for name, located in app_locators:
    assert re.fullmatch(r'"?\$\(python3 Tools/verify_module_build\.py [^)]* --print-app\)"?', located), (name, located)
# No step names the output directory or an App bundle itself, so a stale App in
# dist can never be signed, verified or packaged in place of the selection.
for name, workflow in workflows.items():
    for _, step in all_steps[name]:
        assert not re.search(r'\bdist\b|\.app\b', json.dumps(step)), (name, step.get('name'))
    for scope in (workflow, *workflow['jobs'].values()):
        assert not re.search(r'\bdist\b', json.dumps(scope.get('env') or {})), name


def option(run, flag):
    return [value.replace('${', '$').replace('}', '')
            for value in re.findall(re.escape(flag) + r'\s+"?([^"\s\\]+)', run)]


# Provenance names the workflow that produced the artifact; each verification
# expects a producer's own recorded source, and a macOS producer also checks its
# current toolchain against the recorded one.
producers = {}
for name in workflows:
    for _, step in all_steps[name]:
        for source in option(runs(step), '--workflow-source'):
            assert source == f'.github/workflows/{name}', (name, source)
            producers[source] = name
assert set(producers.values()) == {'build2-macos.yml', 'module-build-matrix.yml'}, producers
for name in workflows:
    for _, step in all_steps[name]:
        if 'Tools/verify_build_provenance.py' not in runs(step):
            continue
        assert [producers.get(source) for source in option(runs(step), '--expected-workflow-source')] == [
            name if name in producers.values() else 'build2-macos.yml'], (name, step.get('name'))
        is_macos = (name, job_of(name, step)) in macos_jobs
        assert ('--match-current-macos-toolchain' in runs(step)) == is_macos, (name, step.get('name'))

# Release coordination stays on Linux and publishes only after the retained
# artifact's provenance verifies and the monotonic tag is re-derived, at the
# exact source SHA.
assert release_job['runs-on'] == 'ubuntu-latest'
release_runs = [runs(step) for step in release_steps]
verified = next(index for index, run in enumerate(release_runs) if 'Tools/verify_build_provenance.py' in run)
retagged = next((index for index, run in enumerate(release_runs)
                 if 'Tools/release_tag.py' in run and 'steps.version.outputs.tag' in run), None)
published = next((index for index, run in enumerate(release_runs) if 'gh release create' in run), None)
assert None not in (retagged, published), 'release must re-derive its tag and publish through gh'
assert verified < retagged < published, (verified, retagged, published)
# Tools/release_tag.py reads local tags: the re-derivation after the
# convergence wait must refresh them first, or it re-checks the checkout's tags.
retag_lines = release_runs[retagged].splitlines()
derive = next(index for index, line in enumerate(retag_lines) if 'Tools/release_tag.py' in line)
assert any('git fetch' in line and '--tags' in line for line in retag_lines[:derive]), release_runs[retagged]
assert re.search(r'^\s*test "\$tag" = "\$\{\{ steps\.version\.outputs\.tag \}\}"\s*$',
                 release_runs[retagged], re.M), release_runs[retagged]
# The published checksum sidecar is itself verified against the artifact.
assert re.search(r'\b(sha256sum|shasum -a 256) -c\b', release_runs[verified]), release_runs[verified]
assert option(release_runs[published], '--target') == ['$GITHUB_SHA'], release_runs[published]

# Coverage evidence from every macOS check run is retained, even after a failed
# lane, and never gates it.
coverage_paths = set()
for _, step in all_steps['build2-macos.yml']:
    if 'Tools/run_macos_checks.sh' in runs(step):
        environment = step.get('env') or {}
        assert environment.get('MGT_FIXTURE_TIMINGS'), step.get('name')
        coverage_paths.add(environment.get('MGT_MACOS_COVERAGE_OUTPUT'))
assert len(coverage_paths) == 1 and None not in coverage_paths, coverage_paths
retained = [step for _, step in all_steps['build2-macos.yml']
            if str(step.get('uses', '')).startswith('actions/upload-artifact@')
            and (step.get('with') or {}).get('path') in coverage_paths]
assert len(retained) == 1, retained
assert 'always()' in conjuncts(retained[0].get('if')), retained[0].get('if')
assert retained[0]['with']['if-no-files-found'] == 'warn', retained[0]['with']


# The release identity step runs as the runner's default `bash -e` shell, with
# a stand-in for macOS-only PlistBuddy, in a throwaway checkout.
def run_step(name, step_name, checkout, plist):
    (step,) = [step for _, step in all_steps[name] if step.get('name') == step_name]
    bindir = checkout.parent / 'bin'
    bindir.mkdir(exist_ok=True)
    buddy = bindir / 'PlistBuddy'
    buddy.write_text(f'#!{sys.executable}\n' + (
        'import plistlib, sys\n'
        'command, path = sys.argv[2], sys.argv[3]\n'
        "print(plistlib.load(open(path, 'rb'))[command.split(':', 1)[1]])\n"))
    buddy.chmod(0o755)
    (checkout / 'Info.plist').write_bytes(plistlib.dumps(plist))
    output = checkout.parent / 'github-output'
    output.write_text('')
    # The hand-rolled parser drops comment lines and indentation, so only a
    # script without heredocs or expressions survives it verbatim.
    assert '<<' not in runs(step) and '${{' not in runs(step), runs(step)
    script = runs(step).replace('/usr/libexec/PlistBuddy', shlex.quote(str(buddy)))
    environment = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    result = subprocess.run(['bash', '-e', '-c', script], cwd=checkout, capture_output=True, text=True,
                            env={**environment, 'GITHUB_OUTPUT': str(output)})
    return result, dict(line.split('=', 1) for line in output.read_text().splitlines())


def git(checkout, *arguments):
    environment = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    return subprocess.run(['git', '-c', 'user.name=Contract', '-c', 'user.email=contract@example.invalid',
                           '-c', 'commit.gpgsign=false', *arguments], cwd=checkout, check=True,
                          capture_output=True, text=True, env=environment).stdout.strip()


# Both release identities come from Info.plist with distinct meanings (SemVer
# product version, positive integer bundle build); the build-source identity is
# the actual checkout, not an event label.
with tempfile.TemporaryDirectory(prefix='mgt-workflow-step-') as temporary:
    checkout = Path(temporary) / 'checkout'
    checkout.mkdir()
    git(checkout, 'init', '-q')
    identity = {'CFBundleShortVersionString': '1.2.3', 'CFBundleVersion': '7'}
    (checkout / 'Info.plist').write_bytes(plistlib.dumps(identity))
    git(checkout, 'add', 'Info.plist')
    git(checkout, 'commit', '-qm', 'identity')
    head = git(checkout, 'rev-parse', 'HEAD')
    result, outputs = run_step('build2-macos.yml', 'Read release identity', checkout, identity)
    assert result.returncode == 0, result.stderr
    assert outputs == {'version': '1.2.3', 'build': '7', 'source_sha': head,
                       'source_tree': git(checkout, 'rev-parse', 'HEAD^{tree}'), 'sha_short': head[:8]}, outputs
    for version, build in (('1.2.3', '0'), ('1.2.3', '7a'), ('1.2', '7')):
        result, outputs = run_step('build2-macos.yml', 'Read release identity', checkout,
                                   {'CFBundleShortVersionString': version, 'CFBundleVersion': build})
        assert result.returncode != 0 and not outputs, (version, build, outputs)

print('ci_workflow_contract_ok')
