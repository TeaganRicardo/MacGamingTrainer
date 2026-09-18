import Foundation

/// Hades-specific shortcut persistence/migration. Global key registration is a
/// host primitive; the semantic actions and their historical migrations belong
/// to the Hades module.
struct Hades2ShortcutStore {
    private(set) var digits: [ShortcutAction: Int]
    private let defaults: UserDefaults

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        self.digits = Dictionary(uniqueKeysWithValues: ShortcutAction.uiOrder.map { ($0, $0.defaultDigit) })
        loadAndMigrate()
    }

    func digit(_ action: ShortcutAction) -> Int {
        digits[action] ?? action.defaultDigit
    }

    func payload() -> [String: Int] {
        Dictionary(uniqueKeysWithValues: ShortcutAction.uiOrder.map { ($0.rawValue, digit($0)) })
    }

    mutating func set(_ action: ShortcutAction, digit newDigit: Int) {
        guard (0...9).contains(newDigit) else { return }
        let previous = digit(action)
        if let other = ShortcutAction.uiOrder.first(where: { $0 != action && digit($0) == newDigit }) {
            digits[other] = previous
            defaults.set(previous, forKey: key(other))
        }
        digits[action] = newDigit
        defaults.set(newDigit, forKey: key(action))
        defaults.set(3, forKey: "shortcut.layoutVersion")
    }

    mutating func applyProfile(_ values: [String: Any]) {
        for action in ShortcutAction.uiOrder {
            if let value = values[action.rawValue] as? Int, (0...9).contains(value) {
                digits[action] = value
            }
        }
        persistCurrentLayout()
    }

    private mutating func loadAndMigrate() {
        let layoutVersion = defaults.integer(forKey: "shortcut.layoutVersion")
        if layoutVersion >= 3 {
            for action in ShortcutAction.uiOrder {
                if let value = defaults.object(forKey: key(action)) as? Int, (0...9).contains(value) {
                    digits[action] = value
                }
            }
            return
        }

        if layoutVersion == 2 {
            let oldDefaults: [ShortcutAction: Int] = [
                .godMode: 1, .infiniteHealth: 2, .infiniteMana: 3, .instantCastCooldown: 4,
                .hexAlwaysReady: 5, .infiniteAmmo: 6, .damageEnabled: 7,
                .moneyMultiplierEnabled: 8, .resourceMultiplierEnabled: 9, .disableAll: 0,
            ]
            let stillDefault = oldDefaults.allSatisfy { action, fallback in
                (defaults.object(forKey: key(action)) as? Int ?? fallback) == fallback
            }
            if stillDefault {
                for action in ShortcutAction.uiOrder { digits[action] = action.defaultDigit }
            } else {
                for action in ShortcutAction.uiOrder where action != .autoMiniGames {
                    if let value = defaults.object(forKey: key(action)) as? Int, (0...9).contains(value) {
                        digits[action] = value
                    }
                }
                let freed = defaults.object(forKey: key(.resourceMultiplierEnabled)) as? Int ?? 9
                let used = Set(ShortcutAction.uiOrder.filter { $0 != .autoMiniGames }.map { digit($0) })
                digits[.autoMiniGames] = used.contains(freed)
                    ? ((0...9).first { !used.contains($0) } ?? ShortcutAction.autoMiniGames.defaultDigit)
                    : freed
            }
            persistCurrentLayout()
            return
        }

        for action in ShortcutAction.uiOrder { digits[action] = action.defaultDigit }
        persistCurrentLayout()
    }

    private func key(_ action: ShortcutAction) -> String {
        "shortcut.action.\(action.rawValue)"
    }

    private func persistCurrentLayout() {
        for action in ShortcutAction.uiOrder { defaults.set(digit(action), forKey: key(action)) }
        defaults.set(3, forKey: "shortcut.layoutVersion")
    }
}
