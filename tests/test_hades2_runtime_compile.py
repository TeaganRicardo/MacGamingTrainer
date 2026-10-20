"""Compile the shipped Hades II resident and measure Lua 5.2 local headroom.

The unchanged production source must compile. A main-chunk probe prefixes
synthetic locals to measure reserve at the most constrained point in the
initializer. Additional probes inject synthetic locals into each named private
factory so each factory's independent Lua 5.2 local budget remains governed.
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
FACTORY_ANCHORS = {
    "cast": "  M.castControl = (function()\n",
    "catalog_projection": "  M.catalogProjection = (function()\n",
}
RECOMMENDED_MAIN_CHUNK_RESERVE = 24
MINIMUM_FACTORY_RESERVE = 16
for scope_name, anchor in FACTORY_ANCHORS.items():
    if source.count(anchor) != 1:
        raise SystemExit(
            f"resident source must contain exactly one {scope_name} function factory "
            "so its independent local budget can be measured"
        )

with tempfile.TemporaryDirectory(prefix="mgt-lua52-local-reserve-") as temporary_directory:
    probe_path = Path(temporary_directory) / "hades.lua"

    def compiles_with(probe_source: str) -> bool:
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

    def measure_reserve(source_for_probe, scope_name: str) -> int:
        def with_extra_locals(extra_locals: int) -> bool:
            names = ", ".join(
                f"__mgt_{scope_name}_reserve_{index}"
                for index in range(1, extra_locals + 1)
            )
            declarations = f"local {names}\n" if extra_locals else ""
            return compiles_with(source_for_probe(declarations))

        available = 0
        candidate = 1
        while with_extra_locals(candidate):
            available = candidate
            candidate *= 2
            if candidate > 256:
                raise SystemExit(
                    f"Lua 5.2 {scope_name} reserve probe did not reach the local limit"
                )

        lower, upper = available, candidate
        while lower + 1 < upper:
            middle = (lower + upper) // 2
            if with_extra_locals(middle):
                lower = middle
            else:
                upper = middle
        return lower

    main_available = measure_reserve(lambda declarations: declarations + source, "main")

    factory_available = {}
    for scope_name, anchor in FACTORY_ANCHORS.items():
        def inject_factory_locals(declarations: str, factory_anchor=anchor) -> str:
            offset = source.index(factory_anchor) + len(factory_anchor)
            return source[:offset] + declarations + source[offset:]

        factory_available[scope_name] = measure_reserve(
            inject_factory_locals, f"{scope_name}_factory"
        )

if main_available < MINIMUM_LOCAL_RESERVE:
    raise SystemExit(
        f"hades2_runtime_local_headroom_failed available={main_available} "
        f"required={MINIMUM_LOCAL_RESERVE}"
    )
for scope_name, available in factory_available.items():
    if available < MINIMUM_FACTORY_RESERVE:
        raise SystemExit(
            f"hades2_runtime_factory_local_headroom_failed scope={scope_name} "
            f"available={available} required={MINIMUM_FACTORY_RESERVE}"
        )
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
