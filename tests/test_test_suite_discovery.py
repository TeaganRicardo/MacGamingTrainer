from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
macos_runner = ROOT / 'Tools/run_macos_checks.sh'
linux_runner = ROOT / 'Tools/run_linux_checks.sh'
macos_workflow = (ROOT / '.github/workflows/build2-macos.yml').read_text()
linux_workflow = (ROOT / '.github/workflows/linux-contracts.yml').read_text()

assert macos_runner.is_file(), 'macOS exhaustive contract runner is missing'
assert linux_runner.is_file(), 'Linux contract runner is missing'

macos_text = macos_runner.read_text()
assert 'tests/test_*.py' in macos_text
assert 'python3 -m compileall -q Backend' in macos_text
assert 'python3 Tools/validate_game_module.py hades2' in macos_text
assert 'python3 "$test_file"' in macos_text
assert 'bash Tools/run_macos_checks.sh' in macos_workflow
assert 'python3 tests/test_host_connection_policy_dev8.py' not in macos_workflow
assert 'python3 tests/test_hades2_run_log_watcher.py' not in macos_workflow
assert 'chmod +x build.sh Tools/*.py' not in macos_workflow

# Linux must also discover tests by filename. New portable regressions should enter
# the permanent gate automatically instead of relying on a hand-maintained list.
linux_text = linux_runner.read_text()
assert 'tests/test_*.py' in linux_text
assert 'python3 "$test_file"' in linux_text
assert re.search(r'(?m)^tests=\(', linux_text) is None, 'Linux runner still uses a curated positive list'
for platform_only in (
    'test_core_save_batch_delete_round20.py',
    'test_core_save_rename_completion_round24.py',
    'test_hades2_run_log_watcher.py',
    'test_trainer_log_sink_shared_append.py',
):
    assert platform_only in linux_text, platform_only
    assert (ROOT / 'tests' / platform_only).is_file(), platform_only
assert 'bash Tools/run_linux_checks.sh' in linux_workflow

print('test_suite_discovery_ok')
