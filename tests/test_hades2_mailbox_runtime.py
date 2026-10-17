"""Production mailbox consumer, with real Lua 5.2 and temporary process leases."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from lua_runtime_support import require_lua52


ROOT = Path(__file__).resolve().parents[1]
lua = Path(require_lua52("Hades command mailbox consumer")).resolve()
compiler = shutil.which("cc")
assert compiler, "A C compiler is required for the native mailbox fixture"
if (lua.parent / "lua.h").is_file() and (lua.parent / "liblua.a").is_file():
    lua_flags = ["-I", str(lua.parent), str(lua.parent / "liblua.a")]
elif Path("/usr/include/lua5.2/lua.h").is_file():
    lua_flags = ["-I", "/usr/include/lua5.2", "-llua5.2"]
else:
    include, library = lua.parent.parent / "include/lua.h", lua.parent.parent / "lib/liblua.a"
    assert include.is_file() and library.is_file(), "Lua 5.2 development headers/library are required"
    lua_flags = ["-I", str(include.parent), str(library)]

with tempfile.TemporaryDirectory(prefix="mgt-mailbox-runtime-") as temporary:
    executable = Path(temporary) / "mailbox_runtime"
    subprocess.run([
        compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-I", str(ROOT / "Backend/games/hades2/native"),
        str(ROOT / "tests/fixtures/hades2/mailbox_runtime.c"), *lua_flags,
        "-lm", *(["-ldl"] if sys.platform.startswith("linux") else []),
        "-o", str(executable),
    ], check=True)
    subprocess.run([str(executable)], check=True, timeout=20)
