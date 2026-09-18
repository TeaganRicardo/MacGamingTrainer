from pathlib import Path
import plistlib

ROOT = Path(__file__).resolve().parents[1]
client = (ROOT / 'Sources/Core/Runtime/BackendClient.swift').read_text()
process = (ROOT / 'Sources/Core/Runtime/BackendProcess.swift').read_text()
session = (ROOT / 'Sources/Core/Runtime/TrainerBackendSession.swift').read_text()
model = (ROOT / 'Sources/Hades2/Hades2Model.swift').read_text()
api = (ROOT / 'Sources/Hades2/Hades2API.swift').read_text()
scheduler = (ROOT / 'Sources/Hades2/Services/Hades2MutationScheduler.swift').read_text()

# Runtime reliability is implemented in behavior-bearing code rather than UI guards.
assert 'timeout: TimeInterval' in client
assert 'currentTimeoutWorkItem' in client
assert 'maxQueueDepth' in client
assert 'deliveringReply' in client
assert 'protocolViolation' in client
assert 'terminalFailureReported' in client
assert 'SIGKILL' in process
assert 'maxStdoutBufferBytes' in process
assert 'onProtocolError' in process
assert 'timeout: timeout' in session

# Hades chooses command-specific timeout policy; Core remains game agnostic.
assert 'var timeout: TimeInterval' in api
for value in ['return 15.0', 'return 8.0', 'return 90.0', 'return 12.0', 'return 30.0']:
    assert value in api
assert 'Hades' not in client and 'Hades' not in process and 'Hades' not in session

# Delayed mutation work is centralized and supports both discard barriers and flush.
assert 'mutationWorkItems' not in model
assert 'Hades2MutationScheduler' in model
assert 'func invalidateAll()' in scheduler
assert 'func flushAll()' in scheduler
assert 'sendBarrier(.disableAll' in model
assert 'sendBarrier(.loadProfile' in model
assert 'sendBarrier(.restoreBackup' in model
assert 'sendBarrier(.disconnect' in model
assert 'flushPendingMutations()' in model

# Backend termination must also tear down restore/session identity state.
reset = model[model.index('private func resetAfterBackendTermination'):model.index('private func apply(', model.index('private func resetAfterBackendTermination'))]
for token in ['pendingRestoreTimer?.invalidate()', 'pendingRestoreID = nil', 'pid = nil', 'invalidatePendingMutations()']:
    assert token in reset

with (ROOT / 'Info.plist').open('rb') as handle:
    plist = plistlib.load(handle)
assert plist['CFBundleShortVersionString'] == '0.1'
assert plist['CFBundleVersion'] == '2'

print('round17_static_ok')
