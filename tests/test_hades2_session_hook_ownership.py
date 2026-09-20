from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
lua = (ROOT / 'Backend/games/hades2/runtime/hades.lua').read_text()

owns = lua[lua.index('  local function owns(name)'):lua.index('  local function releaseHook(name)')]
install = lua[lua.index('  local function installHook(name, body, scope)'):lua.index('  local function refreshHealth()')]
sync = lua[lua.index('  local function synchronize()'):lua.index('  local function enforceResource(id)')]

assert 'hook.ownerSession == SessionState' in owns, 'stale session hook must not count as owned'
assert 'hook.ownerSession = ownerSession' in install
assert 'SessionState == ownerSession' in install, 'wrapper and owns() must share the same session lifetime'
assert 'GameplaySetElapsedTimeMultiplier' not in lua, 'process Time Warp must not regress into Lua hook ownership'
assert 'gameSpeedActive' not in lua
assert 'reconcileDesired(false)' in sync

print('hades2_session_hook_ownership_ok')
