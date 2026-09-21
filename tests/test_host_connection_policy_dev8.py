from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which('swiftc')
if not SWIFTC:
    raise SystemExit('swiftc required for host connection policy test')

harness = r'''
func fail(_ message: String) -> Never {
    fatalError(message)
}

var policy = TrainerConnectionPolicy()

// No target means no background restart/connect.
policy.backendBecameUnavailable()
policy.backendBecameAvailable()
if policy.consumeAutomaticBackendRestartIfEligible(backendAvailable: false, busy: false, actionsEnabled: true) {
    fail("restarted backend without a running target")
}
if policy.consumeAutomaticConnectIfEligible(backendAvailable: true, busy: false, connected: false, actionsEnabled: true) {
    fail("connected without a running target")
}

// A target launch can recover a missing backend first, then connect exactly once
// when that backend becomes available.
policy.targetStateChanged(running: true)
if !policy.consumeAutomaticBackendRestartIfEligible(backendAvailable: false, busy: false, actionsEnabled: true) {
    fail("launch did not request missing backend recovery")
}
if policy.consumeAutomaticBackendRestartIfEligible(backendAvailable: false, busy: false, actionsEnabled: true) {
    fail("backend restart request was not one-shot")
}
policy.backendBecameAvailable()
if !policy.consumeAutomaticConnectIfEligible(backendAvailable: true, busy: false, connected: false, actionsEnabled: true) {
    fail("recovered backend did not lead to automatic connect")
}
if policy.consumeAutomaticConnectIfEligible(backendAvailable: true, busy: false, connected: false, actionsEnabled: true) {
    fail("launch connect was not one-shot")
}

// Merely discovering an already-running target is not a true launch and must
// never grant background debugger permission. Only the explicit launch event
// may do so.
var launchPolicy = TrainerConnectionPolicy()
launchPolicy.targetStateChanged(running: true)
if launchPolicy.backgroundConnectionAllowed {
    fail("initial running snapshot incorrectly granted background permission")
}
launchPolicy.targetLaunched()
if !launchPolicy.backgroundConnectionAllowed {
    fail("explicit launch did not grant background connection permission")
}
if launchPolicy.consumeAutomaticConnectIfEligible(backendAvailable: true, busy: true, connected: false, actionsEnabled: true) {
    fail("background launch connected while busy")
}
if !launchPolicy.backgroundConnectionAllowed {
    fail("busy state discarded background launch permission")
}
if !launchPolicy.consumeAutomaticConnectIfEligible(backendAvailable: true, busy: false, connected: false, actionsEnabled: true) {
    fail("deferred background launch connect was lost")
}
if launchPolicy.backgroundConnectionAllowed {
    fail("background launch permission survived connect consumption")
}

// Busy state defers the same bounded activation request instead of discarding it.
policy.targetActivated()
if policy.consumeAutomaticBackendRestartIfEligible(backendAvailable: false, busy: true, actionsEnabled: true) {
    fail("restarted backend while host was busy")
}
if !policy.consumeAutomaticBackendRestartIfEligible(backendAvailable: false, busy: false, actionsEnabled: true) {
    fail("deferred backend restart was lost")
}
policy.backendBecameAvailable()
if policy.consumeAutomaticConnectIfEligible(backendAvailable: true, busy: true, connected: false, actionsEnabled: true) {
    fail("connected while host was busy")
}
if !policy.consumeAutomaticConnectIfEligible(backendAvailable: true, busy: false, connected: false, actionsEnabled: true) {
    fail("deferred activation connect was lost")
}

// An unexpected backend loss while the target is live becomes one fallback
// restart request after the session-level recovery path is no longer busy.
policy.backendBecameUnavailable()
if policy.consumeAutomaticBackendRestartIfEligible(backendAvailable: false, busy: true, actionsEnabled: true) {
    fail("host raced session-level backend recovery")
}
if !policy.consumeAutomaticBackendRestartIfEligible(backendAvailable: false, busy: false, actionsEnabled: true) {
    fail("backend loss did not preserve fallback recovery intent")
}

// A terminal module state can veto automatic backend churn.
policy.targetActivated()
if policy.consumeAutomaticBackendRestartIfEligible(backendAvailable: false, busy: false, actionsEnabled: false) {
    fail("backend restarted while host actions were terminally disabled")
}

// Explicit debugger detach suppresses reconnect, but does not require killing or
// suppressing the shared backend itself.
policy.backendBecameAvailable()
policy.connectionChanged(connected: true)
policy.userWillToggleConnection(currentlyConnected: true)
policy.targetActivated()
policy.backendBecameAvailable()
if policy.consumeAutomaticConnectIfEligible(backendAvailable: true, busy: false, connected: false, actionsEnabled: true) {
    fail("manual detach was ignored")
}
if !policy.automaticConnectionSuppressed {
    fail("manual detach suppression was not retained")
}

// A foreground snapshot of the same still-running target must be idempotent.
// Trainer activation uses this to repair missed workspace notifications without
// treating every Alt-Tab as a new game lifetime or clearing manual detach.
policy.targetStateChanged(running: true)
policy.connectionChanged(connected: true)
policy.userWillToggleConnection(currentlyConnected: true)
policy.targetStateChanged(running: true)
if !policy.automaticConnectionSuppressed {
    fail("same target snapshot cleared manual disconnect suppression")
}
if policy.connectRequested || policy.backendRestartRequested {
    fail("same target snapshot created a duplicate automatic connection request")
}

// A definitive launch notification starts a new target lifetime even when a
// rapid restart prevented the presence monitor from observing an intermediate
// running=false snapshot.
var rapidRestartPolicy = TrainerConnectionPolicy()
rapidRestartPolicy.targetStateChanged(running: true)
rapidRestartPolicy.connectionChanged(connected: true)
rapidRestartPolicy.userWillToggleConnection(currentlyConnected: true)
rapidRestartPolicy.targetLaunched()
if rapidRestartPolicy.automaticConnectionSuppressed {
    fail("true launch inherited manual disconnect suppression from the old process")
}
if !rapidRestartPolicy.backgroundConnectionAllowed || !rapidRestartPolicy.connectRequested {
    fail("true launch did not start a fresh automatic connection lifetime")
}

// Explicit reconnect clears the suppression immediately.
policy.userWillToggleConnection(currentlyConnected: false)
if policy.automaticConnectionSuppressed {
    fail("manual reconnect did not clear suppression")
}

// Target termination while a game request is still busy must preserve one
// deferred refresh. Otherwise a non-runtime reply such as list_profiles can
// finish successfully after the game exits and leave connected=true stale.
var exitWhileBusyPolicy = TrainerConnectionPolicy()
exitWhileBusyPolicy.targetStateChanged(running: true)
exitWhileBusyPolicy.connectionChanged(connected: true)
exitWhileBusyPolicy.targetStateChanged(running: false)
if exitWhileBusyPolicy.consumeTargetExitRefreshIfEligible(
    backendAvailable: true,
    busy: true,
    connected: true
) {
    fail("target-exit refresh ran while backend was busy")
}
if !exitWhileBusyPolicy.consumeTargetExitRefreshIfEligible(
    backendAvailable: true,
    busy: false,
    connected: true
) {
    fail("target-exit refresh intent was lost after busy cleared")
}
if exitWhileBusyPolicy.consumeTargetExitRefreshIfEligible(
    backendAvailable: true,
    busy: false,
    connected: true
) {
    fail("target-exit refresh was not one-shot")
}

// A target exit invalidates the observed connection even if a replacement
// process launches before the old busy request can finish. The new lifetime
// must not erase that invalidation: otherwise a transport-free reply can leave
// connected=true from the dead process and block the pending reconnect.
var exitRelaunchWhileBusyPolicy = TrainerConnectionPolicy()
exitRelaunchWhileBusyPolicy.targetStateChanged(running: true)
exitRelaunchWhileBusyPolicy.connectionChanged(connected: true)
exitRelaunchWhileBusyPolicy.targetStateChanged(running: false)
if exitRelaunchWhileBusyPolicy.consumeTargetExitRefreshIfEligible(
    backendAvailable: true,
    busy: true,
    connected: true
) {
    fail("target-exit refresh ran while the old request was still busy")
}
exitRelaunchWhileBusyPolicy.targetStateChanged(running: true)
exitRelaunchWhileBusyPolicy.targetLaunched()
if !exitRelaunchWhileBusyPolicy.consumeTargetExitRefreshIfEligible(
    backendAvailable: true,
    busy: false,
    connected: true
) {
    fail("replacement launch erased stale-connection refresh intent")
}
exitRelaunchWhileBusyPolicy.connectionChanged(connected: false)
if !exitRelaunchWhileBusyPolicy.consumeAutomaticConnectIfEligible(
    backendAvailable: true,
    busy: false,
    connected: false,
    actionsEnabled: true
) {
    fail("stale-connection refresh consumed the replacement lifetime reconnect")
}

// NSWorkspace launch is itself definitive lifetime evidence. If presence
// coalescing misses the intermediate running=false snapshot, a launch must still
// invalidate connected=true from the previous process before reconnecting.
var missedExitRelaunchPolicy = TrainerConnectionPolicy()
missedExitRelaunchPolicy.targetStateChanged(running: true)
missedExitRelaunchPolicy.connectionChanged(connected: true)
missedExitRelaunchPolicy.targetLaunched()
if missedExitRelaunchPolicy.consumeTargetExitRefreshIfEligible(
    backendAvailable: true,
    busy: true,
    connected: true
) {
    fail("lifetime refresh ran while old work was still busy")
}
if !missedExitRelaunchPolicy.consumeTargetExitRefreshIfEligible(
    backendAvailable: true,
    busy: false,
    connected: true
) {
    fail("definitive launch did not invalidate the prior connected lifetime")
}
missedExitRelaunchPolicy.connectionChanged(connected: false)
if !missedExitRelaunchPolicy.consumeAutomaticConnectIfEligible(
    backendAvailable: true,
    busy: false,
    connected: false,
    actionsEnabled: true
) {
    fail("launch-time lifetime invalidation lost the reconnect request")
}

// A real target restart resets the previous lifetime's detach/recovery state.
policy.userWillToggleConnection(currentlyConnected: true)
policy.targetStateChanged(running: false)
if policy.automaticConnectionSuppressed || policy.connectRequested || policy.backendRestartRequested || policy.targetRunning {
    fail("target termination did not clear lifecycle state")
}
policy.targetStateChanged(running: true)
if !policy.consumeAutomaticConnectIfEligible(backendAvailable: true, busy: false, connected: false, actionsEnabled: true) {
    fail("new target lifetime did not restore automatic connect")
}

print("host_connection_policy_dev8_ok")
'''

with tempfile.TemporaryDirectory(prefix='mgt-dev8-host-policy-') as td:
    td = Path(td)
    main = td / 'main.swift'
    binary = td / 'policy_test'
    main.write_text(textwrap.dedent(harness), encoding='utf-8')
    subprocess.run([
        SWIFTC,
        str(ROOT / 'Sources/Core/Host/TrainerConnectionPolicy.swift'),
        str(main),
        '-o', str(binary),
    ], check=True, cwd=ROOT)
    proc = subprocess.run([str(binary)], cwd=ROOT, text=True, capture_output=True, timeout=10)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    print(proc.stdout.strip())
