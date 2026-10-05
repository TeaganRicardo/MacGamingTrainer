import Foundation

/// View-local timing for one latest notice. This never changes the operation,
/// error or recovery state that produced the notice.
struct TrainerFeedbackTiming {
    static let readableDuration: TimeInterval = 4
    static let fadeDuration: TimeInterval = 0.25

    private(set) var currentID: UUID?
    private(set) var isFading = false
    private var shownAt: TimeInterval = 0

    /// Returns true only for a new event, which may be announced once.
    mutating func show(_ id: UUID, at time: TimeInterval) -> Bool {
        guard currentID != id else { return false }
        currentID = id
        shownAt = time
        isFading = false
        return true
    }

    mutating func advance(_ id: UUID, at time: TimeInterval) {
        guard currentID == id else { return }
        if time >= shownAt + Self.readableDuration + Self.fadeDuration {
            clear()
        } else if time >= shownAt + Self.readableDuration {
            isFading = true
        }
    }

    mutating func clear() {
        currentID = nil
        isFading = false
    }
}
