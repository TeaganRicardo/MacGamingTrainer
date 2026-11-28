enum HadesRunLogRefreshGate {
    static func shouldConsume(
        pending: Bool,
        connected: Bool,
        backendAvailable: Bool,
        busy: Bool,
        exiting: Bool,
        requiresTargetRestart: Bool
    ) -> Bool {
        pending && connected && backendAvailable && !busy && !exiting && !requiresTargetRestart
    }
}

/// Hades-specific startup barrier over observed game-run-log readiness.
///
/// Host owns the one-shot launch intent; this gate only postpones its LLDB
/// crossing until the game's observed boot/reset cycle has become usable.
struct HadesLaunchAttachGate {
    private(set) var isPending = false
    private var runtimeReadyObserved = false

    mutating func deferUntilReady(targetJustLaunched: Bool, canObserveLifecycle: Bool) -> Bool {
        if isPending { return true }
        guard targetJustLaunched && canObserveLifecycle else { return false }
        isPending = true
        return true
    }

    mutating func observeRuntimeReady() {
        runtimeReadyObserved = true
    }

    mutating func observeRuntimeReset() {
        runtimeReadyObserved = false
    }

    mutating func targetLifetimeChanged() {
        cancel()
    }

    mutating func consumeIfEligible(
        backendAvailable: Bool,
        busy: Bool,
        connected: Bool,
        exiting: Bool,
        requiresTargetRestart: Bool
    ) -> Bool {
        guard isPending, runtimeReadyObserved, backendAvailable, !busy, !connected, !exiting,
              !requiresTargetRestart else {
            return false
        }
        cancel()
        return true
    }

    mutating func cancel() {
        isPending = false
        runtimeReadyObserved = false
    }
}
