"""Behavioral tests for Lua 5.2 resident local-budget discovery and enforcement."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from lua_local_reserve import (
    discover_top_level_factories,
    inject_factory_locals,
    measure_local_reserve,
    require_minimum_reserve,
)
from lua_runtime_support import require_lua52

LUA = require_lua52("resident local-reserve probe tests")


class ResidentLocalReserveProbeTests(unittest.TestCase):
    def test_discovers_added_top_level_factories_and_ignores_nested_iifes(self):
        source = """if true then
  M.first = (function()
    local nested = (function()
      return {}
    end)()
    return nested
  end)()
  local second = (function()
    return {}
  end)()
end
"""
        factories = discover_top_level_factories(source)
        self.assertEqual([factory.name for factory in factories], ["M.first", "second"])
        self.assertEqual([factory.line_number for factory in factories], [2, 8])

    def test_fails_closed_when_a_top_level_factory_shape_is_unrecognized(self):
        source = """if true then
  M.recognized = (function()
    return {}
  end)()
  M.dynamic[index] = (function()
    return {}
  end)()
end
"""
        with self.assertRaisesRegex(ValueError, "unrecognized top-level IIFE factory"):
            discover_top_level_factories(source)

    def test_factory_below_budget_fails_the_same_reserve_gate(self):
        names = ", ".join(f"local_{index}" for index in range(1, 186))
        source = (
            "local M = {}\n"
            "  M.tight = (function()\n"
            f"    local {names}\n"
            "    return {}\n"
            "  end)()\n"
        )
        factory = discover_top_level_factories(source)[0]
        with tempfile.TemporaryDirectory(prefix="mgt-lua52-reserve-regression-") as temporary:
            probe_path = Path(temporary) / "factory.lua"

            def compiles(probe_source):
                probe_path.write_text(probe_source, encoding="utf-8")
                command = f"local f,e=loadfile({str(probe_path)!r}); if not f then error(e) end"
                result = subprocess.run(
                    [LUA, "-e", command], text=True, capture_output=True, timeout=30
                )
                if result.returncode == 0:
                    return True
                if "too many local variables (limit is 200)" in result.stderr:
                    return False
                self.fail("Lua reserve fixture failed unexpectedly: " + result.stderr)

            reserve = measure_local_reserve(
                lambda declarations: inject_factory_locals(source, factory, declarations),
                compiles,
                factory.name,
            )
        self.assertLess(reserve, 16)
        with self.assertRaisesRegex(ValueError, "below required local reserve"):
            require_minimum_reserve(factory.name, reserve, 16)


if __name__ == "__main__":
    unittest.main()
