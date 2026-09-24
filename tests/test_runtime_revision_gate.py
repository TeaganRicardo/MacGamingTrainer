import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'Tools/check_runtime_revision.py'


def run(*args, cwd):
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True)


def commit(repo, message):
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    subprocess.run(['git', 'commit', '-m', message], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()


with tempfile.TemporaryDirectory(prefix='mgt-runtime-revision-') as td:
    repo = Path(td)
    subprocess.run(['git', 'init', '-b', 'main'], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(['git', 'config', 'user.email', 'test@example.invalid'], cwd=repo, check=True)
    subprocess.run(['git', 'config', 'user.name', 'MGT test'], cwd=repo, check=True)
    runtime = repo / 'Backend/games/hades2/runtime/hades.lua'
    runtime.parent.mkdir(parents=True)
    runtime.write_text(
        'local previousModule = __MacGamingTrainerV1\n'
        'if previousModule and previousModule.revision ~= 42 then previousModule = nil end\n'
        'local M = { version = 1, revision = 42 }\n',
        encoding='utf-8',
    )
    base = commit(repo, 'baseline')

    runtime.write_text(runtime.read_text() + '-- behavior change\n', encoding='utf-8')
    unchanged_revision = commit(repo, 'change runtime without bump')
    failed = run('python3', str(SCRIPT), base, unchanged_revision, cwd=repo)
    assert failed.returncode != 0, failed.stdout + failed.stderr
    assert 'resident revision' in failed.stderr.lower(), failed.stderr

    text = runtime.read_text().replace('revision ~= 42', 'revision ~= 43').replace('revision = 42', 'revision = 43')
    runtime.write_text(text, encoding='utf-8')
    bumped = commit(repo, 'bump runtime revision')
    passed = run('python3', str(SCRIPT), base, bumped, cwd=repo)
    assert passed.returncode == 0, passed.stdout + passed.stderr

    (repo / 'README.md').write_text('unrelated\n', encoding='utf-8')
    unrelated = commit(repo, 'unrelated change')
    passed = run('python3', str(SCRIPT), bumped, unrelated, cwd=repo)
    assert passed.returncode == 0, passed.stdout + passed.stderr

    runtime.write_text(runtime.read_text().replace('revision ~= 43', 'revision ~= 44'), encoding='utf-8')
    inconsistent = commit(repo, 'break revision marker consistency')
    failed = run('python3', str(SCRIPT), unrelated, inconsistent, cwd=repo)
    assert failed.returncode != 0, failed.stdout + failed.stderr
    assert 'consistent' in failed.stderr.lower(), failed.stderr

print('runtime_revision_gate_ok')

workflow = (ROOT / '.github/workflows/linux-contracts.yml').read_text()
assert 'fetch-depth: 0' in workflow
assert 'Tools/check_runtime_revision.py' in workflow
assert 'github.event.pull_request.base.sha' in workflow
assert 'github.event.before' in workflow
