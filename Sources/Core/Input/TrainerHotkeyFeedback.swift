import AppKit

/// Game-agnostic result of a global-hotkey toggle after the target module has
/// processed the request. Modules decide whether an enabled request is already
/// active or still deferred; Core only owns the shared feedback vocabulary.
enum TrainerHotkeyFeedback {
    case enabled
    case deferred
    case disabled

    static func toggle(targetEnabled: Bool, active: Bool) -> TrainerHotkeyFeedback {
        guard targetEnabled else { return .disabled }
        return active ? .enabled : .deferred
    }

    fileprivate var systemSoundName: NSSound.Name {
        switch self {
        case .enabled: return NSSound.Name("Glass")
        case .deferred: return NSSound.Name("Pop")
        case .disabled: return NSSound.Name("Tink")
        }
    }
}

enum TrainerHotkeyFeedbackPlayer {
    static func play(_ feedback: TrainerHotkeyFeedback) {
        if let sound = NSSound(named: feedback.systemSoundName) {
            sound.play()
        } else {
            NSSound.beep()
        }
    }
}
