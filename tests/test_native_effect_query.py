"""Run the production C collector/registration against temporary Lua fixtures."""
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path
from lua_native_prerequisites import require_lua52_native

ROOT = Path(__file__).resolve().parents[1]
_, compiler, lua_flags = require_lua52_native("Native effect-block query", language="c")
with tempfile.TemporaryDirectory(prefix='mgt-native-effect-query-') as temporary:
    executable = Path(temporary) / 'query_fixture'
    subprocess.run([compiler, '-std=c11', '-Wall', '-Wextra',
        '-I', str(ROOT / 'Backend/games/hades2/native'),
        str(ROOT / 'tests/fixtures/hades2/native_effect_query.c'),
        *lua_flags, '-lm', *(['-ldl'] if sys.platform.startswith('linux') else []),
        '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True, timeout=15)
    if sys.platform == 'darwin' and platform.machine() == 'arm64':
        # A startup-inserted image precedes the executable in arm64 dyld's
        # loaded-image inventory. The same native fixture must still validate
        # its explicitly supplied main image and refuse the helper UUID.
        source = Path(temporary) / 'startup_insertion.c'
        source.write_text('int mgt_startup_insertion_fixture(void) { return 1; }\n')
        insertion = Path(temporary) / 'libStartupInsertion.dylib'
        subprocess.run([compiler, '-dynamiclib', str(source), '-o', str(insertion)], check=True)
        environment = {**os.environ, 'DYLD_INSERT_LIBRARIES': str(insertion), 'MGT_EXPECT_STARTUP_IMAGE': '1'}
        subprocess.run([str(executable)], check=True, timeout=15, env=environment)
