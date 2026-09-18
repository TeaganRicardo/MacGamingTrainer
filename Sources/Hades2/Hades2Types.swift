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
    case infiniteAmmo, damageEnabled, autoMiniGames, gardenQoL
    case boonRarityEnabled, forceLegendary, forceDuo
    case moneyMultiplierEnabled, resourceMultiplierEnabled
    case applyNextRoomReward, spawnOlympian, spawnPickup, spawnSpecial
    case disableAll

    var id: String { rawValue }

    static let uiOrder: [ShortcutAction] = [
        .godMode, .infiniteHealth, .infiniteMana, .instantCastCooldown, .hexAlwaysReady,
        .infiniteAmmo, .damageEnabled, .autoMiniGames, .gardenQoL,
        .boonRarityEnabled, .forceLegendary, .forceDuo,
        .moneyMultiplierEnabled, .resourceMultiplierEnabled,
        .spawnOlympian, .spawnPickup, .spawnSpecial, .applyNextRoomReward,
        .disableAll,
    ]

    static let legacyDigitActions: [ShortcutAction] = [
        .godMode, .infiniteHealth, .infiniteMana, .instantCastCooldown, .hexAlwaysReady,
        .infiniteAmmo, .damageEnabled, .autoMiniGames, .moneyMultiplierEnabled, .disableAll,
    ]

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
        case .gardenQoL: return "花园便捷操作"
        case .boonRarityEnabled: return "祝福稀有度控制"
        case .forceLegendary: return "强制传奇"
        case .forceDuo: return "强制双重"
        case .moneyMultiplierEnabled: return "金币获取倍率"
        case .resourceMultiplierEnabled: return "材料获取倍率"
        case .applyNextRoomReward: return "应用下一房奖励"
        case .spawnOlympian: return "生成诸神祝福"
        case .spawnPickup: return "生成资源与常规掉落"
        case .spawnSpecial: return "生成特殊祝福"
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
