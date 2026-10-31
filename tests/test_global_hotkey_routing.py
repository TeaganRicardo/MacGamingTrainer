import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = r'''
import AppKit
import Carbon
import Foundation

let app = NSApplication.shared
var received: [String] = []
GlobalHotkeys.selectGame("first")
let first = GlobalHotkeys(gameID: "first") { received.append("first:" + $0) }
let second = GlobalHotkeys(gameID: "second") { received.append("second:" + $0) }
let modifiers = HotkeyChord.controlModifier | HotkeyChord.optionModifier | HotkeyChord.commandModifier
func binding(_ key: UInt32, _ action: String) -> [HotkeyBinding] {
    [HotkeyBinding(actionID: action, chord: HotkeyChord(keyCode: key, modifiers: modifiers, keyLabel: "test"))]
}
precondition(first.register(binding(79, "a")) == nil)
precondition(second.register(binding(79, "b")) == nil)

func deliver(_ value: UInt32) {
    var event: EventRef?
    precondition(CreateEvent(nil, OSType(kEventClassKeyboard), UInt32(kEventHotKeyPressed), 0, 0, &event) == noErr)
    var identity = EventHotKeyID(signature: 0x4D475452, id: value)
    precondition(SetEventParameter(event!, EventParamName(kEventParamDirectObject), EventParamType(typeEventHotKeyID), MemoryLayout<EventHotKeyID>.size, &identity) == noErr)
    _ = SendEventToEventTarget(event!, GetApplicationEventTarget())
    ReleaseEvent(event!)
    RunLoop.main.run(until: Date(timeIntervalSinceNow: 0.03))
}
deliver(1)
deliver(2)
precondition(received == ["first:a"], "Hidden module responded to shortcut: \(received)")
GlobalHotkeys.selectGame("second")
deliver(1)
deliver(2)
precondition(received == ["first:a", "second:b"], "Selection did not transfer shared chord: \(received)")
precondition(second.register(binding(80, "updated")) == nil)
received.removeAll()
deliver(2)
deliver(3)
precondition(received == ["second:updated"])
GlobalHotkeys.selectGame("first")
deliver(3)
deliver(4)
precondition(received == ["second:updated", "first:a"])
let duplicate = GlobalHotkeys(gameID: "first") { _ in preconditionFailure("Conflicting chord must not dispatch") }
guard case .registrationConflicts(let conflicts) = duplicate.register(binding(79, "duplicate")) else {
    preconditionFailure("An active duplicate chord was not reported")
}
precondition(conflicts.count == 1 && conflicts[0].actionID == "duplicate")
GlobalHotkeys.selectGame(nil)
received.removeAll()
deliver(4)
precondition(received.isEmpty)

// The shared capture controller owns one local monitor, suspends global Carbon
// registrations, handles feedback, and cannot commit stale queued assignments.
func testKey(_ code: UInt16, flags: NSEvent.ModifierFlags = [], characters: String = "") -> NSEvent {
    NSEvent.keyEvent(
        with: .keyDown, location: NSPoint.zero, modifierFlags: flags,
        timestamp: 0, windowNumber: 0, context: nil,
        characters: characters, charactersIgnoringModifiers: characters,
        isARepeat: false, keyCode: code
    )!
}
func flushCapture() { RunLoop.main.run(until: Date(timeIntervalSinceNow: 0.03)) }

var monitorHandlers: [Int: (NSEvent) -> NSEvent?] = [:]
var monitorInstalls = 0
var monitorRemovals = 0
let capture = TrainerShortcutCaptureController(
    installMonitor: { handler in
        monitorInstalls += 1
        monitorHandlers[monitorInstalls] = handler
        return monitorInstalls
    },
    removeMonitor: { token in
        guard let identity = token as? Int,
              monitorHandlers.removeValue(forKey: identity) != nil else {
            preconditionFailure("capture removed an unknown or already-removed monitor")
        }
        monitorRemovals += 1
    }
)
var registrationResults: [Bool] = []
GlobalHotkeys.selectGame("capture-fixture")
let captureOwner = GlobalHotkeys(gameID: "capture-fixture", registrationChanged: { failure in
    registrationResults.append(failure == nil)
}) { _ in preconditionFailure("captured key dispatched through registered global shortcut") }
precondition(captureOwner.register(binding(79, "protected")) == nil)
let initialRegistrationCount = registrationResults.count
var committed: [String] = []
let accept: (String, HotkeyChord) -> TrainerShortcutAssignmentResult = { action, chord in
    precondition(GlobalHotkeys.isShortcutCaptureActive,
                 "shortcut callback ran after registrations were restored")
    committed.append(action + ":" + chord.displayText)
    return .applied
}
let digit = testKey(18, flags: [.control, .option], characters: "1")
precondition(capture.handleKeyDown(digit) != nil, "inactive capture swallowed a key")

capture.begin(actionID: "first") { _, _ in .conflict(actionID: "other") }
precondition(GlobalHotkeys.isShortcutCaptureActive)
precondition(monitorHandlers.count == 1)
precondition(registrationResults.count == initialRegistrationCount)
precondition(capture.handleKeyDown(testKey(200)) == nil)
precondition(capture.issue == .unrecognized && capture.capturingActionID == "first")
precondition(monitorHandlers.values.first?(digit) == nil)
flushCapture()
precondition(capture.issue == .conflict(chordText: "⌃⌥1", actionID: "other"))
precondition(capture.capturingActionID == nil && monitorHandlers.isEmpty)
precondition(!GlobalHotkeys.isShortcutCaptureActive)
precondition(registrationResults.count == initialRegistrationCount + 1)

capture.begin(actionID: "second", onAssign: accept)
precondition(monitorHandlers.values.first?(digit) == nil)
flushCapture()
precondition(committed == ["second:⌃⌥1"] && capture.issue == nil)
precondition(!GlobalHotkeys.isShortcutCaptureActive && monitorHandlers.isEmpty)

capture.begin(actionID: "invalid") { _, _ in .rejected(messageKey: "hades.error.shortcutModifier") }
precondition(capture.handleKeyDown(testKey(18, flags: [.shift], characters: "1")) == nil)
flushCapture()
precondition(capture.issue == .rejected(messageKey: "hades.error.shortcutModifier"))
precondition(monitorHandlers.isEmpty)

capture.begin(actionID: "escape", onAssign: accept)
precondition(capture.handleKeyDown(testKey(53)) == nil)
flushCapture()
precondition(capture.capturingActionID == nil && capture.issue == nil)
precondition(committed.count == 1 && monitorHandlers.isEmpty)

// An event captured just before page selection/dismissal is not allowed to
// call a module after the controller is cancelled.
capture.begin(actionID: "stale", onAssign: accept)
precondition(capture.handleKeyDown(digit) == nil)
GlobalHotkeys.selectGame("another-game")
capture.cancel()
flushCapture()
precondition(committed.count == 1 && capture.capturingActionID == nil)
precondition(!GlobalHotkeys.isShortcutCaptureActive && monitorHandlers.isEmpty)
GlobalHotkeys.selectGame("capture-fixture")

capture.begin(actionID: "previous", onAssign: accept)
capture.begin(actionID: "reopened", onAssign: accept)
precondition(monitorHandlers.count == 1 && GlobalHotkeys.isShortcutCaptureActive)
capture.cancel() // sheet dismissal / view disappearance
precondition(monitorHandlers.isEmpty && !GlobalHotkeys.isShortcutCaptureActive)
precondition(monitorInstalls == monitorRemovals)

let unavailable = TrainerShortcutCaptureController(
    installMonitor: { _ in nil },
    removeMonitor: { _ in preconditionFailure("uninstalled monitor removed") }
)
unavailable.begin(actionID: "unavailable", onAssign: accept)
precondition(unavailable.issue == .rejected(messageKey: "host.hotkeys.captureUnavailable"))
precondition(unavailable.capturingActionID == nil && !GlobalHotkeys.isShortcutCaptureActive)
GlobalHotkeys.selectGame(nil)

print("global_hotkey_routing_ok")
'''

with tempfile.TemporaryDirectory(prefix="mgt-hotkey-routing-") as directory:
    main = Path(directory) / "main.swift"
    binary = Path(directory) / "test"
    main.write_text(SOURCE)
    subprocess.run([
        "swiftc", str(ROOT / "Sources/Core/Input/HotkeyChord.swift"),
        str(ROOT / "Sources/Core/Input/GlobalHotkeys.swift"),
        str(ROOT / "Sources/Core/Input/TrainerShortcutCapture.swift"),
        str(main), "-o", str(binary),
    ], check=True)
    subprocess.run([str(binary)], check=True)
