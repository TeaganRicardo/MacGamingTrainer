from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
policy = (ROOT / 'Sources/Core/Host/TrainerConnectionPolicy.swift').read_text()
host = (ROOT / 'Sources/Core/Host/TrainerHost.swift').read_text()

assert 'targetExitRefreshRequested' in policy
assert 'consumeTargetExitRefreshIfEligible' in policy

start = host.index('    private func reconcileAutomaticConnection()')
block = host[start:]
assert 'connectionPolicy.consumeTargetExitRefreshIfEligible(' in block
assert 'model.refreshFromHost()' in block
assert block.index('consumeTargetExitRefreshIfEligible') < block.index('backgroundConnectionAllowed')
assert 'if !running, model.backendAvailable && !model.busy' not in host

print('target_exit_refresh_contract_ok')
