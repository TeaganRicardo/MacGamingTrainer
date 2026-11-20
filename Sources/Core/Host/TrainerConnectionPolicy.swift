/// Shared host-level automatic runtime/connection policy.
///
/// The policy is deliberately pure state: target-process events, backend
/// lifecycle and user intent are translated into one-shot backend-restart and
/// game-connect requests, while the SwiftUI host decides when to invoke the
/// active game module. Keeping this separate from a game model prevents each
/// integration from inventing its own polling/reconnect semantics and makes
/// manual detach and backend recovery behaviour independently testable.
struct TrainerConnectionPolicy {
    enum AutomaticAction: Equatable {
        case refreshAfterTargetExit
        case restartBackend
        case connect(targetJustLaunched: Bool)
        case none
    }

    private(set) var targetRunning = false
    private(set) var connectRequested = false
    private(set) var backendRestartRequested = false
    private(set) var automaticConnectionSuppressed = false
    private(set) var backgroundConnectionAllowed = false
    private(set) var targetExitRefreshRequested = false
    private var retainedTargetExitRefresh = false
    private var observedLaunchGeneration: UInt = 0
    private var awaitingDefinitiveLaunch = false

    /// Consume an atomic process-presence/launch-generation observation.
    /// Activation or refresh can establish presence for Save safety before
    /// NSWorkspace reports a definitive launch; that interim snapshot must
    /// never authorize automatic debugger work.
    mutating func observeTarget(
        running: Bool, launchGeneration: UInt, allowDiscoveryConnect: Bool = true
    ) {
        let wasRunning = targetRunning
        targetStateChanged(running: running, allowAutomaticConnect: allowDiscoveryConnect)
        if running && !wasRunning && !allowDiscoveryConnect {
            awaitingDefinitiveLaunch = true
        }
        guard observedLaunchGeneration != launchGeneration else { return }
        observedLaunchGeneration = launchGeneration
        if running {
            targetLaunched()
        }
    }


    mutating func targetStateChanged(running: Bool, allowAutomaticConnect: Bool = true) {
        guard targetRunning != running else { return }
        targetRunning = running
        if running {
            // A real target-process lifetime resets an explicit detach from the
            // previous run and supplies one background recovery/connect chance.
            // A prior observed exit still invalidates the old connection until
            // that stale observation is refreshed, even if a replacement target
            // has already launched.
            automaticConnectionSuppressed = false
            if allowAutomaticConnect {
                backendRestartRequested = true
                connectRequested = true
            }
        } else {
            targetExitRefreshRequested = true
            backendRestartRequested = false
            connectRequested = false
            automaticConnectionSuppressed = false
            backgroundConnectionAllowed = false
            awaitingDefinitiveLaunch = false
        }
    }

    mutating func targetLaunched() {
        targetRunning = true
        awaitingDefinitiveLaunch = false
        // A launch is definitive target-lifetime evidence. It also covers the
        // rapid-replacement case where aggregate process presence never exposed
        // an intermediate running=false snapshot.
        targetExitRefreshRequested = true
        automaticConnectionSuppressed = false
        backgroundConnectionAllowed = true
        backendRestartRequested = true
        connectRequested = true
    }

    mutating func targetActivated() {
        guard targetRunning, !awaitingDefinitiveLaunch else { return }
        // Activation is a bounded second opportunity when launch-time startup
        // or attach happened before the game had reached a usable state.
        backendRestartRequested = true
        connectRequested = true
    }

    mutating func backendBecameAvailable() {
        backendRestartRequested = false
        guard targetRunning, !awaitingDefinitiveLaunch else { return }
        // A recovered/restarted backend gets one chance to restore the debugger
        // connection, unless the user explicitly detached this target lifetime.
        connectRequested = true
    }

    mutating func backendBecameUnavailable() {
        retainedTargetExitRefresh = false
        guard targetRunning, !awaitingDefinitiveLaunch else { return }
        // TrainerBackendSession owns its own bounded immediate recovery. This
        // pending host request is preserved while it is busy and becomes one
        // final event-driven restart opportunity only if that recovery exhausts.
        backendRestartRequested = true
    }

