"""The Darwin kernel path probe resolves the running native process."""

MGT_PLATFORM = "macos"
MGT_INPUTS = ("Backend/games/hades/adapter.py",)

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

if sys.platform != "darwin":
    raise SystemExit("macOS-only process identity test")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
from core.target_probe import LocatedTarget, locate_target
from games.hades.adapter import process_executable_path

actual = process_executable_path(os.getpid())
assert actual and Path(actual).is_absolute(), "proc_pidpath did not resolve this process"
assert Path(actual).is_file(), "kernel executable path does not name a file"

# Exercise real Darwin ps + proc_pidpath + Info.plist bundle verification against
# an unbundled decoy sharing the same executable name.
with tempfile.TemporaryDirectory(prefix="mgt-darwin-locate-") as directory:
    temp = Path(directory)
    target_src = temp / "target.c"
    target_src.write_text("#include <unistd.h>\nint main(void) { sleep(30); return 0; }\n", encoding="utf-8")

    decoy_exe = temp / "Decoy/MgtTargetLocator"
    decoy_exe.parent.mkdir(parents=True)
    subprocess.run(["/usr/bin/clang", str(target_src), "-o", str(decoy_exe)], check=True)

    bundle = temp / "Real/Mgt Target.app"
    bundle_exe = bundle / "Contents/MacOS/MgtTargetLocator"
    bundle_exe.parent.mkdir(parents=True)
    subprocess.run(["/usr/bin/clang", str(target_src), "-o", str(bundle_exe)], check=True)
    bundle_id = f"com.example.mgt.locator.{os.getpid()}"
    (bundle / "Contents/Info.plist").write_text(
        "<plist version='1.0'><dict>"
        f"<key>CFBundleIdentifier</key><string>{bundle_id}</string>"
        "<key>CFBundleExecutable</key><string>MgtTargetLocator</string>"
        "</dict></plist>",
        encoding="utf-8",
    )

    manifest = SimpleNamespace(
        process_name="MgtTargetLocator",
        bundle_identifier=bundle_id,
        executable_path_suffix="",
    )
    decoy = subprocess.Popen([str(decoy_exe)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    real = subprocess.Popen([str(bundle_exe)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        located = locate_target(manifest)
        assert located == LocatedTarget(real.pid, bundle_exe.resolve(), bundle.resolve()), located
    finally:
        for proc in (decoy, real):
            proc.terminate()
            proc.wait(timeout=10)

print("hades_process_identity_macos_ok")
