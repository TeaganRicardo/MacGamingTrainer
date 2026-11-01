from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
policy = (ROOT / 'Sources/Core/Host/TrainerConnectionPolicy.swift').read_text()
host = (ROOT / 'Sources/Core/Host/TrainerGameContext.swift').read_text()

assert 'targetExitRefreshRequested' in policy
assert 'consumeTargetExitRefreshIfEligible' in policy

start = host.index('    private func reconcileAutomaticConnection()')
block = host[start:]
assert 'connectionPolicy.consumeTargetExitRefreshIfEligible(' in block
assert 'model.refreshFromHost()' in block
assert block.index('consumeTargetExitRefreshIfEligible') < block.index('backgroundConnectionAllowed')
assert 'if !running, model.backendAvailable && !model.busy' not in host

host_view = (ROOT / 'Sources/Core/Host/TrainerHost.swift').read_text()
assert '.onAppear {' in host_view and 'targetMonitor.refresh()' in host_view
assert 'onRefresh: {' in host_view
refresh_action = host_view[host_view.index('onRefresh: {'):host_view.index('onPrimary:', host_view.index('onRefresh: {'))]
assert 'targetMonitor.refresh()' in refresh_action
assert 'model.refreshFromHost()' in refresh_action
sidebar = host_view[host_view.index('struct TrainerHostSidebarCard<'):]
launch_start = sidebar.index('    private var launchAction:')
launch_action = sidebar[launch_start:sidebar.index('    var body: some View', launch_start)]
assert 'onLaunch: launchAction' in sidebar
assert 'targetMonitor.refresh()' in launch_action
assert 'if targetMonitor.isRunning' in launch_action
assert 'context.toggleConnection()' in launch_action
assert 'launch()' in launch_action

print('target_exit_refresh_contract_ok')
