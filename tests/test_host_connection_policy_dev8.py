import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path
from swift_test_compiler import SWIFT_CORE_MODULE, SwiftModule, compile_swift_test

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which('swiftc')
if not SWIFTC:
    raise SystemExit('swiftc required for host connection policy test')

harness = r'''
func fail(_ message: String) -> Never {
    fatalError(message)
}

extension TrainerConnectionPolicy {
    mutating func choosesRestart(backendAvailable: Bool, busy: Bool, recoveryAllowed: Bool) -> Bool {
        nextAutomaticAction(foreground: true, backendAvailable: backendAvailable, busy: busy,
            connected: false, actionsEnabled: false, recoveryAllowed: recoveryAllowed,
            requiresTargetRestart: false) == .restartBackend
    }

    mutating func choosesConnect(backendAvailable: Bool, busy: Bool, connected: Bool, actionsEnabled: Bool) -> Bool {
        if case .connect = nextAutomaticAction(foreground: true, backendAvailable: backendAvailable, busy: busy,
            connected: connected, actionsEnabled: actionsEnabled, recoveryAllowed: false,
            requiresTargetRestart: false) { return true }
        return false
    }

    mutating func choosesExitRefresh(backendAvailable: Bool, busy: Bool, connected: Bool) -> Bool {
        nextAutomaticAction(foreground: false, backendAvailable: backendAvailable, busy: busy,
            connected: connected, actionsEnabled: false, recoveryAllowed: true,
            requiresTargetRestart: false) == .refreshAfterTargetExit
    }
}

var policy = TrainerConnectionPolicy()

// No target means no background restart/connect.
policy.backendBecameUnavailable()
policy.backendBecameAvailable()
if policy.choosesRestart(backendAvailable: false, busy: false, recoveryAllowed: true) {
    fail("restarted backend without a running target")
}
if policy.choosesConnect(backendAvailable: true, busy: false, connected: false, actionsEnabled: true) {
    fail("connected without a running target")
}

// A target launch can recover a missing backend first, then connect exactly once
// when that backend becomes available.
policy.targetStateChanged(running: true)
if !policy.choosesRestart(backendAvailable: false, busy: false, recoveryAllowed: true) {
    fail("launch did not request missing backend recovery")
}
if policy.choosesRestart(backendAvailable: false, busy: false, recoveryAllowed: true) {
    fail("backend restart request was not one-shot")
}
policy.backendBecameAvailable()
if !policy.choosesConnect(backendAvailable: true, busy: false, connected: false, actionsEnabled: true) {
    fail("recovered backend did not lead to automatic connect")
}
if policy.choosesConnect(backendAvailable: true, busy: false, connected: false, actionsEnabled: true) {
    fail("launch connect was not one-shot")
}

// A launch notification publishes running and launchGeneration together.
// Host may observe running first; a single generation-aware observation must
// preserve the launch grant before it consumes the pending connect intent.
var coalescedLaunch = TrainerConnectionPolicy()
coalescedLaunch.observeTarget(running: true, launchGeneration: 0)
if coalescedLaunch.backgroundConnectionAllowed {
    fail("foreground discovery was misidentified as a true launch")
}
coalescedLaunch.observeTarget(running: true, launchGeneration: 1)
if !coalescedLaunch.backgroundConnectionAllowed {
    fail("launch generation was not staged before presence-based auto-connect")
}
if !coalescedLaunch.choosesConnect(
    backendAvailable: true, busy: false, connected: false, actionsEnabled: true
) {
    fail("staged launch did not preserve its single connect opportunity")
}
coalescedLaunch.observeTarget(running: true, launchGeneration: 1)
if coalescedLaunch.backgroundConnectionAllowed || coalescedLaunch.connectRequested {
    fail("duplicate launch observation granted another attach")
}

// Activation and foreground refresh prove game presence for Save safety
// but cannot issue an automatic debugger attach before definitive launch.
var earlyActivation = TrainerConnectionPolicy()
earlyActivation.observeTarget(
    running: true, launchGeneration: 0, allowDiscoveryConnect: false
)
if !earlyActivation.targetRunning {
    fail("activation did not preserve running-state evidence for Save safety")
}
if earlyActivation.choosesRestart(
    backendAvailable: false, busy: false, recoveryAllowed: true
) {
    fail("unconfirmed launch restarted backend before definitive launch")
}
earlyActivation.targetActivated()
earlyActivation.backendBecameAvailable()
if earlyActivation.choosesConnect(
    backendAvailable: true, busy: false, connected: false, actionsEnabled: true
) {
    fail("activation/discovery attached LLDB before definitive launch")
}
earlyActivation.observeTarget(
    running: true, launchGeneration: 1, allowDiscoveryConnect: false
)
if !earlyActivation.choosesConnect(
    backendAvailable: true, busy: false, connected: false, actionsEnabled: true
) {
    fail("definitive launch failed to release automatic connection")
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
if launchPolicy.choosesConnect(backendAvailable: true, busy: true, connected: false, actionsEnabled: true) {
    fail("background launch connected while busy")
}
if !launchPolicy.backgroundConnectionAllowed {
    fail("busy state discarded background launch permission")
}
if !launchPolicy.choosesConnect(backendAvailable: true, busy: false, connected: false, actionsEnabled: true) {
    fail("deferred background launch connect was lost")
}
if launchPolicy.backgroundConnectionAllowed {
    fail("background launch permission survived connect consumption")
}

// Busy state defers the same bounded activation request instead of discarding it.
policy.backendBecameReady()
policy.targetActivated()
if policy.choosesRestart(backendAvailable: false, busy: true, recoveryAllowed: true) {
    fail("restarted backend while host was busy")
}
if !policy.choosesRestart(backendAvailable: false, busy: false, recoveryAllowed: true) {
    fail("deferred backend restart was lost")
}
policy.backendBecameAvailable()
if policy.choosesConnect(backendAvailable: true, busy: true, connected: false, actionsEnabled: true) {
    fail("connected while host was busy")
}
if !policy.choosesConnect(backendAvailable: true, busy: false, connected: false, actionsEnabled: true) {
    fail("deferred activation connect was lost")
}

// An unexpected backend loss while the target is live becomes one fallback
// restart request after the session-level recovery path is no longer busy.
policy.backendBecameReady()
policy.backendBecameUnavailable()
if policy.choosesRestart(backendAvailable: false, busy: true, recoveryAllowed: true) {
    fail("host raced session-level backend recovery")
}
if !policy.choosesRestart(backendAvailable: false, busy: false, recoveryAllowed: true) {
    fail("backend loss did not preserve fallback recovery intent")
}

// Spawning and losing another worker does not create a new failure episode.
// Activation can request connection, but cannot replenish a spent restart.
for _ in 0..<4 {
    policy.backendBecameAvailable()
    policy.backendBecameUnavailable()
    policy.targetActivated()
    if policy.choosesRestart(backendAvailable: false, busy: false, recoveryAllowed: true) {
        fail("unverified worker spawn or target activation rearmed recovery")
    }
}
policy.backendBecameReady()
if !policy.choosesRestart(backendAvailable: false, busy: false, recoveryAllowed: true) {
    fail("verified readiness did not start a fresh recovery episode")
}
policy.backendBecameUnavailable()
policy.userWillConnect()
if !policy.choosesRestart(backendAvailable: false, busy: false, recoveryAllowed: true) {
    fail("explicit connect did not replenish recovery")
}
policy.userWillRestartBackend()
policy.backendBecameUnavailable()
if !policy.choosesRestart(backendAvailable: false, busy: false, recoveryAllowed: true) {
    fail("explicit restart did not replenish recovery")
}
policy.targetLaunched()
if !policy.choosesRestart(backendAvailable: false, busy: false, recoveryAllowed: true) {
    fail("new target lifetime did not replenish recovery")
}

// Host-owned recovery eligibility (quit, incompatible protocol, no restartable
// session) vetoes automatic backend churn.
policy.targetActivated()
if policy.choosesRestart(backendAvailable: false, busy: false, recoveryAllowed: false) {
    fail("backend restarted while Host recovery was not allowed")
}

// Explicit debugger detach suppresses reconnect, but does not require killing or
// suppressing the shared backend itself.
policy.backendBecameAvailable()
policy.connectionChanged(connected: true)
policy.userWillDisconnect()
policy.targetActivated()
policy.backendBecameAvailable()
if policy.choosesConnect(backendAvailable: true, busy: false, connected: false, actionsEnabled: true) {
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
policy.userWillDisconnect()
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
rapidRestartPolicy.userWillDisconnect()
rapidRestartPolicy.targetLaunched()
if rapidRestartPolicy.automaticConnectionSuppressed {
    fail("true launch inherited manual disconnect suppression from the old process")
}
if !rapidRestartPolicy.backgroundConnectionAllowed || !rapidRestartPolicy.connectRequested {
    fail("true launch did not start a fresh automatic connection lifetime")
}

// Explicit reconnect clears the suppression immediately.
policy.userWillConnect()
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
if exitWhileBusyPolicy.choosesExitRefresh(
    backendAvailable: true,
    busy: true,
    connected: true
) {
    fail("target-exit refresh ran while backend was busy")
}
if !exitWhileBusyPolicy.choosesExitRefresh(
    backendAvailable: true,
    busy: false,
    connected: true
) {
    fail("target-exit refresh intent was lost after busy cleared")
}
if exitWhileBusyPolicy.choosesExitRefresh(
    backendAvailable: true,
    busy: false,
    connected: true
) {
    fail("target-exit refresh was not one-shot")
}

// A connect still in flight may publish the exited target after this event.
var exitDuringConnect = TrainerConnectionPolicy()
exitDuringConnect.targetStateChanged(running: true)
exitDuringConnect.targetStateChanged(running: false)
if exitDuringConnect.choosesExitRefresh(backendAvailable: true, busy: true, connected: false) {
    fail("target-exit refresh ran while connect remained busy")
}
exitDuringConnect.connectionChanged(connected: true)
if !exitDuringConnect.choosesExitRefresh(backendAvailable: true, busy: false, connected: true) {
    fail("in-flight connect discarded the target-exit refresh")
}

// A target exit invalidates the observed connection even if a replacement
// process launches before the old busy request can finish. The new lifetime
// must not erase that invalidation: otherwise a transport-free reply can leave
// connected=true from the dead process and block the pending reconnect.
var exitRelaunchWhileBusyPolicy = TrainerConnectionPolicy()
exitRelaunchWhileBusyPolicy.targetStateChanged(running: true)
exitRelaunchWhileBusyPolicy.connectionChanged(connected: true)
exitRelaunchWhileBusyPolicy.targetStateChanged(running: false)
if exitRelaunchWhileBusyPolicy.choosesExitRefresh(
    backendAvailable: true,
    busy: true,
    connected: true
) {
    fail("target-exit refresh ran while the old request was still busy")
}
exitRelaunchWhileBusyPolicy.targetStateChanged(running: true)
exitRelaunchWhileBusyPolicy.targetLaunched()
if !exitRelaunchWhileBusyPolicy.choosesExitRefresh(
    backendAvailable: true,
    busy: false,
    connected: true
) {
    fail("replacement launch erased stale-connection refresh intent")
}
exitRelaunchWhileBusyPolicy.connectionChanged(connected: false)
if !exitRelaunchWhileBusyPolicy.choosesConnect(
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
if missedExitRelaunchPolicy.choosesExitRefresh(
    backendAvailable: true,
    busy: true,
    connected: true
) {
    fail("lifetime refresh ran while old work was still busy")
}
if !missedExitRelaunchPolicy.choosesExitRefresh(
    backendAvailable: true,
    busy: false,
    connected: true
) {
    fail("definitive launch did not invalidate the prior connected lifetime")
}
missedExitRelaunchPolicy.connectionChanged(connected: false)
if !missedExitRelaunchPolicy.choosesConnect(
    backendAvailable: true,
    busy: false,
    connected: false,
    actionsEnabled: true
) {
    fail("launch-time lifetime invalidation lost the reconnect request")
}

// A refresh can discover a different target PID after a missed OS launch
// notification. Host first invalidates the old presence, then publishes the
// replacement as discovery (not a definitive launch). Stale connection state
// must be refreshed, but no background debugger attachment is authorized.
var silentReplacement = TrainerConnectionPolicy()
silentReplacement.observeTarget(running: true, launchGeneration: 0, allowDiscoveryConnect: false)
silentReplacement.connectionChanged(connected: true)
silentReplacement.targetStateChanged(running: false, allowAutomaticConnect: false)
silentReplacement.observeTarget(running: true, launchGeneration: 0, allowDiscoveryConnect: false)
if !silentReplacement.choosesExitRefresh(
    backendAvailable: true, busy: false, connected: true
) {
    fail("PID replacement without launch did not invalidate the old connection")
}
if silentReplacement.backgroundConnectionAllowed || silentReplacement.choosesConnect(
    backendAvailable: true, busy: false, connected: false, actionsEnabled: true
) {
    fail("PID discovery was misidentified as a background attach grant")
}

// A real target restart resets the previous lifetime's detach/recovery state.
policy.userWillDisconnect()
policy.targetStateChanged(running: false)
if policy.automaticConnectionSuppressed || policy.connectRequested || policy.backendRestartRequested || policy.targetRunning {
    fail("target termination did not clear lifecycle state")
}
policy.targetStateChanged(running: true)
if !policy.choosesConnect(backendAvailable: true, busy: false, connected: false, actionsEnabled: true) {
    fail("new target lifetime did not restore automatic connect")
}

// The Host executes exactly one next action. A replacement can invalidate
// local observations before the backend refresh that owns the old attachment.
var ordered = TrainerConnectionPolicy()
ordered.observeTarget(running: true, launchGeneration: 0)
ordered.connectionChanged(connected: true)
ordered.observeTarget(running: true, launchGeneration: 1, allowDiscoveryConnect: false)
ordered.retainTargetExitRefresh()
ordered.connectionChanged(connected: false)
if ordered.nextAutomaticAction(foreground: false, backendAvailable: true, busy: true,
    connected: false, actionsEnabled: true, recoveryAllowed: true, requiresTargetRestart: false) != .none {
    fail("old in-flight work did not delay the next action")
}
if ordered.nextAutomaticAction(foreground: false, backendAvailable: true, busy: false,
    connected: false, actionsEnabled: true, recoveryAllowed: true, requiresTargetRestart: true) != .none {
    fail("unknown outcome admitted an automatic action")
}
if ordered.nextAutomaticAction(foreground: false, backendAvailable: true, busy: false,
    connected: false, actionsEnabled: true, recoveryAllowed: true, requiresTargetRestart: false) != .refreshAfterTargetExit {
    fail("rapid replacement connected before the old attachment was refreshed")
}
ordered.backendBecameUnavailable()
if ordered.nextAutomaticAction(foreground: false, backendAvailable: false, busy: false,
    connected: false, actionsEnabled: false, recoveryAllowed: true, requiresTargetRestart: false) != .restartBackend {
    fail("pending launch did not restore the backend before connection")
}
ordered.backendBecameAvailable()
if ordered.nextAutomaticAction(foreground: false, backendAvailable: true, busy: false,
    connected: false, actionsEnabled: true, recoveryAllowed: true, requiresTargetRestart: false) != .connect(targetJustLaunched: true) {
    fail("the next action lost the single launch-time connection reason")
}
if ordered.nextAutomaticAction(foreground: true, backendAvailable: true, busy: false,
    connected: false, actionsEnabled: true, recoveryAllowed: true, requiresTargetRestart: false) != .none {
    fail("automatic connection repeated without another eligible event")
}

print("host_connection_policy_dev8_ok")
'''

with tempfile.TemporaryDirectory(prefix='mgt-dev8-host-policy-') as td:
    td = Path(td)
    main = td / 'main.swift'
    binary = td / 'policy_test'
    main.write_text(textwrap.dedent(harness), encoding='utf-8')
    # Portable: the Linux lane has no SwiftUI/AppKit, so this compiles only this
    # Foundation-level file.
    compile_swift_test(
        modules=[SwiftModule(SWIFT_CORE_MODULE, [ROOT / 'Sources/Core/Host/TrainerConnectionPolicy.swift'])],
        harness_sources=[main], output=binary, flags=(), swiftc=SWIFTC, cwd=ROOT,
    )
    proc = subprocess.run([str(binary)], cwd=ROOT, text=True, capture_output=True, timeout=10)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    print(proc.stdout.strip())
