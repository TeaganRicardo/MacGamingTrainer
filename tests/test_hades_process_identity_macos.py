"""The Darwin kernel path probe resolves the running native process."""
import os
import sys
from pathlib import Path

if sys.platform != "darwin":
    raise SystemExit("macOS-only process identity test")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
from games.hades.adapter import process_executable_path

actual = process_executable_path(os.getpid())
assert actual and Path(actual).is_absolute(), "proc_pidpath did not resolve this process"
assert Path(actual).is_file(), "kernel executable path does not name a file"
print("hades_process_identity_macos_ok")
