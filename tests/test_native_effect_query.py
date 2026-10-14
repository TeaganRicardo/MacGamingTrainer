"""Run the production C collector/registration against temporary Lua fixtures."""
import shutil
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path
from lua_runtime_support import require_lua52

ROOT = Path(__file__).resolve().parents[1]
lua = Path(require_lua52('Native effect-block query')).resolve()
compiler = shutil.which('cc')
assert compiler, 'A C compiler is required for the native query fixture'
if (lua.parent / 'lua.h').is_file() and (lua.parent / 'liblua.a').is_file():
    lua_flags = ['-I', str(lua.parent), str(lua.parent / 'liblua.a')]
elif Path('/usr/include/lua5.2/lua.h').is_file():
    lua_flags = ['-I', '/usr/include/lua5.2', '-llua5.2']
else:
    include, library = lua.parent.parent / 'include/lua.h', lua.parent.parent / 'lib/liblua.a'
    assert include.is_file() and library.is_file(), 'Lua 5.2 development headers/library are required'
    lua_flags = ['-I', str(include.parent), str(library)]
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
