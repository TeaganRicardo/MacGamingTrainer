from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
runner = ROOT / 'Tools/run_macos_checks.sh'
workflow = (ROOT / '.github/workflows/build2-macos.yml').read_text()

assert runner.is_file(), 'macOS exhaustive contract runner is missing'
text = runner.read_text()
assert 'tests/test_*.py' in text
assert 'python3 -m compileall -q Backend' in text
assert 'python3 Tools/validate_game_module.py hades2' in text
assert 'python3 "$test_file"' in text
assert 'bash Tools/run_macos_checks.sh' in workflow
assert 'python3 tests/test_host_connection_policy_dev8.py' not in workflow
assert 'python3 tests/test_hades2_run_log_watcher.py' not in workflow
assert 'chmod +x build.sh Tools/*.py' not in workflow

print('test_suite_discovery_ok')
