import Foundation
import Carbon

struct HotkeyBinding {
    let actionID: String
    let title: String
    let digit: Int
}

/// Generic Control+Option digit hotkey registrar. The game module decides what
/// each action ID means and which actions exist.
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
            let result = GetEventParameter(event, EventParamName(kEventParamDirectObject), EventParamType(typeEventHotKeyID), nil, MemoryLayout<EventHotKeyID>.size, nil, &id)
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

        let keycodes: [Int: UInt32] = [0:29, 1:18, 2:19, 3:20, 4:21, 5:23, 6:22, 7:26, 8:28, 9:25]
        var failures: [String] = []
        for (index, binding) in bindings.enumerated() {
            guard let keycode = keycodes[binding.digit] else {
                failures.append("\(binding.title)（无效按键）")
                continue
            }
            var reference: EventHotKeyRef?
            let eventID = UInt32(index + 1)
            let result = RegisterEventHotKey(keycode, UInt32(controlKey | optionKey), EventHotKeyID(signature: 0x4D475452, id: eventID), GetApplicationEventTarget(), 0, &reference)
            if result == noErr, let reference = reference {
                references.append(reference)
                eventActions[eventID] = binding.actionID
            } else {
                failures.append("⌃⌥\(binding.digit)（\(result)）")
            }
        }
        return failures.isEmpty ? "" : "快捷键注册失败，可能已被占用：" + failures.joined(separator: "、")
    }

    deinit {
        references.forEach { UnregisterEventHotKey($0) }
        if let handler = handler { RemoveEventHandler(handler) }
    }
}
