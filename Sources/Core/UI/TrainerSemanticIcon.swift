
/// Shared semantic SF Symbol vocabulary.
///
/// Product modules choose a visual role, not an SF Symbol literal. Only roles
/// demonstrated by multiple product surfaces belong here; domain-specific
/// identities remain module-owned.
enum TrainerSemanticIcon {
    enum Section {
        static let metrics = "gauge.with.dots.needle.67percent"
        static let general = "bolt.fill"
        static let effects = "sparkles"
        static let inventory = "shippingbox.fill"
        static let navigation = "door.left.hand.open"
        static let settings = "gearshape.2.fill"
    }

    enum Concept {
        static let protection = "shield.fill"
        static let vitality = "heart.fill"
        static let energy = "drop.fill"
        static let currency = "banknote.fill"
        static let randomize = "dice.fill"
        static let refresh = "arrow.triangle.2.circlepath"
        static let capacity = "infinity"
        static let quality = "star.circle.fill"
        static let impact = "burst.fill"
        static let movement = "figure.run"
        static let actionSpeed = "bolt.fill"
        static let timeScale = "speedometer"
        static let item = "diamond.fill"
        static let controls = "slider.horizontal.3"
        static let defense = "shield.lefthalf.filled"
        static let duration = "hourglass"
        static let timer = "timer"
        static let precision = "scope"
        static let dash = "wind"
        static let level = "arrow.up.circle.fill"
    }

    enum Context {
        static let fishing = "fish.fill"
        static let portal = "circle.hexagongrid.fill"
        static let reward = "gift.fill"
        static let doorway = "door.left.hand.open"
    }

    enum Tool {
        static let saveEditor = "externaldrive.badge.gearshape"
        static let saveManagement = "externaldrive"
        static let profiles = "slider.horizontal.3"
        static let shortcuts = "keyboard"
        static let diagnostics = "stethoscope"
        static let exportDiagnostics = "square.and.arrow.up"
        static let refreshStatus = "arrow.clockwise"
        static let log = "doc.text.magnifyingglass"
        static let logHistory = "clock.arrow.circlepath"
        static let clearLogs = "trash"
        static let disableAll = "power"
    }

    enum Action {
        static let acquire = "plus.circle.fill"
        static let apply = "checkmark.circle.fill"
        static let generate = "plus.circle.fill"
        static let save = "square.and.arrow.down"
        static let load = "arrow.down.circle"
        static let remove = "trash"
        static let restore = "arrow.uturn.backward"
    }
}
