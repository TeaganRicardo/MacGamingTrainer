import Foundation

/// Outcome of importing a serialized shortcut snapshot from a saved Profile.
package enum TrainerShortcutProfileApplyResult: Equatable {
    case applied
    case unsupportedLayoutVersion(Int)
}

/// Module-scoped UserDefaults storage so each game's `<moduleID>.` key
/// namespace holds by construction at the Core/module boundary.
package struct TrainerShortcutStorage<Action: RawRepresentable> where Action.RawValue == String {
    let read: (Action) -> Any?
    let write: (Action, [String: Any]) -> Void
    let remove: (Action) -> Void
    let finalizePersistence: () -> Void

    package init(
        moduleID: String,
        defaults: UserDefaults,
        actionPrefix: String = "shortcut.",
        finalizePersistence: @escaping () -> Void = {}
    ) {
        precondition(!moduleID.isEmpty && !moduleID.contains("."), "moduleID must be a single module identifier")
        precondition(!actionPrefix.isEmpty, "actionPrefix must be non-empty")
        let prefix = "\(moduleID).\(actionPrefix)"
        self.read = { defaults.object(forKey: prefix + $0.rawValue) }
        self.write = { defaults.set($1, forKey: prefix + $0.rawValue) }
        self.remove = { defaults.removeObject(forKey: prefix + $0.rawValue) }
        self.finalizePersistence = finalizePersistence
    }
}

