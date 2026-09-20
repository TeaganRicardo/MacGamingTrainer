from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
model = (ROOT/'Sources/Hades2/Hades2Model.swift').read_text()
host = (ROOT/'Sources/Core/Host/TrainerHost.swift').read_text()
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

# Next-room reward is constrained to real exit-door reward selection, persists
# across every offered door, and is consumed only when the player enters a room.
assert 'requireFunctions("next room reward", { "ChooseRoomReward", "StartRoom" })' in lua
assert 'type(args.Door) ~= "table"' in lua
assert 'M.nextRoomReward = nil\n            releaseNextRoomReward()' in lua
choose_block = lua[lua.index('installHook("ChooseRoomReward"'):lua.index('if not owns("StartRoom")')]
assert 'M.nextRoomReward = nil' not in choose_block
assert 'patchOfferedNextRoomDoors()' in lua
assert 'CurrentRun.CurrentRoom.OfferedRewards[doorId]' in lua
assert 'ReUseIds = true' in lua
assert 'nextRoomRewardPatchedDoors' in lua

print('v01710_regressions_ok')
