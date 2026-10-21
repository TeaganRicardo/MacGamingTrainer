"""Preflight the Lua 5.2 development toolchain used by native test fixtures.

An interpreter alone cannot build the mailbox and native-query fixtures. Use
one path for selecting Lua headers, a linkable library and the C/C++ compiler,
and prove the combination with an isolated compile/link/run before the fixture.
"""

import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from lua_runtime_support import require_lua52

_SETUP = (
    "Install Lua 5.2 development headers and a linkable library, plus a C/C++ "
    "compiler (Debian/Ubuntu: lua5.2 liblua5.2-dev build-essential; "
    "macOS: build Lua 5.2.4 with 'make -C src generic', then set "
    "MGT_LUA52 to the built src/lua)."
)
_HEADERS = ("lua.h", "lauxlib.h", "lualib.h")
_PROBE = r"""
#ifdef __cplusplus
extern "C" {
#endif
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
#ifdef __cplusplus
}
#endif
#if LUA_VERSION_NUM != 502
#error The native test fixtures require Lua 5.2 development headers
#endif
int main(void) {
    lua_State *state = luaL_newstate();
    if (!state) return 1;
    lua_close(state);
    return 0;
}
"""


def _complete_headers(directory: Path) -> bool:
    return all((directory / name).is_file() for name in _HEADERS)


def _link_candidates(lua: Path):
    """Offer explicit Lua source layouts, package metadata and system installs."""
    source_dir = lua.parent
    prefix = source_dir.parent
    for directory, archives in (
        (source_dir, (source_dir / "liblua.a",)),
        (prefix / "include", (prefix / "lib/liblua.a", prefix / "lib/liblua5.2.a")),
        (prefix / "include/lua5.2", (prefix / "lib/liblua.a", prefix / "lib/liblua5.2.a")),
    ):
        if _complete_headers(directory):
            for archive in archives:
                if archive.is_file():
                    yield str(archive), ["-I", str(directory), str(archive)]

    pkg_config = shutil.which("pkg-config")
    if pkg_config:
        for package in ("lua5.2", "lua-5.2"):
            proc = subprocess.run(
                [pkg_config, "--cflags", "--libs", package],
                capture_output=True, text=True, timeout=10,
            )
            if proc.returncode == 0:
                yield f"pkg-config {package}", shlex.split(proc.stdout)

    for directory in (
        Path("/usr/include/lua5.2"),
        Path("/usr/local/include/lua5.2"),
        Path("/opt/homebrew/include/lua5.2"),
        Path("/usr/local/opt/lua@5.2/include/lua5.2"),
        Path("/opt/homebrew/opt/lua@5.2/include/lua5.2"),
        prefix / "include/lua5.2",
        prefix / "include",
    ):
        if _complete_headers(directory):
            flags = ["-I", str(directory)]
            # Custom prefix installs are not normally on the linker's path.
            if directory in (prefix / "include/lua5.2", prefix / "include"):
                flags += ["-L", str(prefix / "lib")]
            yield str(directory), flags + ["-llua5.2"]


def require_lua52_native(subject: str, *, language: str):
    """Return (Lua executable, compiler, Lua link flags) or an actionable error.

    The language argument selects the actual fixture compiler: 'c' or 'c++'.
    All candidates are verified with a real 5.2-header compile, link and run.
    """
    if language not in ("c", "c++"):
        raise ValueError(f"unsupported native fixture language: {language}")
    lua = Path(require_lua52(subject)).resolve()
    compiler_name = "cc" if language == "c" else "c++"
    compiler = shutil.which(compiler_name)
    if compiler is None:
        raise SystemExit(
            f"{subject}: {compiler_name} compiler required for Lua 5.2 native tests. {_SETUP}"
        )

    try:
        version = subprocess.run(
            [str(lua), "-e", "io.write(_VERSION)"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SystemExit(f"{subject}: cannot execute Lua 5.2 interpreter {lua}: {error}") from error
    if version.returncode != 0 or version.stdout.strip() != "Lua 5.2":
        raise SystemExit(
            f"{subject}: interpreter {lua} must be Lua 5.2 "
            f"(got {version.stdout.strip() or version.stderr.strip() or 'no version'}). "
            "Set MGT_LUA52 to a Lua 5.2 interpreter."
        )

    errors = []
    candidates = list(_link_candidates(lua))
    if not candidates:
        raise SystemExit(
            f"{subject}: Lua 5.2 interpreter found at {lua}, but development "
            f"headers ({', '.join(_HEADERS)}) and a linkable library are missing. {_SETUP}"
        )

    suffix, standard = (".c", "-std=c11") if language == "c" else (".cpp", "-std=c++17")
    with tempfile.TemporaryDirectory(prefix="mgt-lua52-native-preflight-") as temp:
        source = Path(temp) / ("probe" + suffix)
        executable = Path(temp) / "probe"
        source.write_text(_PROBE, encoding="utf-8")
        for origin, flags in candidates:
            command = [compiler, standard, str(source), "-o", str(executable), *flags, "-lm"]
            if sys.platform.startswith("linux"):
                command.append("-ldl")
            try:
                compiled = subprocess.run(command, capture_output=True, text=True, timeout=20)
                if compiled.returncode == 0:
                    launched = subprocess.run(
                        [str(executable)], capture_output=True, text=True, timeout=10,
                    )
                    if launched.returncode == 0:
                        return str(lua), compiler, flags
                    detail = launched.stderr.strip() or f"probe exit {launched.returncode}"
                else:
                    detail = compiled.stderr.strip() or f"compiler exit {compiled.returncode}"
            except (OSError, subprocess.TimeoutExpired) as error:
                detail = str(error)
            errors.append(f"{origin}: {' | '.join(detail.splitlines()[-3:]) if detail else 'unknown error'}")

    raise SystemExit(
        f"{subject}: Lua 5.2 headers/library were found, but no C/C++ "
        f"fixture could link and run with {compiler_name}. "
        f"Last failure: {errors[-1]}. {_SETUP}"
    )
