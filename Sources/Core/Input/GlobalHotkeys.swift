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
    let chord: HotkeyChord
}

struct TrainerHotkeyRegistrationConflict: Equatable {
    let actionID: String
    let chordText: String
    let status: Int32
}

enum TrainerHotkeyRegistrationFailure: Equatable {
    case listenerInitialization(status: Int32)
    case registrationConflicts([TrainerHotkeyRegistrationConflict])
}

private final class TrainerGlobalHotkeyRegistry {
    static let shared = TrainerGlobalHotkeyRegistry()
    private let signature: OSType = 0x4D475452
    private var handler: EventHandlerRef?
    private(set) var handlerInstallStatus: OSStatus = noErr
    private var nextEventID: UInt32 = 0
    private var actions: [UInt32: () -> Void] = [:]
    private var references: [UInt32: EventHotKeyRef] = [:]
    private(set) var selectedGameID: String?
    private var owners: [UUID: WeakOwner] = [:]
    private var activeCaptureTokens: Set<UUID> = []

    var isCapturingShortcut: Bool { !activeCaptureTokens.isEmpty }

    private final class WeakOwner {
        weak var value: GlobalHotkeys?
        init(_ value: GlobalHotkeys) { self.value = value }
    }

    func add(_ owner: GlobalHotkeys, id: UUID) { owners[id] = WeakOwner(owner) }
    func remove(id: UUID) { owners.removeValue(forKey: id) }

    /// Temporarily release Carbon registrations so a captured chord reaches
    /// the local NSEvent monitor. A token protects nested/reopened sheets.
    func beginShortcutCapture() -> UUID {
        let token = UUID()
        if activeCaptureTokens.isEmpty {
            for owner in owners.values.compactMap(\.value) { owner.unregister() }
        }
        activeCaptureTokens.insert(token)
        return token
    }

    func endShortcutCapture(_ token: UUID) {
        guard activeCaptureTokens.remove(token) != nil, activeCaptureTokens.isEmpty else { return }
        for owner in owners.values.compactMap(\.value) { owner.updateRegistration() }
    }

    func selectGame(_ id: String?) {
        guard selectedGameID != id else { return }
        selectedGameID = id
        let current = owners.values.compactMap(\.value)
        for owner in current { owner.unregister() }
        for owner in current { owner.updateRegistration() }
    }

    private init() {
        var type = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        handlerInstallStatus = InstallEventHandler(GetApplicationEventTarget(), { _, event, context -> OSStatus in
            guard let context, let event else { return OSStatus(eventNotHandledErr) }
            var identity = EventHotKeyID()
            let result = GetEventParameter(
                event, EventParamName(kEventParamDirectObject), EventParamType(typeEventHotKeyID),
                nil, MemoryLayout<EventHotKeyID>.size, nil, &identity
            )
            guard result == noErr else { return result }
            let registry = Unmanaged<TrainerGlobalHotkeyRegistry>.fromOpaque(context).takeUnretainedValue()
            guard identity.signature == registry.signature,
                  let action = registry.actions[identity.id] else { return OSStatus(eventNotHandledErr) }
            DispatchQueue.main.async(execute: action)
            return noErr
        }, 1, &type, Unmanaged.passUnretained(self).toOpaque(), &handler)
    }

    func register(_ chord: HotkeyChord, action: @escaping () -> Void) -> (UInt32?, OSStatus) {
        nextEventID += 1
        let id = nextEventID
        var reference: EventHotKeyRef?
        let status = RegisterEventHotKey(
            chord.keyCode, chord.modifiers, EventHotKeyID(signature: signature, id: id),
            GetApplicationEventTarget(), 0, &reference
        )
        guard status == noErr, let reference else { return (nil, status) }
        references[id] = reference
        actions[id] = action
        return (id, noErr)
    }

    func unregister(_ ids: [UInt32]) {
        for id in ids {
            if let reference = references.removeValue(forKey: id) { UnregisterEventHotKey(reference) }
            actions.removeValue(forKey: id)
        }
    }
}

final class GlobalHotkeys {
    private let registry = TrainerGlobalHotkeyRegistry.shared
    private let ownerID = UUID()
    private let gameID: String
    private var registeredIDs: [UInt32] = []
    private var bindings: [HotkeyBinding] = []
    private let registrationChanged: (TrainerHotkeyRegistrationFailure?) -> Void
    let action: (String) -> Void

    static func selectGame(_ id: String?) { TrainerGlobalHotkeyRegistry.shared.selectGame(id) }
    static var isShortcutCaptureActive: Bool { TrainerGlobalHotkeyRegistry.shared.isCapturingShortcut }
    static func beginShortcutCapture() -> UUID { TrainerGlobalHotkeyRegistry.shared.beginShortcutCapture() }
    static func endShortcutCapture(_ token: UUID) { TrainerGlobalHotkeyRegistry.shared.endShortcutCapture(token) }

    init(gameID: String,
         registrationChanged: @escaping (TrainerHotkeyRegistrationFailure?) -> Void = { _ in },
         action: @escaping (String) -> Void) {
        self.gameID = gameID
        self.registrationChanged = registrationChanged
        self.action = action
        registry.add(self, id: ownerID)
    }

    @discardableResult
    func register(_ bindings: [HotkeyBinding]) -> TrainerHotkeyRegistrationFailure? {
        self.bindings = bindings
        return updateRegistration()
    }

    fileprivate func unregister() {
        registry.unregister(registeredIDs)
        registeredIDs.removeAll()
    }

    @discardableResult
    fileprivate func updateRegistration() -> TrainerHotkeyRegistrationFailure? {
        unregister()
        guard registry.selectedGameID == gameID, !registry.isCapturingShortcut else { return nil }
        guard registry.handlerInstallStatus == noErr else {
            let failure = TrainerHotkeyRegistrationFailure.listenerInitialization(status: registry.handlerInstallStatus)
            registrationChanged(failure)
            return failure
        }
        var failures: [TrainerHotkeyRegistrationConflict] = []
        let perform = action
        let scope = gameID
        for binding in bindings {
            let (id, status) = registry.register(binding.chord) { [weak registry] in
                guard registry?.selectedGameID == scope, registry?.isCapturingShortcut == false else { return }
                perform(binding.actionID)
            }
            if let id {
                registeredIDs.append(id)
            } else {
                failures.append(TrainerHotkeyRegistrationConflict(
                    actionID: binding.actionID, chordText: binding.chord.displayText, status: status
                ))
            }
        }
        let failure: TrainerHotkeyRegistrationFailure? = failures.isEmpty ? nil : .registrationConflicts(failures)
        registrationChanged(failure)
        return failure
    }

    deinit {
        registry.unregister(registeredIDs)
        registry.remove(id: ownerID)
    }
}
