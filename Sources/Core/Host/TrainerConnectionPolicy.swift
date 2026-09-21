/// Shared host-level automatic runtime/connection policy.
///
/// The policy is deliberately pure state: target-process events, backend
/// lifecycle and user intent are translated into one-shot backend-restart and
/// game-connect requests, while the SwiftUI host decides when to invoke the
/// active game module. Keeping this separate from a game model prevents each
/// integration from inventing its own polling/reconnect semantics and makes
/// manual detach and backend recovery behaviour independently testable.
struct TrainerConnectionPolicy {
    private(set) var targetRunning = false
    private(set) var connectRequested = false
    private(set) var backendRestartRequested = false
    private(set) var automaticConnectionSuppressed = false
    private(set) var backgroundConnectionAllowed = false
    private(set) var targetExitRefreshRequested = false

    mutating func targetStateChanged(running: Bool) {
        guard targetRunning != running else { return }
        targetRunning = running
        if running {
            // A real target-process lifetime resets an explicit detach from the
            // previous run and supplies one background recovery/connect chance.
            // A prior observed exit still invalidates the old connection until
            // that stale observation is refreshed, even if a replacement target
            // has already launched.
            automaticConnectionSuppressed = false
            backendRestartRequested = true
            connectRequested = true
        } else {
            targetExitRefreshRequested = true
            backendRestartRequested = false
            connectRequested = false
            automaticConnectionSuppressed = false
            backgroundConnectionAllowed = false
        }
    }

    mutating func targetLaunched() {
        targetRunning = true
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
        guard targetRunning else { return }
        // Activation is a bounded second opportunity when launch-time startup
        // or attach happened before the game had reached a usable state.
        backendRestartRequested = true
        connectRequested = true
    }

    mutating func backendBecameAvailable() {
        backendRestartRequested = false
        guard targetRunning else { return }
        // A recovered/restarted backend gets one chance to restore the debugger
        // connection, unless the user explicitly detached this target lifetime.
        connectRequested = true
    }

    mutating func backendBecameUnavailable() {
        guard targetRunning else { return }
        // TrainerBackendSession owns its own bounded immediate recovery. This
        // pending host request is preserved while it is busy and becomes one
        // final event-driven restart opportunity only if that recovery exhausts.
        backendRestartRequested = true
    }

    mutating func userWillToggleConnection(currentlyConnected: Bool) {
        if currentlyConnected {
            automaticConnectionSuppressed = true
            backgroundConnectionAllowed = false
            connectRequested = false
        } else {
            // An explicit reconnect is user intent, so future lifecycle events
            // may also reconnect if this immediate attempt does not succeed.
            automaticConnectionSuppressed = false
            backgroundConnectionAllowed = false
        }
    }

    mutating func connectionChanged(connected: Bool) {
        guard connected else {
            if !targetRunning { targetExitRefreshRequested = false }
            return
        }
        connectRequested = false
        automaticConnectionSuppressed = false
        backgroundConnectionAllowed = false
    }

    /// A target exit can arrive while a module request is still in flight.
    /// Preserve one refresh until the shared backend is idle so stale connected
    /// state cannot survive a non-runtime reply that completes after the exit.
    /// The invalidation survives a replacement launch: process presence does not
    /// make the old connection observation valid again.
    mutating func consumeTargetExitRefreshIfEligible(
        backendAvailable: Bool,
        busy: Bool,
        connected: Bool
    ) -> Bool {
        guard targetExitRefreshRequested else { return false }
        guard connected else {
            targetExitRefreshRequested = false
            return false
        }
        guard backendAvailable, !busy else { return false }
        targetExitRefreshRequested = false
        return true
    }

    /// Consumes one pending backend-restart intent only when the target is still
    /// relevant and the Host is idle. `actionsEnabled` lets a module veto
    /// recovery for terminal states such as an incompatible protocol.
    mutating func consumeAutomaticBackendRestartIfEligible(
        backendAvailable: Bool,
        busy: Bool,
        actionsEnabled: Bool
    ) -> Bool {
        if backendAvailable {
            backendRestartRequested = false
            return false
        }
        guard backendRestartRequested,
              targetRunning,
              !busy,
              actionsEnabled else { return false }
        backendRestartRequested = false
        return true
    }

    /// Consumes one pending automatic-connect intent only when the global Host
    /// can safely issue it. Busy/unavailable states preserve the intent so the
    /// corresponding state transition can complete the same bounded attempt.
    mutating func consumeAutomaticConnectIfEligible(
        backendAvailable: Bool,
        busy: Bool,
        connected: Bool,
        actionsEnabled: Bool
    ) -> Bool {
        guard connectRequested,
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
