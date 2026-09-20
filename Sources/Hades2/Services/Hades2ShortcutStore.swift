import Foundation

/// Hades-specific shortcut persistence. Registration/capture mechanics live in
/// Core; this store owns action semantics, derived defaults, explicit user
/// overrides and local migration.
struct Hades2ShortcutStore {
    private(set) var chords: [ShortcutAction: HotkeyChord]
    private var overrides: [ShortcutAction: HotkeyChord] = [:]
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
        if let other = ShortcutAction.uiOrder.first(where: {
            $0 != action && chord($0).keyCode == newChord.keyCode && chord($0).modifiers == newChord.modifiers
        }) {
            return "快捷键 \(newChord.displayText) 已分配给「\(other.title)」。"
        }

        if newChord == Self.defaultLayout()[action] {
            overrides[action] = nil
        } else {
            overrides[action] = newChord
        }
        rebuildResolvedLayout()
        persistOverrides()
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

        // A Profile is an explicit user layout. Keep every imported assignment
        // fixed; only actions absent from the Profile are allowed to reflow.
        for action in ShortcutAction.uiOrder where patch[action] == nil {
            if let existing = overrides[action], patchTokens.contains(Self.token(existing)) {
                overrides[action] = nil
            }
        }
        for (action, proposed) in patch {
            overrides[action] = proposed
        }
        rebuildResolvedLayout()
        persistOverrides()
    }

    private mutating func loadAndMigrate() {
        let layoutVersion = defaults.integer(forKey: "shortcut.layoutVersion")

        if layoutVersion >= 5 {
            loadPersistedOverrides()
            rebuildResolvedLayout()
            return
        }

        if layoutVersion == 4 {
            migrateV4Layout()
            rebuildResolvedLayout()
            persistOverrides()
            return
        }

        if layoutVersion == 3 {
            migrateV3Digits()
            rebuildResolvedLayout()
            persistOverrides()
            return
        }

        // Pre-v3 layouts have already had two historical migrations in released
        // builds. Treat an unrecognized/empty layout as derived defaults rather
        // than pinning another obsolete ordering forever.
        rebuildResolvedLayout()
        persistOverrides()
    }

    private mutating func loadPersistedOverrides() {
        overrides.removeAll()
        var used = Set<String>()
        for action in ShortcutAction.uiOrder {
            guard let value = defaults.object(forKey: key(action)),
                  let parsed = HotkeyChord(payload: value) else { continue }
            let token = Self.token(parsed)
            guard !used.contains(token) else { continue }
            overrides[action] = parsed
            used.insert(token)
        }
    }

    private mutating func migrateV3Digits() {
        overrides.removeAll()
        let legacyDefaults: [ShortcutAction: Int] = [
            .godMode: 1, .infiniteHealth: 2, .infiniteMana: 3, .instantCastCooldown: 4,
            .hexAlwaysReady: 5, .infiniteAmmo: 6, .damageEnabled: 7, .autoMiniGames: 8,
            .moneyMultiplierEnabled: 9, .disableAll: 0,
        ]
        var used = Set<String>()
        for action in ShortcutAction.legacyDigitActions {
            guard let digit = defaults.object(forKey: key(action)) as? Int,
                  digit != legacyDefaults[action],
                  let chord = HotkeyChord.controlOptionDigit(digit) else { continue }
            let token = Self.token(chord)
            guard !used.contains(token) else { continue }
            overrides[action] = chord
            used.insert(token)
        }
    }

    private mutating func migrateV4Layout() {
        overrides.removeAll()
        let currentDefaults = Self.defaultLayout()
        let brokenDefaults = Self.knownBrokenV4MigratedLayout()
        var used = Set<String>()

        for action in ShortcutAction.uiOrder {
            guard let value = defaults.object(forKey: key(action)),
                  let parsed = HotkeyChord(payload: value) else { continue }

            // v4 wrote every computed default to disk. It also produced one
            // deterministic scrambled layout when upgrading untouched v3
            // digits. Both are derived state, not user intent.
            if parsed == currentDefaults[action] || parsed == brokenDefaults[action] {
                continue
            }

            let token = Self.token(parsed)
            guard !used.contains(token) else { continue }
            overrides[action] = parsed
            used.insert(token)
        }
    }

    private static func knownBrokenV4MigratedLayout() -> [ShortcutAction: HotkeyChord] {
        var layout = defaultLayout()
        let legacyDefaults: [ShortcutAction: Int] = [
            .godMode: 1, .infiniteHealth: 2, .infiniteMana: 3, .instantCastCooldown: 4,
            .hexAlwaysReady: 5, .infiniteAmmo: 6, .damageEnabled: 7, .autoMiniGames: 8,
            .moneyMultiplierEnabled: 9, .disableAll: 0,
        ]
        for action in ShortcutAction.legacyDigitActions {
            guard let digit = legacyDefaults[action],
                  let proposed = HotkeyChord.controlOptionDigit(digit) else { continue }
            if let other = ShortcutAction.uiOrder.first(where: {
                $0 != action && layout[$0].map(Self.token) == Self.token(proposed)
            }) {
                layout[other] = layout[action]
            }
            layout[action] = proposed
        }
        return layout
    }

    private mutating func rebuildResolvedLayout() {
        let defaultLayout = Self.defaultLayout()
        var next: [ShortcutAction: HotkeyChord] = [:]
        var used = Set(overrides.values.map(Self.token))

        for action in ShortcutAction.uiOrder {
            if let explicit = overrides[action] {
                next[action] = explicit
                continue
            }

            if let preferred = defaultLayout[action], !used.contains(Self.token(preferred)) {
                next[action] = preferred
                used.insert(Self.token(preferred))
                continue
            }

            if let free = ShortcutAction.uiOrder.enumerated()
                .compactMap({ HotkeyChord.controlOptionDefault(index: $0.offset) })
                .first(where: { !used.contains(Self.token($0)) }) {
                next[action] = free
                used.insert(Self.token(free))
            }
        }
        chords = next
    }

    private static func token(_ chord: HotkeyChord) -> String {
        "\(chord.keyCode):\(chord.modifiers)"
    }

    private func key(_ action: ShortcutAction) -> String {
        "shortcut.action.\(action.rawValue)"
    }

    private func persistOverrides() {
        for action in ShortcutAction.uiOrder {
            if let explicit = overrides[action] {
                defaults.set(explicit.payload, forKey: key(action))
            } else {
                defaults.removeObject(forKey: key(action))
            }
        }
        defaults.set(5, forKey: "shortcut.layoutVersion")
    }
}
