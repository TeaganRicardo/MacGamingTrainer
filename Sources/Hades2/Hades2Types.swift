import Foundation

struct MaterialResource: Identifiable {
    let id: String
    let name: String
    let englishName: String
    let count: Double
    let locked: Bool
    let sectionTitle: String
    let sortOrder: Int
}

struct BoonOption: Identifiable {
    let id: String
    let name: String
    let englishName: String
    let category: String
    let kind: String
    let group: String
    let sectionTitle: String
    let sortSection: Int
    let sortGroup: Int
    let sortOrder: Int
}

enum ShortcutAction: String, CaseIterable, Identifiable {
    case godMode, infiniteHealth, infiniteMana, instantCastCooldown, hexAlwaysReady
    case infiniteAmmo, damageEnabled, autoMiniGames, moneyMultiplierEnabled, resourceMultiplierEnabled, disableAll

    var id: String { rawValue }
    static let uiOrder: [ShortcutAction] = [
        .godMode, .infiniteHealth, .infiniteMana, .instantCastCooldown, .hexAlwaysReady,
        .infiniteAmmo, .damageEnabled, .autoMiniGames, .moneyMultiplierEnabled, .disableAll,
    ]
    var defaultDigit: Int {
        switch self {
        case .godMode: return 1
        case .infiniteHealth: return 2
        case .infiniteMana: return 3
        case .instantCastCooldown: return 4
        case .hexAlwaysReady: return 5
        case .infiniteAmmo: return 6
        case .damageEnabled: return 7
        case .autoMiniGames: return 8
        case .moneyMultiplierEnabled: return 9
        case .resourceMultiplierEnabled: return 9 // no default registration in the 0–9 layout
        case .disableAll: return 0
        }
    }
    var title: String {
        switch self {
        case .godMode: return "God Mode"
        case .infiniteHealth: return "无限生命"
        case .infiniteMana: return "无限魔力"
        case .instantCastCooldown: return "法阵始终可用"
        case .hexAlwaysReady: return "巫咒始终可用"
        case .infiniteAmmo: return "无限弹药"
        case .damageEnabled: return "伤害倍率"
        case .autoMiniGames: return "小游戏自动成功"
        case .moneyMultiplierEnabled: return "金币获取倍率"
        case .resourceMultiplierEnabled: return "材料获取倍率"
        case .disableAll: return "全部关闭"
        }
    }
}

struct ElementCount: Identifiable, Equatable {
    let id: String
    let name: String
    let count: Double
    let locked: Bool
}

struct SaveBackup: Identifiable {
    let id: String
    let name: String
    let createdAt: String
    let fileCount: Int
    let runCount: Int?
    let hotBackup: Bool
    let path: String
    let valid: Bool
    let error: String
}

struct TrainerProfile: Identifiable {
    var id: String { name }
    let name: String
    let updatedAt: String
}

struct DiagnosticCheck: Identifiable {
    var id: String { name }
    let name: String
    let ok: Bool
    let detail: String
}
