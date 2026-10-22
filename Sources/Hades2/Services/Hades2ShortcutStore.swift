import Foundation

/// Hades-specific shortcut persistence. Registration/capture mechanics live in
/// Core; this store owns action semantics, derived defaults, explicit user
/// overrides and local migration.
enum Hades2ShortcutProfileApplyResult: Equatable {
    case applied
    case unsupportedLayoutVersion(Int)
}

struct Hades2ShortcutStore {
    private(set) var chords: [ShortcutAction: HotkeyChord]
    private var overrides: [ShortcutAction: HotkeyChord] = [:]
    private let defaults: UserDefaults

    private static let profileLayoutVersionKey = "_layoutVersion"
    private static let profileLayoutVersion = 1

    /// Frozen ordering used only to recognize defaults written by released
    /// shortcut layouts. Active allocation follows the ordered workbench catalog.
    private static let legacyV4ActionOrder: [String] = [
        "invincibility", "infiniteHealth", "infiniteMana", "instantCastCooldown", "hexAlwaysReady",
        "infiniteAmmo", "damageEnabled", "autoMiniGames", "gardenQoL", "boonRarityEnabled",
        "forceEnableRerolls", "forceLegendary", "forceDuo", "moneyMultiplierEnabled",
        "resourceMultiplierEnabled", "spawnOlympian", "spawnPickup", "spawnSpecial",
        "applyNextRoomReward", "disableAll",
    ]

