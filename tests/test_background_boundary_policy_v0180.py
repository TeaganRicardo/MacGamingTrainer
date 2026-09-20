from pathlib import Path

root = Path(__file__).resolve().parents[1]
hades_sources = list((root/'Sources/Hades2').rglob('*.swift'))
texts = {path: path.read_text() for path in hades_sources}
model = texts[root/'Sources/Hades2/Hades2Model.swift']

# Repeating timers are a known performance hazard because status/connect can
# cross the LLDB/Lua boundary. Save restore is now Host-event-driven as well,
# so Hades owns no repeating Timer.scheduledTimer path at all.
all_scheduled_timers = [
    (path, text.count('Timer.scheduledTimer'))
    for path, text in texts.items()
    if 'Timer.scheduledTimer' in text
]
assert all_scheduled_timers == []

# The removed feature-state polling regression must stay removed.
for forbidden in ('featureStateTimer', 'updateFeatureStatePolling', '同步功能状态'):
    assert forbidden not in model

# The source comment documents the boundary rule next to mutation scheduling so
# future UI maintenance does not reintroduce an automatic live-status loop.
assert 'Do not poll in-process Lua state automatically' in model
assert 'Every status request crosses' in model

print('background_boundary_policy_v0180_ok')
