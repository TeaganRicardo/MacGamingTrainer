from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
model = (ROOT/'Sources/Hades2/Hades2Model.swift').read_text()
management = (ROOT/'Sources/Hades2/Views/Hades2ManagementViews.swift').read_text()
lua = (ROOT/'Backend/games/hades2/runtime/hades.lua').read_text()

# The v0.17.9 4-second live status timer caused debugger boundary stops in play.
assert 'featureStateTimer' not in model
assert 'updateFeatureStatePolling' not in model
assert '同步功能状态' not in model

# Passive staged-restore scans do not lock/flash the Save Manager itself.
assert 'var saveManagerBusy: Bool' in model
save_view = management[:management.index('struct Hades2ProfileManagerView')]
assert 'model.saveManagerBusy' in save_view
assert 'model.busy' not in save_view

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
