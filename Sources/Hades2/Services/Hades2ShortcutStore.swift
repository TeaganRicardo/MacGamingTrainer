import Foundation
import TrainerCore

/// Hades II-specific shortcut defaults and historical schema migrations over Core `TrainerShortcutStore`.
typealias Hades2ShortcutProfileApplyResult = TrainerShortcutProfileApplyResult

struct Hades2ShortcutStore {
    private var core: TrainerShortcutStore<ShortcutAction>

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
                read: { defaults.object(forKey: Self.key($0)) },
                write: { defaults.set($1, forKey: Self.key($0)) },
                remove: { defaults.removeObject(forKey: Self.key($0)) },
                finalizePersistence: {
                    defaults.removeObject(forKey: "shortcut.action.godMode")
                    defaults.removeObject(forKey: "shortcut.action.damageEnabled")
                    defaults.set(6, forKey: "shortcut.layoutVersion")
                }
            ),
            cleanupLegacy: {
                defaults.removeObject(forKey: "shortcut.action.gardenQoL")
                defaults.removeObject(forKey: "shortcut.action.damageEnabled")
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
                Array(Self.legacyV3DefaultDigits.keys),
            ]
        )
    }

    private static func migrateHistoricalOverrides(_ defaults: UserDefaults) -> [ShortcutAction: HotkeyChord]? {
        let layoutVersion = defaults.integer(forKey: "shortcut.layoutVersion")
        if layoutVersion >= 6 { return nil }
        if layoutVersion == 5 { return migrateV5Identity(defaults) }
        if layoutVersion == 4 { return migrateV4Layout(defaults) }
        if layoutVersion == 3 { return migrateV3Digits(defaults) }
        // Pre-v3 layouts have already had two historical migrations in released builds.
        return [:]
    }

    private static func migrateV5Identity(_ defaults: UserDefaults) -> [ShortcutAction: HotkeyChord] {
        var result: [ShortcutAction: HotkeyChord] = [:]
        var used = Set<String>()
        for action in Hades2WorkbenchCatalog.orderedShortcutActions {
            guard let value = defaults.object(forKey: legacyKey(action)),
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

    private static func key(_ action: ShortcutAction) -> String {
        "shortcut.action.\(action.rawValue)"
    }

    private static func legacyKey(_ action: ShortcutAction) -> String {
        action == .invincibility ? "shortcut.action.godMode" : Self.key(action)
    }
}
