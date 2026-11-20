"""Test portable Linux test discovery behavior."""

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
macos_runner = ROOT / 'Tools/run_macos_checks.sh'
linux_runner = ROOT / 'Tools/run_linux_checks.sh'

assert macos_runner.is_file(), 'macOS platform contract runner is missing'
assert linux_runner.is_file(), 'Linux contract runner is missing'

# Build 2 macOS owns platform-specific tests plus the real Hades build/package.
# Portable Python contracts are deliberately not re-run on macOS.
macos_text = macos_runner.read_text()
assert 'tests/test_*.py' not in macos_text
assert 'python3 -m compileall -q Backend' not in macos_text
assert 'python3 Tools/validate_game_module.py hades2' not in macos_text
assert 'run_check "$name" python3 "$test_file"' in macos_text
assert 'if "$@"; then' in macos_text
assert 'record_failure "$label (exit $status)"' in macos_text
assert 'macOS contract suite failed in %d check(s)' in macos_text
assert 'set -euo pipefail' not in macos_text

# Portable discovery includes all unmarked test entrypoints recursively.
linux_text = linux_runner.read_text()
assert 'discover_linux_tests.py' in linux_text
assert 'if discovered_tests="$(python3 Tools/discover_linux_tests.py --root "$ROOT")"; then' in linux_text
assert 'run_check "$test_file" python3 "$test_file"' in linux_text
assert 'if "$@"; then' in linux_text
assert 'record_failure "$label (exit $status)"' in linux_text
assert 'Linux contract suite failed in %d check(s)' in linux_text
assert 'done < <(' not in linux_text, 'process substitution hides discovery failure'
assert 'set -euo pipefail' not in linux_text
assert 'python3 "$test_file"' in linux_text
assert 'tests/test_*.py' not in linux_text
assert 'tests=(' not in linux_text, 'Linux runner must not maintain a curated positive test list'
with tempfile.TemporaryDirectory() as temporary_root:
    fixture_root = Path(temporary_root)
    nested_tests = fixture_root / 'tests' / 'nested'
    nested_tests.mkdir(parents=True)
    (nested_tests / 'test_nested_fixture.py').write_text('pass\n')
    native = fixture_root / 'tests' / 'test_excluded_fixture.py'
    native.write_text('MGT_PLATFORM = "macos"\nraise AssertionError("discovery must not execute tests")\n')

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
    assert discovery.stdout.splitlines() == ['tests/nested/test_nested_fixture.py']

    (nested_tests / 'test_nested_fixture.py').write_text('MGT_PLATFORM = "macos"\n')
    native_discovery = subprocess.run(
        [sys.executable, str(ROOT / 'Tools/test_inventory.py'), '--root', str(fixture_root)],
        check=True, capture_output=True, text=True,
    )
    assert native_discovery.stdout.splitlines() == ['nested/test_nested_fixture.py', 'test_excluded_fixture.py']
    empty = subprocess.run(
        [sys.executable, str(ROOT / 'Tools/discover_linux_tests.py'), '--root', str(fixture_root)],
        capture_output=True,
        text=True,
    )
    assert empty.returncode != 0, 'zero portable tests must fail closed'

    native.write_text('MGT_PLATFORM = "macOS"\n')
    invalid = subprocess.run(
        [sys.executable, str(ROOT / 'Tools/test_inventory.py'), '--root', str(fixture_root)],
        capture_output=True, text=True,
    )
    assert invalid.returncode != 0 and 'test_excluded_fixture.py' in invalid.stderr

assert not fixture_root.exists(), 'temporary discovery fixture was not cleaned up'

print('test_suite_discovery_ok')
