import Foundation

/// Serializable global-hotkey identity. Modifier bit values intentionally match
/// Carbon's EventModifiers so the data layer stays Foundation-only.
struct HotkeyChord: Equatable {
    static let commandModifier: UInt32 = 1 << 8
    static let shiftModifier: UInt32 = 1 << 9
    static let optionModifier: UInt32 = 1 << 11
    static let controlModifier: UInt32 = 1 << 12
    static let supportedModifierMask = commandModifier | shiftModifier | optionModifier | controlModifier

    let keyCode: UInt32
    let modifiers: UInt32
    let keyLabel: String

    var displayText: String {
        var prefix = ""
        if modifiers & Self.controlModifier != 0 { prefix += "⌃" }
        if modifiers & Self.optionModifier != 0 { prefix += "⌥" }
        if modifiers & Self.shiftModifier != 0 { prefix += "⇧" }
        if modifiers & Self.commandModifier != 0 { prefix += "⌘" }
        return prefix + keyLabel
    }

    var payload: [String: Any] {
        ["keyCode": Int(keyCode), "modifiers": Int(modifiers), "keyLabel": keyLabel]
    }

    init(keyCode: UInt32, modifiers: UInt32, keyLabel: String) {
        self.keyCode = keyCode
        self.modifiers = modifiers
        self.keyLabel = keyLabel
    }

    init?(payload: Any) {
        guard let row = payload as? [String: Any],
              let keyCode = row["keyCode"] as? Int, (0...65535).contains(keyCode),
              let rawModifiers = row["modifiers"] as? Int, rawModifiers >= 0, rawModifiers <= Int(UInt32.max),
              let keyLabel = row["keyLabel"] as? String,
              !keyLabel.isEmpty, keyLabel.count <= 16,
              keyLabel.unicodeScalars.allSatisfy({ $0.value >= 32 }) else { return nil }
        let modifiers = UInt32(rawModifiers)
        guard modifiers & ~Self.supportedModifierMask == 0 else { return nil }
        self.init(keyCode: UInt32(keyCode), modifiers: modifiers, keyLabel: keyLabel)
    }

    private static let defaultKeys: [(keyCode: UInt32, label: String)] = [
        (18, "1"), (19, "2"), (20, "3"), (21, "4"), (23, "5"),
        (22, "6"), (26, "7"), (28, "8"), (25, "9"), (29, "0"),
        // Letters follow the physical keyboard rows (QWERTY order) so the
        // sequence stays predictable for muscle memory, not alphabetised.
        (12, "Q"), (13, "W"), (14, "E"), (15, "R"), (17, "T"), (16, "Y"),
        (32, "U"), (34, "I"), (31, "O"), (35, "P"),
        (0, "A"), (1, "S"), (2, "D"), (3, "F"), (5, "G"), (4, "H"),
        (38, "J"), (40, "K"), (37, "L"),
        (6, "Z"), (7, "X"), (8, "C"), (9, "V"), (11, "B"), (45, "N"), (46, "M"),
    ]

    /// Frozen key sequence used only to recognize the released v4 defaults.
    /// Active allocation uses the numeric-zero key before the letter sequence.
    private static let legacyV4Keys: [(keyCode: UInt32, label: String)] = [
        (18, "1"), (19, "2"), (20, "3"), (21, "4"), (23, "5"),
        (22, "6"), (26, "7"), (28, "8"), (25, "9"),
        (0, "A"), (11, "B"), (8, "C"), (2, "D"), (14, "E"), (3, "F"), (5, "G"),
        (4, "H"), (34, "I"), (38, "J"), (40, "K"), (37, "L"), (46, "M"), (45, "N"),
        (31, "O"), (35, "P"), (12, "Q"), (15, "R"), (1, "S"), (17, "T"), (32, "U"),
        (9, "V"), (13, "W"), (7, "X"), (16, "Y"), (6, "Z"),
    ]

    /// Active allocation uses 1–9, 0, then letters in the first modifier layer.
    /// Later actions automatically use modifier layers rather than requiring
    /// another manually maintained key list.
    private static let defaultModifierLayers: [UInt32] = [
        controlModifier | optionModifier,
        controlModifier | optionModifier | shiftModifier,
        controlModifier | optionModifier | commandModifier,
        controlModifier | optionModifier | shiftModifier | commandModifier,
    ]

    static var defaultShortcutCapacity: Int {
        defaultKeys.count * defaultModifierLayers.count
    }

    /// Historical v4 migration only. Do not use this for active allocation:
    /// it deliberately exposes the released Control+Option key sequence.
    static func controlOptionDefault(index: Int) -> HotkeyChord? {
        guard legacyV4Keys.indices.contains(index) else { return nil }
        let key = legacyV4Keys[index]
        return HotkeyChord(
            keyCode: key.keyCode,
            modifiers: controlModifier | optionModifier,
            keyLabel: key.label
        )
    }

    /// Derived default allocation for the ordered action registry.
    static func defaultShortcut(index: Int) -> HotkeyChord? {
        guard index >= 0, index < defaultShortcutCapacity else { return nil }
        let layer = index / defaultKeys.count
        let key = defaultKeys[index % defaultKeys.count]
        return HotkeyChord(
            keyCode: key.keyCode,
            modifiers: defaultModifierLayers[layer],
            keyLabel: key.label
        )
    }

    static func controlOptionDigit(_ digit: Int) -> HotkeyChord? {
        let keycodes: [Int: UInt32] = [0:29, 1:18, 2:19, 3:20, 4:21, 5:23, 6:22, 7:26, 8:28, 9:25]
        guard let keyCode = keycodes[digit] else { return nil }
        return HotkeyChord(
            keyCode: keyCode,
            modifiers: controlModifier | optionModifier,
            keyLabel: String(digit)
        )
    }
}
