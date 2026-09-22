from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
macos_runner = ROOT / 'Tools/run_macos_checks.sh'
linux_runner = ROOT / 'Tools/run_linux_checks.sh'
macos_only_list = ROOT / 'Tools/macos_only_tests.txt'
workflow = (ROOT / '.github/workflows/build2-macos.yml').read_text()

assert macos_runner.is_file(), 'macOS platform contract runner is missing'
assert linux_runner.is_file(), 'Linux contract runner is missing'
assert macos_only_list.is_file(), 'shared macOS-only test list is missing'

macos_only = [
    name.strip()
    for name in macos_only_list.read_text().splitlines()
    if name.strip()
]
assert len(macos_only) == len(set(macos_only)), 'macOS-only test list contains duplicates'
assert set(macos_only) == {
    'test_core_save_batch_delete_round20.py',
    'test_core_save_rename_completion_round24.py',
    'test_hades2_run_log_watcher.py',
    'test_trainer_log_sink_shared_append.py',
}
for name in macos_only:
    assert (ROOT / 'tests' / name).is_file(), name

# Build 2 macOS owns platform-specific tests plus the real Hades build/package.
# Portable Python contracts are deliberately not re-run on macOS.
macos_text = macos_runner.read_text()
assert 'macos_only_tests.txt' in macos_text
assert 'tests/test_*.py' not in macos_text
assert 'python3 -m compileall -q Backend' not in macos_text
assert 'python3 Tools/validate_game_module.py hades2' not in macos_text
assert 'python3 "$test_file"' in macos_text
assert 'bash Tools/run_macos_checks.sh' in workflow
assert 'python3 tests/test_host_connection_policy_dev8.py' not in workflow
assert 'python3 tests/test_hades2_run_log_watcher.py' not in workflow
assert 'chmod +x build.sh Tools/*.py' not in workflow

# Linux remains exhaustive by default. The shared macOS-only list is the only
# exclusion source, so new portable test_*.py files cannot silently miss the
# fastest CI lane.
linux_text = linux_runner.read_text()
assert 'tests/test_*.py' in linux_text
assert 'macos_only_tests.txt' in linux_text
assert 'python3 "$test_file"' in linux_text
assert 'tests=(' not in linux_text, 'Linux runner must not maintain a curated positive test list'
for name in macos_only:
    assert name not in linux_text, name

print('test_suite_discovery_ok')
