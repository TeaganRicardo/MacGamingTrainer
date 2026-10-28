
/// Cross-game semantic icon vocabulary.
///
/// Game modules choose a semantic role, not an SF Symbol literal. Shared roles
/// must resolve here so Hades integrations do not drift or redraw the same
/// concept independently. Game-specific concepts remain module-owned.
enum TrainerSemanticIcon {
    enum Section {
        static let values = "gauge.with.dots.needle.67percent"
        static let common = "bolt.fill"
        static let boons = "sparkles"
        static let resources = "shippingbox.fill"
        static let rooms = "door.left.hand.open"
        static let management = "gearshape.2.fill"
    }

    enum Feature {
        static let invincibility = "shield.fill"
        static let life = "heart.fill"
        static let magick = "drop.fill"
        static let currency = "banknote.fill"
        static let rerolls = "dice.fill"
        static let forceRerolls = "arrow.triangle.2.circlepath"
        static let infiniteAmmo = "infinity"
        static let boonRarity = "star.circle.fill"
        static let damageMultiplier = "burst.fill"
        static let moveSpeedMultiplier = "figure.run"
        static let attackSpeedMultiplier = "bolt.fill"
        static let gameSpeed = "speedometer"
        static let resource = "diamond.fill"
    }

    enum World {
        static let fishing = "fish.fill"
        static let chaosGate = "circle.hexagongrid.fill"
        static let reward = "gift.fill"
        static let exit = "door.left.hand.open"
    }

    enum Tool {
        static let saveEditor = "externaldrive.badge.gearshape"
        static let saveManagement = "externaldrive"
        static let profiles = "slider.horizontal.3"
        static let shortcuts = "keyboard"
        static let diagnostics = "stethoscope"
        static let log = "doc.text.magnifyingglass"
        static let logHistory = "clock.arrow.circlepath"
        static let clearLogs = "trash"
        static let disableAll = "power"
    }

    enum Action {
        static let acquire = "plus.circle.fill"
        static let remove = "trash"
        static let restore = "arrow.uturn.backward"
    }
}
