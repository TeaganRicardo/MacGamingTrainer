
/// Shared semantic SF Symbol vocabulary.
///
/// Product modules choose a visual role, not an SF Symbol literal. Only roles
/// demonstrated by multiple product surfaces belong here; domain-specific
/// identities remain module-owned.
package enum TrainerSemanticIcon {
    package enum Section {
        package static let metrics = "gauge.with.dots.needle.67percent"
        package static let general = "bolt.fill"
        package static let effects = "sparkles"
        package static let inventory = "shippingbox.fill"
        package static let navigation = "door.left.hand.open"
        package static let settings = "gearshape.2.fill"
    }

    package enum Concept {
        package static let protection = "shield.fill"
        package static let vitality = "heart.fill"
        package static let energy = "drop.fill"
        package static let currency = "banknote.fill"
        package static let randomize = "dice.fill"
        package static let refresh = "arrow.triangle.2.circlepath"
        package static let capacity = "infinity"
        package static let quality = "star.circle.fill"
        package static let impact = "burst.fill"
        package static let movement = "figure.run"
        package static let actionSpeed = "bolt.fill"
        package static let timeScale = "speedometer"
        package static let item = "diamond.fill"
        package static let controls = "slider.horizontal.3"
        package static let defense = "shield.lefthalf.filled"
        package static let duration = "hourglass"
        package static let timer = "timer"
        package static let precision = "scope"
        package static let dash = "wind"
        package static let level = "arrow.up.circle.fill"
    }

    package enum Context {
        package static let fishing = "fish.fill"
        package static let portal = "circle.hexagongrid.fill"
        static let reward = "gift.fill"
        package static let characterReward = "moon.stars.fill"
        package static let doorway = "door.left.hand.open"
    }

    package enum Tool {
        package static let saveEditor = "externaldrive.badge.gearshape"
        package static let saveManagement = "externaldrive"
        package static let saveFolder = "folder"
        package static let saveHistory = "clock.arrow.circlepath"
        static let retention = "clock.badge.checkmark"
        package static let profiles = "square.stack.3d.up"
        package static let shortcuts = "keyboard"
        package static let diagnostics = "stethoscope"
        static let exportDiagnostics = "square.and.arrow.up"
        package static let refreshStatus = "arrow.clockwise"
        static let currentIssues = "exclamationmark.circle"
        package static let log = "doc.text.magnifyingglass"
        package static let logHistory = "clock.arrow.circlepath"
        package static let clearLogs = "trash"
        package static let disableAll = "power"
    }

    package enum Action {
        package static let acquire = "plus.circle.fill"
        package static let apply = "checkmark.circle.fill"
        package static let generate = "plus.circle.fill"
        static let save = "square.and.arrow.down"
        static let load = "arrow.down.circle"
        package static let edit = "square.and.pencil"
        package static let rename = "pencil"
        static let protect = "lock"
        static let unprotect = "lock.open"
        package static let remove = "trash"
        package static let restore = "arrow.uturn.backward"
        static let dismiss = "xmark"
    }

    package enum Feedback {
        package static let success = "checkmark.circle"
        static let warning = "exclamationmark.triangle"
        static let storageWarning = "externaldrive.badge.exclamationmark"
        package static let toastSuccess = "checkmark.circle.fill"
        static let toastWarning = "exclamationmark.triangle.fill"
        static let toastInfo = "info.circle.fill"
    }
}
