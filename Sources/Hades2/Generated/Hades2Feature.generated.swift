// Generated from Backend/games/hades2/schema.py. Do not edit.
import Foundation

enum Hades2FeatureKey: String, CaseIterable, Hashable {
    case invincibility
    case infiniteHealth
    case infiniteMana
    case damageEnabled
    case instantCastCooldown
    case hexAlwaysReady
    case infiniteAmmo
    case autoMiniGames
    case gardenQoL
    case boonRarityEnabled
    case forceEnableRerolls
    case moneyMultiplierEnabled
    case resourceMultiplierEnabled
}

enum Hades2MultiplierRuntimeOwner: Equatable {
    case resident
    case core
}

enum Hades2MultiplierKey: String, CaseIterable {
    case damageMultiplier
    case moneyMultiplier
    case resourceMultiplier
    case gameSpeed

    var defaultValue: Double {
        switch self {
        case .damageMultiplier: return 2.0
        case .moneyMultiplier: return 2.0
        case .resourceMultiplier: return 2.0
        case .gameSpeed: return 1.0
        }
    }

    var range: ClosedRange<Double> {
        switch self {
        case .damageMultiplier: return 1.0...100.0
        case .moneyMultiplier: return 1.0...100.0
        case .resourceMultiplier: return 1.0...100.0
        case .gameSpeed: return 0.0...10.0
        }
    }

    var runtimeOwner: Hades2MultiplierRuntimeOwner {
        switch self {
        case .damageMultiplier: return .resident
        case .moneyMultiplier: return .resident
        case .resourceMultiplier: return .resident
        case .gameSpeed: return .core
        }
    }
}
