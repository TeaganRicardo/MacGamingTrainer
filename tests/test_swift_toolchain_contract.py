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


# Standing workflow dependencies are supply-chain inputs. Keep the exact commit
# immutable; the trailing comment preserves the reviewed upstream major tag.
pins = {
    "actions/checkout": "11d5960a326750d5838078e36cf38b85af677262 # v4",
    "actions/setup-python": "a26af69be951a213d495a4c3e4e4022e16d87065 # v5",
    "actions/upload-artifact": "ea165f8d65b6e75b540449e92b4886f43607fa02 # v4",
}
workflow_root = ROOT / ".github" / "workflows"
for workflow in workflow_root.glob("*.yml"):
    source = workflow.read_text()
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- uses: actions/"):
            continue
        use = stripped.removeprefix("- uses: ")
        action = use.split("@", 1)[0]
        assert action in pins, (workflow.name, use)
        assert use == f"{action}@{pins[action]}", (workflow.name, use)

for name in ("build2-macos.yml", "module-build-matrix.yml"):
    source = (workflow_root / name).read_text()
    assert "'macos-26' || 'ubuntu-latest'" in source, name
    assert "MGT_MACOS_RUNNER_LABEL: macos-26" in source, name
    assert "DEVELOPER_DIR: /Applications/Xcode_26.6.app/Contents/Developer" in source, name
    assert "python3 Tools/macos_toolchain_identity.py" in source, name
    assert "macos-latest" not in source, name

release = (workflow_root / "direct-release.yml").read_text()
assert "runs-on: macos-26" in release
assert "macos-latest" not in release
assert 'manifest["toolchain"]' in release

print("swift_toolchain_ci_contract_ok")