    private static let legacyV3DefaultDigits: [String: Int] = [
        "invincibility": 1, "infiniteHealth": 2, "infiniteMana": 3, "instantCastCooldown": 4,
        "hexAlwaysReady": 5, "infiniteAmmo": 6, "damageEnabled": 7, "autoMiniGames": 8,
        "moneyMultiplierEnabled": 9, "disableAll": 0,
    ]

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        self.chords = Self.defaultLayout()
        loadAndMigrate()
        defaults.removeObject(forKey: "shortcut.action.gardenQoL")
        defaults.removeObject(forKey: "shortcut.action.damageEnabled")
    }

    static func defaultLayout() -> [ShortcutAction: HotkeyChord] {
        let ordinary = Hades2WorkbenchCatalog.orderedShortcutActions.filter { !$0.isSpeedAdjustment }
        var result = Dictionary(uniqueKeysWithValues: ordinary.enumerated().compactMap { index, action in
            HotkeyChord.defaultShortcut(index: index).map { (action, $0) }
        })
        let modifiers = HotkeyChord.controlModifier | HotkeyChord.optionModifier
        result[.decreaseGameSpeed] = HotkeyChord(keyCode: 27, modifiers: modifiers, keyLabel: "−")
        result[.increaseGameSpeed] = HotkeyChord(keyCode: 24, modifiers: modifiers, keyLabel: "+")
        return result
    }

    func chord(_ action: ShortcutAction) -> HotkeyChord {
        chords[action] ?? Self.defaultLayout()[action]!
    }

    /// Profile payloads persist user overrides, not derived defaults. The format
    /// marker lets older full-layout Profiles migrate without mistaking a new
    /// intentional shortcut for a chord that used to be a default.
    func payload() -> [String: Any] {
        var result: [String: Any] = [Self.profileLayoutVersionKey: Self.profileLayoutVersion]
        for action in Hades2WorkbenchCatalog.orderedShortcutActions {
            if let explicit = overrides[action] {
                result[action.rawValue] = explicit.payload
            }
        }
        return result
    }

    mutating func set(_ action: ShortcutAction, chord newChord: HotkeyChord) -> ShortcutAction? {
        if let other = ShortcutAction.allCases.first(where: {
            $0 != action && chord($0).keyCode == newChord.keyCode && chord($0).modifiers == newChord.modifiers
        }) {
            return other
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

    @discardableResult
    mutating func applyProfile(_ values: [String: Any]) -> Hades2ShortcutProfileApplyResult {
        let importedLayoutVersion = values[Self.profileLayoutVersionKey] as? Int
        if let importedLayoutVersion, importedLayoutVersion != Self.profileLayoutVersion {
            return .unsupportedLayoutVersion(importedLayoutVersion)
        }
        let isCurrentPayload = importedLayoutVersion == Self.profileLayoutVersion
        let legacyV4Defaults = Self.legacyV4DefaultLayout()
        let legacyV3Defaults = Self.legacyV3DefaultChords()
        var patch: [ShortcutAction: HotkeyChord] = [:]
        var patchTokens = Set<String>()

        for action in Hades2WorkbenchCatalog.orderedShortcutActions {
            guard let value = values[action.rawValue], let proposed = HotkeyChord(payload: value) else { continue }
            if !isCurrentPayload,
               (proposed == legacyV4Defaults[action.rawValue] || proposed == legacyV3Defaults[action.rawValue]) {
                // Old Profiles serialized derived defaults as if they were
                // user choices. Re-derive those slots in the current UI order.
                continue
            }
            let token = Self.token(proposed)
            guard !patchTokens.contains(token) else { continue }
            patch[action] = proposed
            patchTokens.insert(token)
        }

        if isCurrentPayload {
            // Current Profiles are complete override snapshots. An empty
            // override set intentionally restores derived defaults.
            overrides = patch
            rebuildResolvedLayout()
            persistOverrides()
            return .applied
        }

        let completeLegacyV4Layout = Self.legacyV4ActionOrder.filter { ShortcutAction(rawValue: $0) != nil }.allSatisfy {
            values[$0] != nil
        }
        let completeLegacyV3Layout = Self.legacyV3DefaultDigits.keys.allSatisfy {
            values[$0] != nil
        }
        if completeLegacyV4Layout || completeLegacyV3Layout {
            overrides = patch
        } else {
            // Unversioned partial patches keep the historical merge semantics.
            guard !patch.isEmpty else { return .applied }
            for action in ShortcutAction.allCases where patch[action] == nil {
                if let existing = overrides[action], patchTokens.contains(Self.token(existing)) {
                    overrides[action] = nil
                }
            }
            for (action, proposed) in patch {
                overrides[action] = proposed
            }
        }

        rebuildResolvedLayout()
        persistOverrides()
        return .applied
    }

    private mutating func loadAndMigrate() {
        let layoutVersion = defaults.integer(forKey: "shortcut.layoutVersion")

        if layoutVersion >= 6 {
            loadPersistedOverrides()
            rebuildResolvedLayout()
            return
        }

        if layoutVersion == 5 {
            migrateV5Identity()
            rebuildResolvedLayout()
            persistOverrides()
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
        for action in Hades2WorkbenchCatalog.orderedShortcutActions {
            guard let value = defaults.object(forKey: key(action)),
                  let parsed = HotkeyChord(payload: value) else { continue }
            let token = Self.token(parsed)
            guard !used.contains(token) else { continue }
            overrides[action] = parsed
            used.insert(token)
        }
    }

    private mutating func migrateV5Identity() {
        overrides.removeAll()
        var used = Set<String>()
        for action in Hades2WorkbenchCatalog.orderedShortcutActions {
            guard let value = defaults.object(forKey: legacyKey(action)),
                  let parsed = HotkeyChord(payload: value) else { continue }
            let token = Self.token(parsed)
            guard !used.contains(token) else { continue }
            overrides[action] = parsed
            used.insert(token)
        }
    }

    private mutating func migrateV3Digits() {
        overrides.removeAll()
        var used = Set<String>()
        for action in ShortcutAction.legacyDigitActions {
            guard let digit = defaults.object(forKey: legacyKey(action)) as? Int,
                  digit != Self.legacyV3DefaultDigits[action.rawValue],
                  let chord = HotkeyChord.controlOptionDigit(digit) else { continue }
            let token = Self.token(chord)
            guard !used.contains(token) else { continue }
            overrides[action] = chord
            used.insert(token)
        }
    }

    private mutating func migrateV4Layout() {
        overrides.removeAll()
        let currentDefaults = Self.legacyV4DefaultLayout()
        let brokenDefaults = Self.knownBrokenV4MigratedLayout()
        var used = Set<String>()

        for identity in Self.legacyV4ActionOrder {
            guard let action = ShortcutAction(rawValue: identity),
                  let value = defaults.object(forKey: legacyKey(action)),
                  let parsed = HotkeyChord(payload: value) else { continue }

            // v4 wrote every computed default to disk. It also produced one
            // deterministic scrambled layout when upgrading untouched v3
            // digits. Both are derived state, not user intent.
            if parsed == currentDefaults[action.rawValue] || parsed == brokenDefaults[action.rawValue] {
                continue
            }

            let token = Self.token(parsed)
            guard !used.contains(token) else { continue }
            overrides[action] = parsed
            used.insert(token)
        }
    }

    private static func legacyV4DefaultLayout() -> [String: HotkeyChord] {
        Dictionary(uniqueKeysWithValues: legacyV4ActionOrder.enumerated().compactMap { index, action in
            HotkeyChord.controlOptionDefault(index: index).map { (action, $0) }
        })
    }

    private static func legacyV3DefaultChords() -> [String: HotkeyChord] {
        Dictionary(uniqueKeysWithValues: legacyV3DefaultDigits.compactMap { identity, digit in
            HotkeyChord.controlOptionDigit(digit).map { (identity, $0) }
        })
    }

    private static func knownBrokenV4MigratedLayout() -> [String: HotkeyChord] {
        var layout = legacyV4DefaultLayout()
        for (identity, digit) in legacyV3DefaultDigits {
            guard let proposed = HotkeyChord.controlOptionDigit(digit) else { continue }
            if let other = legacyV4ActionOrder.first(where: {
                $0 != identity && layout[$0].map(Self.token) == Self.token(proposed)
            }) {
                layout[other] = layout[identity]
            }
            layout[identity] = proposed
        }
        return layout
    }

    private mutating func rebuildResolvedLayout() {
        let defaultLayout = Self.defaultLayout()
        var next: [ShortcutAction: HotkeyChord] = [:]
        var used = Set(overrides.values.map(Self.token))

        for action in Hades2WorkbenchCatalog.orderedShortcutActions {
            if let explicit = overrides[action] {
                next[action] = explicit
                continue
            }

            if let preferred = defaultLayout[action], !used.contains(Self.token(preferred)) {
                next[action] = preferred
                used.insert(Self.token(preferred))
                continue
            }

            if let free = (0..<HotkeyChord.defaultShortcutCapacity)
                .compactMap({ HotkeyChord.defaultShortcut(index: $0) })
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

    private func legacyKey(_ action: ShortcutAction) -> String {
        action == .invincibility ? "shortcut.action.godMode" : key(action)
    }

    private mutating func persistOverrides() {
        for action in Hades2WorkbenchCatalog.orderedShortcutActions {
            if let explicit = overrides[action] {
                defaults.set(explicit.payload, forKey: key(action))
            } else {
                defaults.removeObject(forKey: key(action))
            }
        }
        defaults.removeObject(forKey: "shortcut.action.godMode")
        defaults.removeObject(forKey: "shortcut.action.damageEnabled")
        defaults.set(6, forKey: "shortcut.layoutVersion")
    }
}
