import Foundation
import TrainerCore

/// Hades II-specific shortcut defaults and historical schema migrations over Core `TrainerShortcutStore`.
typealias Hades2ShortcutProfileApplyResult = TrainerShortcutProfileApplyResult

struct Hades2ShortcutStore {
    static let currentLayoutVersion = 7
    private static let moduleNamespace = "hades2"
    static var layoutVersionKey: String { "\(moduleNamespace).shortcut.layoutVersion" }
    private static let legacyLayoutVersionKey = "shortcut.layoutVersion"
    private var core: TrainerShortcutStore<ShortcutAction>

    /// Frozen key sequence used only to recognize the released v4 defaults.
    private static let legacyV4Keys: [(keyCode: UInt32, label: String)] = [
        (18, "1"), (19, "2"), (20, "3"), (21, "4"), (23, "5"),
        (22, "6"), (26, "7"), (28, "8"), (25, "9"),
        (0, "A"), (11, "B"), (8, "C"), (2, "D"), (14, "E"), (3, "F"), (5, "G"),
        (4, "H"), (34, "I"), (38, "J"), (40, "K"), (37, "L"), (46, "M"), (45, "N"),
        (31, "O"), (35, "P"), (12, "Q"), (15, "R"), (1, "S"), (17, "T"), (32, "U"),
        (9, "V"), (13, "W"), (7, "X"), (16, "Y"), (6, "Z"),
    ]

