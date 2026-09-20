from pathlib import Path
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from games.hades2.preferences import Hades2PreferenceStore
from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter

view = (ROOT/'Sources/Hades2/Hades2View.swift').read_text()
card = (ROOT/'Sources/Core/UI/Primitives/TrainerCard.swift').read_text()
stats = (ROOT/'Sources/Core/UI/Components/TrainerStatControls.swift').read_text()
toggle = (ROOT/'Sources/Core/UI/Primitives/TrainerToggleControl.swift').read_text()
host = (ROOT/'Sources/Core/Host/TrainerHost.swift').read_text()
model = (ROOT/'Sources/Hades2/Hades2Model.swift').read_text()
lua = (ROOT/'Backend/games/hades2/runtime/hades.lua').read_text()

# Compact session cards: no artificial min-height may insert a blank strip
# above the title row; paired values/suffixes stay visually together.
metric_block = card[card.index('struct TrainerMetricCard'):]
assert '.padding(.top, 6)' in metric_block and '.padding(.bottom, 8)' in metric_block
assert 'minHeight: 82' not in metric_block
assert '.frame(maxWidth: .infinity, alignment: .leading)' in metric_block
assert 'HStack(spacing: 2)' in stats
assert stats.count('.frame(width: 54)') >= 2
assert 'HStack(spacing: 3)' in stats and '.frame(width: 58)' in stats

# Whole expand/collapse label is one compact hit target.
assert 'HStack(spacing: 5)' in view
assert '.contentShape(Rectangle())' in view

# Shared switch remains the one native implementation; purple is the default
# and feature rows may synchronize it with warning/active indicator state.
assert '.controlSize(.regular)' in toggle
assert '.tint(tint ?? theme.accent)' in toggle

# Save manager is not disabled/re-enabled by every transient game request.
save_start = host.index('Label("存档管理"')
save_line = host[save_start:host.index('}', save_start) + 1]
assert 'model.busy' not in save_line
assert '!model.backendAvailable' in save_line

# Never poll live Lua automatically: every status call crosses the debugger
# boundary and can stop the game for hundreds of milliseconds.
for token in ('featureStateTimer', 'updateFeatureStatePolling()', 'withTimeInterval: 4.0', 'self.send(.status, title: "同步功能状态", announceSuccess: false)'):
    assert token not in model, token
assert 'saveManagerBusy' not in model

# Next-room UI and Lua both use current reward IDs, not early-access RoomReward* IDs.
for token in ('RoomMoneyDrop','MetaCurrencyDrop','MetaCardPointsCommonDrop','MemPointsCommonDrop','MaxHealthDrop','MaxManaDrop','StackUpgrade','WeaponUpgrade','SpellDrop'):
    assert token in view, token
for old in ('RoomRewardMoney','RoomRewardMetaPoint','RoomRewardPsyche','RoomRewardMixerFabric','RoomRewardMaxHealth','RoomRewardPom'):
    assert old not in view, old
assert 'room.ChosenRewardType = rewardType' in lua
assert 'return "Boon", wanted' in lua

# SpellDrop is the special case that must use the game's full native room
# reward path, which in turn initializes the Selene LootData through GiveLoot.
assert 'if rewardId == "SpellDrop" then' in lua
assert 'requireFunctions("Selene room reward spawning", { "SpawnRoomReward" })' in lua
assert 'RewardOverride = "SpellDrop"' in lua

# Old stored preferences migrate forward instead of silently retaining dead IDs.
normalized = Hades2PreferenceStore.normalize({'nextRoomReward':'RoomRewardMoney'})
assert normalized['nextRoomReward'] == 'RoomMoneyDrop'
normalized = Hades2PreferenceStore.normalize({'nextRoomReward':'RoomRewardPom'})
assert normalized['nextRoomReward'] == 'StackUpgrade'
normalized = Hades2PreferenceStore.normalize({'nextRoomReward':'RoomRewardMixerFabric'})
assert normalized['nextRoomReward'] is None

# Once Lua consumes a one-shot override, a clean status must clear persistence
# instead of resurrecting it from the desired-state overlay.
class StatusTransport:
    pid = 4242
    last_duration = 0.0
    def alive(self): return True
    def execute(self, code):
        return json.dumps({
            'connected': True, 'status': 'ready', 'scene': 'run',
            'capabilities': {}, 'desiredFeatures': {}, 'activeFeatures': {},
            'dormantFeatures': {}, 'featureErrors': {}, 'resources': [],
            'rewards': [], 'stats': {}, 'statSupport': {}, 'statAvailable': {},
            'elements': [],
        })
    def detach(self): pass
    def close(self): pass

old_data = preparation.DATA
try:
    preparation.DATA = Path(tempfile.mkdtemp(prefix='mgt-v0179-one-shot-'))
    adapter = Hades2Adapter(transport=StatusTransport())
    adapter.preferences = adapter._default_preferences()
    adapter.preferences['nextRoomReward'] = 'MaxHealthDrop'
    adapter.preference_initialized = True
    adapter.preference_dirty = False
    adapter.state.update(connected=True, status='ready', nextRoomReward='MaxHealthDrop')
    state = adapter.execute('status', {})
    assert adapter.preferences['nextRoomReward'] is None
    assert state['nextRoomReward'] is None
finally:
    preparation.DATA = old_data

print('v0179_regressions_ok')
