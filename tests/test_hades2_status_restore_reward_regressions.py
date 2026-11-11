from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
model = (ROOT/'Sources/Hades2/Hades2Model.swift').read_text()
host = (ROOT/'Sources/Core/Host/TrainerGameContext.swift').read_text()
save_model = (ROOT/'Sources/Core/Save/TrainerSaveManagerModel.swift').read_text()
lua = (ROOT/'Backend/games/hades2/runtime/hades.lua').read_text()

# The v0.17.9 4-second live status timer caused debugger boundary stops in play.
assert 'featureStateTimer' not in model
assert 'updateFeatureStatePolling' not in model
assert '同步功能状态' not in model

# Staged restore is Host-event-driven; the removed Hades save manager has no
# passive scan timer or special busy projection.
assert 'saveManagerBusy' not in model
assert 'pendingRestoreTimer' not in model
assert 'saveManager.applyStagedIfPossible()' in host
assert 'Timer.scheduledTimer' not in save_model

# #704 retires the global all-exits next-room owner. Row 1 is exact-door
# resident state, route Apply is a reservation, and LeaveRoom is the only
# generic-room materialization seam.
assert 'command == "set_next_room_reward"' not in lua
assert "M.nextRoomReward" not in lua
assert "local function rewardCandidates(door)" in lua
assert "local function applyReward(door, target, doorToken)" in lua
assert "local function applyRoute(door, target, doorToken)" in lua
apply_start = lua.index("local function applyRoute(door, target, doorToken)")
apply_end = lua.index("local function preflightApply", apply_start)
apply_block = lua[apply_start:apply_end]
assert "CreateRoom(" not in apply_block
assert "GetRandomValue(" not in apply_block
assert "AssignRoomToExitDoor(" not in apply_block
assert 'installHook("LeaveRoom"' in lua
commit_start = lua.index("local function materializeRoute(run, door, lease)")
commit_end = lua.index("local function installRouteHooks", commit_start)
commit_block = lua[commit_start:commit_end]
assert "GetRandomValue(candidates)" in commit_block
assert "CreateRoom(data" in commit_block
assert "AssignRoomToExitDoor(door, target)" in commit_block

print('v01710_regressions_ok')