/// Shared module shortcut store with locked-chord protection, physical-key
/// conflict resolution, retired-action cleanup, and Profile import/export.
package struct TrainerShortcutStore<Action: Hashable & RawRepresentable> where Action.RawValue == String {
    package static var profileLayoutVersionKey: String { "_layoutVersion" }
    package static var currentProfileLayoutVersion: Int { 1 }

    package private(set) var chords: [Action: HotkeyChord]
    package private(set) var overrides: [Action: HotkeyChord] = [:]

    private let orderedActions: [Action]
    private let defaultLayout: [Action: HotkeyChord]
    private let lockedActions: [Action: HotkeyChord]
    private let storage: TrainerShortcutStorage<Action>

    package init(
        orderedActions: [Action],
        defaultLayout: [Action: HotkeyChord],
        lockedActions: [Action: HotkeyChord] = [:],
        storage: TrainerShortcutStorage<Action>,
        cleanupLegacy: () -> Void = {},
        migrateOverrides: (() -> [Action: HotkeyChord]?)? = nil
    ) {
        self.orderedActions = orderedActions
        self.defaultLayout = defaultLayout
        self.lockedActions = lockedActions
        self.storage = storage
        self.chords = defaultLayout

        if let migrated = migrateOverrides?() {
            overrides = migrated
            rebuild()
            persist()
        } else {
            loadPersistedOverrides()
            rebuild()
        }
        cleanupLegacy()
    }

    package func chord(_ action: Action) -> HotkeyChord {
        chords[action] ?? defaultLayout[action]!
    }

    package mutating func reset() {
        overrides.removeAll()
        rebuild()
        persist()
    }

    package mutating func set(
        _ action: Action,
        chord proposed: HotkeyChord,
        conflictCandidates: [Action]? = nil
    ) -> Action? {
        if let fixed = lockedActions[action] {
            return TrainerHotkeyLayout.sameKeys(proposed, fixed) ? nil : action
        }
        if let locked = lockedAction(matching: proposed) {
            return locked
        }
        let candidates = conflictCandidates ?? orderedActions
        if let other = candidates.first(where: {
            $0 != action && TrainerHotkeyLayout.sameKeys(chord($0), proposed)
        }) {
            return other
        }

        if proposed == defaultLayout[action] {
            overrides[action] = nil
        } else {
            overrides[action] = proposed
        }
        rebuild()
        persist()
        return nil
    }

    /// Snapshot of explicit user overrides and layout schema version for Profile storage.
    package func payload() -> [String: Any] {
        var result: [String: Any] = [
            Self.profileLayoutVersionKey: Self.currentProfileLayoutVersion,
        ]
        for action in orderedActions where lockedActions[action] == nil {
            if let explicit = overrides[action] {
                result[action.rawValue] = explicit.payload
            }
        }
        return result
    }

    @discardableResult
    package mutating func applyProfile(
        _ values: [String: Any],
        legacyDefaultTables: [[String: HotkeyChord]] = [],
        completeLegacyLayouts: [[String]] = [],
        legacyActionAliases: [String: Action] = [:]
    ) -> TrainerShortcutProfileApplyResult {
        let importedLayoutVersion = values[Self.profileLayoutVersionKey] as? Int
        if let importedLayoutVersion, importedLayoutVersion != Self.currentProfileLayoutVersion {
            return .unsupportedLayoutVersion(importedLayoutVersion)
        }
        let isCurrentPayload = importedLayoutVersion == Self.currentProfileLayoutVersion
        var legacyKeysByAction: [Action: [String]] = [:]
        for (legacyKey, canonicalAction) in legacyActionAliases {
            legacyKeysByAction[canonicalAction, default: []].append(legacyKey)
        }
        for action in legacyKeysByAction.keys {
            legacyKeysByAction[action]?.sort()
        }

        var patch: [Action: HotkeyChord] = [:]
        var patchTokens = Set<String>()

        for action in orderedActions where lockedActions[action] == nil {
            var matchedKey: String?
            var rawValue: Any?
            if let canonicalValue = values[action.rawValue] {
                matchedKey = action.rawValue
                rawValue = canonicalValue
            } else if let aliases = legacyKeysByAction[action] {
                for alias in aliases {
                    if let aliasValue = values[alias] {
                        matchedKey = alias
                        rawValue = aliasValue
                        break
                    }
                }
            }
            guard let matchedKey,
                  let value = rawValue,
                  let proposed = HotkeyChord(payload: value),
                  lockedAction(matching: proposed) == nil else { continue }
            if !isCurrentPayload,
               legacyDefaultTables.contains(where: { $0[matchedKey] == proposed || $0[action.rawValue] == proposed }) {
                // Historical full-layout Profiles persisted computed defaults as
                // explicit bindings; re-derive them under the active order.
                continue
            }
            let identity = TrainerHotkeyLayout.identity(proposed)
            guard patchTokens.insert(identity).inserted else { continue }
            patch[action] = proposed
        }

        if isCurrentPayload || completeLegacyLayouts.contains(where: { layout in
            !layout.isEmpty && layout.allSatisfy { values[$0] != nil }
        }) {
            overrides = patch
        } else {
            // An unversioned or empty shortcut section (for example, legacy
            // Profiles without shortcuts) leaves current bindings unchanged.
            guard !patch.isEmpty else { return .applied }
            for action in orderedActions where patch[action] == nil {
                if let existing = overrides[action],
                   patchTokens.contains(TrainerHotkeyLayout.identity(existing)) {
                    overrides[action] = nil
                }
            }
            for (action, proposed) in patch {
                overrides[action] = proposed
            }
        }

        rebuild()
        persist()
        return .applied
    }

    private func lockedAction(matching chord: HotkeyChord) -> Action? {
        orderedActions.first { action in
            guard let fixed = lockedActions[action] else { return false }
            return TrainerHotkeyLayout.sameKeys(chord, fixed)
        }
    }

    private mutating func loadPersistedOverrides() {
        overrides.removeAll()
        var seen = Set<String>()
        for action in orderedActions where lockedActions[action] == nil {
            guard let saved = storage.read(action),
                  let parsed = HotkeyChord(payload: saved) else { continue }
            guard lockedAction(matching: parsed) == nil,
                  seen.insert(TrainerHotkeyLayout.identity(parsed)).inserted else {
                storage.remove(action)
                continue
            }
            overrides[action] = parsed
        }
        for lockedAction in lockedActions.keys {
            storage.remove(lockedAction)
        }
    }

    private mutating func rebuild() {
        overrides = overrides.filter { action, chord in
            lockedActions[action] == nil && lockedAction(matching: chord) == nil
        }
        chords = TrainerHotkeyLayout.resolvedLayout(
            orderedActions: orderedActions,
            defaults: defaultLayout,
            overrides: overrides,
            locked: lockedActions
        )
    }

    private func persist() {
        for action in orderedActions {
            if lockedActions[action] == nil, let explicit = overrides[action] {
                storage.write(action, explicit.payload)
            } else {
                storage.remove(action)
            }
        }
        storage.finalizePersistence()
    }
}
