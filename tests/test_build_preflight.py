"""Portable synthetic proof that build.sh typecheck mode never packages or signs.

This does not claim macOS compilation: the real Swift compiler remains covered
by the macOS PR lane and the exact-SHA release convergence job.
"""
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
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

with tempfile.TemporaryDirectory(prefix="mgt-runtime-cache-") as temporary:
    root = Path(temporary)
    fakebin = root / "bin"
    fakebin.mkdir()
    payload = root / "runtime.tar.gz"
    runtime_python = b'#!/bin/sh\nprintf "3.13.0\\n"\n'
    with tarfile.open(payload, "w:gz") as archive:
        member = tarfile.TarInfo("python/bin/python3")
        member.mode = 0o755
        member.size = len(runtime_python)
        archive.addfile(member, io.BytesIO(runtime_python))
    digest = hashlib.sha256(payload.read_bytes()).hexdigest()
    manifest = root / "runtime.json"
    manifest.write_text(json.dumps({"version": "3.13.0", "release": "fixture", "distributions": {
        "arm64": {"url": "https://fixture.invalid/runtime", "sha256": digest}}}))
    plutil = fakebin / "plutil"
    plutil.write_text(f"#!{sys.executable}\n" + """
import json,sys
value=json.load(open(sys.argv[-1]))
for component in sys.argv[2].split('.'): value=value[component]
print(value)
""")
    plutil.chmod(0o755)
    curl = fakebin / "curl"
    curl.write_text(f"#!{sys.executable}\n" + """
import os,pathlib,shutil,sys,time
destination=pathlib.Path(sys.argv[sys.argv.index('-o')+1])
mode=os.environ['MGT_CACHE_MODE']
if mode=='fail':
    destination.write_bytes(b'partial download')
    sys.exit(22)
if mode=='bad-hash':
    destination.write_bytes(b'corrupt download')
    sys.exit(0)
barrier=pathlib.Path(os.environ['MGT_CACHE_BARRIER'])
(barrier/str(os.getpid())).write_text(str(destination))
deadline=time.monotonic()+10
while len(list(barrier.iterdir()))<2:
    if time.monotonic()>deadline: sys.exit(95)
    time.sleep(.01)
shutil.copyfile(os.environ['MGT_CACHE_PAYLOAD'],destination)
""")
    curl.chmod(0o755)
    # Exercise the production bootstrap without invoking the compiler/package path.
    build_source = (ROOT / "build.sh").read_text()
    functions = build_source.split("python_runtime_field()", 1)[1].split('\nHOST_ARCH=', 1)[0]
    harness = root / "bootstrap.sh"
    harness.write_text('set -euo pipefail\npython_runtime_field()' + functions + '\nprepare_python_runtime arm64\n')
    cache = root / "cache"
    barrier = root / "barrier"
    barrier.mkdir()
    env = {**os.environ, "PATH": str(fakebin) + os.pathsep + os.environ["PATH"],
           "PYTHON_RUNTIME_MANIFEST": str(manifest), "MGT_PYTHON_RUNTIME_CACHE_DIR": str(cache),
           "MGT_CACHE_PAYLOAD": str(payload), "MGT_CACHE_BARRIER": str(barrier), "MGT_CACHE_MODE": "concurrent"}
    processes = [subprocess.Popen(["bash", str(harness)], env={**env, "GENERATED_DIR": str(root / f"build-{index}")},
                                  text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for index in range(2)]
    for process in processes:
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == 0, stdout + '\n' + stderr
    downloads = [path.read_text() for path in barrier.iterdir()]
    assert len(downloads) == 2 and len(set(downloads)) == 2, downloads
    cached = cache / "cpython-3.13.0+fixture-arm64-apple-darwin-install_only.tar.gz"
    assert hashlib.sha256(cached.read_bytes()).hexdigest() == digest
    assert not list(cache.glob('*.tmp.*')), 'successful concurrent downloads left temporary state'
    for mode in ('fail', 'bad-hash'):
        cached.write_bytes(b'old invalid cache')
        result = subprocess.run(["bash", str(harness)], env={**env, "MGT_CACHE_MODE": mode,
                                "GENERATED_DIR": str(root / mode)}, text=True, capture_output=True, timeout=20)
        assert result.returncode != 0, result.stdout + '\n' + result.stderr
        assert cached.read_bytes() == b'old invalid cache', 'failed download replaced the prior archive'
        assert not list(cache.glob('*.tmp.*')), 'failed download left temporary state'

print("build_preflight_and_runtime_cache_ok")
