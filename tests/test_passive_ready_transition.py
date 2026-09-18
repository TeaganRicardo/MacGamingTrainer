from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
model = (ROOT / 'Sources/Hades2/Hades2Model.swift').read_text()
host = (ROOT / 'Sources/Core/Host/TrainerHost.swift').read_text()

# Waiting completion is deliberately bounded: exactly two independently
# scheduled one-shot probes at 15s and 30s from the waiting transition. The
# second probe must not be chained off completion of the first.
assert 'private static let passiveReadyProbeDelays: [TimeInterval] = [15, 30]' in model
assert 'private var passiveReadyProbeWorkItems: [DispatchWorkItem] = []' in model
block = model[model.index('    private func beginPassiveReadyProbes'):model.index('    private func applyStat')]
assert 'for delay in Self.passiveReadyProbeDelays' in block
assert 'passiveReadyProbeWorkItems.append(work)' in block
assert 'DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: work)' in block
assert 'passiveReadyProbeWorkItems.forEach { $0.cancel() }' in block
assert 'passiveReadyProbeWorkItems.removeAll()' in block
assert 'generation == self.passiveReadyProbeGeneration' in block
assert 'self.status == "waiting"' in block
assert '!self.busy' in block
assert 'self.send(.status' in block
assert 'schedulePassiveReadyProbe' not in block
assert 'passiveReadyProbeIndex' not in block
assert 'Timer.' not in block and 'scheduledTimer' not in block

# A new connected->waiting transition arms the bounded watch; ready, detach,
# backend termination and app termination all invalidate its generation.
apply = model[model.index('    private func apply('):model.index('    private func applyStat')]
assert 'connected && status == "waiting" && (!wasConnected || previousStatus != "waiting")' in apply
assert 'else if !connected || status != "waiting"' in apply
assert 'cancelPassiveReadyProbes()' in model[model.index('    private func resetAfterBackendTermination'):model.index('    private func apply(')]
assert 'cancelPassiveReadyProbes()' in model[model.index('    func prepareForTermination'):model.index('    private func finishExit')]

# Host remains event-driven; no generic target-process polling was introduced.
assert 'Timer.' not in host and 'scheduledTimer' not in host
print('passive_ready_transition_ok')
