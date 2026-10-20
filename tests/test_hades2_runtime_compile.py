"""Compile the shipped Hades II resident and measure Lua 5.2 local headroom.

The unchanged production source must compile. A main-chunk probe prefixes
synthetic locals to measure reserve at the most constrained point in the
initializer. Additional probes inject synthetic locals into each named private
factory so each factory's independent Lua 5.2 local budget remains governed.
"""

import subprocess
import tempfile
from pathlib import Path

from lua_local_reserve import (
    discover_top_level_factories,
    inject_factory_locals,
    measure_local_reserve,
    require_minimum_reserve,
)
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
factories = discover_top_level_factories(source)
RECOMMENDED_MAIN_CHUNK_RESERVE = 24
MINIMUM_FACTORY_RESERVE = 16

with tempfile.TemporaryDirectory(prefix="mgt-lua52-local-reserve-") as temporary_directory:
    probe_path = Path(temporary_directory) / "hades.lua"

    def compiles(probe_source: str) -> bool:
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

    main_available = measure_local_reserve(
        lambda declarations: declarations + source,
        compiles,
        "main_chunk",
    )
    factory_available = {}
    for factory in factories:
        factory_available[factory.name] = measure_local_reserve(
            lambda declarations, scope=factory: inject_factory_locals(
                source, scope, declarations
            ),
            compiles,
            f"factory_{factory.name}",
        )

try:
    require_minimum_reserve("main chunk", main_available, MINIMUM_LOCAL_RESERVE)
    for scope_name, available in factory_available.items():
        require_minimum_reserve(scope_name, available, MINIMUM_FACTORY_RESERVE)
except ValueError as error:
    raise SystemExit(str(error))

if main_available < RECOMMENDED_MAIN_CHUNK_RESERVE:
    print(
        f"hades2_runtime_local_headroom_warning available={main_available} "
        f"recommended={RECOMMENDED_MAIN_CHUNK_RESERVE} minimum={MINIMUM_LOCAL_RESERVE}"
    )
else:
    print(
        f"hades2_runtime_local_headroom_ok available={main_available} "
        f"minimum={MINIMUM_LOCAL_RESERVE} recommended={RECOMMENDED_MAIN_CHUNK_RESERVE}"
    )
for scope_name, available in factory_available.items():
    print(
        f"hades2_runtime_factory_local_headroom_ok scope={scope_name} "
        f"available={available} required={MINIMUM_FACTORY_RESERVE}"
    )
