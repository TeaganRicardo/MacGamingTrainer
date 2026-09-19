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
