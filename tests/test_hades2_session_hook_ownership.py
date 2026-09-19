from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
lua = (ROOT / 'Backend/games/hades2/runtime/hades.lua').read_text()

owns = lua[lua.index('  local function owns(name)'):lua.index('  local function releaseHook(name)')]
install = lua[lua.index('  local function installHook(name, body, scope)'):lua.index('  local function refreshHealth()')]
sync = lua[lua.index('  local function synchronize()'):lua.index('  local function enforceResource(id)')]

assert 'hook.ownerSession == SessionState' in owns, 'stale session hook must not count as owned'
assert 'hook.ownerSession = ownerSession' in install
assert 'SessionState == ownerSession' in install, 'wrapper and owns() must share the same session lifetime'
assert 'M.gameSpeedActive and not owns("GameplaySetElapsedTimeMultiplier")' in sync
game_speed_rebind = sync[sync.index('if M.gameSpeedActive and not owns("GameplaySetElapsedTimeMultiplier")'):]
game_speed_rebind = game_speed_rebind[:game_speed_rebind.index('end') + len('end')]
assert 'releaseGameSpeed()' not in game_speed_rebind, 'session rebind must not undo the factor against a fresh Hero'
assert 'releaseHook("GameplaySetElapsedTimeMultiplier")' in game_speed_rebind
assert 'installGameSpeedHook()' in game_speed_rebind
assert 'refreshSpeedGlobal()' in game_speed_rebind
assert 'reconcileDesired(false)' in sync

print('hades2_session_hook_ownership_ok')
