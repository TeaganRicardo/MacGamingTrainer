import Foundation

/// Hades-specific shortcut persistence. Registration/capture mechanics live in
/// Core; this store owns action semantics, defaults, local migration and
/// collision handling.
struct Hades2ShortcutStore {
    private(set) var chords: [ShortcutAction: HotkeyChord]
    private let defaults: UserDefaults

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        self.chords = Self.defaultLayout()
        loadAndMigrate()
    }

    static func defaultLayout() -> [ShortcutAction: HotkeyChord] {
        Dictionary(uniqueKeysWithValues: ShortcutAction.uiOrder.enumerated().compactMap { index, action in
            HotkeyChord.controlOptionDefault(index: index).map { (action, $0) }
        })
    }

    func chord(_ action: ShortcutAction) -> HotkeyChord {
        chords[action] ?? Self.defaultLayout()[action]!
    }

    func payload() -> [String: Any] {
        Dictionary(uniqueKeysWithValues: ShortcutAction.uiOrder.map { ($0.rawValue, chord($0).payload) })
    }

    mutating func set(_ action: ShortcutAction, chord newChord: HotkeyChord) -> String? {
        if let other = ShortcutAction.uiOrder.first(where: { $0 != action && chord($0).keyCode == newChord.keyCode && chord($0).modifiers == newChord.modifiers }) {
            return "快捷键 \(newChord.displayText) 已分配给「\(other.title)」。"
        }
        chords[action] = newChord
        defaults.set(newChord.payload, forKey: key(action))
        defaults.set(4, forKey: "shortcut.layoutVersion")
        return nil
    }

    mutating func applyProfile(_ values: [String: Any]) {
        var patch: [ShortcutAction: HotkeyChord] = [:]
        var patchTokens = Set<String>()
        for action in ShortcutAction.uiOrder {
            guard let value = values[action.rawValue], let proposed = HotkeyChord(payload: value) else { continue }
            let token = Self.token(proposed)
            guard !patchTokens.contains(token) else { continue }
            patch[action] = proposed
            patchTokens.insert(token)
        }
        guard !patch.isEmpty else { return }

        var next = chords
        for (action, proposed) in patch { next[action] = proposed }

        // Apply imported assignments as one layout. Non-imported actions that
        // collide with an imported chord are moved to a free default slot.
        // This allows valid Profile swaps without comparing each assignment
        // against the stale pre-import layout.
        var used = patchTokens
        let defaultsLayout = Self.defaultLayout()
        for action in ShortcutAction.uiOrder where patch[action] == nil {
            var current = next[action] ?? defaultsLayout[action]!
            if used.contains(Self.token(current)) {
                if let preferred = defaultsLayout[action], !used.contains(Self.token(preferred)) {
                    current = preferred
                } else if let free = ShortcutAction.uiOrder.enumerated()
                    .compactMap({ HotkeyChord.controlOptionDefault(index: $0.offset) })
                    .first(where: { !used.contains(Self.token($0)) }) {
                    current = free
                }
            }
            next[action] = current
            used.insert(Self.token(current))
        }
        chords = next
        persistCurrentLayout()
    }

    private mutating func loadAndMigrate() {
        let layoutVersion = defaults.integer(forKey: "shortcut.layoutVersion")
        if layoutVersion >= 4 {
            for action in ShortcutAction.uiOrder {
                if let value = defaults.object(forKey: key(action)), let parsed = HotkeyChord(payload: value) {
                    chords[action] = parsed
                }
            }
            repairCollisions()
            return
        }

        // Layout v3 stored Control+Option digits only. This is local UserDefaults
        // migration, not Profile compatibility: current Profile schema stores
        // full chord objects.
        if layoutVersion == 3 {
            for action in ShortcutAction.legacyDigitActions {
                guard let digit = defaults.object(forKey: key(action)) as? Int,
                      let oldChord = HotkeyChord.controlOptionDigit(digit) else { continue }
                assignMigrated(action, oldChord)
            }
        }
        persistCurrentLayout()
    }

    private mutating func assignMigrated(_ action: ShortcutAction, _ proposed: HotkeyChord) {
        if let other = ShortcutAction.uiOrder.first(where: {
            $0 != action && chord($0).keyCode == proposed.keyCode && chord($0).modifiers == proposed.modifiers
        }) {
            let previous = chord(action)
            chords[other] = previous
        }
        chords[action] = proposed
    }

    private mutating func repairCollisions() {
        var used = Set<String>()
        let defaultsLayout = Self.defaultLayout()
        for action in ShortcutAction.uiOrder {
            var current = chord(action)
            var token = Self.token(current)
            if used.contains(token), let fallback = defaultsLayout[action] {
                current = fallback
                token = Self.token(current)
            }
            if used.contains(token),
               let free = ShortcutAction.uiOrder.enumerated()
                .compactMap({ HotkeyChord.controlOptionDefault(index: $0.offset) })
                .first(where: { !used.contains(Self.token($0)) }) {
                current = free
                token = Self.token(current)
            }
            chords[action] = current
            used.insert(token)
        }
        persistCurrentLayout()
    }

    private static func token(_ chord: HotkeyChord) -> String {
        "\(chord.keyCode):\(chord.modifiers)"
    }

    private func key(_ action: ShortcutAction) -> String {
        "shortcut.action.\(action.rawValue)"
    }

    private func persistCurrentLayout() {
        for action in ShortcutAction.uiOrder {
            defaults.set(chord(action).payload, forKey: key(action))
        }
        defaults.set(4, forKey: "shortcut.layoutVersion")
    }
}
