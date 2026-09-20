from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
macos_runner = ROOT / 'Tools/run_macos_checks.sh'
linux_runner = ROOT / 'Tools/run_linux_checks.sh'
workflow = (ROOT / '.github/workflows/build2-macos.yml').read_text()

assert macos_runner.is_file(), 'macOS exhaustive contract runner is missing'
assert linux_runner.is_file(), 'Linux contract runner is missing'

macos_text = macos_runner.read_text()
assert 'tests/test_*.py' in macos_text
assert 'python3 -m compileall -q Backend' in macos_text
assert 'python3 Tools/validate_game_module.py hades2' in macos_text
assert 'python3 "$test_file"' in macos_text
assert 'bash Tools/run_macos_checks.sh' in workflow
assert 'python3 tests/test_host_connection_policy_dev8.py' not in workflow
assert 'python3 tests/test_hades2_run_log_watcher.py' not in workflow
assert 'chmod +x build.sh Tools/*.py' not in workflow

# Linux uses exhaustive discovery too. Platform-only tests are an explicit denylist,
# so every new test_*.py is included by default instead of silently missing the
# fastest CI lane until somebody edits a curated list.
linux_text = linux_runner.read_text()
assert 'tests/test_*.py' in linux_text
assert 'python3 "$test_file"' in linux_text
assert 'tests=(' not in linux_text, 'Linux runner must not maintain a curated positive test list'
for platform_only in (
    'test_core_save_batch_delete_round20.py',
    'test_core_save_rename_completion_round24.py',
    'test_hades2_run_log_watcher.py',
    'test_trainer_log_sink_shared_append.py',
):
    assert platform_only in linux_text, platform_only

print('test_suite_discovery_ok')
