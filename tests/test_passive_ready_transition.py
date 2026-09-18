from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
model = (ROOT / 'Sources/Hades2/Hades2Model.swift').read_text()
host = (ROOT / 'Sources/Core/Host/TrainerHost.swift').read_text()
contract = (ROOT / 'Sources/Core/Host/TrainerGameModule.swift').read_text()

# A live Hades status request crosses LLDB and temporarily stops/resumes the
# target. Readiness detection must therefore never be timer-driven while the
# player is using the game in the background.
for retired in (
    'passiveReadyProbeDelays',
    'passiveReadyProbeWorkItems',
    'passiveReadyProbeGeneration',
    'beginPassiveReadyProbes',
    'cancelPassiveReadyProbes',
):
    assert retired not in model, retired

# The host records target lifecycle intent through TrainerConnectionPolicy, but
# debugger restart/connect work is consumed only while Trainer itself is active.
assert 'guard NSApp.isActive else { return }' in host
assert 'NSApplication.didBecomeActiveNotification' in host
assert 'targetMonitor.refresh()' in host
assert 'reconcileAutomaticConnection()' in host
assert 'model.hostDidBecomeActive()' in host
assert 'connectionPolicy.targetActivated()' in host

# Target activation only records an opportunity. It must not consume that
# opportunity immediately because NSWorkspace target-activation can race the
# trainer's own didResignActive transition.
activation_start = host.index('.onChange(of: targetMonitor.activationGeneration)')
activation_end = host.index('.onChange(of: model.backendAvailable)', activation_start)
activation_block = host[activation_start:activation_end]
assert 'connectionPolicy.targetActivated()' in activation_block
assert 'reconcileAutomaticConnection()' not in activation_block

# Trainer activation is the only place that repairs a potentially missed target
# snapshot before consuming pending debugger work.
foreground_start = host.index('NSApplication.didBecomeActiveNotification')
foreground_end = host.index('\n    }\n\n    private func handlePrimaryConnectionAction', foreground_start)
host_foreground = host[foreground_start:foreground_end]
for token in (
    'targetMonitor.refresh()',
    'connectionPolicy.targetStateChanged(running: targetMonitor.isRunning)',
    'reconcileAutomaticConnection()',
    'model.hostDidBecomeActive()',
):
    assert token in host_foreground, token
assert host_foreground.index('targetMonitor.refresh()') < host_foreground.index('connectionPolicy.targetStateChanged')
assert host_foreground.index('connectionPolicy.targetStateChanged') < host_foreground.index('reconcileAutomaticConnection()')

# App activation is a generic optional lifecycle hook. Hades uses it only for a
# single foreground refresh when an existing connection is still waiting.
assert 'func hostDidBecomeActive()' in contract
assert 'extension TrainerHostModel' in contract
start = model.index('    func hostDidBecomeActive()')
end = model.index('\n    func toggleConnection()', start)
foreground = model[start:end]
for token in (
    'guard connected',
    'status == "waiting"',
    'backendAvailable',
    '!busy',
    '!exiting',
    'send(.status',
    'announceSuccess: false',
):
    assert token in foreground, token

# No generic process/Lua polling loop is introduced by the foreground design.
assert 'Timer.' not in host and 'scheduledTimer' not in host
assert 'asyncAfter' not in foreground

print('passive_ready_transition_ok')
