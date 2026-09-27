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

    /// Language-neutral help copy. The Host resolves it, so this value stays
    /// comparable (no localized string inside a presentation struct) and a
    /// language switch re-renders without rebuilding the model.
    var helpToken: TrainerTextToken? {
        switch phase {
        case .waiting: return Hades2Presentation.token("hades2.phase.waiting")
        case .detached: return Hades2Presentation.token("hades2.phase.detached")
        case .mismatch: return Hades2Presentation.token("hades2.phase.mismatch")
        default: return nil
        }
    }

    /// Resolved help copy for call sites that already hold the Host store.
    @MainActor
    func helpText(using localization: TrainerLocalizationStore) -> String {
        guard let helpToken else { return "" }
        return localization.string(helpToken)
    }

    @MainActor
    func trainerControlState(using theme: TrainerTheme, localization: TrainerLocalizationStore) -> TrainerFeatureControlState {
        TrainerFeatureControlState(
            isOn: enabled,
            isInteractive: isInteractive,
            canEditValue: canEditDesired,
            opacity: opacity,
            indicatorColor: tint(using: theme),
            helpText: helpText(using: localization),
            isWarning: phase == .waiting || phase == .mismatch
        )
    }

}

extension Hades2TrainerModel {
    func featurePresentation(_ key: Hades2FeatureKey, enabled: Bool) -> Hades2FeaturePresentation {
        Hades2FeaturePresentation(
            enabled: enabled,
            supported: supportsFeature(key),
            connected: connected,
            active: activeFeatures[key.rawValue] ?? false,
            dormant: dormantFeatures[key.rawValue] ?? false,
            activationPending: isFeatureActivationPending(key),
            canActivate: canSetFeature,
            canEditDesired: canEditDesired
        )
    }
}
