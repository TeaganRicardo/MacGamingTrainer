from pathlib import Path

root = Path(__file__).resolve().parents[1]
hades_sources = list((root/'Sources/Hades2').rglob('*.swift'))
texts = {path: path.read_text() for path in hades_sources}
model = texts[root/'Sources/Hades2/Hades2Model.swift']

# Repeating timers are a known performance hazard because status/connect can
# cross the LLDB/Lua boundary.  The only repeating Hades timer retained by the
# current design is the staged-save-restore watcher, whose scan is gated on a
# pending restore and does not invoke live Lua status.
all_scheduled_timers = [
    (path, text.count('Timer.scheduledTimer'))
    for path, text in texts.items()
    if 'Timer.scheduledTimer' in text
]
assert all_scheduled_timers == [(root/'Sources/Hades2/Hades2Model.swift', 1)]

start = model.index('pendingRestoreTimer = Timer.scheduledTimer')
end = model.index('\n    func shortcutDigit', start)
watcher = model[start:end]
assert 'repeats: true' in watcher
assert 'pendingRestoreID != nil' in watcher
assert 'self.send(.scan' in watcher
for forbidden in ('.status', '.connect', '.listBackups', '.loadProfile', '.saveProfile'):
    assert forbidden not in watcher

# The removed feature-state polling regression must stay removed.
for forbidden in ('featureStateTimer', 'updateFeatureStatePolling', '同步功能状态'):
    assert forbidden not in model

# The source comment documents the boundary rule next to mutation scheduling so
# future UI maintenance does not reintroduce an automatic live-status loop.
assert 'Do not poll in-process Lua state automatically' in model
assert 'Every status request crosses' in model

print('background_boundary_policy_v0180_ok')
