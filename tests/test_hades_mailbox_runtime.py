"""Hades I mailbox consumer runtime test with real Lua 5.2 and temporary leases."""
from pathlib import Path
import subprocess
import sys
import tempfile

from lua_native_prerequisites import require_lua52_native


ROOT = Path(__file__).resolve().parents[1]
_, compiler, lua_flags = require_lua52_native("Hades command mailbox consumer", language="c")
with tempfile.TemporaryDirectory(prefix="mgt-hades-mailbox-runtime-") as temporary:
    executable = Path(temporary) / "mailbox_runtime"
    subprocess.run([
        compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-I", str(ROOT / "Backend/games/hades/native"),
        str(ROOT / "tests/fixtures/hades/mailbox_runtime.c"), *lua_flags,
        "-lm", *(["-ldl"] if sys.platform.startswith("linux") else []),
        "-o", str(executable),
    ], check=True)
    subprocess.run([str(executable)], check=True, timeout=20)
print("test_hades_mailbox_runtime_ok")
