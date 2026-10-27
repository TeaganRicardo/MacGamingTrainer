"""Portable synthetic proof that build.sh typecheck mode never packages or signs.

This does not claim macOS compilation: the real Swift compiler remains covered
by the macOS PR lane and the exact-SHA release convergence job.
"""
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def executable(path: Path, source: str) -> None:
    path.write_text("#!/bin/sh\n" + source, encoding="utf-8")
    path.chmod(0o755)


with tempfile.TemporaryDirectory(prefix="mgt-build-preflight-") as temporary:
    root = Path(temporary)
    fakebin = root / "bin"
    fakebin.mkdir()
    log = root / "swiftc-args.txt"
    executable(fakebin / "xcrun", """
if [ "$1" = "--sdk" ] && [ "$2" = "macosx" ] && [ "$3" = "--show-sdk-path" ]; then
    echo /synthetic/sdk
    exit 0
fi
if [ "$1" = "--find" ]; then
    case "$2" in
        swiftc|clang) echo "$MGT_FAKE_BIN/$2"; exit 0 ;;
    esac
fi
exit 92
""")
    executable(fakebin / "swiftc", """
printf '%s\n' "$@" > "$MGT_FAKE_SWIFTC_LOG"
case " $* " in
    *" -typecheck "*) exit 0 ;;
esac
echo "Unexpected non-typecheck compilation" >&2
exit 93
""")
    # None of these distribution-only commands may run in typecheck mode.
    for name in ("clang", "codesign", "curl", "plutil", "shasum", "xattr", "xcode-select"):
        executable(fakebin / name, 'echo "Distribution-only command unexpectedly ran" >&2\nexit 94\n')

    isolated_tmp = root / "tmp"
    isolated_tmp.mkdir()
    output = root / "unpublished"
    env = {
        **os.environ,
        "PATH": str(fakebin) + os.pathsep + os.environ["PATH"],
        "TMPDIR": str(isolated_tmp),
        "MGT_BUILD_OUTPUT_DIR": str(output),
        "MGT_FAKE_BIN": str(fakebin),
        "MGT_FAKE_SWIFTC_LOG": str(log),
    }
    invocation = subprocess.run(
        ["bash", str(ROOT / "build.sh"), "--typecheck", "--all"],
        cwd=ROOT, env=env, text=True, capture_output=True, check=False,
    )
    assert invocation.returncode == 0, invocation.stdout + "\n" + invocation.stderr
    assert "MGT_BUILD_TIMING mode=typecheck selection=all phase=swift-typecheck" in invocation.stdout
    assert "Validated Swift product catalog" in invocation.stdout
    arguments = log.read_text(encoding="utf-8").splitlines()
    assert "-typecheck" in arguments, arguments
    assert "-parse-as-library" in arguments, arguments
    assert "-O" not in arguments, arguments
    assert any(name.endswith("/Sources/App.swift") for name in arguments)
    assert any(name.endswith("/Sources/Hades/HadesModule.swift") for name in arguments)
    assert any(name.endswith("/Sources/Hades2/Hades2Module.swift") for name in arguments)
    assert any(name.endswith("/ActiveGame.generated.swift") for name in arguments)
    assert "-target" in arguments and "arm64-apple-macosx14.0" in arguments
    assert not output.exists(), "typecheck mode published an artifact"
    assert not list(isolated_tmp.iterdir()), "typecheck mode left temporary build state"

    invalid = subprocess.run(
        ["bash", str(ROOT / "build.sh"), "--typecheck", "--all", "extra"],
        cwd=ROOT, env=env, text=True, capture_output=True, check=False,
    )
    assert invalid.returncode == 2, invalid.stdout + "\n" + invalid.stderr

print("build_preflight_ok")
