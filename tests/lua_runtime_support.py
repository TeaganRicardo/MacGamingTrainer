"""Resolve the Lua interpreter required by Hades II resident tests.

Resident behavior fixtures execute the shipped Lua source under the game's ABI,
so they need a real Lua 5.2. The compile gate parses that same source to catch
Lua 5.2's per-function local-variable limit. A single resolution path keeps a
locally green run and CI in agreement instead of letting the gate silently
depend on a machine-specific PATH.
"""

import os
import shutil
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]

# Shared guard that routes every harness dispatch through the production JSON
# boundary (see the file header for the defect it closes).
RESIDENT_DISPATCH_CONTRACT = (
    ROOT / "tests/fixtures/hades2/resident_dispatch_contract.lua"
)

_BARE_NAMES = ("lua5.2",)

_CONVENTIONAL_PATHS = (
    Path("/opt/homebrew/opt/lua@5.2/bin/lua5.2"),
    Path("/usr/local/opt/lua@5.2/bin/lua5.2"),
    Path("/usr/local/bin/lua5.2"),
    Path("/usr/bin/lua5.2"),
)


def _executable(candidate: Path) -> Optional[str]:
    if candidate.is_file() and os.access(str(candidate), os.X_OK):
        return str(candidate)
    return None


def lua52() -> Optional[str]:
    """Return the Lua 5.2 interpreter path, or None when none is available."""
    override = os.environ.get("MGT_LUA52")
    if override:
        resolved = _executable(Path(override).expanduser())
        if resolved is None:
            raise SystemExit(f"MGT_LUA52 is not an executable file: {override}")
        return resolved

    for name in _BARE_NAMES:
        found = shutil.which(name)
        if found:
            return found

    for candidate in _CONVENTIONAL_PATHS:
        resolved = _executable(candidate)
        if resolved:
            return resolved

    return None


def require_lua52(subject: str) -> str:
    """Return the Lua 5.2 interpreter, or fail with an actionable message."""
    resolved = lua52()
    if resolved is None:
        raise SystemExit(
            f"lua5.2 is required for {subject}; install Lua 5.2, put it on PATH, "
            "or set MGT_LUA52 to the interpreter path"
        )
    return resolved
