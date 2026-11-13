"""Hades I game-native simulation-time behavior under the declared Lua ABI."""
import subprocess
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from lua_runtime_support import require_lua52

lua = require_lua52('Hades I simulation-time composition')
fixture = ROOT / 'tests/fixtures/hades/simulation_time_warp_contract.lua'
module = ROOT / 'Backend/games/hades/simulation_time_warp.lua'
result = subprocess.run([lua, str(fixture), str(module)], text=True,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
assert result.returncode == 0, result.stdout + result.stderr
assert 'hades_simulation_time_warp_lua_contract_ok' in result.stdout
print(result.stdout.strip())
