import SwiftUI

enum TrainerFeaturePhase: Equatable {
    case unsupported
    case off
    case active
    case pending
    case waiting
    case detached
    case mismatch
}

/// Desired-versus-observed state of one durable feature intent. A game module
/// supplies its own observations (support, activity, dormancy, an in-flight
/// intent and whether its runtime can apply one now); Core derives the shared
/// phase, tint and help so the same state reads the same in every game.
struct TrainerFeaturePresentation: Equatable {
    let enabled: Bool
    let supported: Bool
    let connected: Bool
    let active: Bool
    let dormant: Bool
    let activationPending: Bool
    let canActivate: Bool
    let canEditDesired: Bool

    var phase: TrainerFeaturePhase {
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
        case .waiting: return TrainerTextToken(key: "host.feature.phase.waiting")
        case .detached: return TrainerTextToken(key: "host.feature.phase.detached")
        case .mismatch: return TrainerTextToken(key: "host.feature.phase.mismatch")
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

/// Pure presentation state for a feature control. Game modules translate their
/// own runtime/desired-state semantics into this visual state; Core never knows
/// why a feature is waiting, detached, unsupported, etc.
struct TrainerFeatureControlState {
    let isOn: Bool
    let isInteractive: Bool
    let canEditValue: Bool
    let opacity: Double
    let indicatorColor: Color
    let helpText: String
    let isWarning: Bool
}

struct TrainerFeatureToggleRow: View {
    let title: String
    let icon: String
    let state: TrainerFeatureControlState
    /// What the feature does. It belongs to the label: help on the whole row
    /// would replace the switch's own phase help.
    var helpText: String = ""
    let shortcutText: String?
    let action: () -> Void

    var body: some View {
        TrainerLabeledControlRow(title: title, icon: icon, tint: state.indicatorColor,
                                emphasized: state.isOn, opacity: state.opacity, helpText: helpText) {
            TrainerShortcutBadgeSlot(text: shortcutText)
            TrainerToggleControl(
                title: title,
                isOn: state.isOn,
                enabled: state.isInteractive,
                helpText: state.helpText,
                tint: state.indicatorColor,
                action: action
            )
        }
    }
}

struct TrainerFeatureMultiplierRow: View {
    let title: String
    let icon: String
    let state: TrainerFeatureControlState
    @Binding var text: String
    var onCommit: (TrainerTextField.Completion) -> String = { $0.text }
    var onEditingChanged: (Bool) -> Void = { _ in }
    let shortcutText: String?
    let action: () -> Void

    var body: some View {
        TrainerLabeledControlRow(title: title, icon: icon, tint: state.indicatorColor,
                                emphasized: state.isOn, opacity: state.opacity) {
            TrainerNumberField(text: $text, placeholder: "2", accessibilityLabel: title, width: 70, enabled: state.canEditValue, alignment: .leading, onEditingChanged: onEditingChanged, onCommit: onCommit)
            Text("×").foregroundStyle(.secondary)
            TrainerShortcutBadgeSlot(text: shortcutText)
            TrainerToggleControl(
                title: title,
                isOn: state.isOn,
                enabled: state.isInteractive,
                helpText: state.helpText,
                tint: state.indicatorColor,
                action: action
            )
        }
    }
}
