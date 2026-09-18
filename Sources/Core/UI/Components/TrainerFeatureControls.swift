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
                    isOn: state.isOn,
                    enabled: state.isInteractive,
                    helpText: state.helpText,
                    tint: state.indicatorColor,
                    action: action
                )
                .accessibilityLabel(title)
                .accessibilityValue(state.isOn ? "开启" : "关闭")
            }
        }
    }
}

struct TrainerFeatureMultiplierRow: View {
    let title: String
    let icon: String
    let state: TrainerFeatureControlState
    @Binding var text: String
    let shortcutText: String?
    let action: () -> Void

    var body: some View {
        TrainerRow(opacity: state.opacity) {
            HStack(spacing: 16) {
                TrainerIconLabel(title: title, icon: icon, tint: state.indicatorColor, emphasized: state.isOn)
                Spacer()
                TrainerNumberField(text: $text, placeholder: "2", width: 70, enabled: state.canEditValue, alignment: .leading)
                Text("×").foregroundStyle(.secondary)
                TrainerShortcutBadgeSlot(text: shortcutText)
                TrainerToggleControl(
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
    let shortcutText: String?
    let action: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            HStack(spacing: 6) {
                Image(systemName: icon)
                    .foregroundStyle(state.indicatorColor)
                Text(title)
                    .foregroundStyle(state.isWarning ? theme.warning : .primary)
            }
            .font(.subheadline.weight(.medium))
            Spacer()
            TrainerNumberField(text: $text, placeholder: "2", width: 70, enabled: state.canEditValue, alignment: .leading)
            Text("×").foregroundStyle(.secondary)
            TrainerShortcutBadgeSlot(text: shortcutText)
            TrainerToggleControl(
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
