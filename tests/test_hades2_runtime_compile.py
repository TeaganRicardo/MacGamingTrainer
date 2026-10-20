"""Compile the shipped Hades II resident and measure Lua 5.2 local headroom.

The unchanged production source must compile. A second compile probe prefixes
synthetic locals to the source so they remain active across the entire main
chunk, including nested scopes. This measures the minimum spare-local capacity
at the most constrained point in the main function.
"""

import subprocess
import tempfile
from pathlib import Path

from lua_runtime_support import require_lua52

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "Backend/games/hades2/runtime/hades.lua"
LUA = require_lua52("resident-runtime compile verification")
MINIMUM_LOCAL_RESERVE = 16

version_proc = subprocess.run(
    [LUA, "-e", "io.write(_VERSION)"],
    text=True,
    capture_output=True,
    timeout=30,
)
if version_proc.returncode != 0 or version_proc.stdout.strip() != "Lua 5.2":
    actual_version = (
        version_proc.stdout.strip()
        or version_proc.stderr.strip()
        or "no version output"
    )
    raise SystemExit(
        "resident-runtime compile verification requires Lua 5.2; "
        f"got {actual_version}"
    )


def compile_file(path: Path):
    command = f"local f,e=loadfile({str(path)!r}); if not f then error(e) end"
    return subprocess.run(
        [LUA, "-e", command],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )


proc = compile_file(RUNTIME)
if proc.returncode != 0:
    print(proc.stdout)
    print(proc.stderr)
    raise SystemExit(proc.returncode)
print("hades2_runtime_compile_ok")

source = RUNTIME.read_text(encoding="utf-8")

with tempfile.TemporaryDirectory(prefix="mgt-lua52-local-reserve-") as temporary_directory:
    probe_path = Path(temporary_directory) / "hades.lua"

    def compiles_with(extra_locals: int) -> bool:
        names = ", ".join(
            f"__mgt_local_reserve_{index}" for index in range(1, extra_locals + 1)
        )
        declarations = f"local {names}\n" if extra_locals else ""
        probe_source = declarations + source
        probe_path.write_text(probe_source, encoding="utf-8")
        result = compile_file(probe_path)
        if result.returncode == 0:
            return True
        if "too many local variables (limit is 200)" in result.stderr:
            return False
        raise SystemExit(
            "Lua 5.2 local-reserve probe failed for an unexpected reason:\n"
            + result.stderr
        )

    available = 0
    candidate = 1
    while compiles_with(candidate):
        available = candidate
        candidate *= 2
        if candidate > 256:
            raise SystemExit("Lua 5.2 local-reserve probe did not reach the local limit")

    lower, upper = available, candidate
    while lower + 1 < upper:
        middle = (lower + upper) // 2
        if compiles_with(middle):
            lower = middle
        else:
            upper = middle
    available = lower

if available < MINIMUM_LOCAL_RESERVE:
    raise SystemExit(
        f"hades2_runtime_local_headroom_failed available={available} "
        f"required={MINIMUM_LOCAL_RESERVE}"
    )
print(
    f"hades2_runtime_local_headroom_ok available={available} "
    f"required={MINIMUM_LOCAL_RESERVE}"
)
