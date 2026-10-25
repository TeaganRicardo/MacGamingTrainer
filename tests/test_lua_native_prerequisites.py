"""Actionable Lua 5.2 native fixture prerequisite diagnostics and real link probe."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import lua_native_prerequisites as native


class LuaNativePrerequisiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mgt-native-preflight-contract-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.lua = self.root / "lua"
        self.lua.write_text("#!/bin/sh\nprintf 'Lua 5.2'\n", encoding="utf-8")
        self.lua.chmod(0o755)
        self.lua_patch = mock.patch.object(native, "require_lua52", return_value=str(self.lua))
        self.lua_patch.start()
        self.addCleanup(self.lua_patch.stop)

    def test_missing_compiler_is_actionable(self):
        real_which = shutil.which
        with mock.patch.object(native.shutil, "which", side_effect=lambda name: None if name == "c++" else real_which(name)):
            with self.assertRaises(SystemExit) as failure:
                native.require_lua52_native("fixture", language="c++")
        self.assertIn("c++ compiler required", str(failure.exception))
        self.assertIn("liblua5.2-dev", str(failure.exception))

    def test_interpreter_only_install_reports_headers_and_library(self):
        # Reproduce a Lua binary without its development package, independently
        # of development libraries installed on the host running this test.
        with mock.patch.object(native, "_link_candidates", return_value=[]):
            with self.assertRaises(SystemExit) as failure:
                native.require_lua52_native("mailbox", language="c")
        message = str(failure.exception)
        self.assertIn("interpreter found", message)
        self.assertIn("lauxlib.h", message)
        self.assertIn("linkable library", message)

    def test_non_52_interpreter_is_rejected_before_native_link(self):
        self.lua.write_text("#!/bin/sh\nprintf 'Lua 5.4'\n", encoding="utf-8")
        with self.assertRaises(SystemExit) as failure:
            native.require_lua52_native("query", language="c")
        self.assertIn("must be Lua 5.2", str(failure.exception))

    @unittest.skipUnless(shutil.which("cc"), "requires C compiler")
    def test_unlinkable_library_is_reported_by_actual_compiler(self):
        for name in native._HEADERS:
            (self.root / name).write_text("#define LUA_VERSION_NUM 502\n", encoding="utf-8")
        archive = self.root / "liblua.a"
        archive.write_bytes(b"not an archive")
        flags = ["-I", str(self.root), str(archive)]
        with mock.patch.object(native, "_link_candidates", return_value=[("fake archive", flags)]):
            with self.assertRaises(SystemExit) as failure:
                native.require_lua52_native("native query", language="c")
        message = str(failure.exception)
        self.assertIn("could link and run", message)
        self.assertIn("fake archive", message)

    @unittest.skipUnless(all(shutil.which(name) for name in ("cc", "c++", "ar")), "requires compilers and ar")
    def test_real_compiler_and_linker_smoke_for_c_and_cpp(self):
        (self.root / "lua.h").write_text(
            "#define LUA_VERSION_NUM 502\n"
            "typedef struct lua_State lua_State;\n"
            "void lua_close(lua_State *state);\n", encoding="utf-8"
        )
        (self.root / "lauxlib.h").write_text(
            '#include "lua.h"\nlua_State *luaL_newstate(void);\n', encoding="utf-8"
        )
        (self.root / "lualib.h").write_text('#include "lua.h"\n', encoding="utf-8")
        stub = self.root / "stub.c"
        stub.write_text(
            '#include "lua.h"\n'
            'struct lua_State {int live;};\n'
            'static struct lua_State state;\n'
            'lua_State *luaL_newstate(void) {return &state;}\n'
            'void lua_close(lua_State *unused) {(void)unused;}\n', encoding="utf-8"
        )
        subprocess.run(["cc", "-I", str(self.root), "-c", str(stub), "-o", str(self.root / "stub.o")], check=True)
        archive = self.root / "liblua.a"
        subprocess.run(["ar", "rcs", str(archive), str(self.root / "stub.o")], check=True)
        flags = ["-I", str(self.root), str(archive)]
        for language in ("c", "c++"):
            with self.subTest(language=language):
                lua, compiler, selected_flags = native.require_lua52_native("fixture", language=language)
                self.assertEqual(lua, str(self.lua.resolve()))
                self.assertEqual(selected_flags, flags)
                self.assertTrue(compiler)


if __name__ == "__main__":
    unittest.main()
