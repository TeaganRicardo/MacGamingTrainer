import shutil
import subprocess
import tempfile
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

# Idle refresh admission is an executable gate over an observed lifecycle
# signal. Comment wording and the currently selected transport do not own it.
swiftc = shutil.which("swiftc")
if not swiftc:
    raise SystemExit("swiftc required")
main_source = r'''
if !Hades2RunLogRefreshGate.shouldConsume(
    pending: true, connected: true, backendAvailable: true, busy: false, exiting: false
) {
    fatalError("an armed runtime-ready event must be consumable even if the previous GUI snapshot was ready")
}
if Hades2RunLogRefreshGate.shouldConsume(
    pending: false, connected: true, backendAvailable: true, busy: false, exiting: false
) {
    fatalError("no pending lifecycle refresh must mean no Lua boundary")
}
if Hades2RunLogRefreshGate.shouldConsume(
    pending: true, connected: false, backendAvailable: true, busy: false, exiting: false
) {
    fatalError("detached trainer must not cross the Lua boundary")
}
if Hades2RunLogRefreshGate.shouldConsume(
    pending: true, connected: true, backendAvailable: true, busy: true, exiting: false
) {
    fatalError("busy trainer must defer the lifecycle refresh")
}

if Hades2RunLogRefreshGate.shouldConsume(
    pending: true, connected: true, backendAvailable: false, busy: false, exiting: false
) {
    fatalError("unavailable backend must defer the lifecycle refresh")
}
if Hades2RunLogRefreshGate.shouldConsume(
    pending: true, connected: true, backendAvailable: true, busy: false, exiting: true
) {
    fatalError("an exiting trainer must not refresh runtime observations")
}
'''
with tempfile.TemporaryDirectory(prefix="mgt-background-boundary-") as temporary:
    main = Path(temporary) / "main.swift"
    binary = Path(temporary) / "refresh-gate"
    main.write_text(main_source)
    subprocess.run([swiftc, str(root / "Sources/Hades2/Services/Hades2RunLogRefreshGate.swift"),
                    str(main), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

print('background_boundary_policy_v0180_ok')
