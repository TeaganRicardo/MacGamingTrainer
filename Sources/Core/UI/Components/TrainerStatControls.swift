import SwiftUI

struct TrainerVitalMetricCard<Field: Hashable>: View {
    let title: String
    let icon: String
    let tint: Color
    @Binding var current: String
    @Binding var maximum: String
    let focus: FocusState<Field?>.Binding
    let currentField: Field
    let maximumField: Field
    let locked: Bool
    let editable: Bool
    let onLock: () -> Void

    var body: some View {
        TrainerMetricCard(title: title, icon: icon, tint: tint) {
            TrainerLockButton(locked: locked, enabled: editable, action: onLock)
        } content: {
            HStack(spacing: 2) {
                TextField("—", text: $current)
                    .textFieldStyle(.plain)
                    .multilineTextAlignment(.center)
                    .frame(width: 54)
                    .font(.system(size: 19, weight: .semibold, design: .rounded))
                    .monospacedDigit()
                    .focused(focus, equals: currentField)
                    .disabled(!editable)
                Text("/").foregroundStyle(.secondary)
                TextField("—", text: $maximum)
                    .textFieldStyle(.plain)
                    .multilineTextAlignment(.center)
                    .frame(width: 54)
                    .font(.system(size: 19, weight: .semibold, design: .rounded))
                    .monospacedDigit()
                    .focused(focus, equals: maximumField)
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
    let focus: FocusState<Field?>.Binding
    let focusValue: Field
    let locked: Bool
    let editable: Bool
    let placeholder: String
    let onLock: () -> Void

    init(
        title: String,
        icon: String,
        tint: Color,
        text: Binding<String>,
        focus: FocusState<Field?>.Binding,
        focusValue: Field,
        locked: Bool,
        editable: Bool,
        placeholder: String = "—",
        onLock: @escaping () -> Void
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
    }

    var body: some View {
        TrainerMetricCard(title: title, icon: icon, tint: tint) {
            TrainerLockButton(locked: locked, enabled: editable, action: onLock)
        } content: {
            TextField(placeholder, text: $text)
                .textFieldStyle(.plain)
                .multilineTextAlignment(.center)
                .font(.system(size: 20, weight: .semibold, design: .rounded))
                .monospacedDigit()
                .frame(maxWidth: .infinity, alignment: .center)
                .focused(focus, equals: focusValue)
                .disabled(!editable)
        }
    }
}

struct TrainerCounterMetricCard<Field: Hashable>: View {
    let title: String
    let icon: String
    let tint: Color
    @Binding var text: String
    let focus: FocusState<Field?>.Binding
    let focusValue: Field
    let detail: String?
    let editable: Bool

    var body: some View {
        TrainerMetricCard(title: title, icon: icon, tint: tint) {
            if let detail {
                Text(detail).font(.caption2).foregroundStyle(.secondary)
            }
        } content: {
            TextField("—", text: $text)
                .textFieldStyle(.plain)
                .multilineTextAlignment(.center)
                .font(.system(size: 20, weight: .semibold, design: .rounded))
                .monospacedDigit()
                .frame(maxWidth: .infinity, alignment: .center)
                .focused(focus, equals: focusValue)
                .disabled(!editable)
        }
    }
}

struct TrainerStatMetricCard<Field: Hashable>: View {
    @Environment(\.trainerTheme) private var theme
    let title: String
    let icon: String
    @Binding var text: String
    let focus: FocusState<Field?>.Binding
    let focusValue: Field
    let suffix: String
    let locked: Bool
    let supported: Bool
    let available: Bool
    let editable: Bool
    let onLock: () -> Void

    private var isEditable: Bool { editable && supported && available }

    var body: some View {
        TrainerMetricCard(title: title, icon: icon, tint: theme.accent) {
            TrainerLockButton(locked: locked, enabled: isEditable, action: onLock)
        } content: {
            HStack(spacing: 3) {
                TextField("—", text: $text)
                    .textFieldStyle(.plain)
                    .multilineTextAlignment(.center)
                    .frame(width: 58)
                    .font(.system(size: 20, weight: .semibold, design: .rounded))
                    .monospacedDigit()
                    .focused(focus, equals: focusValue)
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
    let focus: FocusState<Field?>.Binding
    let focusValue: Field
    let suffix: String
    let locked: Bool
    let supported: Bool
    let available: Bool
    let editable: Bool
    let onLockChange: (Bool) -> Void

    private var isEditable: Bool { editable && supported && available }

    var body: some View {
        TrainerRow(opacity: supported ? (available ? 1 : 0.65) : 0.45) {
            HStack(spacing: 12) {
                Text(title).font(.subheadline.weight(.semibold))
                Spacer()
                TrainerNumberField(text: $text, placeholder: "数值", width: 90, enabled: isEditable, alignment: .leading)
                    .focused(focus, equals: focusValue)
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
