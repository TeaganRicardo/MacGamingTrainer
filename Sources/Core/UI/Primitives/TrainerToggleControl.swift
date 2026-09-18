import SwiftUI

/// Single shared switch implementation used by every trainer game surface.
/// It intentionally mirrors the compact native macOS switch used by the
/// pre-decoupling Hades UI: small control size, purple accent and native thumb
/// animation. Feature rows may supply their neutral presentation tint so the
/// switch and its corresponding indicator communicate the same phase.
struct TrainerToggleControl: View {
    @Environment(\.trainerTheme) private var theme
    let isOn: Bool
    let enabled: Bool
    let helpText: String
    let tint: Color?
    private let onChange: (Bool) -> Void

    init(
        isOn: Bool,
        enabled: Bool = true,
        helpText: String = "",
        tint: Color? = nil,
        action: @escaping () -> Void
    ) {
        self.isOn = isOn
        self.enabled = enabled
        self.helpText = helpText
        self.tint = tint
        self.onChange = { _ in action() }
    }

    init(
        isOn: Bool,
        enabled: Bool = true,
        helpText: String = "",
        tint: Color? = nil,
        onChange: @escaping (Bool) -> Void
    ) {
        self.isOn = isOn
        self.enabled = enabled
        self.helpText = helpText
        self.tint = tint
        self.onChange = onChange
    }

    var body: some View {
        Toggle("", isOn: Binding(get: { isOn }, set: onChange))
            .labelsHidden()
            .toggleStyle(.switch)
            .controlSize(.regular)
            .tint(tint ?? theme.accent)
            .disabled(!enabled)
            .help(helpText)
            .fixedSize()
            .animation(.easeInOut(duration: 0.16), value: isOn)
    }
}

/// Shared checkbox implementation for game-specific option panels. Keeping the
/// checkbox here prevents game modules from owning another Toggle rendering
/// path while preserving the native checkbox appearance.
struct TrainerCheckboxControl: View {
    let title: String
    let isOn: Bool
    let enabled: Bool
    private let onChange: (Bool) -> Void

    init(title: String, isOn: Bool, enabled: Bool = true, onChange: @escaping (Bool) -> Void) {
        self.title = title
        self.isOn = isOn
        self.enabled = enabled
        self.onChange = onChange
    }

    var body: some View {
        Toggle(title, isOn: Binding(get: { isOn }, set: onChange))
            .toggleStyle(.checkbox)
            .disabled(!enabled)
    }
}

struct TrainerLockButton: View {
    @Environment(\.trainerTheme) private var theme
    let locked: Bool
    let enabled: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: locked ? "lock.fill" : "lock.open")
                .font(.caption.weight(.semibold))
                .foregroundStyle(locked ? theme.accent : .secondary)
                .frame(width: 26, height: 24)
                .background((locked ? theme.mutedFill.opacity(0.62) : theme.subtleFill.opacity(0.875)), in: RoundedRectangle(cornerRadius: theme.compactCornerRadius))
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
    }
}
