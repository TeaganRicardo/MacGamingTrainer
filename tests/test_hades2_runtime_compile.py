"""Compile the production Hades II resident with the target Lua ABI.

This guards the exact source shipped to the game. Behavior harnesses must not
rewrite top-level locals before compilation, because that can hide Lua 5.2's
per-function local-variable limit.
"""

import subprocess
from pathlib import Path

from lua_runtime_support import require_lua52

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "Backend/games/hades2/runtime/hades.lua"
LUA = require_lua52("resident-runtime compile verification")

proc = subprocess.run(
    [
        LUA,
        "-e",
        "local f,e=loadfile('Backend/games/hades2/runtime/hades.lua'); if not f then error(e) end",
    ],
    cwd=ROOT,
    text=True,
    capture_output=True,
    timeout=30,
)
if proc.returncode != 0:
    print(proc.stdout)
    print(proc.stderr)
    raise SystemExit(proc.returncode)

print("hades2_runtime_compile_ok")
