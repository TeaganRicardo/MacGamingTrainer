enum Hades2RunLogRefreshGate {
    static func shouldConsume(
        pending: Bool,
        connected: Bool,
        backendAvailable: Bool,
        busy: Bool,
        exiting: Bool
    ) -> Bool {
        pending && connected && backendAvailable && !busy && !exiting
    }
}

/// Hades-specific startup barrier over observed game-run-log readiness.
///
/// Host owns the one-shot launch intent; this gate only postpones its LLDB
/// crossing until the game's observed boot/reset cycle has become usable.
struct Hades2LaunchAttachGate {
    private(set) var isPending = false
    private var runtimeReadyObserved = false

    mutating func deferUntilReady(targetJustLaunched: Bool, canObserveLifecycle: Bool) -> Bool {
        if isPending { return true }
        guard targetJustLaunched && canObserveLifecycle else { return false }
        isPending = true
        // Readiness may have arrived before backend recovery delivered the
        // Host's one-shot connect intent. It belongs to the game lifetime.
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
        exiting: Bool
    ) -> Bool {
        guard isPending, runtimeReadyObserved, backendAvailable, !busy, !connected, !exiting else {
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
