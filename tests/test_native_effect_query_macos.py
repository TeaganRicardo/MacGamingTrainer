"""The native collector locates the supplied main image with a startup dylib."""
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path
from lua_native_prerequisites import require_lua52_native
from macos_fixture_policy import launch_fixture

if sys.platform != "darwin":
    raise SystemExit("macOS-only native effect-query image test")
assert platform.machine() == "arm64", "the supported native-query fixture requires arm64"
ROOT = Path(__file__).resolve().parents[1]
_, compiler, lua_flags = require_lua52_native("Native effect-block query", language="c")
with tempfile.TemporaryDirectory(prefix="mgt-native-effect-query-image-") as temporary:
    executable = Path(temporary) / "query_fixture"
    subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra",
        "-I", str(ROOT / "Backend/games/hades2/native"),
        str(ROOT / "tests/fixtures/hades2/native_effect_query.c"),
        *lua_flags, "-lm", "-o", str(executable)], check=True)
    source = Path(temporary) / "startup_insertion.c"
    source.write_text("int mgt_startup_insertion_fixture(void) { return 1; }\n")
    insertion = Path(temporary) / "libStartupInsertion.dylib"
    subprocess.run([compiler, "-dynamiclib", str(source), "-o", str(insertion)], check=True)
    environment = {**os.environ, "DYLD_INSERT_LIBRARIES": str(insertion), "MGT_EXPECT_STARTUP_IMAGE": "1"}
    launch_fixture([str(executable)], journey="native_effect_query.image_identity", check=True, env=environment)
