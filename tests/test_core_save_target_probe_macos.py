"""The Core Save running-target probe sees a long-path game from a terminal-less worker.

The backend worker runs with piped stdin/stdout and no terminal, which is when
ps(1) on macOS falls back to a fixed output width. A Steam install path is
longer than that width, so the probe must list executables at unlimited width.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if sys.platform != "darwin":
    raise SystemExit("macOS-only Core Save target probe test")
ROOT = Path(__file__).resolve().parents[1]
PROBE = (
    "import sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "from core.protocol import _target_process_running\n"
    "print(_target_process_running(sys.argv[2], sys.argv[3]))\n"
)


def probe(process_name, executable_path_suffix=""):
    """Run the probe the way the worker does: no terminal on any stdio, no COLUMNS."""
    environ = {key: value for key, value in os.environ.items() if key != "COLUMNS"}
    result = subprocess.run(
        [sys.executable, "-c", PROBE, str(ROOT / "Backend"), process_name, executable_path_suffix],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, env=environ, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


with tempfile.TemporaryDirectory(prefix="mgt-save-probe-") as temporary:
    name = "Mac Gaming Trainer Probe Target"
    suffix = f"{name}/{name}.app/Contents/MacOS/{name}"
    executable = Path(temporary, "Library/Application Support/Steam/steamapps/common", suffix)
    executable.parent.mkdir(parents=True)
    # Content and mode only: the system binary's protected file flags cannot
    # be applied to a copy (chflags is not permitted), and the probe needs none.
    shutil.copy("/bin/sleep", executable)
    assert len(str(executable)) > 120 and len(name.encode()) > 16
    target = subprocess.Popen([str(executable), "60"], stdin=subprocess.DEVNULL)
    try:
        assert probe(name) == "True", "a running long-path target was reported stopped (executable name)"
        assert probe(name, suffix) == "True", "a running long-path target was reported stopped (path suffix)"
    finally:
        target.kill()
        target.wait(timeout=10)
    assert probe(name) == "False", "a stopped target was reported running"
print("core_save_target_probe_macos_ok")
