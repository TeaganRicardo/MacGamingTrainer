from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / 'Tools/check_runtime_revision_bump.py'
assert GUARD.is_file(), 'runtime revision bump guard is missing'
GIT = shutil.which('git')
PYTHON = shutil.which('python3')
assert GIT and PYTHON, 'git/python3 required for runtime revision guard test'

RUNTIME = Path('Backend/games/hades2/runtime/hades.lua')


def write_runtime(repo, revision, body='return true', previous_revision=None):
    previous = revision if previous_revision is None else previous_revision
    path = repo / RUNTIME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        'local previousModule = __MacGamingTrainerV1\n'
        f'if previousModule and previousModule.revision ~= {previous} then\n'
        '  __MacGamingTrainerV1 = nil\n'
        'end\n'
        f'local M = {{ version = 1, revision = {revision} }}\n'
        f'{body}\n',
        encoding='utf-8',
    )


def git(repo, *args):
    return subprocess.run([GIT, *args], cwd=repo, check=True, text=True, capture_output=True).stdout.strip()


def commit(repo, message):
    git(repo, 'add', '.')
    git(repo, '-c', 'user.name=Audit Test', '-c', 'user.email=audit@example.invalid', 'commit', '-m', message)
    return git(repo, 'rev-parse', 'HEAD')


def run_guard(repo, base, head):
    return subprocess.run(
        [PYTHON, str(GUARD), base, head, '--repo', str(repo)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


with tempfile.TemporaryDirectory(prefix='mgt-runtime-revision-') as td:
    repo = Path(td)
    git(repo, 'init')
    write_runtime(repo, 42)
    base = commit(repo, 'base')

    # Non-runtime changes do not demand a revision bump.
    (repo / 'README.md').write_text('docs only\n', encoding='utf-8')
    docs_head = commit(repo, 'docs')
    result = run_guard(repo, base, docs_head)
    assert result.returncode == 0, result.stderr + result.stdout

    # Any runtime source change with the same resident revision is rejected.
    write_runtime(repo, 42, body='return false')
    stale_head = commit(repo, 'runtime without bump')
    result = run_guard(repo, docs_head, stale_head)
    assert result.returncode != 0
    assert 'must increase resident revision' in result.stderr

    # An actual revision increase makes the same runtime edit admissible.
    write_runtime(repo, 43, body='return false')
    bumped_head = commit(repo, 'bump revision')
    result = run_guard(repo, stale_head, bumped_head)
    assert result.returncode == 0, result.stderr + result.stdout

    # The two resident-revision declarations are one invariant, not independent
    # strings that may drift apart.
    write_runtime(repo, 44, body='return false', previous_revision=43)
    mismatch_head = commit(repo, 'mismatched declarations')
    result = run_guard(repo, bumped_head, mismatch_head)
    assert result.returncode != 0
    assert 'revision declarations disagree' in result.stderr

print('runtime_revision_guard_ok')
