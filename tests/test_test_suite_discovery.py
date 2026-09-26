"""Test portable Linux test discovery behavior."""

import subprocess
import sys
import tempfile
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
assert macos_only, 'macOS-only test list must not be empty'
assert len(macos_only) == len(set(macos_only)), 'macOS-only test list contains duplicates'
assert 'test_host_localization_runtime.py' not in macos_only, (
    'source-only host localization contract must run on portable Linux'
)
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

# Linux uses recursive discovery. The shared macOS-only list is the only
# exclusion source, so new portable test_*.py files cannot miss the gate.
linux_text = linux_runner.read_text()
assert 'discover_linux_tests.py' in linux_text
assert 'discovered_tests="$(python3 Tools/discover_linux_tests.py --root "$ROOT")"' in linux_text, (
    'discovery failure must propagate through the set -e runner, not process substitution'
)
assert 'done < <(' not in linux_text, 'process substitution hides discovery failure'
assert 'macos_only_tests.txt' in linux_text
assert 'python3 "$test_file"' in linux_text
assert 'tests/test_*.py' not in linux_text
assert 'test_host_localization_runtime.py' not in linux_text
assert 'tests=(' not in linux_text, 'Linux runner must not maintain a curated positive test list'
for name in macos_only:
    assert name not in linux_text, name

with tempfile.TemporaryDirectory() as temporary_root:
    fixture_root = Path(temporary_root)
    nested_tests = fixture_root / 'tests' / 'nested'
    nested_tests.mkdir(parents=True)
    (nested_tests / 'test_nested_fixture.py').write_text('pass\n')
    (fixture_root / 'tests' / 'test_excluded_fixture.py').write_text('pass\n')
    (fixture_root / 'Tools').mkdir()
    (fixture_root / 'Tools' / 'macos_only_tests.txt').write_text(
        'test_excluded_fixture.py\n'
    )

    discovery = subprocess.run(
        [
            sys.executable,
            str(ROOT / 'Tools/discover_linux_tests.py'),
            '--root',
            str(fixture_root),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert 'tests/nested/test_nested_fixture.py' in discovery.stdout
    assert 'tests/test_excluded_fixture.py' not in discovery.stdout

    (fixture_root / 'Tools' / 'macos_only_tests.txt').write_text(
        'test_excluded_fixture.py\ntest_nested_fixture.py\n'
    )
    empty = subprocess.run(
        [sys.executable, str(ROOT / 'Tools/discover_linux_tests.py'), '--root', str(fixture_root)],
        capture_output=True,
        text=True,
    )
    assert empty.returncode != 0, 'zero portable tests must fail closed'

assert not fixture_root.exists(), 'temporary discovery fixture was not cleaned up'

print('test_suite_discovery_ok')
