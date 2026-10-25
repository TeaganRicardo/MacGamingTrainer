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
print("global_hotkey_routing_ok")
'''

with tempfile.TemporaryDirectory(prefix="mgt-hotkey-routing-") as directory:
    main = Path(directory) / "main.swift"
    binary = Path(directory) / "test"
    main.write_text(SOURCE)
    subprocess.run([
        "swiftc", str(ROOT / "Sources/Core/Input/HotkeyChord.swift"),
        str(ROOT / "Sources/Core/Input/GlobalHotkeys.swift"), str(main), "-o", str(binary),
    ], check=True)
    subprocess.run([str(binary)], check=True)
