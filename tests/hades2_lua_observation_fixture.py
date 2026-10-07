"""A live Lua 5.2 resident behind the real Python session JSON boundary."""
import ast
import subprocess
import tempfile
from pathlib import Path

from core.adapter import AdapterError
from games.hades2.resident_session import lua_value
from lua_runtime_support import RESIDENT_DISPATCH_CONTRACT, require_lua52

ROOT = Path(__file__).resolve().parents[1]


class LuaObservationTransport:
    def __init__(self):
        tree = ast.parse((ROOT / "tests/test_hades2_force_enable_rerolls.py").read_text())
        fixture = next(ast.literal_eval(node.value) for node in tree.body
                       if isinstance(node, ast.Assign)
                       and any(isinstance(target, ast.Name) and target.id == 'HARNESS'
                               for target in node.targets))
        fixture = fixture[:fixture.index("assert(CurrentRun.NumRerolls == 10)")]
        fixture += r'''
UpdateHealthUI = function() end
UpdateWeaponMana = function() end
UpdateManaMeterUI = function() end
GetHeroMaxAvailableMana = function()
  return math.max(0, CurrentRun.Hero.MaxMana - (CurrentRun.Hero.ReservedMana or 0))
end
GetWeaponData = function() return {} end
GetManaSpendCost = function() return 20 end
for source in io.lines() do
  local fn, message = load(source)
  local ok, result = false, message
  if fn then ok, result = pcall(fn) end
  io.write(ok and tostring(result) or ('ERROR:' .. tostring(result)), '\n')
  io.flush()
end
'''
        self.temporary = tempfile.TemporaryDirectory(prefix="mgt-lua-observation-")
        harness = Path(self.temporary.name) / 'resident.lua'
        harness.write_text(fixture)
        self.process = subprocess.Popen(
            [require_lua52("resident observation integration"), str(harness),
             str(ROOT / 'Backend/games/hades2/runtime/hades.lua'), str(RESIDENT_DISPATCH_CONTRACT)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.pid = 4242
        self.live = True
        self.tainted = False
        self.last_duration = 0
        self.last_expression_duration = 0
        self.last_attach_profile = {}

    def alive(self):
        return self.live and self.process.poll() is None

    def execute(self, source, *, expression_timeout_seconds=None):
        self.process.stdin.write('return assert(load(' + lua_value(source) + '))()\n')
        self.process.stdin.flush()
        result = self.process.stdout.readline().rstrip('\n')
        if result.startswith('ERROR:'):
            raise AdapterError('lua_error', result[6:])
        if not result:
            raise AssertionError(self.process.stderr.read())
        return result

    def evaluate(self, source):
        return self.execute(source + '\nreturn "ok"')

    def attach(self, pid):
        self.pid = pid
        self.live = True

    def detach(self):
        self.live = False

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=5)
        self.process.stdout.close()
        self.process.stderr.close()
        self.temporary.cleanup()
