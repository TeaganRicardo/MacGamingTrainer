import SwiftUI

/// Motion belongs to the interaction that changes presentation. Callers choose
/// a role at that boundary; live observations and backend work never inherit a
/// blanket animation. Native controls keep their own press/focus behavior.
enum TrainerMotion {
    enum Role {
        case directManipulation
        case selection
        case disclosure
        case transientFeedback
    }

    static func animation(_ role: Role, reduceMotion: Bool) -> Animation? {
        guard !reduceMotion else { return nil }
        switch role {
        case .directManipulation:
            return nil
        case .selection:
            // A short, zero-bounce spring can retarget without a timing-curve
            // restart when someone reverses a selection rapidly.
            return .smooth(duration: 0.18)
        case .disclosure:
            return .smooth(duration: 0.24)
        case .transientFeedback:
            // This role is for opacity, not moving a notice through content.
            return .easeOut(duration: 0.16)
        }
    }

    static func transaction(_ role: Role, reduceMotion: Bool) -> Transaction {
        var transaction = Transaction(animation: animation(role, reduceMotion: reduceMotion))
        transaction.disablesAnimations = transaction.animation == nil
        return transaction
    }

    /// Leave native motion authoritative normally, including native keyboard
    /// focus and pressed feedback. Reduced motion also blocks any enclosing
    /// layout animation from reaching a native control's state update.
    static func nativeControlTransaction(_ transaction: inout Transaction, reduceMotion: Bool) {
        guard reduceMotion else { return }
        transaction.animation = nil
        transaction.disablesAnimations = true
    }
}
