import SwiftUI

enum Hades2FeaturePhase: Equatable {
    case unsupported
    case off
    case active
    case pending
    case waiting
    case detached
    case mismatch
}

struct Hades2FeaturePresentation: Equatable {
    let enabled: Bool
    let supported: Bool
    let connected: Bool
    let active: Bool
    let dormant: Bool
    let activationPending: Bool
    let canActivate: Bool
    let canEditDesired: Bool

    var phase: Hades2FeaturePhase {
        guard supported else { return .unsupported }
        guard enabled else { return .off }
        guard connected else { return .detached }
        if active { return .active }
        if activationPending { return .pending }
        if dormant || !canActivate { return .waiting }
        return .mismatch
    }

    var isInteractive: Bool { supported && canEditDesired }
    var opacity: Double { supported ? 1 : 0.45 }

    func tint(using theme: TrainerTheme) -> Color {
        switch phase {
        case .waiting, .mismatch: return theme.warning
        case .detached: return theme.warning
        case .active, .pending: return theme.accent
        case .unsupported, .off: return .secondary
        }
    }

    var helpText: String {
        switch phase {
        case .waiting:
            return "当前运行环境尚不可用；保持开启并在条件满足时自动生效。"
        case .detached:
            return "已保留开启状态；重新连接后自动恢复。"
        case .mismatch:
            return "已请求开启，但运行时尚未确认生效。"
        default:
            return ""
        }
    }
    func trainerControlState(using theme: TrainerTheme) -> TrainerFeatureControlState {
        TrainerFeatureControlState(
            isOn: enabled,
            isInteractive: isInteractive,
            canEditValue: canEditDesired,
            opacity: opacity,
            indicatorColor: tint(using: theme),
            helpText: helpText,
            isWarning: phase == .waiting || phase == .mismatch
        )
    }

}

extension Hades2TrainerModel {
    func featurePresentation(_ key: String, enabled: Bool) -> Hades2FeaturePresentation {
        Hades2FeaturePresentation(
            enabled: enabled,
            supported: supportsFeature(key),
            connected: connected,
            active: activeFeatures[key] ?? false,
            dormant: dormantFeatures[key] ?? false,
            activationPending: isFeatureActivationPending(key),
            canActivate: canSetFeature,
            canEditDesired: canEditDesired
        )
    }
}