    /// Historical v4 migration only. Do not use this for active allocation.
    static func controlOptionDefault(index: Int) -> HotkeyChord? {
        guard legacyV4Keys.indices.contains(index) else { return nil }
        let key = legacyV4Keys[index]
        return HotkeyChord(
            keyCode: key.keyCode,
            modifiers: HotkeyChord.controlModifier | HotkeyChord.optionModifier,
            keyLabel: key.label
        )
    }

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
        self.core = TrainerShortcutStore(
            orderedActions: Hades2WorkbenchCatalog.orderedShortcutActions,
            defaultLayout: Self.defaultLayout(),
            lockedActions: [.disableAll: TrainerHotkeyLayout.disableAllChord],
            storage: TrainerShortcutStorage(
                moduleID: "hades2",
                defaults: defaults,
                actionPrefix: "shortcut.action.",
                finalizePersistence: {
                    defaults.set(Self.currentLayoutVersion, forKey: Self.layoutVersionKey)
                    Self.removeLegacyAndRetiredKeys(defaults)
                }
            ),
            cleanupLegacy: {
                if defaults.integer(forKey: Self.layoutVersionKey) < Self.currentLayoutVersion {
                    defaults.set(Self.currentLayoutVersion, forKey: Self.layoutVersionKey)
                }
                Self.removeLegacyAndRetiredKeys(defaults)
            },
            migrateOverrides: { Self.migrateHistoricalOverrides(defaults) }
        )
    }

    static func defaultLayout() -> [ShortcutAction: HotkeyChord] {
        let modifiers = HotkeyChord.controlModifier | HotkeyChord.optionModifier
        return TrainerHotkeyLayout.defaultLayout(
            orderedActions: Hades2WorkbenchCatalog.orderedShortcutActions,
            dedicated: [
                .decreaseGameSpeed: HotkeyChord(keyCode: 27, modifiers: modifiers, keyLabel: "−"),
                .increaseGameSpeed: HotkeyChord(keyCode: 24, modifiers: modifiers, keyLabel: "+"),
                .disableAll: TrainerHotkeyLayout.disableAllChord,
            ]
        )
    }

    func chord(_ action: ShortcutAction) -> HotkeyChord {
        core.chord(action)
    }

    /// Reset explicit user overrides, then derive the current visible action
    /// order again. Keep the fixed Disable All chord and schema migrations.
    mutating func resetToDefaults() {
        core.reset()
    }

    /// Profile payloads persist user overrides, not derived defaults.
    func payload() -> [String: Any] {
        core.payload()
    }

    mutating func set(_ action: ShortcutAction, chord newChord: HotkeyChord) -> ShortcutAction? {
        core.set(action, chord: newChord, conflictCandidates: ShortcutAction.allCases)
    }

    @discardableResult
    mutating func applyProfile(_ values: [String: Any]) -> Hades2ShortcutProfileApplyResult {
        core.applyProfile(
            values,
            legacyDefaultTables: [Self.legacyV4DefaultLayout(), Self.legacyV3DefaultChords()],
            completeLegacyLayouts: [
                Self.legacyV4ActionOrder.filter { ShortcutAction(rawValue: $0) != nil },
                Self.legacyV3DefaultDigits.keys.filter { ShortcutAction(rawValue: $0) != nil },
            ]
        )
    }

    private static func migrateHistoricalOverrides(_ defaults: UserDefaults) -> [ShortcutAction: HotkeyChord]? {
        if defaults.integer(forKey: layoutVersionKey) >= currentLayoutVersion {
            return nil
        }
        let legacyVersion = defaults.integer(forKey: legacyLayoutVersionKey)
        if legacyVersion >= 6 { return migrateV6Unprefixed(defaults) }
        if legacyVersion == 5 { return migrateV5Identity(defaults) }
        if legacyVersion == 4 { return migrateV4Layout(defaults) }
        if legacyVersion == 3 { return migrateV3Digits(defaults) }
        if legacyVersion > 0 || hasLegacyUnprefixedKeys(defaults) {
            // Pre-v3 layouts have already had two historical migrations in released builds.
            return [:]
        }
        return nil
    }

    private static func migrateV6Unprefixed(_ defaults: UserDefaults) -> [ShortcutAction: HotkeyChord] {
        var result: [ShortcutAction: HotkeyChord] = [:]
        var used = Set<String>()
        for action in Hades2WorkbenchCatalog.orderedShortcutActions {
            guard let value = defaults.object(forKey: unprefixedKey(action)),
                  let parsed = HotkeyChord(payload: value) else { continue }
            guard used.insert(TrainerHotkeyLayout.identity(parsed)).inserted else { continue }
            result[action] = parsed
        }
        return result
    }

    private static func migrateV5Identity(_ defaults: UserDefaults) -> [ShortcutAction: HotkeyChord] {
        var result: [ShortcutAction: HotkeyChord] = [:]
        var used = Set<String>()
        for action in Hades2WorkbenchCatalog.orderedShortcutActions {
            let value = defaults.object(forKey: legacyKey(action)) ?? defaults.object(forKey: unprefixedKey(action))
            guard let value,
                  let parsed = HotkeyChord(payload: value) else { continue }
            guard used.insert(TrainerHotkeyLayout.identity(parsed)).inserted else { continue }
            result[action] = parsed
        }
        return result
    }

    private static func migrateV3Digits(_ defaults: UserDefaults) -> [ShortcutAction: HotkeyChord] {
        var result: [ShortcutAction: HotkeyChord] = [:]
        var used = Set<String>()
        for action in ShortcutAction.legacyDigitActions {
            guard let digit = defaults.object(forKey: legacyKey(action)) as? Int,
                  digit != legacyV3DefaultDigits[action.rawValue],
                  let chord = HotkeyChord.controlOptionDigit(digit) else { continue }
            guard used.insert(TrainerHotkeyLayout.identity(chord)).inserted else { continue }
            result[action] = chord
        }
        return result
    }

    private static func migrateV4Layout(_ defaults: UserDefaults) -> [ShortcutAction: HotkeyChord] {
        var result: [ShortcutAction: HotkeyChord] = [:]
        let currentDefaults = legacyV4DefaultLayout()
        let brokenDefaults = knownBrokenV4MigratedLayout()
        var used = Set<String>()

        for identity in legacyV4ActionOrder {
            guard let action = ShortcutAction(rawValue: identity),
                  let value = defaults.object(forKey: legacyKey(action)),
                  let parsed = HotkeyChord(payload: value) else { continue }
            if parsed == currentDefaults[action.rawValue] || parsed == brokenDefaults[action.rawValue] {
                continue
            }
            guard used.insert(TrainerHotkeyLayout.identity(parsed)).inserted else { continue }
            result[action] = parsed
        }
        return result
    }

    private static func legacyV4DefaultLayout() -> [String: HotkeyChord] {
        Dictionary(uniqueKeysWithValues: legacyV4ActionOrder.enumerated().compactMap { index, action in
            Self.controlOptionDefault(index: index).map { (action, $0) }
        })
    }

    private static func legacyV3DefaultChords() -> [String: HotkeyChord] {
        Dictionary(uniqueKeysWithValues: legacyV3DefaultDigits.compactMap { identity, digit in
            HotkeyChord.controlOptionDigit(digit).map { (identity, $0) }
        })
    }

    private static func knownBrokenV4MigratedLayout() -> [String: HotkeyChord] {
        var layout = legacyV4DefaultLayout()
        for identity in legacyV4ActionOrder {
            guard let digit = legacyV3DefaultDigits[identity],
                  let proposed = HotkeyChord.controlOptionDigit(digit) else { continue }
            if let other = legacyV4ActionOrder.first(where: {
                $0 != identity && layout[$0].map(TrainerHotkeyLayout.identity) == TrainerHotkeyLayout.identity(proposed)
            }) {
                layout[other] = layout[identity]
            }
            layout[identity] = proposed
        }
        return layout
    }

    private static let retiredSuffixes: [String] = ["godMode", "gardenQoL", "damageEnabled"]

    private static func hasLegacyUnprefixedKeys(_ defaults: UserDefaults) -> Bool {
        if defaults.object(forKey: legacyLayoutVersionKey) != nil { return true }
        for suffix in retiredSuffixes where defaults.object(forKey: "shortcut.action.\(suffix)") != nil {
            return true
        }
        return ShortcutAction.allCases.contains { defaults.object(forKey: unprefixedKey($0)) != nil }
    }

    private static func removeLegacyAndRetiredKeys(_ defaults: UserDefaults) {
        defaults.removeObject(forKey: legacyLayoutVersionKey)
        for suffix in retiredSuffixes {
            defaults.removeObject(forKey: "shortcut.action.\(suffix)")
            defaults.removeObject(forKey: "\(moduleNamespace).shortcut.action.\(suffix)")
        }
        for action in ShortcutAction.allCases {
            defaults.removeObject(forKey: unprefixedKey(action))
        }
    }

    private static func unprefixedKey(_ action: ShortcutAction) -> String {
        "shortcut.action.\(action.rawValue)"
    }

    private static func legacyKey(_ action: ShortcutAction) -> String {
        action == .invincibility ? "shortcut.action.godMode" : unprefixedKey(action)
    }
}
