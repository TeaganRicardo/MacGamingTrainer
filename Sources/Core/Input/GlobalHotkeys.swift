import Foundation
import AppKit
import Carbon

extension HotkeyChord {
    static func capture(_ event: NSEvent) -> HotkeyChord? {
        let flags = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
        var modifiers: UInt32 = 0
        if flags.contains(.control) { modifiers |= controlModifier }
        if flags.contains(.option) { modifiers |= optionModifier }
        if flags.contains(.shift) { modifiers |= shiftModifier }
        if flags.contains(.command) { modifiers |= commandModifier }
        guard let label = label(for: event), !label.isEmpty else { return nil }
        return HotkeyChord(keyCode: UInt32(event.keyCode), modifiers: modifiers, keyLabel: label)
    }

    private static func label(for event: NSEvent) -> String? {
        let fixed: [UInt16: String] = [
            36:"↩", 48:"⇥", 49:"Space", 51:"⌫", 117:"⌦",
            123:"←", 124:"→", 125:"↓", 126:"↑",
            122:"F1", 120:"F2", 99:"F3", 118:"F4", 96:"F5", 97:"F6",
            98:"F7", 100:"F8", 101:"F9", 109:"F10", 103:"F11", 111:"F12",
        ]
        if let label = fixed[event.keyCode] { return label }
        guard let raw = event.charactersIgnoringModifiers, !raw.isEmpty else { return nil }
        let visible = raw.uppercased().trimmingCharacters(in: .whitespacesAndNewlines)
        return visible.isEmpty ? nil : String(visible.prefix(8))
    }
}

struct HotkeyBinding {
    let actionID: String
    let title: String
    let chord: HotkeyChord
}

final class GlobalHotkeys {
    private var references: [EventHotKeyRef] = []
    private var handler: EventHandlerRef?
    private var eventActions: [UInt32: String] = [:]
    let action: (String) -> Void

    init(action: @escaping (String) -> Void) {
        self.action = action
        var type = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        InstallEventHandler(GetApplicationEventTarget(), { _, event, context -> OSStatus in
            guard let context = context, let event = event else { return OSStatus(eventNotHandledErr) }
            var id = EventHotKeyID()
            let result = GetEventParameter(
                event, EventParamName(kEventParamDirectObject), EventParamType(typeEventHotKeyID),
                nil, MemoryLayout<EventHotKeyID>.size, nil, &id
            )
            guard result == noErr else { return result }
            let owner = Unmanaged<GlobalHotkeys>.fromOpaque(context).takeUnretainedValue()
            guard let mapped = owner.eventActions[id.id] else { return OSStatus(eventNotHandledErr) }
            let action = owner.action
            DispatchQueue.main.async { action(mapped) }
            return noErr
        }, 1, &type, Unmanaged.passUnretained(self).toOpaque(), &handler)
    }

    func register(_ bindings: [HotkeyBinding]) -> String {
        references.forEach { UnregisterEventHotKey($0) }
        references.removeAll()
        eventActions.removeAll()
        var failures: [String] = []
        for (index, binding) in bindings.enumerated() {
            var reference: EventHotKeyRef?
            let eventID = UInt32(index + 1)
            let result = RegisterEventHotKey(
                binding.chord.keyCode,
                binding.chord.modifiers,
                EventHotKeyID(signature: 0x4D475452, id: eventID),
                GetApplicationEventTarget(),
                0,
                &reference
            )
            if result == noErr, let reference {
                references.append(reference)
                eventActions[eventID] = binding.actionID
            } else {
                failures.append("\(binding.chord.displayText) \(binding.title)（\(result)）")
            }
        }
        return failures.isEmpty ? "" : "快捷键注册失败，可能已被系统或其他应用占用：" + failures.joined(separator: "、")
    }

    deinit {
        references.forEach { UnregisterEventHotKey($0) }
        if let handler { RemoveEventHandler(handler) }
    }
}
