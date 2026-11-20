from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
model = (ROOT / 'Sources/Hades2/Hades2Model.swift').read_text()
host = (ROOT / 'Sources/Core/Host/TrainerGameContext.swift').read_text()
api = (ROOT / 'Sources/Hades2/Hades2API.swift').read_text()
command_binding = (ROOT / 'Sources/Hades2/Generated/Hades2Command.generated.swift').read_text()
watcher_path = ROOT / 'Sources/Hades2/Services/Hades2RunLogWatcher.swift'
assert watcher_path.exists(), 'Hades2 run-log watcher is missing'
watcher = watcher_path.read_text()

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

# App activation is a generic optional lifecycle hook. Hades uses it only for a
# single foreground refresh when an existing connection is still waiting.
start = model.index('    func hostDidBecomeActive()')
end = model.index('\n    private func handleRunLogEvent', start)
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

# Automatic connection carries the true-launch reason through the generic Host
# contract (verified behaviorally in test_core_host_lifecycle_macos.py).
assert 'func connectFromHost(reason: TrainerHostConnectReason)' in model
assert 'launchAttachGate.deferUntilReady(' in model
assert 'consumeDeferredLaunchAttachIfPossible()' in model
# Backend recovery can delay Host's grant until after native readiness.
# The gate owns readiness across backend restarts and clears it only on a
# native reset or definitive target OS-process lifetime change.
launch_connect = model[model.index('    private func connectAutomatically('):model.index('    func refreshFromHost()', model.index('    private func connectAutomatically('))]
assert 'launchAttachGate.deferUntilReady(' in launch_connect
assert 'consumeDeferredLaunchAttachIfPossible()' in launch_connect
assert 'hostTargetLifetimeChanged(observation: TrainerTargetObservation)' in model
assert 'launchAttachGate.observeRuntimeReset()' in model

assert 'connect(probeRuntime: true' in model
assert 'case connect(probeRuntime: Bool, recoverLostAttach: Bool)' in api
assert '["probeRuntime": probeRuntime, "recoverLostAttach": recoverLostAttach]' in api

# Kept (lint): no compile or render hook rules out background timer polling in the Host context.
assert 'Timer.' not in host and 'scheduledTimer' not in host
assert 'asyncAfter' not in foreground

# First-ever Hades launch can create its Application Support/log directory after
# the Trainer's launch notification. The pre-connect watcher start is therefore
# paired with an idempotent post-connect start so the event-driven lifecycle
# cannot be permanently missed without adding polling.
connect_start = model.index('    private func connect(recoverLostAttach: Bool = false)')
connect_end = model.index('\n    func launchGame()', connect_start)
connect = model[connect_start:connect_end]
assert connect.count('runLogWatcher.start()') >= 2
completion_start = connect.index('send(.connect')
completion = connect[completion_start:]
assert completion.index('runLogWatcher.start()') < completion.index('consumeRunLogReadySignalIfPossible()')

print('passive_ready_transition_ok')


# Hades lifecycle refreshes are driven by real game-log writes, never by a
# timer. Ordinary room transitions must not cross LLDB: the expensive refresh
# is armed only by a world stop / Lua-generation reset and consumed after that
# reset's load completes.
for token in (
    'DispatchSource.makeFileSystemObjectSource',
    'Loading package: MainMenu.pkg',
    'App.Reset Start',
    'Lua interface destroyed',
    'Finished loadScreen onExit',
    'runtimeResetPending',
    'systemFileNumber',
):
    assert token in watcher, token
assert 'World::Begin()' not in watcher
assert 'World::Stop()' not in watcher
assert 'Timer.' not in watcher
assert 'asyncAfter' not in watcher

for token in (
    'Hades2RunLogWatcher',
    'Hades2RunLogEvent',
    'pendingRunReadySignal',
    'handleRunLogEvent',
    'consumeRunLogReadySignalIfPossible',
):
    assert token in model, token

consume_start = model.index('    private func consumeRunLogReadySignalIfPossible()')
consume_end = model.index('\n    private func connect(recoverLostAttach: Bool = false)', consume_start)
run_log_refresh = model[consume_start:consume_end]
assert 'Hades2RunLogRefreshGate.shouldConsume' in run_log_refresh
assert 'status == "ready"' not in run_log_refresh
assert 'status == "waiting"' not in run_log_refresh

event_start = model.index('    private func handleRunLogEvent(')
event_end = model.index('\n    private func consumeRunLogReadySignalIfPossible()', event_start)
event_block = model[event_start:event_end]
for token in ('.mainMenu', '.runtimeReset', '.runtimeReady', 'activeFeatures = [:]', 'capabilities = capabilities.mapValues'):
    assert token in event_block, token

# The game log already tells us that App.Reset destroyed the Lua generation.
# Propagate that fact to the backend without crossing LLDB, so runtimeReady can
# bootstrap immediately instead of discovering the missing resident module by
# executing one doomed status request first.
assert 'case runtimeReset = "runtime_reset"' in command_binding
assert 'send(.runtimeReset' in event_block
event_switch_start = event_block.rindex('        switch event {')
event_switch = event_block[event_switch_start:]
assert event_switch.index('send(.runtimeReset') < event_switch.index('case .runtimeReady')

# If runtimeReady wins the race against background attach completion, retain the
# signal while disconnected; the post-connect completion consumes it exactly
# once instead of leaving the deferred connection stuck in waiting.
ready_block = event_switch[event_switch.index('case .runtimeReady'):]
assert ready_block.index('pendingRunReadySignal = true') < ready_block.index('guard connected else { return }')

status_observer = model[model.index('        statusObserver ='):model.index('        DispatchQueue.main.async', model.index('        statusObserver ='))]
assert 'if !current.busy' in status_observer
assert 'consumeRunLogReadySignalIfPossible()' in status_observer
