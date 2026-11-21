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
    invalid_platform = subprocess.run(
        [sys.executable, str(ROOT / 'Tools/test_inventory.py'), '--root', str(fixture_root)],
        capture_output=True, text=True,
    )
    assert invalid_platform.returncode != 0 and 'test_excluded_fixture.py' in invalid_platform.stderr

# Generic prerequisite discovery from portable tests and module manifests.
with tempfile.TemporaryDirectory() as prereq_root_dir:
    prereq_root = Path(prereq_root_dir)
    (prereq_root / 'Tools/ci_prerequisites').mkdir(parents=True)
    (prereq_root / 'Tools/ci_prerequisites/sample_pkg.sh').write_text('#!/usr/bin/env bash\n')
    (prereq_root / 'Tools/ci_prerequisites/manifest_pkg.sh').write_text('#!/usr/bin/env bash\n')
    (prereq_root / 'Backend/games/alpha').mkdir(parents=True)
    (prereq_root / 'Backend/games/alpha/module.json').write_text(
        '{"buildRequirements": {"testPrerequisites": ["manifest_pkg"]}}\n'
    )
    (prereq_root / 'tests').mkdir()
    (prereq_root / 'tests/helper.py').write_text('MGT_PREREQUISITES = ("sample_pkg",)\n')
    (prereq_root / 'tests/test_uses_helper.py').write_text('import helper\n')
    prereqs = subprocess.run(
        [sys.executable, str(ROOT / 'Tools/discover_linux_tests.py'), '--root', str(prereq_root), '--prerequisites'],
        check=True, capture_output=True, text=True,
    )
    assert prereqs.stdout.splitlines() == ['manifest_pkg', 'sample_pkg'], prereqs.stdout

    (prereq_root / 'tests/test_unknown.py').write_text('MGT_PREREQUISITES = ("no_such_prereq",)\n')
    unknown = subprocess.run(
        [sys.executable, str(ROOT / 'Tools/discover_linux_tests.py'), '--root', str(prereq_root), '--prerequisites'],
        capture_output=True, text=True,
    )
    assert unknown.returncode != 0 and 'no_such_prereq' in unknown.stderr

    (prereq_root / 'tests/test_unknown.py').unlink()
    for bad_manifest in (
        '{"buildRequirements": {"testPrerequisites": [{"bad": 1}]}}\n',
        '{"buildRequirements": {"testPrerequisites": ["manifest_pkg", "manifest_pkg"]}}\n',
    ):
        (prereq_root / 'Backend/games/alpha/module.json').write_text(bad_manifest)
        bad = subprocess.run(
            [sys.executable, str(ROOT / 'Tools/discover_linux_tests.py'), '--root', str(prereq_root), '--prerequisites'],
            capture_output=True, text=True,
        )
        assert bad.returncode == 2 and 'TypeError' not in bad.stderr, bad.stderr

sys.path.insert(0, str(ROOT / 'Tools'))
import module_support  # noqa: E402
for bad_prereqs in ([{"bad": 1}], ["lua52", "lua52"]):
    with tempfile.TemporaryDirectory() as fake_root_dir:
        fake_root = Path(fake_root_dir)
        (fake_root / 'Tools/ci_prerequisites').mkdir(parents=True)
        (fake_root / 'Tools/ci_prerequisites/lua52.sh').write_text('#!/usr/bin/env bash\n')
        (fake_root / 'Backend/games/alpha').mkdir(parents=True)
        (fake_root / 'Backend/games/alpha/adapter.py').write_text('class A: pass\n')
        (fake_root / 'Backend/games/alpha/module.json').write_text(
            '{"schemaVersion": 1, "id": "alpha", "displayName": "Alpha", "protocolVersion": 21, '
            '"backend": {"adapter": "games.alpha.adapter:A"}, '
            '"frontend": {"sourceDirectory": "Sources/Alpha", "moduleType": "AlphaModule", '
            '"architectures": ["arm64"], "minimumMacOS": "14.0"}, '
            '"targetApplication": {"processName": "Alpha", "bundleIdentifier": "com.example.alpha"}, '
            '"buildRequirements": {"testPrerequisites": '
            + repr(bad_prereqs).replace("'", '"') + '}}\n'
        )
        (fake_root / 'Sources/Alpha').mkdir(parents=True)
        (fake_root / 'Info.plist').write_bytes(b'<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd"><plist version="1.0"><dict><key>CFBundleExecutable</key><string>App</string></dict></plist>')
        original_root = module_support.ROOT
        try:
            module_support.ROOT = fake_root
            try:
                module_support.load_manifest('alpha')
            except module_support.ManifestError:
                pass
            else:
                raise AssertionError(f"expected ManifestError for testPrerequisites={bad_prereqs!r}")
        finally:
            module_support.ROOT = original_root

repo_linux_prereqs = subprocess.run(
    [sys.executable, str(ROOT / 'Tools/discover_linux_tests.py'), '--root', str(ROOT), '--prerequisites'],
    check=True, capture_output=True, text=True,
)
assert repo_linux_prereqs.stdout.splitlines() == ['lua52'], repo_linux_prereqs.stdout

repo_macos_prereqs = subprocess.run(
    [sys.executable, str(ROOT / 'Tools/select_macos_pr_tests.py'), '--all-prerequisites'],
    check=True, capture_output=True, text=True,
)
assert repo_macos_prereqs.stdout.splitlines() == ['lua52'], repo_macos_prereqs.stdout

assert not fixture_root.exists(), 'temporary discovery fixture was not cleaned up'

print('test_suite_discovery_ok')
