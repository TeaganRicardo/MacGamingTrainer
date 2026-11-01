import Foundation

/// A native sheet may retain its controls during dismissal. A captured action
/// belongs to one presentation, even when the same view is opened again.
struct TrainerSheetLifetime {
    private(set) var id = UUID()
    private(set) var isActive = true

    mutating func appear() {
        guard !isActive else { return }
        id = UUID()
        isActive = true
    }

    mutating func invalidate() { isActive = false }

    func accepts(_ id: UUID) -> Bool { isActive && self.id == id }
}
