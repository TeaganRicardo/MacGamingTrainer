import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SWIFT_TESTS = (
    "test_hades2_feature_identity.py",
    "test_shortcut_chord_semantics.py",
)

# Simulate a machine without Swift even when this contract itself runs on macOS.
with tempfile.TemporaryDirectory(prefix="mgt-no-swift-") as empty_path:
    env = {**os.environ, "PATH": empty_path}
    for name in SWIFT_TESTS:
        result = subprocess.run(
            [sys.executable, str(ROOT / "tests" / name)],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode != 0, (name, result.returncode, result.stderr)
        assert "swiftc required" in result.stderr, (name, result.stderr)

# Native warning policy: clang emits diagnostics for maintainers, while the
# unfiltered production-plus-vendor build stays nonfatal until baselined.
macos_runner = (ROOT / "Tools/run_macos_checks.sh").read_text()
assert "macos_only_tests.txt" in macos_runner
assert 'python3 "$test_file"' in macos_runner
assert "while IFS= read -r name" in macos_runner

linux_runner = (ROOT / "Tools/run_linux_checks.sh").read_text()
assert 'discovered_tests="$(python3 Tools/discover_linux_tests.py --root "$ROOT")"' in linux_runner
macos_list = (ROOT / "Tools/macos_only_tests.txt").read_text().splitlines()
for name in SWIFT_TESTS:
    assert name in macos_list, "compiled-only tests must run in the macOS lane"

print("swift_toolchain_ci_contract_ok")
