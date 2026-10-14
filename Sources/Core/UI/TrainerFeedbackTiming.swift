import Foundation

/// View-local timing for one latest notice. This never changes the operation,
/// error or recovery state that produced the notice.
struct TrainerFeedbackTiming {
    static let ordinaryDuration: TimeInterval = 6
    static let errorDuration: TimeInterval = 8
    static let fadeDuration: TimeInterval = 0.25

    private(set) var currentID: UUID?
    private(set) var isFading = false
    private var shownAt: TimeInterval = 0
    private var readableDuration: TimeInterval = 0
    private var pausedAt: TimeInterval?

    /// Returns true only for a new event, which may be announced once.
    mutating func show(_ id: UUID, duration: TimeInterval, at time: TimeInterval) -> Bool {
        guard currentID != id else { return false }
        currentID = id
        shownAt = time
        readableDuration = duration
        pausedAt = nil
        isFading = false
        return true
    }

    mutating func advance(_ id: UUID, at time: TimeInterval) {
        guard currentID == id, pausedAt == nil else { return }
        if time >= shownAt + readableDuration + Self.fadeDuration {
            clear()
        } else if time >= shownAt + readableDuration {
            isFading = true
        }
    }

    mutating func pause(_ id: UUID, at time: TimeInterval) {
        guard currentID == id, pausedAt == nil else { return }
        pausedAt = time
        isFading = false
    }

    mutating func resume(_ id: UUID, at time: TimeInterval) {
        guard currentID == id, let pausedAt else { return }
        shownAt += time - pausedAt
        self.pausedAt = nil
    }

    func remainingReadableTime(at time: TimeInterval) -> TimeInterval {
        max(0, shownAt + readableDuration - (pausedAt ?? time))
    }

    mutating func clear() {
        currentID = nil
        isFading = false
        pausedAt = nil
    }
}
