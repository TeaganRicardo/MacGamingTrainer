from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
model = (ROOT/'Sources/Hades2/Hades2Model.swift').read_text()
api = (ROOT/'Sources/Hades2/Hades2API.swift').read_text()
adapter = (ROOT/'Backend/games/hades2/adapter.py').read_text()
router = (ROOT/'Backend/games/hades2/command_router.py').read_text()

termination = model[model.index('    private var runtimeCleanupRequired'):model.index('    private func finishExit')]
assert 'failExit' not in termination
assert 'let cleanupRequired = runtimeCleanupRequired' in termination
assert 'dormantFeatures.values.contains(true)' in termination
assert 'Hades2FeatureKey.allCases.contains(where: desiredFeatureEnabled)' in termination
assert 'desiredFeatureKeys' not in termination
assert 'sendBarrier(.resetDesired' in termination
assert 'guard self.connected, cleanupRequired else' in termination
assert 'sendBarrier(.disableAll' in termination
assert 'announceSuccess: false' in termination
assert 'self.finishExit(completion: completion)' in termination

# The exit-only desired reset is a typed Hades command and never needs a Lua boundary.
assert 'case resetDesired = "reset_desired"' in api
assert "elif command=='reset_desired':result=adapter.reset_desired()" in router
reset_method = adapter[adapter.index('    def reset_desired'):adapter.index('    def _capture_runtime_preferences')]
assert 'self._reset_preferences()' in reset_method
assert 'self.transport.attach' not in reset_method
assert 'mark_disconnected(self.state)' in reset_method

# Normal disable_all still clears durable intent before any reattach/boundary attempt.
# If durable persistence is explicitly blocked, runtime cleanup remains best-effort
# and the persistence failure is surfaced only after that boundary attempt.
execute = adapter[adapter.index('    def execute('):adapter.index('    def disconnect(', adapter.index('    def execute('))]
reset_pos = execute.index('try:self._reset_preferences()')
persist_catch_pos = execute.index('except PersistenceError as error:')
reattach_pos = execute.index("if command in ('disable_all','cleanup') and not self.transport.alive()")
boundary_pos = execute.index('decoded=execute_with_ledger')
persist_raise_pos = execute.index('if teardown_persistence_error is not None:raise teardown_persistence_error', boundary_pos)
assert reset_pos < persist_catch_pos < reattach_pos < boundary_pos < persist_raise_pos
reset = adapter[adapter.index('    def _reset_preferences'):adapter.index('    def reset_desired')]
assert reset.index('self.preference_store.save(preferences)') < reset.index('self.preferences=preferences')
print('exit_semantics_ok')