    mutating func userWillDisconnect() {
        automaticConnectionSuppressed = true
        backgroundConnectionAllowed = false
        connectRequested = false
    }

    mutating func userWillConnect() {
        // Future lifecycle events may reconnect if this attempt fails.
        automaticConnectionSuppressed = false
        backgroundConnectionAllowed = false
    }

    mutating func connectionChanged(connected: Bool) {
        guard connected else {
            if !targetRunning && !retainedTargetExitRefresh { targetExitRefreshRequested = false }
            return
        }
        connectRequested = false
        automaticConnectionSuppressed = false
        backgroundConnectionAllowed = false
    }

    /// Local state may already be invalidated while the backend still has an
    /// old connection to refresh. Retain the refresh through that reset.
    mutating func retainTargetExitRefresh() {
        if targetExitRefreshRequested { retainedTargetExitRefresh = true }
    }

    mutating func nextAutomaticAction(
        foreground: Bool, backendAvailable: Bool, busy: Bool, connected: Bool,
        actionsEnabled: Bool, recoveryAllowed: Bool, requiresTargetRestart: Bool
    ) -> AutomaticAction {
        guard !requiresTargetRestart else { return .none }
        if consumeTargetExitRefreshIfEligible(backendAvailable: backendAvailable, busy: busy, connected: connected) {
            return .refreshAfterTargetExit
        }
        guard backgroundConnectionAllowed || foreground else { return .none }
        if consumeAutomaticBackendRestartIfEligible(
            backendAvailable: backendAvailable, busy: busy, recoveryAllowed: recoveryAllowed
        ) {
            return .restartBackend
        }
        let targetJustLaunched = backgroundConnectionAllowed
        if consumeAutomaticConnectIfEligible(
            backendAvailable: backendAvailable, busy: busy, connected: connected, actionsEnabled: actionsEnabled
        ) {
            return .connect(targetJustLaunched: targetJustLaunched)
        }
        return .none
    }

    /// A target exit can arrive while a module request is still in flight.
    /// Preserve one refresh until the shared backend is idle so stale connected
    /// state cannot survive a non-runtime reply that completes after the exit.
    /// The invalidation survives a replacement launch: process presence does not
    /// make the old connection observation valid again.
    private mutating func consumeTargetExitRefreshIfEligible(
        backendAvailable: Bool,
        busy: Bool,
        connected: Bool
    ) -> Bool {
        guard targetExitRefreshRequested else { return false }
        // An in-flight connect can still report the exited target as connected.
        guard backendAvailable, !busy else { return false }
        targetExitRefreshRequested = false
        let needsRefresh = connected || retainedTargetExitRefresh
        retainedTargetExitRefresh = false
        return needsRefresh
    }

    /// Consumes one pending backend-restart intent only when the target is still
    /// relevant and the Host is idle. `recoveryAllowed` is the Host-owned restart
    /// eligibility (`TrainerGameContext.backendRestartAllowed`), never a module
    /// request gate: an unavailable backend is exactly when recovery must remain
    /// reachable.
    private mutating func consumeAutomaticBackendRestartIfEligible(
        backendAvailable: Bool,
        busy: Bool,
        recoveryAllowed: Bool
    ) -> Bool {
        if backendAvailable {
            backendRestartRequested = false
            return false
        }
        guard backendRestartRequested,
              targetRunning,
              !awaitingDefinitiveLaunch,
              !busy,
              recoveryAllowed else { return false }
        backendRestartRequested = false
        return true
    }

    /// Consumes one pending automatic-connect intent only when the global Host
    /// can safely issue it. Busy/unavailable states preserve the intent so the
    /// corresponding state transition can complete the same bounded attempt.
    private mutating func consumeAutomaticConnectIfEligible(
        backendAvailable: Bool,
        busy: Bool,
        connected: Bool,
        actionsEnabled: Bool
    ) -> Bool {
        guard connectRequested,
              !awaitingDefinitiveLaunch,
              !automaticConnectionSuppressed,
              targetRunning,
              backendAvailable,
              !busy,
              !connected,
              actionsEnabled else { return false }
        connectRequested = false
        backgroundConnectionAllowed = false
        return true
    }
}
