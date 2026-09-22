from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
model = (ROOT / 'Sources/Hades2/Hades2Model.swift').read_text()
host = (ROOT / 'Sources/Core/Host/TrainerHost.swift').read_text()
contract = (ROOT / 'Sources/Core/Host/TrainerGameModule.swift').read_text()
api = (ROOT / 'Sources/Hades2/Hades2API.swift').read_text()
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

# Initial process discovery and a real NSWorkspace launch are distinct events.
# Only didLaunch may grant permission to attach while Trainer is backgrounded.
monitor = (ROOT / 'Sources/Core/Runtime/TrainerTargetProcessMonitor.swift').read_text()
assert '@Published private(set) var launchGeneration' in monitor
launch_note = monitor[monitor.index('NSWorkspace.didLaunchApplicationNotification'):monitor.index('NSWorkspace.didActivateApplicationNotification')]
assert 'launchGeneration &+= 1' in launch_note

launch_start = host.index('.onChange(of: targetMonitor.launchGeneration)')
launch_end = host.index('.onChange(of: targetMonitor.activationGeneration)', launch_start)
launch_block = host[launch_start:launch_end]
for token in (
    'connectionPolicy.targetStateChanged(running: targetMonitor.isRunning)',
    'connectionPolicy.targetLaunched()',
    'reconcileAutomaticConnection()',
):
    assert token in launch_block, token

# A true target-process launch grants a one-shot background connection
# permission in the pure connection policy. The permission survives temporary
# busy/backend recovery states until connect is consumed; ordinary activation
# never grants it.
assert 'connectionPolicy.backgroundConnectionAllowed || NSApp.isActive' in host
assert 'reconcileAutomaticConnection(allowBackground:' not in host
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
# contract. Game modules that do not care keep the default toggle behavior;
# Hades uses the launch reason only to defer its first expensive runtime probe.
assert 'func connectAutomaticallyFromHost(targetJustLaunched: Bool)' in contract
assert 'connectAutomaticallyFromHost(targetJustLaunched:' in host
automatic_start = host.index('    private func reconcileAutomaticConnection()')
automatic_block = host[automatic_start:]
assert 'let targetJustLaunched = connectionPolicy.backgroundConnectionAllowed' in automatic_block
assert automatic_block.index('let targetJustLaunched = connectionPolicy.backgroundConnectionAllowed') < automatic_block.index('consumeAutomaticConnectIfEligible')
assert 'model.connectAutomaticallyFromHost(targetJustLaunched: targetJustLaunched)' in automatic_block

assert 'func connectAutomaticallyFromHost(targetJustLaunched: Bool)' in model
assert 'let canDeferRuntimeProbe = targetJustLaunched && runLogWatcher.canObserveLifecycle' in model
assert 'toggleConnection(probeRuntime: !canDeferRuntimeProbe)' in model
assert 'case connect(probeRuntime: Bool)' in api
assert '["probeRuntime": probeRuntime]' in api

# No generic process/Lua polling loop is introduced by the foreground design.
assert 'Timer.' not in host and 'scheduledTimer' not in host
assert 'asyncAfter' not in foreground

# First-ever Hades launch can create its Application Support/log directory after
# the Trainer's launch notification. The pre-connect watcher start is therefore
# paired with an idempotent post-connect start so the event-driven lifecycle
# cannot be permanently missed without adding polling.
toggle_start = model.index('    private func toggleConnection(probeRuntime: Bool)')
toggle_end = model.index('\n    func restartBackendFromHost()', toggle_start)
toggle = model[toggle_start:toggle_end]
assert toggle.count('runLogWatcher.start()') >= 2
completion_start = toggle.index('send(.connect')
completion = toggle[completion_start:]
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
consume_end = model.index('\n    private func toggleConnection(probeRuntime: Bool)', consume_start)
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
assert 'runtimeReset = "runtime_reset"' in api
assert 'case runtimeReset' in api
assert 'send(.runtimeReset' in event_block
assert event_block.index('send(.runtimeReset') < event_block.index('case .runtimeReady')

# If runtimeReady wins the race against background attach completion, retain the
# signal while disconnected; the post-connect completion consumes it exactly
# once instead of leaving the deferred connection stuck in waiting.
ready_block = event_block[event_block.index('case .runtimeReady'):]
assert ready_block.index('pendingRunReadySignal = true') < ready_block.index('guard connected else { return }')

backend_start = model[model.index('    private func startBackend()'):model.index('    private func resetAfterBackendTermination()')]
assert 'if !status.busy' in backend_start
assert 'consumeRunLogReadySignalIfPossible()' in backend_start
