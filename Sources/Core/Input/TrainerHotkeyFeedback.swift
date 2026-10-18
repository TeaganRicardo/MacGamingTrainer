import AppKit

/// Game-agnostic result of a global-hotkey toggle after the target module has
/// processed the request. Modules decide whether an enabled request is already
/// active or still deferred; Core only owns the shared feedback vocabulary.
enum TrainerHotkeyFeedback {
    case enabled
    case deferred
    case disabled
    case completed
    case rejected
    case unconfirmed

    fileprivate var systemSoundName: NSSound.Name {
        switch self {
        case .enabled: return NSSound.Name("Glass")
        case .deferred: return NSSound.Name("Pop")
        case .disabled: return NSSound.Name("Tink")
        case .completed: return NSSound.Name("Glass")
        case .rejected: return NSSound.Name("Basso")
        case .unconfirmed: return NSSound.Name("Morse")
        }
    }
}

/// NSSound(named:) returns a shared sound. Replaying it before the previous
/// voice finishes may fail silently. Each feedback owns an independent copy,
/// retained until its actual completion so rapid confirmed actions remain
/// eligible for distinct playback.
private final class TrainerHotkeySoundVoices: NSObject, NSSoundDelegate {
    private var playing: [ObjectIdentifier: NSSound] = [:]

    func play(_ feedback: TrainerHotkeyFeedback) {
        guard let sound = NSSound(named: feedback.systemSoundName)?.copy() as? NSSound else {
            NSSound.beep()
            return
        }
        let key = ObjectIdentifier(sound)
        sound.delegate = self
        playing[key] = sound
        if !sound.play() {
            playing.removeValue(forKey: key)
            NSSound.beep()
        }
    }

    func sound(_ sound: NSSound, didFinishPlaying finishedPlaying: Bool) {
        playing.removeValue(forKey: ObjectIdentifier(sound))
    }
}

enum TrainerHotkeyFeedbackPlayer {
    private static let voices = TrainerHotkeySoundVoices()

    static func play(_ feedback: TrainerHotkeyFeedback) {
        voices.play(feedback)
    }
}
