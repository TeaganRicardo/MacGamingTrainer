import SwiftUI

/// Single shared switch implementation used by every trainer game surface.
/// It uses the native macOS switch: regular control size, purple accent and
/// system thumb animation. Feature rows may supply
/// their neutral presentation tint so the switch and its corresponding
/// indicator communicate the same phase.
struct TrainerToggleControl: View {
    @Environment(\.trainerTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let title: String
    let isOn: Bool
    let enabled: Bool
    let helpText: String
    let tint: Color?
    private let onChange: (Bool) -> Void

    init(
        title: String,
        isOn: Bool,
        enabled: Bool = true,
        helpText: String = "",
        tint: Color? = nil,
        action: @escaping () -> Void
    ) {
        self.title = title
        self.isOn = isOn
        self.enabled = enabled
        self.helpText = helpText
        self.tint = tint
        self.onChange = { _ in action() }
    }

    init(
        title: String,
        isOn: Bool,
        enabled: Bool = true,
        helpText: String = "",
        tint: Color? = nil,
        onChange: @escaping (Bool) -> Void
    ) {
        self.title = title
        self.isOn = isOn
        self.enabled = enabled
        self.helpText = helpText
        self.tint = tint
        self.onChange = onChange
    }

    var body: some View {
        Toggle(title, isOn: Binding(get: { isOn }, set: onChange))
            .labelsHidden()
            .toggleStyle(.switch)
            .controlSize(.regular)
            .tint(tint ?? theme.accent)
            .disabled(!enabled)
            .help(helpText)
            .fixedSize()
            .transaction { transaction in
                TrainerMotion.nativeControlTransaction(&transaction, reduceMotion: reduceMotion)
            }
    }
}

/// Shared checkbox implementation for game-specific option panels. Keeping the
/// checkbox here prevents game modules from owning another Toggle rendering
/// path while preserving the native checkbox appearance.
struct TrainerCheckboxControl: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
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
            .transaction { transaction in
                TrainerMotion.nativeControlTransaction(&transaction, reduceMotion: reduceMotion)
            }
    }
}

struct TrainerLockButton: View {
    @Environment(\.trainerTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @EnvironmentObject private var localization: TrainerLocalizationStore
    let title: String
    let locked: Bool
    let enabled: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: locked ? "lock.fill" : "lock.open")
                .font(.caption.weight(.semibold))
                .foregroundStyle(locked ? theme.accent : .secondary)
                .frame(width: 14, height: 16)
                .contentTransition(.opacity)
                .animation(TrainerMotion.animation(.selection, reduceMotion: reduceMotion), value: locked)
        }
        .buttonStyle(.bordered)
        .controlSize(.mini)
        .frame(width: 26, height: 24)
        .disabled(!enabled)
        .transaction { transaction in
            TrainerMotion.nativeControlTransaction(&transaction, reduceMotion: reduceMotion)
        }
        .accessibilityLabel(localization.localized(locked ? "host.unlockValue" : "host.lockValue", arguments: [title]))
        .help(localization.localized(locked ? "host.unlockValue" : "host.lockValue", arguments: [title]))
    }
}
