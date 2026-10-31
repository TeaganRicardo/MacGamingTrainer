import AppKit
import Combine

/// The module validates and persists a shortcut; Core owns capture feedback.
enum TrainerShortcutAssignmentResult: Equatable {
    case applied
    case conflict(actionID: String)
    case rejected(messageKey: String)
}

enum TrainerShortcutCaptureIssue: Equatable {
    case unrecognized
    case conflict(chordText: String, actionID: String)
    case rejected(messageKey: String)
}

/// One key monitor per open capture. Injection keeps native key/monitor behavior
/// testable without installing a global event tap or changing user preferences.
final class TrainerShortcutCaptureController: ObservableObject {
    typealias MonitorInstaller = (@escaping (NSEvent) -> NSEvent?) -> Any?

    @Published private(set) var capturingActionID: String?
    @Published private(set) var issue: TrainerShortcutCaptureIssue?

    private let installMonitor: MonitorInstaller
    private let removeMonitor: (Any) -> Void
    private var monitor: Any?
    private var registrationToken: UUID?
    private var onAssign: ((String, HotkeyChord) -> TrainerShortcutAssignmentResult)?
    private var generation = 0
    private var pending = false

    init(
        installMonitor: @escaping MonitorInstaller = {
            NSEvent.addLocalMonitorForEvents(matching: .keyDown, handler: $0)
        },
        removeMonitor: @escaping (Any) -> Void = { NSEvent.removeMonitor($0) }
    ) {
        self.installMonitor = installMonitor
        self.removeMonitor = removeMonitor
    }

    func begin(
        actionID: String,
        onAssign: @escaping (String, HotkeyChord) -> TrainerShortcutAssignmentResult
    ) {
        cancel()
        issue = nil
        capturingActionID = actionID
        self.onAssign = onAssign
        registrationToken = GlobalHotkeys.beginShortcutCapture()
        monitor = installMonitor { [weak self] event in
            self?.handleKeyDown(event) ?? event
        }
        if monitor == nil {
            cancel()
            issue = .rejected(messageKey: "host.hotkeys.captureUnavailable")
        }
    }

    /// Returns nil for consumed events. Late queued assignments must never
    /// commit after Escape, sheet dismissal, page selection or a new capture.
    @discardableResult
    func handleKeyDown(_ event: NSEvent) -> NSEvent? {
        guard let actionID = capturingActionID else { return event }
        guard !pending else { return nil }
        let capturedGeneration = generation

        if event.keyCode == 53 {
            pending = true
            DispatchQueue.main.async { [weak self] in
                guard let self, self.generation == capturedGeneration else { return }
                self.cancel()
            }
            return nil
        }
        guard let chord = HotkeyChord.capture(event) else {
            issue = .unrecognized
            return nil
        }
        pending = true
        DispatchQueue.main.async { [weak self] in
            guard let self, self.generation == capturedGeneration,
                  self.capturingActionID == actionID else { return }
            // Apply while global bindings remain suspended. The module's
            // registration update is deferred until the capture releases them.
            let outcome = self.onAssign?(actionID, chord)
            self.finishCapture()
            switch outcome {
            case .applied:
                self.issue = nil
            case .conflict(let conflictID):
                self.issue = .conflict(chordText: chord.displayText, actionID: conflictID)
            case .rejected(let key):
                self.issue = .rejected(messageKey: key)
            case nil:
                self.issue = .unrecognized
            }
        }
        return nil
    }

    func cancel() {
        finishCapture()
        issue = nil
    }

    private func finishCapture() {
        generation &+= 1
        pending = false
        capturingActionID = nil
        onAssign = nil
        if let monitor {
            self.monitor = nil
            removeMonitor(monitor)
        }
        if let token = registrationToken {
            registrationToken = nil
            GlobalHotkeys.endShortcutCapture(token)
        }
    }

    deinit {
        if let monitor { removeMonitor(monitor) }
        if let registrationToken { GlobalHotkeys.endShortcutCapture(registrationToken) }
    }
}
