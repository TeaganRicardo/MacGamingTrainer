import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Tools"))

import macos_toolchain_identity as identity

DEVELOPER_DIR = "/Applications/Xcode_26.6.app/Contents/Developer"


def fake_command_text(command, env=None):
    command = tuple(command)
    if command == ("xcodebuild", "-version"):
        return "Xcode 26.6\nBuild version 17F113"
    values = {
        ("xcode-select", "-p"): DEVELOPER_DIR,
        ("sw_vers", "-productVersion"): "26.6.2",
        ("sw_vers", "-buildVersion"): "25G83",
        ("xcrun", "--sdk", "macosx", "--show-sdk-path"): "/SDKs/MacOSX26.5.sdk",
        ("xcrun", "--sdk", "macosx", "--show-sdk-version"): "26.5",
        ("xcrun", "--sdk", "macosx", "--show-sdk-build-version"): "25F90",
        ("xcrun", "--find", "swiftc"): "/toolchain/swiftc",
        ("xcrun", "swiftc", "--version"): "Apple Swift version 6.3",
        ("xcrun", "--find", "clang"): "/toolchain/clang",
        ("xcrun", "clang", "--version"): "Apple clang version 17.0.0",
        ("xcrun", "--find", "lldb"): "/toolchain/lldb",
        ("xcrun", "lldb", "--version"): "lldb-2600.0.31.7",
        ("xcrun", "lldb", "-P"): "/LLDB/Python",
        ("xcrun", "--find", "python3"): "/toolchain/python3",
        ("xcrun", "python3", "--version"): "Python 3.9.6",
    }
    return values[command]


def collect(label, arch):
    env = {
        "MGT_MACOS_RUNNER_LABEL": label,
        "RUNNER_OS": "macOS",
        "RUNNER_ARCH": arch,
        "ImageOS": "macos26",
        "ImageVersion": "fixture",
        "DEVELOPER_DIR": DEVELOPER_DIR,
    }
    with patch.object(identity, "command_text", side_effect=fake_command_text):
        return identity.collect_macos_toolchain(env)


arm = collect("macos-26", "ARM64")
identity.verify_recorded_macos_toolchain(arm)
assert arm["host"]["runnerArch"] == "ARM64"

# The retired Intel pool (#671) is no longer a verified release profile: an
# x86_64-built artifact cannot satisfy the arm64-only product.
try:
    collect("macos-26-intel", "X64")
except RuntimeError:
    pass
else:
    raise AssertionError("the retired Intel runner profile was accepted")

mismatched = dict(arm)
mismatched["host"] = dict(arm["host"])
mismatched["host"]["runnerArch"] = "X64"
try:
    identity.verify_recorded_macos_toolchain(mismatched)
except RuntimeError:
    pass
else:
    raise AssertionError("runner label/architecture mismatch must be rejected")

try:
    collect("macos-26", "X64")
except RuntimeError:
    pass
else:
    raise AssertionError("runtime runner label/architecture mismatch must be rejected")

# One verified hosted profile: the release verifier and the native fixture
# watchdog policy must agree on it.
sys.path.insert(0, str(ROOT / "tests"))
import macos_fixture_policy

assert identity.SUPPORTED_RUNNER_PROFILES == {macos_fixture_policy.HOSTED_PROFILE: "ARM64"}

print("macos_toolchain_runner_profiles_ok")
