import SwiftUI

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
    let shortcutText: String?
    let action: () -> Void

    var body: some View {
        TrainerRow(opacity: state.opacity) {
            HStack(spacing: 16) {
                TrainerIconLabel(title: title, icon: icon, tint: state.indicatorColor, emphasized: state.isOn)
                Spacer()
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
        TrainerRow(opacity: state.opacity) {
            HStack(spacing: 16) {
                TrainerIconLabel(title: title, icon: icon, tint: state.indicatorColor, emphasized: state.isOn)
                Spacer()
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
}

/// Compact multiplier row using the same shared small purple switch as every
/// other trainer switch. Only the row layout differs.
struct TrainerCompactMultiplierRow: View {
    @Environment(\.trainerTheme) private var theme
    let title: String
    let icon: String
    let state: TrainerFeatureControlState
    @Binding var text: String
    var onCommit: (TrainerTextField.Completion) -> String = { $0.text }
    var onEditingChanged: (Bool) -> Void = { _ in }
    let shortcutText: String?
    let action: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            TrainerIconLabel(title: title, icon: icon, tint: state.indicatorColor, emphasized: state.isOn)
                .foregroundStyle(state.isWarning ? theme.warning : .primary)
            Spacer()
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
        .opacity(state.opacity)
    }
}
