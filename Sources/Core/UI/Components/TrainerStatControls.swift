import SwiftUI

struct TrainerVitalMetricCard<Field: Hashable>: View {
    @EnvironmentObject private var localization: TrainerLocalizationStore
    let title: String
    let icon: String
    let tint: Color
    @Binding var current: String
    @Binding var maximum: String
    let focus: Binding<Field?>
    let currentField: Field
    var onCurrentCommit: (TrainerTextField.Completion) -> String = { $0.text }
    var onMaximumCommit: (TrainerTextField.Completion) -> String = { $0.text }
    let maximumField: Field
    let locked: Bool
    let editable: Bool
    let onLock: () -> Void

    var body: some View {
        TrainerMetricCard(title: title, icon: icon, tint: tint) {
            TrainerLockButton(locked: locked, enabled: editable, action: onLock)
        } content: {
            HStack(spacing: 2) {
                TrainerTextField(title: "—", text: $current, accessibilityLabel: localization.localized("host.input.currentValue", arguments: [title]), onEditingChanged: TrainerTextField.editingTracker(focus, equals: currentField), onCommit: onCurrentCommit, style: .plain, alignment: .center, font: TrainerTextField.metricFont(size: 19))
                    .frame(width: 54)
                    .disabled(!editable)
                Text("/").foregroundStyle(.secondary)
                TrainerTextField(title: "—", text: $maximum, accessibilityLabel: localization.localized("host.input.maximumValue", arguments: [title]), onEditingChanged: TrainerTextField.editingTracker(focus, equals: maximumField), onCommit: onMaximumCommit, style: .plain, alignment: .center, font: TrainerTextField.metricFont(size: 19))
                    .frame(width: 54)
                    .disabled(!editable)
            }
        }
    }
}

struct TrainerAmountMetricCard<Field: Hashable>: View {
    let title: String
    let icon: String
    let tint: Color
    @Binding var text: String
    let focus: Binding<Field?>
    let focusValue: Field
    let locked: Bool
    let editable: Bool
    let placeholder: String
    let onLock: () -> Void
    var onCommit: (TrainerTextField.Completion) -> String = { $0.text }

    init(
        title: String,
        icon: String,
        tint: Color,
        text: Binding<String>,
        focus: Binding<Field?>,
        focusValue: Field,
        locked: Bool,
        editable: Bool,
        placeholder: String = "—",
        onLock: @escaping () -> Void,
        onCommit: @escaping (TrainerTextField.Completion) -> String = { $0.text }
    ) {
        self.title = title
        self.icon = icon
        self.tint = tint
        self._text = text
        self.focus = focus
        self.focusValue = focusValue
        self.locked = locked
        self.editable = editable
        self.placeholder = placeholder
        self.onLock = onLock
        self.onCommit = onCommit
    }

    var body: some View {
        TrainerMetricCard(title: title, icon: icon, tint: tint) {
            TrainerLockButton(locked: locked, enabled: editable, action: onLock)
        } content: {
            TrainerTextField(title: placeholder, text: $text, accessibilityLabel: title, onEditingChanged: TrainerTextField.editingTracker(focus, equals: focusValue), onCommit: onCommit, style: .plain, alignment: .center, font: TrainerTextField.metricFont(size: 20))
                .frame(maxWidth: .infinity, alignment: .center)
                .disabled(!editable)
        }
    }
}

struct TrainerCounterMetricCard<Field: Hashable>: View {
    let title: String
    let icon: String
    let tint: Color
    @Binding var text: String
    let focus: Binding<Field?>
    let focusValue: Field
    let detail: String?
    var onCommit: (TrainerTextField.Completion) -> String = { $0.text }
    let editable: Bool

    var body: some View {
        TrainerMetricCard(title: title, icon: icon, tint: tint) {
            if let detail {
                Text(detail).font(.caption2).foregroundStyle(.secondary)
            }
        } content: {
            TrainerTextField(title: "—", text: $text, accessibilityLabel: title, onEditingChanged: TrainerTextField.editingTracker(focus, equals: focusValue), onCommit: onCommit, style: .plain, alignment: .center, font: TrainerTextField.metricFont(size: 20))
                .frame(maxWidth: .infinity, alignment: .center)
                .disabled(!editable)
        }
    }
}

struct TrainerStatMetricCard<Field: Hashable>: View {
    @Environment(\.trainerTheme) private var theme
    let title: String
    let icon: String
    @Binding var text: String
    let focus: Binding<Field?>
    let focusValue: Field
    let suffix: String
    let locked: Bool
    let supported: Bool
    let available: Bool
    let editable: Bool
    let onLock: () -> Void
    var onCommit: (TrainerTextField.Completion) -> String = { $0.text }

    private var isEditable: Bool { editable && supported && available }

    var body: some View {
        TrainerMetricCard(title: title, icon: icon, tint: theme.accent) {
            TrainerLockButton(locked: locked, enabled: isEditable, action: onLock)
        } content: {
            HStack(spacing: 3) {
                TrainerTextField(title: "—", text: $text, accessibilityLabel: title, onEditingChanged: TrainerTextField.editingTracker(focus, equals: focusValue), onCommit: onCommit, style: .plain, alignment: .center, font: TrainerTextField.metricFont(size: 20))
                    .frame(width: 58)
                    .disabled(!isEditable)
                if !suffix.isEmpty {
                    Text(suffix).font(.caption).foregroundStyle(.secondary)
                }
            }
        }
        .opacity(supported ? (available ? 1 : 0.65) : 0.42)
    }
}

struct TrainerInlineStatEditor<Field: Hashable>: View {
    let title: String
    @Binding var text: String
    let focus: Binding<Field?>
    let focusValue: Field
    let suffix: String
    let locked: Bool
    let supported: Bool
    let available: Bool
    let editable: Bool
    let onLockChange: (Bool) -> Void
    var onCommit: (TrainerTextField.Completion) -> String = { $0.text }

    private var isEditable: Bool { editable && supported && available }

    var body: some View {
        TrainerRow(opacity: supported ? (available ? 1 : 0.65) : 0.45) {
            HStack(spacing: 12) {
                Text(title).font(.subheadline.weight(.semibold))
                Spacer()
                TrainerNumberField(text: $text, placeholder: "host.value", accessibilityLabel: title, width: 90, enabled: isEditable, alignment: .leading, onEditingChanged: TrainerTextField.editingTracker(focus, equals: focusValue), onCommit: onCommit)
                if !suffix.isEmpty {
                    Text(suffix).foregroundStyle(.secondary).frame(width: 18)
                }
                TrainerToggleControl(
                    isOn: locked,
                    enabled: isEditable,
                    onChange: onLockChange
                )
            }
        }
    }
}
